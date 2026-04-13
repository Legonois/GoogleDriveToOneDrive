"""
Entry point.

Usage:
    python main.py

Edit config.py to set GDRIVE_ROOT and ONEDRIVE_DEST before first run.
"""
import sys

from config import CHECKPOINT_EVERY, GDRIVE_ROOT, ONEDRIVE_DEST
from backup import backup_one, iter_files
from logger import iso_now, log
from manifest import load_manifest, save_manifest, write_summary


def main() -> int:
    if not GDRIVE_ROOT.exists():
        log(f"Source not found: {GDRIVE_ROOT}")
        return 1
    ONEDRIVE_DEST.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(ONEDRIVE_DEST)
    log(f"Starting backup: {GDRIVE_ROOT} -> {ONEDRIVE_DEST}")
    if manifest.get("last_run"):
        log(f"Previous run: {manifest['last_run']}")

    processed = updated = skipped = 0

    try:
        for src in iter_files(GDRIVE_ROOT):
            rel = src.relative_to(GDRIVE_ROOT)
            dst = ONEDRIVE_DEST / rel
            rel_key = str(rel).replace("\\", "/")   # stable cross-platform key
            try:
                result = backup_one(src, dst, manifest, rel_key)
                processed += 1
                if result == "updated":
                    updated += 1
                elif result == "skipped":
                    skipped += 1
                if processed % CHECKPOINT_EVERY == 0:
                    save_manifest(ONEDRIVE_DEST, manifest)
            except Exception as e:
                log(f"ERROR on {src}: {e}")
    except KeyboardInterrupt:
        log("Interrupted by user; saving manifest.")
        manifest["last_run"] = iso_now()
        save_manifest(ONEDRIVE_DEST, manifest)
        write_summary(ONEDRIVE_DEST, manifest, processed, updated, skipped)
        return 130

    manifest["last_run"] = iso_now()
    save_manifest(ONEDRIVE_DEST, manifest)
    write_summary(ONEDRIVE_DEST, manifest, processed, updated, skipped)
    log(f"Finished. Processed {processed} (updated {updated}, skipped {skipped}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
