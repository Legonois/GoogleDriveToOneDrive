"""Manifest: per-file fingerprints + timestamps, stored at the backup root."""
import json
from pathlib import Path

from config import MANIFEST_NAME, SUMMARY_NAME
from logger import iso_now, log


def load_manifest(dest_root: Path) -> dict:
    path = dest_root / MANIFEST_NAME
    if not path.exists():
        return {"created": iso_now(), "last_run": None, "files": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"Manifest unreadable ({e}); starting fresh.")
        return {"created": iso_now(), "last_run": None, "files": {}}


def save_manifest(dest_root: Path, manifest: dict) -> None:
    """Atomic write: temp file + rename."""
    path = dest_root / MANIFEST_NAME
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    tmp.replace(path)


def write_summary(
    dest_root: Path,
    manifest: dict,
    processed: int,
    updated: int,
    skipped: int,
) -> None:
    lines = [
        f"Last backup run : {manifest.get('last_run')}",
        f"Manifest created: {manifest.get('created')}",
        f"Total files tracked: {len(manifest.get('files', {}))}",
        f"This run - processed: {processed}, updated: {updated}, skipped: {skipped}",
    ]
    (dest_root / SUMMARY_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")


def source_fingerprint(path: Path) -> tuple[int, int]:
    """(size, mtime_ns) -- used to decide if a file changed since last backup."""
    st = path.stat()
    return st.st_size, st.st_mtime_ns
