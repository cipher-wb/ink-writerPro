@echo off
REM env-setup.cmd — Windows 双击/CMD 入口，转发到 PowerShell 版本
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0env-setup.ps1" %*
exit /b %ERRORLEVEL%
