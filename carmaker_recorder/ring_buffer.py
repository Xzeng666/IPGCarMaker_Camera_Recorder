from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RingBufferStats:
    capacity: int
    size: int
    pushed: int
    popped: int
    dropped: int
    high_watermark: int


class RingBuffer(Generic[T]):
    """Bounded non-blocking producer buffer with observable overwrite statistics."""

    def __init__(self, capacity: int):
        self.cap = max(2, int(capacity))
        self.buf: list[Optional[T]] = [None] * self.cap
        self.w = 0
        self.r = 0
        self.count = 0
        self.pushed = 0
        self.popped = 0
        self.dropped = 0
        self.high_watermark = 0
        self.lock = threading.Lock()
        self.not_empty = threading.Condition(self.lock)

    def push_overwrite(self, item: T) -> bool:
        """Push item and return True when the oldest queued item had to be dropped."""
        overwritten = False
        with self.lock:
            self.pushed += 1
            if self.count == self.cap:
                self.r = (self.r + 1) % self.cap
                self.count -= 1
                self.dropped += 1
                overwritten = True
            self.buf[self.w] = item
            self.w = (self.w + 1) % self.cap
            self.count += 1
            self.high_watermark = max(self.high_watermark, self.count)
            self.not_empty.notify()
        return overwritten

    def pop(self, timeout: Optional[float] = None) -> Optional[T]:
        with self.not_empty:
            if self.count == 0 and not self.not_empty.wait(timeout=timeout):
                return None
            if self.count == 0:
                return None
            item = self.buf[self.r]
            self.buf[self.r] = None
            self.r = (self.r + 1) % self.cap
            self.count -= 1
            self.popped += 1
            return item

    def size(self) -> int:
        with self.lock:
            return self.count

    def stats(self) -> RingBufferStats:
        with self.lock:
            return RingBufferStats(
                capacity=self.cap,
                size=self.count,
                pushed=self.pushed,
                popped=self.popped,
                dropped=self.dropped,
                high_watermark=self.high_watermark,
            )
