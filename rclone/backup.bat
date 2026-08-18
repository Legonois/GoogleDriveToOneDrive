@echo off
REM ===========================================================================
REM  Google Drive -> OneDrive backup, via rclone.
REM
REM  Runs cloud-to-cloud: it does NOT read the G:\ drive and does NOT write
REM  into the OneDrive sync folder, so neither Windows filter driver is in the
REM  path. That is what was causing WinError 1450 and the multi-minute stalls.
REM
REM  Safe to re-run. It only transfers files that are new or changed, so an
REM  interrupted run resumes simply by starting it again.
REM
REM  Before first use: run setup once (see SETUP.md) so that the remotes
REM  "gdrive" and "onedrive" exist.
REM ===========================================================================

setlocal

REM --- Edit this if you want the backup somewhere else in OneDrive ----------
set DEST=onedrive:School Google Drive Backup

set LOGDIR=%~dp0logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
REM wmic is removed in recent Windows 11 builds, so use PowerShell for the stamp
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set STAMP=%%I
set LOG=%LOGDIR%\backup-%STAMP%.log

echo.
echo  Google Drive  --^>  %DEST%
echo  Log: %LOG%
echo.
echo  Press Ctrl-C at any time. Nothing is deleted; re-run to resume.
echo.

rclone copy "gdrive:" "%DEST%" ^
  --create-empty-src-dirs ^
  --drive-export-formats docx,xlsx,pptx,svg ^
  --drive-acknowledge-abuse ^
  --drive-skip-shortcuts ^
  --fast-list ^
  --transfers 8 ^
  --checkers 16 ^
  --retries 5 ^
  --low-level-retries 20 ^
  --progress ^
  --stats 30s ^
  --stats-one-line ^
  --log-file "%LOG%" ^
  --log-level INFO ^
  --exclude "~$*" ^
  --exclude "*.tmp" ^
  --exclude "~WRL*.tmp" ^
  --exclude "desktop.ini" ^
  --exclude ".DS_Store"

set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (
  echo  DONE - everything copied successfully.
) else (
  echo  Finished with errors ^(exit code %RC%^).
  echo  Search the log for lines containing ERROR:
  echo     findstr /C:"ERROR" "%LOG%"
  echo  Re-running this file will retry only what did not make it.
)
echo.
pause
endlocal
