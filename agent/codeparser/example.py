import os
import hashlib
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Set, Optional, Callable, Tuple, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod
import uuid
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Constants
BATCH_SEGMENT_THRESHOLD = 100
MAX_LIST_FILES_LIMIT_CODE_INDEX = 10000
PARSING_CONCURRENCY = 5
BATCH_PROCESSING_CONCURRENCY = 3
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
MAX_PENDING_BATCHES = 10
MAX_BATCH_RETRIES = 3
INITIAL_RETRY_DELAY_MS = 1000
QDRANT_CODE_BLOCK_NAMESPACE = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')

# Supported file extensions for scanning
SCANNER_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', 
    '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala', 
    '.dart', '.lua', '.r', '.m', '.mm', '.sh', '.bash', '.zsh'
}

# Directories to ignore
IGNORED_DIRECTORIES = {
    'node_modules', '.git', '__pycache__', '.pytest_cache', 'venv', 
    'env', '.venv', '.env', 'dist', 'build', '.next', '.nuxt'
}


@dataclass
class CodeBlock:
    """Represents a code block with its metadata."""
    content: str
    file_path: str
    start_line: int
    end_line: int
    segment_hash: str


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


class IEmbedder(ABC):
    """Interface for embedding generation."""
    
    @abstractmethod
    async def create_embeddings(self, texts: List[str]) -> Dict[str, List[List[float]]]:
        """Create embeddings for a list of texts."""
        pass


class IVectorStore(ABC):
    """Interface for vector storage operations."""
    
    @abstractmethod
    async def upsert_points(self, points: List[Dict[str, Any]]) -> None:
        """Upsert points to the vector store."""
        pass
    
    @abstractmethod
    async def delete_points_by_file_path(self, file_path: str) -> None:
        """Delete points by file path."""
        pass
    
    @abstractmethod
    async def delete_points_by_multiple_file_paths(self, file_paths: List[str]) -> None:
        """Delete points by multiple file paths."""
        pass


class ICodeParser(ABC):
    """Interface for code parsing."""
    
    @abstractmethod
    async def parse_file(self, file_path: str, file_info: Dict[str, Any]) -> List[CodeBlock]:
        """Parse a file and return code blocks."""
        pass


class CacheManager:
    """Manages file hash caching."""
    
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self._cache: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._load_cache()
    
    def _load_cache(self) -> None:
        """Load cache from disk."""
        cache_file = self.cache_dir / "file_hashes.txt"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '|' in line:
                            file_path, file_hash = line.strip().split('|', 1)
                            self._cache[file_path] = file_hash
            except Exception as e:
                logging.warning(f"Failed to load cache: {e}")
    
    def _save_cache(self) -> None:
        """Save cache to disk."""
        cache_file = self.cache_dir / "file_hashes.txt"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                for file_path, file_hash in self._cache.items():
                    f.write(f"{file_path}|{file_hash}\n")
        except Exception as e:
            logging.warning(f"Failed to save cache: {e}")
    
    def get_hash(self, file_path: str) -> Optional[str]:
        """Get cached hash for a file."""
        with self._lock:
            return self._cache.get(file_path)
    
    async def update_hash(self, file_path: str, file_hash: str) -> None:
        """Update hash for a file."""
        with self._lock:
            self._cache[file_path] = file_hash
            self._save_cache()
    
    async def delete_hash(self, file_path: str) -> None:
        """Delete hash for a file."""
        with self._lock:
            self._cache.pop(file_path, None)
            self._save_cache()
    
    def get_all_hashes(self) -> Dict[str, str]:
        """Get all cached hashes."""
        with self._lock:
            return self._cache.copy()


class RooIgnoreController:
    """Handles .rooignore file patterns."""
    
    def __init__(self, directory_path: str):
        self.directory_path = Path(directory_path)
        self.patterns: List[str] = []
    
    async def initialize(self) -> None:
        """Initialize by reading .rooignore file."""
        rooignore_file = self.directory_path / ".rooignore"
        if rooignore_file.exists():
            try:
                with open(rooignore_file, 'r', encoding='utf-8') as f:
                    self.patterns = [
                        line.strip() for line in f 
                        if line.strip() and not line.startswith('#')
                    ]
            except Exception as e:
                logging.warning(f"Failed to read .rooignore: {e}")
    
    def filter_paths(self, file_paths: List[str]) -> List[str]:
        """Filter file paths based on .rooignore patterns."""
        if not self.patterns:
            return file_paths
        
        filtered_paths = []
        for file_path in file_paths:
            should_include = True
            rel_path = os.path.relpath(file_path, self.directory_path)
            
            for pattern in self.patterns:
                # Simple pattern matching (can be enhanced with fnmatch/glob)
                if pattern in rel_path or rel_path.startswith(pattern):
                    should_include = False
                    break
            
            if should_include:
                filtered_paths.append(file_path)
        
        return filtered_paths


class TelemetryService:
    """Simple telemetry service for error tracking."""
    
    instance = None
    
    def __init__(self):
        if TelemetryService.instance is None:
            TelemetryService.instance = self
    
    def capture_event(self, event_name: str, properties: Dict[str, Any]) -> None:
        """Capture telemetry event."""
        logging.info(f"Telemetry: {event_name} - {properties}")


def sanitize_error_message(message: str) -> str:
    """Sanitize error message for telemetry."""
    return message[:500] if message else ""


def generate_relative_file_path(file_path: str, workspace: str) -> str:
    """Generate relative file path from workspace."""
    return os.path.relpath(file_path, workspace)


def generate_normalized_absolute_path(file_path: str, workspace: str) -> str:
    """Generate normalized absolute path."""
    if os.path.isabs(file_path):
        return os.path.normpath(file_path)
    return os.path.normpath(os.path.join(workspace, file_path))


def get_workspace_path_for_context(directory_path: str) -> str:
    """Get workspace path for context."""
    return os.path.abspath(directory_path)


def is_path_in_ignored_directory(file_path: str) -> bool:
    """Check if path is in an ignored directory."""
    path_parts = Path(file_path).parts
    return any(part in IGNORED_DIRECTORIES for part in path_parts)


async def list_files(directory: str, recursive: bool = True, limit: int = None) -> Tuple[List[str], int]:
    """List files in directory."""
    files = []
    count = 0
    
    if recursive:
        for root, dirs, filenames in os.walk(directory):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]
            
            for filename in filenames:
                if limit and count >= limit:
                    break
                file_path = os.path.join(root, filename)
                files.append(file_path)
                count += 1
    else:
        try:
            for item in os.listdir(directory):
                if limit and count >= limit:
                    break
                item_path = os.path.join(directory, item)
                if os.path.isfile(item_path):
                    files.append(item_path)
                    count += 1
        except OSError as e:
            logging.error(f"Failed to list directory {directory}: {e}")
    
    return files, count


class DirectoryScanner:
    """Main directory scanner class."""
    
    def __init__(
        self,
        embedder: Optional[IEmbedder] = None,
        qdrant_client: Optional[IVectorStore] = None,
        code_parser: Optional[ICodeParser] = None,
        cache_manager: Optional[CacheManager] = None,
        batch_segment_threshold: Optional[int] = None
    ):
        self.embedder = embedder
        self.qdrant_client = qdrant_client
        self.code_parser = code_parser
        self.cache_manager = cache_manager or CacheManager()
        self.batch_segment_threshold = batch_segment_threshold or BATCH_SEGMENT_THRESHOLD
        self.telemetry = TelemetryService()
    
    async def scan_directory(
        self,
        directory: str,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_blocks_indexed: Optional[Callable[[int], None]] = None,
        on_file_parsed: Optional[Callable[[int], None]] = None
    ) -> ScanResult:
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
        scan_workspace = get_workspace_path_for_context(directory_path)
        
        # Get all files recursively
        all_paths, _ = await list_files(directory_path, True, MAX_LIST_FILES_LIMIT_CODE_INDEX)
        
        # Filter out directories
        file_paths = [p for p in all_paths if os.path.isfile(p)]
        
        # Initialize ignore controller
        ignore_controller = RooIgnoreController(directory_path)
        await ignore_controller.initialize()
        
        # Filter paths using .rooignore
        allowed_paths = ignore_controller.filter_paths(file_paths)
        
        # Filter by supported extensions and ignored directories
        supported_paths = []
        for file_path in allowed_paths:
            ext = os.path.splitext(file_path)[1].lower()
            
            # Check if file is in an ignored directory
            if is_path_in_ignored_directory(file_path):
                continue
                
            if ext in SCANNER_EXTENSIONS:
                supported_paths.append(file_path)
        
        # Initialize tracking variables
        processed_files: Set[str] = set()
        processed_count = 0
        skipped_count = 0
        total_block_count = 0
        
        # Batch processing variables
        current_batch_blocks: List[CodeBlock] = []
        current_batch_texts: List[str] = []
        current_batch_file_infos: List[Dict[str, Any]] = []
        batch_lock = asyncio.Lock()
        
        # Semaphores for concurrency control
        parse_semaphore = asyncio.Semaphore(PARSING_CONCURRENCY)
        batch_semaphore = asyncio.Semaphore(BATCH_PROCESSING_CONCURRENCY)
        
        async def process_file(file_path: str) -> None:
            nonlocal processed_count, skipped_count, total_block_count
            nonlocal current_batch_blocks, current_batch_texts, current_batch_file_infos
            
            async with parse_semaphore:
                try:
                    # Check file size
                    file_stats = os.stat(file_path)
                    if file_stats.st_size > MAX_FILE_SIZE_BYTES:
                        skipped_count += 1
                        return
                    
                    # Read file content
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    # Calculate current hash
                    current_file_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
                    processed_files.add(file_path)
                    
                    # Check against cache
                    cached_file_hash = self.cache_manager.get_hash(file_path)
                    is_new_file = not cached_file_hash
                    
                    if cached_file_hash == current_file_hash:
                        # File is unchanged
                        skipped_count += 1
                        return
                    
                    # File is new or changed - parse it
                    if self.code_parser:
                        blocks = await self.code_parser.parse_file(
                            file_path, 
                            {'content': content, 'fileHash': current_file_hash}
                        )
                        file_block_count = len(blocks)
                        if on_file_parsed:
                            on_file_parsed(file_block_count)
                        processed_count += 1
                        
                        # Process embeddings if configured
                        if self.embedder and self.qdrant_client and blocks:
                            added_blocks_from_file = False
                            
                            async with batch_lock:
                                for block in blocks:
                                    trimmed_content = block.content.strip()
                                    if trimmed_content:
                                        current_batch_blocks.append(block)
                                        current_batch_texts.append(trimmed_content)
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
                                                    on_blocks_indexed
                                                )
                                            )
                                
                                # Add file info once per file
                                if added_blocks_from_file:
                                    total_block_count += file_block_count
                                    current_batch_file_infos.append({
                                        'filePath': file_path,
                                        'fileHash': current_file_hash,
                                        'isNew': is_new_file
                                    })
                        else:
                            # Update hash if not being processed in batch
                            await self.cache_manager.update_hash(file_path, current_file_hash)
                    
                except Exception as error:
                    logging.error(f"Error processing file {file_path}: {error}")
                    self.telemetry.capture_event("CODE_INDEX_ERROR", {
                        'error': sanitize_error_message(str(error)),
                        'location': 'scanDirectory:processFile'
                    })
                    if on_error:
                        on_error(Exception(f"{error} (Workspace: {scan_workspace}, File: {file_path})"))
        
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
                    on_blocks_indexed
                )
        
        # Handle deleted files
        old_hashes = self.cache_manager.get_all_hashes()
        for cached_file_path in old_hashes:
            if cached_file_path not in processed_files:
                # File was deleted or is no longer supported
                if self.qdrant_client:
                    try:
                        await self.qdrant_client.delete_points_by_file_path(cached_file_path)
                        await self.cache_manager.delete_hash(cached_file_path)
                    except Exception as error:
                        logging.error(f"Failed to delete points for {cached_file_path}: {error}")
                        self.telemetry.capture_event("CODE_INDEX_ERROR", {
                            'error': sanitize_error_message(str(error)),
                            'location': 'scanDirectory:deleteRemovedFiles'
                        })
                        if on_error:
                            on_error(Exception(
                                f"Failed to delete points for {cached_file_path} "
                                f"(Workspace: {scan_workspace})"
                            ))
        
        return ScanResult(
            stats=ScanStats(processed=processed_count, skipped=skipped_count),
            total_block_count=total_block_count
        )
    
    async def _process_batch(
        self,
        batch_blocks: List[CodeBlock],
        batch_texts: List[str],
        batch_file_infos: List[Dict[str, Any]],
        scan_workspace: str,
        batch_semaphore: asyncio.Semaphore,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_blocks_indexed: Optional[Callable[[int], None]] = None
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
                    unique_file_paths = list(set([
                        info['filePath'] for info in batch_file_infos 
                        if not info['isNew']
                    ]))
                    
                    if unique_file_paths and self.qdrant_client:
                        try:
                            await self.qdrant_client.delete_points_by_multiple_file_paths(unique_file_paths)
                        except Exception as delete_error:
                            logging.error(f"Failed to delete points for batch: {delete_error}")
                            raise Exception(
                                f"Failed to delete points for {len(unique_file_paths)} files. "
                                f"Workspace: {scan_workspace}. {delete_error}"
                            ) from delete_error
                    
                    # Create embeddings
                    if self.embedder:
                        embedding_result = await self.embedder.create_embeddings(batch_texts)
                        embeddings = embedding_result['embeddings']
                        
                        # Prepare points for vector store
                        points = []
                        for i, block in enumerate(batch_blocks):
                            normalized_path = generate_normalized_absolute_path(block.file_path, scan_workspace)
                            point_id = str(uuid.uuid5(QDRANT_CODE_BLOCK_NAMESPACE, block.segment_hash))
                            
                            points.append({
                                'id': point_id,
                                'vector': embeddings[i],
                                'payload': {
                                    'filePath': generate_relative_file_path(normalized_path, scan_workspace),
                                    'codeChunk': block.content,
                                    'startLine': block.start_line,
                                    'endLine': block.end_line,
                                    'segmentHash': block.segment_hash
                                }
                            })
                        
                        # Upsert points
                        if self.qdrant_client:
                            await self.qdrant_client.upsert_points(points)
                        
                        if on_blocks_indexed:
                            on_blocks_indexed(len(batch_blocks))
                        
                        # Update hashes for successfully processed files
                        for file_info in batch_file_infos:
                            await self.cache_manager.update_hash(
                                file_info['filePath'], 
                                file_info['fileHash']
                            )
                        
                        success = True
                
                except Exception as error:
                    last_error = error
                    logging.error(f"Error processing batch (attempt {attempts}): {error}")
                    self.telemetry.capture_event("CODE_INDEX_ERROR", {
                        'error': sanitize_error_message(str(error)),
                        'location': 'processBatch:retry',
                        'attemptNumber': attempts,
                        'batchSize': len(batch_blocks)
                    })
                    
                    if attempts < MAX_BATCH_RETRIES:
                        delay = INITIAL_RETRY_DELAY_MS * (2 ** (attempts - 1)) / 1000
                        await asyncio.sleep(delay)
            
            if not success and last_error:
                logging.error(f"Failed to process batch after {MAX_BATCH_RETRIES} attempts")
                if on_error:
                    error_message = str(last_error)
                    on_error(Exception(
                        f"Failed to process batch after {MAX_BATCH_RETRIES} retries. "
                        f"Error: {error_message}"
                    ))


# Example usage
async def main():
    """Example usage of DirectoryScanner."""
    
    # You would need to implement these interfaces based on your specific needs
    class ExampleEmbedder(IEmbedder):
        async def create_embeddings(self, texts: List[str]) -> Dict[str, List[List[float]]]:
            # Mock implementation - replace with actual embedding generation
            import random
            embeddings = [[random.random() for _ in range(384)] for _ in texts]
            return {'embeddings': embeddings}
    
    class ExampleVectorStore(IVectorStore):
        async def upsert_points(self, points: List[Dict[str, Any]]) -> None:
            print(f"Upserting {len(points)} points")
        
        async def delete_points_by_file_path(self, file_path: str) -> None:
            print(f"Deleting points for {file_path}")
        
        async def delete_points_by_multiple_file_paths(self, file_paths: List[str]) -> None:
            print(f"Deleting points for {len(file_paths)} files")
    
    class ExampleCodeParser(ICodeParser):
        async def parse_file(self, file_path: str, file_info: Dict[str, Any]) -> List[CodeBlock]:
            # Mock implementation - replace with actual code parsing
            content = file_info['content']
            lines = content.split('\n')
            
            # Create a simple block for the entire file
            segment_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            
            return [CodeBlock(
                content=content,
                file_path=file_path,
                start_line=1,
                end_line=len(lines),
                segment_hash=segment_hash
            )]
    
    # Initialize components
    embedder = ExampleEmbedder()
    vector_store = ExampleVectorStore()
    code_parser = ExampleCodeParser()
    cache_manager = CacheManager()
    
    # Create scanner
    scanner = DirectoryScanner(
        embedder=embedder,
        qdrant_client=vector_store,
        code_parser=code_parser,
        cache_manager=cache_manager
    )
    
    # Scan directory
    def on_error(error: Exception):
        print(f"Error: {error}")
    
    def on_blocks_indexed(count: int):
        print(f"Indexed {count} blocks")
    
    def on_file_parsed(count: int):
        print(f"Parsed file with {count} blocks")
    
    result = await scanner.scan_directory(
        directory="./src",  # Replace with your target directory
        on_error=on_error,
        on_blocks_indexed=on_blocks_indexed,
        on_file_parsed=on_file_parsed
    )
    
    print(f"Scan completed: {result.stats.processed} processed, "
          f"{result.stats.skipped} skipped, "
          f"{result.total_block_count} total blocks")


if __name__ == "__main__":
    asyncio.run(main())