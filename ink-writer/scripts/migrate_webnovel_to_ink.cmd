@echo off
REM migrate_webnovel_to_ink.cmd — Windows 双击/CMD 入口，转发到 PowerShell 版本
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0migrate_webnovel_to_ink.ps1" %*
exit /b %ERRORLEVEL%
