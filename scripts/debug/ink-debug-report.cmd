@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ink-debug-report.ps1" %*
exit /b %ERRORLEVEL%
