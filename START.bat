@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
  py "PhoneMirror.py"
  goto end
)
where python >nul 2>&1
if %errorlevel%==0 (
  python "PhoneMirror.py"
  goto end
)
echo Python 3 is required for this source build.
pause
:end
endlocal
