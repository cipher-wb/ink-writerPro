@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ink-debug-status.ps1" %*
exit /b %ERRORLEVEL%
