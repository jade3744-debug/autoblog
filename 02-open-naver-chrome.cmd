@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\autoblog.ps1" -Mode chrome
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
