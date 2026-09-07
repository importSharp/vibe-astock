@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-local.ps1"
set "SCRIPT_EXIT=%ERRORLEVEL%"
if errorlevel 1 (
    echo.
    echo STOP FAILED. Check the error message above.
)
echo.
pause
exit /b %SCRIPT_EXIT%
