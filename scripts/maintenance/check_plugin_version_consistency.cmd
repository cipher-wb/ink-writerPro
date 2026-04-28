@echo off
REM check_plugin_version_consistency.cmd — Windows 双击/CMD 入口，转发到 PowerShell 版本
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_plugin_version_consistency.ps1" %*
exit /b %ERRORLEVEL%
