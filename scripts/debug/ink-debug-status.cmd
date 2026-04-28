@echo off
setlocal
pushd "%~dp0..\.."
python3 -m ink_writer.debug.cli --project-root "%CD%" status %*
set RC=%ERRORLEVEL%
popd
exit /b %RC%
