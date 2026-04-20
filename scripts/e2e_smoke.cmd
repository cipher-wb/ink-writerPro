@echo off
REM e2e_smoke.cmd — Windows 双击/CMD 入口，转发到 PowerShell 版本
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0e2e_smoke.ps1" %*
exit /b %ERRORLEVEL%
