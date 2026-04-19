@echo off
REM ink-auto.cmd — Windows 双击/CMD 入口，转发到 PowerShell 版本
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ink-auto.ps1" %*
exit /b %ERRORLEVEL%
