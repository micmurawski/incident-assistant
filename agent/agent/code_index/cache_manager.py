import asyncio
import functools
import json
import os
from typing import Any

from agent.code_index.safe_writer import safe_write_json

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
                    return await fn(*args, **kwargs)
                except asyncio.CancelledError:
                    # Ignore cancellation, as this is expected for debouncing
                    return None

            # Schedule the new call and await it
            task = asyncio.create_task(call_it())
            try:
                res = await task
                return res
            except asyncio.CancelledError:
                # If the outer await is cancelled, propagate the cancellation
                raise

        return debounced

    return decorator


class CacheManager:
    _instances: dict[str, "CacheManager"] = {}

    @classmethod
    def get_instance(cls, cache_dir: str = ".index_cache.json"):
        if cache_dir not in cls._instances:
            cls._instances[cache_dir] = CacheManager(cache_dir)
        return cls._instances[cache_dir]

    def __init__(self, cache_dir: str = ".index_cache.json"):
        self.lock = asyncio.Lock()
        self.cache_path = os.path.join(HOME_DIR, cache_dir)
        print(f"Cache path: {self.cache_path}")
        base_path = os.path.dirname(self.cache_path)
        if not os.path.exists(base_path):
            os.makedirs(base_path)
        self.file_hashes: dict[str, str] = {}
        self._load_cache_from_disk()

    def _load_cache_from_disk(self):
        """Load the cache from disk into self.file_hashes."""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.file_hashes = data
                    else:
                        self.file_hashes = {}
            except Exception as e:
                print(f"Error loading cache from {self.cache_path}: {e}")
                self.file_hashes = {}
        else:
            self.file_hashes = {}

    @staticmethod
    async def _safe_write_json(file_path: str, data: Any):
        try:
            await safe_write_json(file_path, data)
        except Exception as e:
            print(f"Error saving cache: {e}")

    async def _perform_save(self):
        await self._safe_write_json(self.cache_path, self.file_hashes)

    async def _clear_cache(self):
        await self._safe_write_json(self.cache_path, {})
        self.file_hashes = {}

    def get_file_hash(self, file_path: str) -> str:
        return self.file_hashes.get(file_path)

    async def update_file_hash(self, file_path: str, file_hash: str):
        async with self.lock:
            self.file_hashes[file_path] = file_hash
        await self._debounced_save_cache()

    async def delete_file_hash(self, file_path: str):
        if file_path in self.file_hashes:
            del self.file_hashes[file_path]
            await self._debounced_save_cache()

    def get_all_file_hashes(self) -> dict[str, str]:
        return self.file_hashes.copy()

    @async_debounce(1.5)
    async def _debounced_save_cache(self):
        await self._perform_save()


if __name__ == "__main__":

    @async_debounce(1.5)
    async def test_debounce(num: int):
        await asyncio.sleep(num)
        print("Hello", num)

    async def main():
        # Only the last call should actually execute after debounce period.
        # If both are awaited in parallel, the first will be cancelled.
        t1 = asyncio.create_task(test_debounce(1))
        await asyncio.sleep(0.1)  # Simulate rapid succession
        t2 = asyncio.create_task(test_debounce(5))
        # Only the last call should print after debounce period
        await asyncio.gather(t1, t2, return_exceptions=True)

    asyncio.run(main())
