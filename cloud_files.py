"""Windows Cloud Files API helpers: pin, dehydrate, detect placeholders."""
import subprocess
import time
from pathlib import Path

import cancel
from config import HYDRATE_TIMEOUT, POLL_INTERVAL
from logger import log


def _run_attrib(flags: list[str], path: Path) -> None:
    """Run Windows `attrib` to pin/unpin a cloud file. Errors are non-fatal."""
    try:
        subprocess.run(
            ["attrib", *flags, str(path)],
            check=False, capture_output=True, text=True,
        )
    except FileNotFoundError:
        log("attrib.exe not found -- are you on Windows?")
        raise


def pin(path: Path) -> None:
    """'Always keep on this device' -> forces download."""
    _run_attrib(["+P", "-U"], path)


def dehydrate(path: Path) -> None:
    """'Free up space' -> online-only placeholder."""
    _run_attrib(["+U", "-P"], path)


def is_placeholder(path: Path) -> bool:
    """
    True if the file is an online-only/recall placeholder (content not local).
    Checks FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS, RECALL_ON_OPEN, and OFFLINE.
    """
    try:
        import ctypes
        GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
        attrs = GetFileAttributesW(str(path))
        if attrs == -1:
            return False
        RECALL_ON_DATA_ACCESS = 0x00400000
        RECALL_ON_OPEN        = 0x00040000
        OFFLINE               = 0x00001000
        return bool(attrs & (RECALL_ON_DATA_ACCESS | RECALL_ON_OPEN | OFFLINE))
    except Exception:
        return False


def wait_until_hydrated(path: Path) -> bool:
    """Block until the file is fully downloaded locally, or timeout."""
    deadline = time.time() + HYDRATE_TIMEOUT
    expected = path.stat().st_size
    while time.time() < deadline:
        cancel.check()
        if not is_placeholder(path):
            s1 = path.stat().st_size
            cancel.sleep(0.5)
            s2 = path.stat().st_size
            if s1 == s2 == expected:
                return True
        cancel.sleep(POLL_INTERVAL)
    return False
