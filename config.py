"""Configuration for the Google Drive -> OneDrive backup script."""
from pathlib import Path

# ---- Paths -----------------------------------------------------------------
# Adjust these. Google Drive is usually G:\My Drive (streaming mode)
# or %USERPROFILE%\My Drive (mirror mode).
GDRIVE_ROOT   = Path(r"G:\My Drive")
ONEDRIVE_DEST = Path(r"C:\Users\YOURNAME\OneDrive\Backups\GoogleDrive")

# ---- Hydration tuning ------------------------------------------------------
HYDRATE_TIMEOUT = 300      # max seconds to wait for a single file
POLL_INTERVAL   = 1.0      # seconds between size checks

# ---- Manifest / summary filenames -----------------------------------------
MANIFEST_NAME = ".backup_manifest.json"
SUMMARY_NAME  = "LAST_BACKUP.txt"
LOG_FILE      = Path("backup.log")

# ---- Behavior --------------------------------------------------------------
CHECKPOINT_EVERY = 25              # save manifest every N files
PUBLISHER_EXTS   = {".pub"}        # always dehydrate these on the source side

# Google-native shortcuts; skipped because they aren't real files.
SKIP_EXTS = {".gdoc", ".gsheet", ".gslides", ".gform", ".gdraw"}
