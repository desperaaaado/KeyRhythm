from __future__ import annotations

from typing import Generic, TypeVar


T = TypeVar("T")


class SpscRingBuffer(Generic[T]):
    """Fixed-capacity SPSC queue.

    CPython's GIL makes index publication atomic for the supported Python
    prototype. The API deliberately does not resize or take locks. A native
    implementation can replace this class without changing callers.
    """

    __slots__ = ("_items", "_size", "_head", "_tail", "overflows")

    def __init__(self, capacity: int):
        if capacity < 2:
            raise ValueError("capacity must be at least 2")
        self._items: list[T | None] = [None] * (capacity + 1)
        self._size = capacity + 1
        self._head = 0
        self._tail = 0
        self.overflows = 0

    @property
    def capacity(self) -> int:
        return self._size - 1

    def push(self, item: T) -> bool:
        next_head = (self._head + 1) % self._size
        if next_head == self._tail:
            self.overflows += 1
            return False
        self._items[self._head] = item
        self._head = next_head
        return True

    def pop(self) -> T | None:
        if self._tail == self._head:
            return None
        item = self._items[self._tail]
        self._items[self._tail] = None
        self._tail = (self._tail + 1) % self._size
        return item

    def clear(self) -> None:
        while self.pop() is not None:
            pass

    def __len__(self) -> int:
        return (self._head - self._tail) % self._size

