@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\autoblog.ps1" -Mode collect
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
