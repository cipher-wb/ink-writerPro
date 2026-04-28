@echo off
REM interactive_bootstrap.cmd — Windows double-click launcher for the .ps1
SET SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%interactive_bootstrap.ps1" %*
exit /b %ERRORLEVEL%
