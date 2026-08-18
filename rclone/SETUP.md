# rclone backup: Google Drive -> OneDrive

One-time setup, then `backup.bat` is the whole job.

## Why this replaces the Python script

The Python script read files through Google Drive's `G:\` virtual drive and
wrote them into the OneDrive sync folder. That stacks two Windows filter
drivers in one I/O path, which is what produced
`WinError 1450: Insufficient system resources` and the stalls where a 2 MB
photo took three minutes and then failed.

rclone talks to both services over their APIs instead. Nothing touches `G:\`,
nothing is written into the OneDrive sync folder, and no local disk space is
needed for staging. It also fixes several things the script got wrong:

| | Python script | rclone |
|---|---|---|
| Google Docs/Sheets/Slides | silently skipped (data loss) | exported to .docx/.xlsx/.pptx |
| Verification | size + mtime only | checksummed every file |
| Stuck on one bad file | blocks forever, unkillable | per-request timeouts, moves on |
| Paths over 260 chars | fails | handled |
| Names illegal on Windows | fails | encoded automatically |
| Resume | manifest, every 25 files | per-file, automatic |
| Parallel transfers | 1 at a time | 8 at a time |

## Step 1 - Install rclone

In PowerShell:

    winget install Rclone.Rclone

Close and reopen PowerShell, then confirm:

    rclone version

If `winget` is unavailable, download the Windows zip from
<https://rclone.org/downloads/>, extract it, and put `rclone.exe` somewhere on
your PATH.

## Step 2 - Connect Google Drive

    rclone config

Answer the prompts:

- `n` for new remote
- name: **gdrive**
- storage: type `drive`
- `client_id` / `client_secret`: press Enter to skip both
- scope: `1` (full access) - or `2` for read-only, which is safer for a
  backup and means the script can never modify your Drive
- `service_account_file`: press Enter
- advanced config: `n`
- use web browser to authenticate: `y` - a browser opens, sign in to the
  Google account that owns the Drive, click Allow
- configure as Shared Drive: `n` (see "Shared drives" below if you need them)
- `y` to confirm

## Step 3 - Connect OneDrive

Still in `rclone config`:

- `n` for new remote
- name: **onedrive**
- storage: type `onedrive`
- `client_id` / `client_secret`: Enter to skip both
- region: `1` (Microsoft Cloud Global)
- advanced config: `n`
- use web browser: `y` - sign in to the Microsoft account
- pick the account type when asked (`onedrive` for personal, or the listed
  business/SharePoint entry)
- confirm the drive it found, then `y`

Then `q` to quit config.

## Step 4 - Check it works

    rclone lsd gdrive:
    rclone lsd onedrive:

Both should list folders. If they do, you're connected.

## Step 5 - Dry run first

This transfers nothing, it just reports what *would* happen:

    rclone copy "gdrive:" "onedrive:School Google Drive Backup" --dry-run --fast-list --max-depth 2

## Step 6 - Run the backup

Double-click **backup.bat**.

Leave it running. It shows live progress: files done, bytes transferred,
current rate, and ETA. Logs land in `rclone\logs\`.

## Answering "is it stuck?"

The `--progress` display refreshes continuously with byte-level movement, so
if numbers are changing it is working. The log also writes a one-line stats
summary every 30 seconds, so you can check progress after the fact:

    Get-Content rclone\logs\backup-*.log -Wait -Tail 5

Note: a click inside a Windows console window activates QuickEdit and
*genuinely suspends the process* until you press Enter. If output freezes,
click the window and press Enter before assuming anything is wrong.

## Stopping and resuming

Ctrl-C stops it. Nothing is deleted and nothing is corrupted - partial files
are discarded, not left behind. Run `backup.bat` again and it skips everything
already transferred and picks up where it left off.

## Re-running later

Just run `backup.bat` again. It compares both sides and transfers only what is
new or changed. A no-change run over 64k files takes a few minutes.

`copy` never deletes anything on the OneDrive side, so files you remove from
Google Drive stay in the backup. That is deliberate for a backup. (`rclone
sync` would mirror deletions - don't use it unless that's what you want.)

## Shared drives

`gdrive:` covers My Drive only. For Shared drives, add a second remote:

    rclone config

Same as Step 2, but answer `y` to "configure as Shared Drive" and pick the
drive from the list. Name it e.g. `gshared`, then add a line to `backup.bat`:

    rclone copy "gshared:" "onedrive:School Google Drive Backup - Shared" ...

## If something goes wrong

Find the failures:

    findstr /C:"ERROR" rclone\logs\backup-20260817-213448.log

- **`429` / `rate limit` / `userRateLimitExceeded`** - Google is throttling.
  Add `--tpslimit 10` to the command in `backup.bat`, or lower `--transfers 8`
  to `--transfers 4`.
- **`quotaExceeded`** - a Drive download quota was hit; wait 24 hours.
- **`cannotDownloadAbusiveFile`** - already handled by
  `--drive-acknowledge-abuse` in the batch file.
- **`quota` on the OneDrive side** - the OneDrive account is full. Check how
  much you're about to move first: `rclone size gdrive: --fast-list`
- **Path too long for OneDrive** - OneDrive rejects full paths over ~400
  characters. Shorten the destination folder name, or move the offending
  folder deeper-nested files.
