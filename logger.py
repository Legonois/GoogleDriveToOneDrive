"""Tiny logger: prints to stdout and appends to a log file."""
import time
from datetime import datetime, timezone

from config import LOG_FILE


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def iso_now() -> str:
    """Local-time ISO 8601 with offset, seconds precision."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
