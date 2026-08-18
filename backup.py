"""Per-file backup logic + directory walker."""
import os
import shutil
import tempfile
from pathlib import Path

from config import (
    COPY_CHUNK_SIZE,
    COPY_RETRIES,
    COPY_RETRY_WAIT,
    PUBLISHER_EXTS,
    SKIP_EXTS,
    SOURCE_IS_GOOGLE_DRIVE,
    STAGING_DIR,
    USE_STAGING,
)
import cancel
from cloud_files import dehydrate, is_placeholder, pin, wait_until_hydrated
from logger import iso_now, log
from manifest import source_fingerprint

# ERROR_NO_SYSTEM_RESOURCES / ERROR_WORKING_SET_QUOTA -- transient kernel
# resource exhaustion from stacked filter drivers (Drive FS + OneDrive).
TRANSIENT_WINERRORS = {1450, 1453}

STAGE_PREFIX = "gd2od-"


def is_publisher_file(path: Path) -> bool:
    return path.suffix.lower() in PUBLISHER_EXTS


def iter_files(root: Path):
    """Yield every real file under `root`, skipping Google-native shortcuts."""
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if Path(name).suffix.lower() in SKIP_EXTS:
                continue
            yield Path(dirpath) / name


def dehydrate_if_needed(path: Path) -> None:
    """Only shell out to attrib when the file isn't already a placeholder."""
    if not is_placeholder(path):
        dehydrate(path)


def dehydrate_source(path: Path) -> None:
    """No-op on Google Drive, which doesn't implement the Cloud Files API."""
    if SOURCE_IS_GOOGLE_DRIVE:
        return
    dehydrate_if_needed(path)


def staging_dir() -> Path:
    """The folder we copy into before renaming across to OneDrive."""
    base = Path(STAGING_DIR) if STAGING_DIR else Path(tempfile.gettempdir()) / "gd2od-staging"
    base.mkdir(parents=True, exist_ok=True)
    return base


def prepare_staging(dest_root: Path) -> None:
    """Warn if staging won't buy us anything, and clear leftovers from a crash."""
    if not USE_STAGING:
        return
    stage = staging_dir()

    if stage.drive.lower() != dest_root.drive.lower():
        log(f"WARNING: staging dir {stage} is on a different drive than "
            f"{dest_root}; the hand-off will be a full copy, not a rename. "
            f"Set STAGING_DIR in config.py to a folder on {dest_root.drive}")

    stale = list(stage.glob(STAGE_PREFIX + "*"))
    for leftover in stale:
        try:
            leftover.unlink()
        except OSError:
            pass
    if stale:
        log(f"Cleared {len(stale)} leftover staged file(s) from {stage}")


def _stream(src: Path, dst: Path) -> None:
    """Copy src -> dst through a bounded buffer. dst must not already exist."""
    with open(src, "rb", buffering=0) as fsrc, open(dst, "wb", buffering=0) as fdst:
        while True:
            # Safe point: a pending Ctrl-C stops us here rather than after the
            # whole file. This is as responsive as it gets -- the read below is
            # not interruptible once it blocks.
            cancel.check()
            chunk = fsrc.read(COPY_CHUNK_SIZE)
            if not chunk:
                break
            fdst.write(chunk)
        fdst.flush()
        os.fsync(fdst.fileno())


def _copy_direct(src: Path, dst: Path) -> None:
    """Stream straight into the destination folder via a .part temp file."""
    tmp = dst.with_name(dst.name + ".part")
    try:
        _stream(src, tmp)
        shutil.copystat(src, tmp)
        os.replace(tmp, dst)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _copy_staged(src: Path, dst: Path) -> None:
    """
    Two hops: G: -> local staging file, then staging file -> destination.

    The second hop is os.replace, which is a metadata-only rename when both
    sides share a volume. So Drive FS never reads while OneDrive writes, and
    the staged file is already complete and closed before OneDrive sees it.
    """
    fd, tmp_name = tempfile.mkstemp(prefix=STAGE_PREFIX, dir=staging_dir())
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        _stream(src, tmp)
        shutil.copystat(src, tmp)
        try:
            os.replace(tmp, dst)
        except OSError as e:
            # Cross-volume rename (ERROR_NOT_SAME_DEVICE / EXDEV). Fall back to
            # a second stream; still worth it, since the read side is now local
            # disk rather than Drive FS.
            if getattr(e, "winerror", None) != 17 and e.errno != 18:
                raise
            _copy_direct(tmp, dst)
            tmp.unlink(missing_ok=True)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def copy_with_retry(src: Path, dst: Path) -> None:
    """Chunked copy, retrying transient filter-driver resource errors."""
    copier = _copy_staged if USE_STAGING else _copy_direct
    for attempt in range(1, COPY_RETRIES + 1):
        try:
            copier(src, dst)
            return
        except OSError as e:
            transient = getattr(e, "winerror", None) in TRANSIENT_WINERRORS
            if not transient or attempt == COPY_RETRIES:
                raise
            log(f"RETRY {attempt}/{COPY_RETRIES - 1} after WinError "
                f"{e.winerror} on {src}")
            cancel.sleep(COPY_RETRY_WAIT * attempt)
            cancel.check()


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
