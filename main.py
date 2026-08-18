"""
Entry point.

Usage:
    python main.py

Edit config.py to set GDRIVE_ROOT and ONEDRIVE_DEST before first run.
Install dependency: pip install tqdm
"""
import sys

from tqdm import tqdm

import cancel
from config import CHECKPOINT_EVERY, GDRIVE_ROOT, ONEDRIVE_DEST
from backup import backup_one, iter_files, prepare_staging
from logger import iso_now, log
from manifest import load_manifest, save_manifest, write_summary


def count_files(root) -> int:
    """Pre-walk to get a total for the progress bar. Cheap -- just stats dirs."""
    return sum(1 for _ in iter_files(root))


def main() -> int:
    cancel.install()

    if not GDRIVE_ROOT.exists():
        log(f"Source not found: {GDRIVE_ROOT}")
        return 1
    ONEDRIVE_DEST.mkdir(parents=True, exist_ok=True)

    prepare_staging(ONEDRIVE_DEST)

    manifest = load_manifest(ONEDRIVE_DEST)
    log(f"Starting backup: {GDRIVE_ROOT} -> {ONEDRIVE_DEST}")
    if manifest.get("last_run"):
        log(f"Previous run: {manifest['last_run']}")

    log("Counting files...")
    total = count_files(GDRIVE_ROOT)
    log(f"Found {total} files to check.")

    processed = updated = skipped = failed = 0

    bar = tqdm(
        total=total,
        unit="file",
        dynamic_ncols=True,
        smoothing=0.1,           # steadier ETA for mixed file sizes
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]{postfix}",
    )

    try:
        for src in iter_files(GDRIVE_ROOT):
            cancel.check()
            rel = src.relative_to(GDRIVE_ROOT)
            dst = ONEDRIVE_DEST / rel
            rel_key = str(rel).replace("\\", "/")

            # Truncate long names so the bar doesn't wrap
            display = str(rel)
            if len(display) > 50:
                display = "..." + display[-47:]
            bar.set_description(display)

            try:
                result = backup_one(src, dst, manifest, rel_key)
                processed += 1
                if result == "updated":
                    updated += 1
                elif result == "skipped":
                    skipped += 1
                elif result == "failed":
                    failed += 1
                bar.set_postfix(
                    updated=updated, skipped=skipped, failed=failed, refresh=False
                )
                if processed % CHECKPOINT_EVERY == 0:
                    save_manifest(ONEDRIVE_DEST, manifest)
            except Exception as e:
                log(f"ERROR on {src}: {e}")
                failed += 1
            finally:
                bar.update(1)
    except KeyboardInterrupt:
        bar.close()
        log("Interrupted by user; saving manifest.")
        manifest["last_run"] = iso_now()
        save_manifest(ONEDRIVE_DEST, manifest)
        write_summary(ONEDRIVE_DEST, manifest, processed, updated, skipped)
        return 130

    bar.close()
    manifest["last_run"] = iso_now()
    save_manifest(ONEDRIVE_DEST, manifest)
    write_summary(ONEDRIVE_DEST, manifest, processed, updated, skipped)
    log(
        f"Finished. Processed {processed} "
        f"(updated {updated}, skipped {skipped}, failed {failed})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())