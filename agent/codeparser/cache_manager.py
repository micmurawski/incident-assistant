from safe_writer import safe_write_json
from typing import Dict, Any
import os
import asyncio
import functools

HOME_DIR = os.path.expanduser("~")


def async_debounce(wait_seconds):
    """
    Async debounce decorator for async methods.

    This decorator ensures that if the decorated async function is called multiple times
    in quick succession, only the last call will actually execute after the specified
    wait_seconds delay. Any previous pending calls are cancelled.

    Useful for batching or rate-limiting expensive operations (e.g., saving to disk)
    that may be triggered frequently in a short period.
    """
    def decorator(fn):
        task = None

        @functools.wraps(fn)
        async def debounced(*args, **kwargs):
            nonlocal task
            # Cancel any previously scheduled call that hasn't run yet
            if task is not None and not task.done():
                task.cancel()

            async def call_it():
                try:
                    await asyncio.sleep(wait_seconds)
                    await fn(*args, **kwargs)
                except asyncio.CancelledError:
                    # Ignore cancellation, as this is expected for debouncing
                    pass
            # Schedule the new call and await it
            task = asyncio.create_task(call_it())
            await task
        return debounced
    return decorator


class CacheManager:

    def __init__(self, cache_dir: str = ".index_cache.json"):
        self.cache_path = os.path.join(HOME_DIR, cache_dir)
        self.file_hashes: dict[str, str] = {}

    @staticmethod
    async def _safe_write_json(file_path: str, data: Any):
        print("Saving cache to", file_path)
        try:
            await safe_write_json(file_path, data)
        except Exception as e:
            print(f"Error saving cache: {e}")

    async def _perform_save(self):
        await self._safe_write_json(self.cache_path, self.file_hashes)

    async def _clear_cache(self):
        await self._safe_write_json(self.cache_path, {})

    def get_file_hash(self, file_path: str) -> str:
        return self.file_hashes.get(file_path)

    async def update_file_hash(self, file_path: str, file_hash: str):
        self.file_hashes[file_path] = file_hash
        print("AWAIT", file_path)
        await self._debounced_save_cache()

    async def delete_file_hash(self, file_path: str):
        del self.file_hashes[file_path]
        await self._debounced_save_cache()

    def get_all_file_hashes(self) -> dict[str, str]:
        return self.file_hashes

    @async_debounce(1.5)
    async def _debounced_save_cache(self):
        await self._perform_save()
