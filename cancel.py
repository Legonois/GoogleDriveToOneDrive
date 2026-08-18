"""
Cooperative cancellation.

Ctrl-C can't preempt a blocking read on Windows -- there is no EINTR for a
stalled ReadFile against a filter-driver filesystem like Google Drive's, so the
interpreter cannot raise KeyboardInterrupt until that read returns. What we can
do is acknowledge the keypress immediately and stop at the next safe point
(between chunks, between files, during a retry backoff) instead of leaving the
user staring at a dead terminal wondering whether it registered.
"""
import signal
import threading

from logger import log

_cancelled = threading.Event()


def is_cancelled() -> bool:
    return _cancelled.is_set()


def request_cancel() -> None:
    _cancelled.set()


def sleep(seconds: float) -> None:
    """Interruptible sleep -- returns early if cancellation is requested."""
    _cancelled.wait(seconds)


def check() -> None:
    """Raise at a safe point if cancellation was requested."""
    if _cancelled.is_set():
        raise KeyboardInterrupt


def install() -> None:
    """First Ctrl-C asks to stop cleanly; a second one exits now."""
    def handler(signum, frame):
        if _cancelled.is_set():
            log("Second interrupt -- exiting immediately, manifest NOT saved.")
            raise KeyboardInterrupt
        _cancelled.set()
        log("Cancelling... finishing the current chunk, then saving manifest. "
            "Press Ctrl-C again to quit immediately.")

    signal.signal(signal.SIGINT, handler)
