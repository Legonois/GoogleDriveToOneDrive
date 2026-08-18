"""Per-file backup logic + directory walker."""
import os
import shutil
import time
from pathlib import Path

from config import (
    COPY_CHUNK_SIZE,
    COPY_RETRIES,
    COPY_RETRY_WAIT,
    PUBLISHER_EXTS,
    SKIP_EXTS,
    SOURCE_IS_GOOGLE_DRIVE,
)
from cloud_files import dehydrate, is_placeholder, pin, wait_until_hydrated
from logger import iso_now, log
from manifest import source_fingerprint

# ERROR_NO_SYSTEM_RESOURCES / ERROR_WORKING_SET_QUOTA -- transient kernel
# resource exhaustion from stacked filter drivers (Drive FS + OneDrive).
TRANSIENT_WINERRORS = {1450, 1453}


def is_publisher_file(path: Path) -> bool:
    return path.suffix.lower() in PUBLISHER_EXTS


def dehydrate_if_needed(path: Path) -> None:
    """Only shell out to attrib when the file isn't already a placeholder."""
    if not is_placeholder(path):
        dehydrate(path)


def dehydrate_source(path: Path) -> None:
    """No-op on Google Drive, which doesn't implement the Cloud Files API."""
    if SOURCE_IS_GOOGLE_DRIVE:
        return
    dehydrate_if_needed(path)


def _copy_chunked(src: Path, dst: Path) -> None:
    """
    Stream src -> dst through a bounded buffer, writing to a .part temp file
    and renaming on success.

    Deliberately avoids shutil.copy2, which on Windows dispatches to the Win32
    CopyFile2 API. CopyFile2 fails with WinError 1450 when the read side is
    Google Drive's virtual drive and the write side is a OneDrive-synced
    folder; a plain read/write loop pulls the stream at a pace Drive FS can
    actually serve.
    """
    tmp = dst.with_name(dst.name + ".part")
    try:
        with open(src, "rb", buffering=0) as fsrc, open(tmp, "wb", buffering=0) as fdst:
            while True:
                chunk = fsrc.read(COPY_CHUNK_SIZE)
                if not chunk:
                    break
                fdst.write(chunk)
            fdst.flush()
            os.fsync(fdst.fileno())
        os.replace(tmp, dst)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    shutil.copystat(src, dst)


def copy_with_retry(src: Path, dst: Path) -> None:
    """Chunked copy, retrying transient filter-driver resource errors."""
    for attempt in range(1, COPY_RETRIES + 1):
        try:
            _copy_chunked(src, dst)
            return
        except OSError as e:
            transient = getattr(e, "winerror", None) in TRANSIENT_WINERRORS
            if not transient or attempt == COPY_RETRIES:
                raise
            log(f"RETRY {attempt}/{COPY_RETRIES - 1} after WinError "
                f"{e.winerror} on {src}")
            time.sleep(COPY_RETRY_WAIT * attempt)


def iter_files(root: Path):
    """Yield every real file under `root`, skipping Google-native shortcuts."""
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if Path(name).suffix.lower() in SKIP_EXTS:
                continue
            yield Path(dirpath) / name


def backup_one(src: Path, dst: Path, manifest: dict, rel_key: str) -> str:
    """
    Back up a single file. Returns 'updated', 'skipped', or 'failed'.

    - If source was online-only originally, restore it to online-only after.
    - If source is a Publisher (.pub) file, always dehydrate after.
    - If source was already kept locally, leave it hydrated (respect user choice).
    - Destination is always dehydrated so OneDrive frees space after upload.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)

    src_was_placeholder = is_placeholder(src)
    force_dehydrate_src = is_publisher_file(src)

    # Fingerprint BEFORE pinning so we don't disturb mtime.
    try:
        size, mtime_ns = source_fingerprint(src)
    except OSError as e:
        log(f"STAT FAILED {src}: {e}")
        return "failed"

    prev = manifest["files"].get(rel_key)
    unchanged = (
        prev is not None
        and prev.get("size") == size
        and prev.get("mtime_ns") == mtime_ns
        and dst.exists()
    )

    if unchanged:
        log(f"SKIP (unchanged since {prev.get('backed_up_at')}): {src}")
        if force_dehydrate_src or src_was_placeholder:
            dehydrate_source(src)
        dehydrate_if_needed(dst)
        return "skipped"

    # Hydrate if needed. Skipped for Google Drive sources: DriveFS doesn't
    # expose placeholder attributes, so is_placeholder() is always False there
    # and the chunked read below pulls the stream on demand instead.
    if src_was_placeholder:
        log(f"PIN   {src}")
        pin(src)
        if not wait_until_hydrated(src):
            log(f"TIMEOUT waiting for hydration, skipping: {src}")
            dehydrate_source(src)
            return "failed"

    log(f"COPY  -> {dst}")
    try:
        copy_with_retry(src, dst)
    except Exception as e:
        log(f"COPY FAILED for {src}: {e}")
        if src_was_placeholder or force_dehydrate_src:
            dehydrate_source(src)
        return "failed"

    # Re-stat in case mtime shifted during hydration, then record.
    try:
        size, mtime_ns = source_fingerprint(src)
    except OSError:
        pass
    manifest["files"][rel_key] = {
        "size": size,
        "mtime_ns": mtime_ns,
        "backed_up_at": iso_now(),
    }

    dehydrate_if_needed(dst)
    if force_dehydrate_src:
        dehydrate_source(src)
    elif src_was_placeholder:
        dehydrate_source(src)

    log(f"DONE  {src}")
    return "updated"
