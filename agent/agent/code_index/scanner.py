import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Dict, Optional
from uuid import uuid5

from agent.code_index.cache_manager import CacheManager
from agent.code_index.file_processor import CodeBlock, CodeParser
from agent.code_index.models import (EmbedderResponse, IEmbedder, Payload,
                                     PointStruct)
from agent.code_index.vector_store import VectorStoreClient
from agent.constants import (BATCH_PROCESSING_CONCURRENCY,
                             BATCH_SEGMENT_THRESHOLD, DIRS_TO_IGNORE,
                             EXTENSIONS, INITIAL_RETRY_DELAY_MS,
                             MAX_BATCH_RETRIES, MAX_FILE_SIZE,
                             MAX_LIST_FILES_LIMIT_CODE_INDEX,
                             PARSING_CONCURRENCY, QDRANT_CODE_BLOCK_NAMESPACE)
from agent.list_files import Ignore, list_files
from agent.telemetry_service import TelemetryService


def generate_relative_file_path(file_path: str, workspace: str) -> str:
    """Generate relative file path from workspace."""
    return os.path.relpath(file_path, workspace)


def generate_normalized_absolute_path(file_path: str, workspace: str) -> str:
    """Generate normalized absolute path."""
    if os.path.isabs(file_path):
        return os.path.normpath(file_path)
    return os.path.normpath(os.path.join(workspace, file_path))


@dataclass
class DirectoryScanResult:
    stats: Dict[str, Any]
    total_block_count: int


def is_path_in_ignored_dir(path: str, ignore_config: Ignore) -> bool:
    normalized_path = os.path.normpath(path)
    path_parts = [part for part in normalized_path.split(os.sep) if part]

    # Check for dot-directories if ".*" is in DIRS_TO_IGNORE
    if ".*" in DIRS_TO_IGNORE:
        if any(part.startswith(".") and part != "." for part in path_parts):
            return True

    # Check for any ignored directory in the path parts
    if any(part in DIRS_TO_IGNORE for part in path_parts):
        return True

    return False


@dataclass
class ScanStats:
    """Statistics from directory scanning."""

    processed: int
    skipped: int


@dataclass
class ScanResult:
    """Result of directory scanning."""

    stats: ScanStats
    total_block_count: int


class DirectoryScanner:
    """Main directory scanner class."""

    def __init__(
        self,
        embedder: IEmbedder,
        vector_store_client: VectorStoreClient,
        code_parser: CodeParser,
        cache_manager: CacheManager,
        ignore_config: Ignore,
        batch_segment_threshold: Optional[int] = None,
    ):
        self.embedder = embedder
        self.vector_store_client = vector_store_client
        self.code_parser = code_parser
        self.cache_manager: CacheManager = cache_manager
        self.batch_segment_threshold = batch_segment_threshold or BATCH_SEGMENT_THRESHOLD
        self.telemetry = TelemetryService()
        self.ignore_config = ignore_config

    async def scan_directory(
        self,
        directory: str,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_blocks_indexed: Optional[Callable[[int], None]] = None,
        on_file_parsed: Optional[Callable[[int], None]] = None,
    ) -> Coroutine[Any, Any, ScanResult]:
        """
        Recursively scan a directory for code blocks in supported files.

        Args:
            directory: The directory to scan
            on_error: Optional error handler callback
            on_blocks_indexed: Optional callback for when blocks are indexed
            on_file_parsed: Optional callback for when a file is parsed

        Returns:
            ScanResult with stats and total block count
        """
        directory_path = os.path.abspath(directory)
        scan_workspace = directory_path
        # raise Exception(directory, directory_path)

        # Get all files recursively
        all_paths, _ = await list_files(directory_path, True, MAX_LIST_FILES_LIMIT_CODE_INDEX)
        # raise Exception(all_paths)
        # Filter out directories
        file_paths = [p for p in all_paths if os.path.isfile(os.path.join(directory_path, p))]
        # Initialize ignore controller
        # ignore_controller = RooIgnoreController(directory_path)
        # await ignore_controller.initialize()

        # Filter paths using .rooignore
        #  allowed_paths = ignore_controller.filter_paths(file_paths)
        allowed_paths = file_paths

        # Filter by supported extensions and ignored directories
        supported_paths = []
        for file_path in allowed_paths:
            ext = os.path.splitext(file_path)[1].lower()
            # Check if file is in an ignored directory
            if is_path_in_ignored_dir(file_path, self.ignore_config):
                continue

            if ext in EXTENSIONS:
                supported_paths.append(file_path)
        # Initialize tracking variables
        processed_files: set[str] = set()
        processed_count = 0
        skipped_count = 0
        total_block_count = 0

        # Batch processing variables
        current_batch_blocks: list[CodeBlock] = []
        current_batch_texts: list[str] = []
        current_batch_file_infos: list[dict[str, Any]] = []
        batch_lock = asyncio.Lock()

        # Semaphores for concurrency control
        parse_semaphore = asyncio.Semaphore(PARSING_CONCURRENCY)
        # update
        batch_semaphore = asyncio.Semaphore(BATCH_PROCESSING_CONCURRENCY)

        async def process_file(file_path: str) -> None:
            nonlocal processed_count, skipped_count, total_block_count
            nonlocal current_batch_blocks, current_batch_texts, current_batch_file_infos

            async with parse_semaphore:
                try:
                    # Check file size
                    file_stats = os.stat(os.path.join(directory_path, file_path))
                    if file_stats.st_size > MAX_FILE_SIZE:
                        skipped_count += 1
                        return

                    # Read file content
                    with open(os.path.join(directory_path, file_path), "rb") as f:
                        content = f.read()

                    # Calculate current hash
                    current_file_hash = self.code_parser.create_hash(content)
                    processed_files.add(file_path)

                    # Check against cache
                    cached_file_hash = self.cache_manager.get_file_hash(file_path)
                    is_new_file = not cached_file_hash
                    if cached_file_hash == current_file_hash:
                        # File is unchanged
                        skipped_count += 1
                        return

                    # File is new or changed - parse it
                    if self.code_parser:
                        blocks = await self.code_parser.parse_file(
                            scan_workspace, file_path, {"content": content, "file_hash": current_file_hash}
                        )
                        file_block_count = len(blocks)
                        if on_file_parsed:
                            on_file_parsed(file_block_count)
                        processed_count += 1

                        # Process embeddings if configured
                        if self.embedder and self.vector_store_client and blocks:
                            added_blocks_from_file = False

                            async with batch_lock:
                                block: CodeBlock
                                for block in blocks:
                                    trimmed_content = block.content.strip()
                                    if trimmed_content:
                                        current_batch_blocks.append(block)
                                        current_batch_texts.append(trimmed_content.decode("utf-8"))
                                        added_blocks_from_file = True

                                        # Check if batch threshold is met
                                        if len(current_batch_blocks) >= self.batch_segment_threshold:
                                            # Copy current batch data and clear
                                            batch_blocks = current_batch_blocks.copy()
                                            batch_texts = current_batch_texts.copy()
                                            batch_file_infos = current_batch_file_infos.copy()

                                            current_batch_blocks.clear()
                                            current_batch_texts.clear()
                                            current_batch_file_infos.clear()

                                            # Process batch
                                            asyncio.create_task(
                                                self._process_batch(
                                                    batch_blocks,
                                                    batch_texts,
                                                    batch_file_infos,
                                                    scan_workspace,
                                                    batch_semaphore,
                                                    on_error,
                                                    on_blocks_indexed,
                                                )
                                            )

                                # Add file info once per file
                                if added_blocks_from_file:
                                    total_block_count += file_block_count
                                    current_batch_file_infos.append(
                                        {"file_path": file_path, "file_hash": current_file_hash, "is_new": is_new_file}
                                    )
                        else:
                            # Update hash if not being processed in batch
                            await self.cache_manager.update_file_hash(file_path, current_file_hash)

                except Exception as error:
                    # Log with full stack trace
                    logging.exception(f"Error processing file {file_path}: {error}")
                    self.telemetry.echo(json.dumps({"error": str(error), "location": "scanDirectory:processFile"}))
                    if on_error:
                        on_error(Exception(f"{error} (Workspace: {scan_workspace}, File: {file_path})"))
                    raise error

        # Process all files concurrently
        tasks = [process_file(file_path) for file_path in supported_paths]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Process any remaining items in batch
        async with batch_lock:
            if current_batch_blocks:
                await self._process_batch(
                    current_batch_blocks,
                    current_batch_texts,
                    current_batch_file_infos,
                    scan_workspace,
                    batch_semaphore,
                    on_error,
                    on_blocks_indexed,
                )

        # Handle deleted files
        old_hashes = self.cache_manager.get_all_file_hashes()
        for cached_file_path in old_hashes:
            if cached_file_path not in processed_files:
                # File was deleted or is no longer supported
                if self.vector_store_client:
                    try:
                        await self.vector_store_client.delete_points_by_file_path(cached_file_path)
                        await self.cache_manager.delete_file_hash(cached_file_path)
                    except Exception as error:
                        # Log with full stack trace
                        logging.exception(f"Failed to delete points for {cached_file_path}: {error}")
                        self.telemetry.echo(
                            json.dumps({"error": str(error), "location": "scanDirectory:deleteRemovedFiles"})
                        )
                        if on_error:
                            on_error(
                                Exception(
                                    f"Failed to delete points for {cached_file_path} (Workspace: {scan_workspace})"
                                )
                            )
                        raise error

        return ScanResult(
            stats=ScanStats(processed=processed_count, skipped=skipped_count), total_block_count=total_block_count
        )

    async def _process_batch(
        self,
        batch_blocks: list[CodeBlock],
        batch_texts: list[str],
        batch_file_infos: list[dict[str, Any]],
        scan_workspace: str,
        batch_semaphore: asyncio.Semaphore,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_blocks_indexed: Optional[Callable[[int], None]] = None,
    ) -> None:
        """Process a batch of code blocks."""
        if not batch_blocks:
            return

        async with batch_semaphore:
            attempts = 0
            success = False
            last_error: Optional[Exception] = None

            while attempts < MAX_BATCH_RETRIES and not success:
                attempts += 1
                try:
                    # Delete existing points for modified files
                    unique_file_paths = list(
                        set([info["file_path"] for info in batch_file_infos if not info["is_new"]])
                    )

                    if unique_file_paths and self.vector_store_client:
                        try:
                            await self.vector_store_client.delete_points_by_multiple_file_paths(unique_file_paths)
                        except Exception as delete_error:
                            logging.error(f"Failed to delete points for batch: {delete_error}")
                            raise Exception(
                                f"Failed to delete points for {len(unique_file_paths)} files. "
                                f"Workspace: {scan_workspace}. {delete_error}"
                            ) from delete_error

                    # Create embeddings
                    if self.embedder:
                        embedding_result: EmbedderResponse = await self.embedder.create_embeddings(batch_texts)
                        embeddings = embedding_result.embeddings

                        # Prepare points for vector store
                        points = []
                        for i, block in enumerate(batch_blocks):
                            normalized_path = generate_normalized_absolute_path(block.file_path, scan_workspace)
                            point_id = str(uuid5(QDRANT_CODE_BLOCK_NAMESPACE, block.segment_hash))
                            # print(block.content.decode('utf-8'), block.type)
                            points.append(
                                PointStruct(
                                    id=point_id,
                                    vector=embeddings[i],
                                    payload=Payload(
                                        file_path=generate_relative_file_path(normalized_path, scan_workspace),
                                        code_chunk=block.content.decode("utf-8"),
                                        start_line=block.start_line,
                                        end_line=block.end_line,
                                        segment_hash=block.segment_hash,
                                        type=block.type,
                                    ),
                                )
                            )

                        # Upsert points
                        if self.vector_store_client:
                            await self.vector_store_client.upsert_points(points)

                        if on_blocks_indexed:
                            on_blocks_indexed(len(batch_blocks))

                        # Update hashes for successfully processed files
                        for file_info in batch_file_infos:
                            await self.cache_manager.update_file_hash(file_info["file_path"], file_info["file_hash"])

                        success = True

                except Exception as error:
                    last_error = error
                    # Log with full stack trace
                    logging.exception(f"Error processing batch (attempt {attempts}): {error}")
                    self.telemetry.echo(
                        json.dumps(
                            {
                                "error": str(error),
                                "location": "processBatch:retry",
                                "attemptNumber": attempts,
                                "batchSize": len(batch_blocks),
                            }
                        )
                    )

                    if attempts < MAX_BATCH_RETRIES:
                        delay = INITIAL_RETRY_DELAY_MS * (2 ** (attempts - 1)) / 1000
                        await asyncio.sleep(delay)

            if not success and last_error:
                logging.error(f"Failed to process batch after {MAX_BATCH_RETRIES} attempts")
                if on_error:
                    error_message = str(last_error)
                    on_error(
                        Exception(f"Failed to process batch after {MAX_BATCH_RETRIES} retries. Error: {error_message}")
                    )
