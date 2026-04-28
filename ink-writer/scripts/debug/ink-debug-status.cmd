@echo off
setlocal
set "SHIM_DIR=%~dp0..\_pyshim"
if "%INK_PROJECT_ROOT%"=="" (set "PROJECT=%CD%") else (set "PROJECT=%INK_PROJECT_ROOT%")
python3 -c "import ink_writer.debug.cli" >/dev/null 2>&1
if %ERRORLEVEL%==0 (
    python3 -m ink_writer.debug.cli --project-root "%PROJECT%" status %*
) else (
    set "PYTHONPATH=%SHIM_DIR%;%PYTHONPATH%"
    python3 -m ink_writer.debug.cli --project-root "%PROJECT%" status %*
)
set RC=%ERRORLEVEL%
endlocal & exit /b %RC%
