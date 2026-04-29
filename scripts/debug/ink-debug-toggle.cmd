@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ink-debug-toggle.ps1" %*
exit /b %ERRORLEVEL%
