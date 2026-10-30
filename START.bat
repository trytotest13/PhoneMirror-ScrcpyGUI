@echo off
setlocal
cd /d "%~dp0"

rem Probe --version: the Windows Store "python" stub passes `where` but is
rem not a real interpreter when no Store Python is installed.
py --version >nul 2>&1
if not errorlevel 1 (
  py "PhoneMirror.py"
  goto end
)
python --version >nul 2>&1
if not errorlevel 1 (
  python "PhoneMirror.py"
  goto end
)
if exist "D:\AiModelFree\bin\miniforge\python.exe" (
  "D:\AiModelFree\bin\miniforge\python.exe" "PhoneMirror.py"
  goto end
)
echo Python 3 is required for this source build.
pause
:end
endlocal
