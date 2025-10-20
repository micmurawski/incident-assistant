import asyncio
import time
from typing import Callable, Dict, List, TypedDict, TypeVar
from uuid import uuid4


class QueueMessage(TypedDict):
    id: str
    text: str
    timestamp: int


class AsyncEventEmitter:
    """Simple async event emitter for handling events."""

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}

    def on(self, event: str, callback: Callable) -> None:
        """Register a listener for an event."""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def off(self, event: str, callback: Callable) -> None:
        """Remove a listener from an event."""
        if event in self._listeners:
            self._listeners[event].remove(callback)
            if not self._listeners[event]:
                del self._listeners[event]

    async def emit(self, event: str, *args, **kwargs) -> None:
        """Emit an event and call all registered listeners."""
        if event in self._listeners:
            # Create tasks for all listeners and run concurrently
            tasks = [self._call_listener(listener, *args, **kwargs) for listener in self._listeners[event]]
            await asyncio.gather(*tasks)

    async def _call_listener(self, listener: Callable, *args, **kwargs) -> None:
        """Call a listener, handling both async and sync functions."""
        result = listener(*args, **kwargs)
        if asyncio.iscoroutine(result):
            await result

    def once(self, event: str, callback: Callable) -> None:
        """Register a listener that fires only once."""

        async def wrapper(*args, **kwargs):
            await self._call_listener(callback, *args, **kwargs)
            self.off(event, wrapper)

        self.on(event, wrapper)


T = TypeVar("T", bound="MessageQueueService")


class MessageQueueService(AsyncEventEmitter):
    _instance: T | None = None
    _messages: asyncio.Queue[QueueMessage] = asyncio.Queue()

    @classmethod
    def get_instance(cls) -> "MessageQueueService":
        if cls._instance is None:
            cls._instance = MessageQueueService()
        return cls._instance

    async def _find_message(self, _id: str) -> QueueMessage | None:
        async for i, message in enumerate(self._messages):
            if message["id"] == _id:
                return i, message
        return -1, None

    async def add_message(self, text: str):
        if not text.strip():
            return

        message = QueueMessage(id=str(uuid4()), text=text, timestamp=time.time())
        await self._messages.put(message)
        await self.emit("message_added", message)
        return message

    async def remove_message(self, _id: str) -> bool:
        index, message = await self._find_message(_id)
        if message:
            del self._messages[index]
            await self.emit("message_removed", message)
            return True
        return False

    async def dequeue(self) -> QueueMessage:
        return await self._messages.get()

    @property
    def messages(self) -> List[QueueMessage]:
        return list(self._messages)

    def is_empty(self) -> bool:
        return len(self._messages) == 0

    def dispose(self) -> None:
        self._messages = asyncio.Queue()
        self._listeners.clear()
