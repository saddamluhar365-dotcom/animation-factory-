from __future__ import annotations

from collections.abc import Callable
import queue


class UiEventBridge:
    """Thread-safe bridge for sending callbacks from workers to the Tk UI thread."""

    def __init__(self) -> None:
        self._events: queue.Queue[Callable[[], None]] = queue.Queue()

    def post(self, callback: Callable[[], None]) -> None:
        self._events.put(callback)

    def drain(self, limit: int | None = None) -> int:
        processed = 0
        while limit is None or processed < limit:
            try:
                callback = self._events.get_nowait()
            except queue.Empty:
                break
            callback()
            processed += 1
        return processed
