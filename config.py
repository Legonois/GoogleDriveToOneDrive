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

# ---- Copy tuning -----------------------------------------------------------
# Google Drive's G: drive is NOT a Windows Cloud Files provider -- it does not
# use placeholder attributes, and attrib +P/-U is a no-op there. Leave this on
# so we skip the pointless pin/dehydrate subprocess calls on the source side.
SOURCE_IS_GOOGLE_DRIVE = True

# We copy in chunks rather than via shutil.copy2, because shutil uses the Win32
# CopyFile2 API, which throws ERROR_NO_SYSTEM_RESOURCES (WinError 1450) when
# reading from Google Drive's filter driver and writing into a OneDrive-synced
# folder. A plain buffered read/write loop avoids that path entirely.
COPY_CHUNK_SIZE = 1024 * 1024   # 1 MiB
COPY_RETRIES    = 3             # attempts per file before giving up
COPY_RETRY_WAIT = 5.0           # seconds to wait between attempts

# ---- Staging ---------------------------------------------------------------
# Copy G: -> a plain local folder first, then rename that file into the
# OneDrive destination. The rename is metadata-only when staging and
# destination share a volume, so Drive FS reads and OneDrive writes never
# happen inside the same I/O operation -- which is what starves the kernel's
# paged pool and produces WinError 1450.
#
# STAGING_DIR must be on the SAME DRIVE as ONEDRIVE_DEST (normally C:) and
# must NOT be inside a OneDrive-synced folder. None -> a "gd2od-staging"
# folder under the system temp dir, which satisfies both on a stock setup.
USE_STAGING = True
STAGING_DIR = None

# ---- Manifest / summary filenames -----------------------------------------
MANIFEST_NAME = ".backup_manifest.json"
SUMMARY_NAME  = "LAST_BACKUP.txt"
LOG_FILE      = Path("backup.log")

# ---- Behavior --------------------------------------------------------------
CHECKPOINT_EVERY = 25              # save manifest every N files
PUBLISHER_EXTS   = {".pub"}        # always dehydrate these on the source side

# Google-native shortcuts; skipped because they aren't real files.
SKIP_EXTS = {".gdoc", ".gsheet", ".gslides", ".gform", ".gdraw"}
