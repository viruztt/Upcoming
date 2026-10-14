@echo off
rem Removes the Startup shortcut created by install_startup.bat.
setlocal
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Upcoming.lnk"

if exist "%LNK%" (
    del "%LNK%"
    echo Removed - Upcoming will no longer start with Windows.
) else (
    echo No startup shortcut found; nothing to remove.
)
pause
