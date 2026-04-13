"""Per-file backup logic + directory walker."""
import os
import shutil
from pathlib import Path

from config import PUBLISHER_EXTS, SKIP_EXTS
from cloud_files import dehydrate, is_placeholder, pin, wait_until_hydrated
from logger import iso_now, log
from manifest import source_fingerprint


def is_publisher_file(path: Path) -> bool:
    return path.suffix.lower() in PUBLISHER_EXTS


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
            dehydrate(src)
        dehydrate(dst)
        return "skipped"

    # Hydrate if needed
    if src_was_placeholder:
        log(f"PIN   {src}")
        pin(src)
        if not wait_until_hydrated(src):
            log(f"TIMEOUT waiting for hydration, skipping: {src}")
            dehydrate(src)
            return "failed"
    else:
        log(f"ALREADY LOCAL  {src}")

    log(f"COPY  -> {dst}")
    try:
        shutil.copy2(src, dst)
    except Exception as e:
        log(f"COPY FAILED for {src}: {e}")
        if src_was_placeholder or force_dehydrate_src:
            dehydrate(src)
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

    dehydrate(dst)
    if force_dehydrate_src:
        log(f"DEHYDRATE (publisher): {src}")
        dehydrate(src)
    elif src_was_placeholder:
        dehydrate(src)
    else:
        log(f"LEAVE HYDRATED: {src}")

    log(f"DONE  {src}")
    return "updated"
