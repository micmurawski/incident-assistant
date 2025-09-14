from constants import BATCH_SEGMENT_THRESHOLD, MAX_LIST_FILES_LIMIT_CODE_INDEX, EXTENSIONS, DIRS_TO_IGNORE, PARSING_CONCURRENCY, BATCH_PROCESSING_CONCURRENCY, MAX_FILE_SIZE, MAX_PENDING_BATCHES, MAX_BATCH_RETRIES, QDRANT_CODE_BLOCK_NAMESPACE, INITIAL_RETRY_DELAY_MS
from dataclasses import dataclass
from typing import Dict, Any, Coroutine, Callable
from telemetry_service import TelemetryService
import os
from list_files import list_files, Ignore
from pathlib import Path
from file_processor import CodeBlock
from cache_manager import CacheManager
from file_processor import CodeParser
import asyncio
import logging
from uuid import uuid5
import json


class Embedder:
    pass


class VectorStoreClient:
    pass


@dataclass
class DirectoryScanResult:
    stats: Dict[str, Any]
    total_block_count: int


@dataclass
class PointStruct:
    id: str
    vector: list[float]
    payload: dict[str, Any]


def is_path_in_ignored_dir(path: str, ignore_config: Ignore) -> bool:
    normalized_path = os.path.normpath(path)
    path_parts = normalized_path.split(os.sep)
    for part in path_parts:
        if not part:
            continue
        if ".*" in DIRS_TO_IGNORE and part.startswith(".") and part != ".":
            return True

        if part in DIRS_TO_IGNORE:
            return True

    for dir in DIRS_TO_IGNORE:
        if dir == ".*":
            continue
        if f"{os.sep}{dir}{os.sep}" in normalized_path:
            return True
    return False


def generate_normalized_abs_path(path: str, root_path: str) -> str:
    resolved_path = os.path.resolve(root_path, path)
    return os.path.normpath(resolved_path)


class DirectoryScanner:
    batch_segment_threshold: int

    def __init__(self, embedder, vector_store_client, code_parser: CodeParser, cache_manager: CacheManager, ignore_config: Ignore, batch_segment_threshold: int = BATCH_SEGMENT_THRESHOLD):
        self.embedder = embedder
        self.vector_store_client = vector_store_client
        self.code_parser = code_parser
        self.cache_manager = cache_manager
        self.ignore_config = ignore_config
        self.batch_segment_threshold = batch_segment_threshold
        self.telemetry = TelemetryService()

    async def scan_directory(self, directory_path: str, on_error: Callable[[Exception], None] | None = None, on_blocks_indexed: Callable[[int], None] | None = None, on_files_parsed: Callable[[int], None] | None = None) -> Coroutine[Any, Any, list[DirectoryScanResult]]:
        all_paths, _ = await list_files(directory_path, True, MAX_LIST_FILES_LIMIT_CODE_INDEX)
        file_paths = filter(lambda path: not path.endswith(os.sep), all_paths)
        # TODO: consider additional filters

        # Filter by supported extensions, ignore patterns, and excluded directories
        def supported_paths_filter(path: str) -> bool:
            ext = Path(path).suffix.lower()
            full_path = os.path.join(directory_path, path)
            # Check if file is in an ignored directory using the shared helper
            if is_path_in_ignored_dir(full_path, self.ignore_config):
                return False

            return ext in EXTENSIONS and not self.ignore_config.ignores(full_path)

        supported_paths = list(filter(supported_paths_filter, file_paths))
    

        processed_files: set[str] = set()
        processed_count = 0
        skipped_count = 0
        total_block_count = 0

        # consider to remove these
        current_batch_blocks: list[CodeBlock] = []
        current_batch_texts: list[bytes] = []
        current_batch_file_infos: list[dict[str, Any]] = []

        parse_semaphore = asyncio.Semaphore(PARSING_CONCURRENCY)
        batch_semaphore = asyncio.Semaphore(BATCH_PROCESSING_CONCURRENCY)
        # to delete?
        lock = asyncio.Lock()
        current_batch_blocks = []
        current_batch_texts = []
        current_batch_file_infos = []
        active_batch_tasks = set()
        pending_batch_count = 0
        # execute process_file on all supported paths
        tasks = map(
            lambda path:
                self.process_file(
                    directory_path=directory_path,
                    file_path=path,
                    on_error=on_error,
                    processed_files=processed_files,
                    current_batch_blocks=current_batch_blocks,
                    current_batch_texts=current_batch_texts,
                    current_batch_file_infos=current_batch_file_infos,
                    active_batch_tasks=active_batch_tasks,
                    parse_semaphore=parse_semaphore,
                    batch_semaphore=batch_semaphore,
                    pending_batch_count=pending_batch_count,
                    skipped_count=skipped_count,
                    processed_count=processed_count,
                    lock=lock,
                    total_block_count=total_block_count,
                ),
                supported_paths
        )
        await asyncio.gather(*tasks)
        raise Exception(current_batch_blocks)
        if len(current_batch_blocks) > 0:
            with lock:
                batch_blocks = [*current_batch_blocks]
                batch_texts = [*current_batch_texts]
                batch_file_infos = [*current_batch_file_infos]
                current_batch_blocks.clear()
                current_batch_texts.clear()
                current_batch_file_infos.clear()
                pending_batch_count += 1

                batch_task = asyncio.create_task(self.process_batch(
                    directory_path, batch_blocks, batch_texts, batch_file_infos, batch_semaphore))
                active_batch_tasks.put(batch_task)

                def on_done_batch(task: asyncio.Task):
                    nonlocal pending_batch_count, active_batch_tasks
                    active_batch_tasks.discard(task)
                    pending_batch_count -= 1

                batch_task.add_done_callback(on_done_batch)

        old_hashes = self.cache_manager.get_all_file_hashes()
        for cached_file_path in old_hashes:
            if self.vector_store_client:
                await self.vector_store_client.delete_point_by_file(cached_file_path)
                await self.cache_manager.delete_file_hash(cached_file_path)

    async def process_batch(self, directory_path: str, batch_blocks: list[CodeBlock], batch_texts: list[bytes], batch_file_infos: list[dict[str, Any]], batch_semaphore: asyncio.Semaphore):
        if len(batch_blocks) == 0:
            return

        def map_block_to_point(block: CodeBlock, index: int, embeddings: list[list[float]], directory_path: str) -> PointStruct:
            normalized_abs_path = generate_normalized_abs_path(
                block.file_path, directory_path)
            point_id = uuid5(block.segment_hash, QDRANT_CODE_BLOCK_NAMESPACE)
            return PointStruct(
                id=point_id,
                vector=embeddings[index],
                payload={
                    "file_path": normalized_abs_path,
                    "file_hash": block.file_hash,
                    "is_new": block.is_new,
                }
            )
        async with batch_semaphore:
            attempts = 0
            success = False
            last_error = None
            while attempts < MAX_BATCH_RETRIES and not success:
                attempts += 1
                try:
                    unique_file_paths = set(
                        map(lambda info: info["file_path"], filter(lambda info: not info["is_new"])))
                    if unique_file_paths:
                        await self.vector_store_client.delete_points_by_file(unique_file_paths)

                    embeddings = await self.embedder.create_embeddings(batch_texts)
                    points = list(map(lambda block, index: map_block_to_point(
                        block, index, embeddings, directory_path), batch_blocks, range(len(batch_blocks))))
                    await self.vector_store_client.upsert_points(points)

                    if self.on_blocks_indexed:
                        self.on_blocks_indexed(len(batch_blocks))

                    for file_info in batch_file_infos:
                        await self.cache_manager.update_file_hash(file_info["file_path"], file_info["file_hash"])
                    success = True
                except Exception as e:
                    last_error = e
                    if attempts < MAX_BATCH_RETRIES:
                        delay = INITIAL_RETRY_DELAY_MS * 2**(attempts - 1)
                        await asyncio.sleep(delay)

            if not success and last_error:
                logging.error(
                    "[DirectoryScanner] Failed to process batch after ${MAX_BATCH_RETRIES} attempts")
                if self.on_error:
                    self.on_error(
                        Exception(f"Failed to process batch: {last_error}"))

    async def process_file(
        self,
        directory_path: str,
        file_path: str,
        processed_files: set[str],
        current_batch_blocks: list[CodeBlock],
        current_batch_texts: list[bytes],
        current_batch_file_infos: list[dict[str, Any]],
        active_batch_tasks: list[asyncio.Task],
        parse_semaphore: asyncio.Semaphore,
        batch_semaphore: asyncio.Semaphore,
        pending_batch_count: int,
        skipped_count: int,
        processed_count: int,
        total_block_count: int,
        lock: asyncio.Lock,
        on_error: Callable[[Exception], None] | None = None,
        on_files_parsed: Callable[[int], None] | None = None,
    ):
        file_path = os.path.join(directory_path, file_path)
        async with parse_semaphore:
            try:
                file_stats = os.stat(file_path)
                if file_stats.st_size > MAX_FILE_SIZE:
                    skipped_count += 1
                    return
                content = open(file_path, "rb").read()
                current_file_hash = self.code_parser.create_hash(content)
                processed_files.add(file_path)
                cached_file_cache = self.cache_manager.get_file_hash(
                    file_path)
                if cached_file_cache == current_file_hash:
                    skipped_count += 1
                    return

                blocks = await self.code_parser.parse_file(file_path, {"content": content, "file_hash": current_file_hash})
                file_blocks_count = len(blocks)
                if on_files_parsed:
                    on_files_parsed(file_blocks_count)
                processed_count += 1

                if (self.embedder and self.vector_store_client and len(blocks) > 0):
                    async with lock:
                        for block in blocks:
                            trimmed_content = block.content.strip()
                            if trimmed_content:
                                current_batch_blocks.append(block)
                                current_batch_texts.append(trimmed_content)
                                added_blocks_from_file = True

                                if len(current_batch_blocks) >= self.batch_segment_threshold:
                                    while pending_batch_count >= MAX_PENDING_BATCHES:
                                        done, _ = await asyncio.wait(active_batch_tasks, return_when=asyncio.FIRST_COMPLETED)
                                        for task in done:
                                            active_batch_tasks.discard(task)
                                            pending_batch_count -= 1

                                    batch_blocks = [*current_batch_blocks]
                                    batch_texts = [*current_batch_texts]
                                    batch_file_infos = [*current_batch_file_infos]

                                    current_batch_blocks = []
                                    current_batch_texts = []
                                    current_batch_file_infos = []

                                    task = asyncio.create_task(
                                        self.process_batch(
                                            directory_path,
                                            batch_blocks,
                                            batch_texts,
                                            batch_file_infos,
                                            batch_semaphore,
                                        )
                                    )
                                    
                                    active_batch_tasks.add(task)
                                    pending_batch_count += 1

                                    def on_done_batch(task: asyncio.Task):
                                        nonlocal pending_batch_count, active_batch_tasks
                                        active_batch_tasks.discard(task)
                                        pending_batch_count -= 1

                                    task.add_done_callback(on_done_batch)

                    if added_blocks_from_file:
                        async with lock:
                            total_block_count += file_blocks_count
                            current_batch_file_infos.append(
                                {"file_path": file_path, "file_hash": current_file_hash, "is_new": True})
                    else:
                        await self.cache_manager.update_file_hash(file_path, current_file_hash)

            except Exception as e:
                logging.error(
                    f"Failed to delete points for {file_path}: {e}")
                self.telemetry.error(
                    json.dumps({
                        # sanitize_error_message(str(error)),
                        'error': str(e),
                        'type': type(e).__name__,
                        'location': 'scanDirectory:deleteRemovedFiles'
                    })
                )
                if on_error:
                    on_error(Exception(
                        f"Failed to delete points for {file_path} "
                        # f"(Workspace: {scan_workspace})"
                    ))
                raise e


async def main():
    embedder = Embedder()
    vector_store_client = VectorStoreClient()
    code_parser = CodeParser()
    cache_manager = CacheManager()
    ignore_config = Ignore()
    scanner = DirectoryScanner(
        embedder,
        vector_store_client,
        code_parser,
        cache_manager,
        ignore_config,
    )
    await scanner.scan_directory("/Users/micmur/GITHUB/o8s/agent/codeparser")

if __name__ == "__main__":
    asyncio.run(main())
