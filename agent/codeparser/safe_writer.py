import asyncio
import aiofiles
import aiofiles.os
import json
import os
import time
import random
import string
from pathlib import Path
from typing import Any, Optional
import fcntl
import errno


class LockError(Exception):
    """Exception raised when file locking operations fail."""
    pass


class FileLock:
    """
    Async context manager for file locking using fcntl (Unix-like systems).
    For Windows compatibility, you'd need to use msvcrt or a cross-platform library.
    """
    
    def __init__(self, file_path: str, stale_timeout: float = 31.0, 
                 update_interval: float = 10.0, retries: int = 5,
                 retry_factor: float = 2.0, min_timeout: float = 0.1,
                 max_timeout: float = 1.0):
        self.file_path = file_path
        self.lock_file_path = f"{file_path}.lock"
        self.stale_timeout = stale_timeout
        self.update_interval = update_interval
        self.retries = retries
        self.retry_factor = retry_factor
        self.min_timeout = min_timeout
        self.max_timeout = max_timeout
        self.lock_file = None
        self._update_task = None
        
    async def __aenter__(self):
        await self._acquire_lock()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._release_lock()
        
    async def _acquire_lock(self):
        """Acquire the file lock with retries and exponential backoff."""
        timeout = self.min_timeout
        
        for attempt in range(self.retries + 1):
            try:
                # Check if existing lock is stale
                if os.path.exists(self.lock_file_path):
                    try:
                        stat = os.stat(self.lock_file_path)
                        if time.time() - stat.st_mtime > self.stale_timeout:
                            # Remove stale lock
                            os.unlink(self.lock_file_path)
                    except (OSError, FileNotFoundError):
                        pass
                
                # Try to acquire lock
                self.lock_file = open(self.lock_file_path, 'w')
                try:
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    # Write PID to lock file
                    self.lock_file.write(str(os.getpid()))
                    self.lock_file.flush()
                    
                    # Start update task to prevent staleness
                    self._update_task = asyncio.create_task(self._update_lock_mtime())
                    return
                    
                except (OSError, IOError) as e:
                    if e.errno == errno.EAGAIN or e.errno == errno.EACCES:
                        # Lock is held by another process
                        self.lock_file.close()
                        self.lock_file = None
                        if attempt < self.retries:
                            await asyncio.sleep(min(timeout, self.max_timeout))
                            timeout *= self.retry_factor
                            continue
                        else:
                            raise LockError(f"Failed to acquire lock for {self.file_path} after {self.retries} retries")
                    else:
                        raise
                        
            except Exception as e:
                if self.lock_file:
                    self.lock_file.close()
                    self.lock_file = None
                if attempt == self.retries:
                    raise LockError(f"Failed to acquire lock for {self.file_path}: {e}")
                await asyncio.sleep(min(timeout, self.max_timeout))
                timeout *= self.retry_factor
                
    async def _release_lock(self):
        """Release the file lock."""
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
                
        if self.lock_file:
            try:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                self.lock_file.close()
                os.unlink(self.lock_file_path)
            except (OSError, FileNotFoundError):
                pass
            finally:
                self.lock_file = None
                
    async def _update_lock_mtime(self):
        """Periodically update lock file mtime to prevent it from becoming stale."""
        try:
            while True:
                await asyncio.sleep(self.update_interval)
                if self.lock_file and not self.lock_file.closed:
                    try:
                        # Update modification time
                        os.utime(self.lock_file_path)
                    except (OSError, FileNotFoundError):
                        break
        except asyncio.CancelledError:
            pass


async def safe_write_json(file_path: str, data: Any) -> None:
    """
    Safely writes JSON data to a file.
    - Creates parent directories if they don't exist
    - Uses file locking to prevent concurrent writes to the same path
    - Writes to a temporary file first
    - If the target file exists, it's backed up before being replaced
    - Attempts to roll back and clean up in case of errors
    
    Args:
        file_path: The absolute path to the target file
        data: The data to serialize to JSON and write
        
    Raises:
        LockError: If file locking fails
        OSError: If file operations fail
        json.JSONEncodeError: If data cannot be serialized to JSON
    """
    absolute_file_path = os.path.abspath(file_path)
    dir_path = os.path.dirname(absolute_file_path)
    
    # Ensure directory structure exists
    try:
        os.makedirs(dir_path, exist_ok=True)
        # Verify directory exists after creation attempt
        if not os.path.exists(dir_path):
            raise OSError(f"Failed to create directory: {dir_path}")
    except OSError as dir_error:
        print(f"Failed to create or access directory for {absolute_file_path}: {dir_error}")
        raise dir_error
        
    # Acquire the lock before any file operations
    async with FileLock(absolute_file_path) as lock:
        # Variables to hold the actual paths of temp files if they are created
        actual_temp_new_file_path: Optional[str] = None
        actual_temp_backup_file_path: Optional[str] = None
        
        try:
            # Step 1: Write data to a new temporary file
            timestamp = int(time.time() * 1000)  # milliseconds
            random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            base_name = os.path.basename(absolute_file_path)
            
            actual_temp_new_file_path = os.path.join(
                dir_path,
                f".{base_name}.new_{timestamp}_{random_suffix}.tmp"
            )
            
            await _write_json_to_file(actual_temp_new_file_path, data)
            
            # Step 2: Check if the target file exists. If so, rename it to a backup path
            try:
                await aiofiles.os.stat(absolute_file_path)
                # Target exists, create a backup path and rename
                actual_temp_backup_file_path = os.path.join(
                    dir_path,
                    f".{base_name}.bak_{timestamp}_{random_suffix}.tmp"
                )
                await aiofiles.os.rename(absolute_file_path, actual_temp_backup_file_path)
            except FileNotFoundError:
                # Target file does not exist, so no backup is made
                pass
                
            # Step 3: Rename the new temporary file to the target file path
            # This is the main "commit" step
            await aiofiles.os.rename(actual_temp_new_file_path, absolute_file_path)
            
            # If we reach here, the new file is successfully in place
            # Mark as "used" or "committed"
            actual_temp_new_file_path = None
            
            # Step 4: If a backup was created, attempt to delete it
            if actual_temp_backup_file_path:
                try:
                    await aiofiles.os.unlink(actual_temp_backup_file_path)
                    # Mark backup as handled
                    actual_temp_backup_file_path = None
                except OSError as unlink_backup_error:
                    # Log this error, but do not re-throw. The main operation was successful
                    print(f"Successfully wrote {absolute_file_path}, but failed to clean up backup "
                          f"{actual_temp_backup_file_path}: {unlink_backup_error}")
                          
        except Exception as original_error:
            print(f"Operation failed for {absolute_file_path}: [Original Error Caught] {original_error}")
            
            new_file_to_cleanup = actual_temp_new_file_path
            backup_file_to_rollback = actual_temp_backup_file_path
            
            # Attempt rollback if a backup was made
            if backup_file_to_rollback:
                try:
                    await aiofiles.os.rename(backup_file_to_rollback, absolute_file_path)
                    # Mark as handled, prevent later cleanup of this path
                    actual_temp_backup_file_path = None
                except OSError as rollback_error:
                    print(f"[Catch] Failed to restore backup {backup_file_to_rollback} to "
                          f"{absolute_file_path}: {rollback_error}")
                          
            # Cleanup the .new file if it exists
            if new_file_to_cleanup:
                try:
                    await aiofiles.os.unlink(new_file_to_cleanup)
                except OSError as cleanup_error:
                    print(f"[Catch] Failed to clean up temporary new file {new_file_to_cleanup}: {cleanup_error}")
                    
            # Cleanup the .bak file if it still needs to be (i.e., wasn't successfully restored)
            if actual_temp_backup_file_path:
                try:
                    await aiofiles.os.unlink(actual_temp_backup_file_path)
                except OSError as cleanup_error:
                    print(f"[Catch] Failed to clean up temporary backup file "
                          f"{actual_temp_backup_file_path}: {cleanup_error}")
                          
            # Re-raise the original error
            raise original_error


async def _write_json_to_file(target_path: str, data: Any) -> None:
    """
    Helper function to write JSON data to a file.
    Handles undefined values by converting them to null.
    
    Args:
        target_path: The path to write the data to
        data: The data to serialize and write
    """
    # Handle undefined values (None in Python) similar to TypeScript version
    if data is None:
        json_data = json.dumps(None)
    else:
        json_data = json.dumps(data, separators=(',', ':'))  # Compact JSON
        
    async with aiofiles.open(target_path, 'w', encoding='utf-8') as f:
        await f.write(json_data)


# Example usage
if __name__ == "__main__":
    async def main():
        test_data = {
            "name": "test",
            "values": [1, 2, 3, 4, 5],
            "nested": {
                "key": "value",
                "number": 42
            }
        }
        
        try:
            await safe_write_json("/tmp/test.json", test_data)
            print("Successfully wrote JSON file")
        except Exception as e:
            print(f"Error: {e}")
            
    asyncio.run(main())