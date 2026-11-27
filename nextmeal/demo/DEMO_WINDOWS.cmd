@echo off
setlocal
cd /d "%~dp0.."
if not exist "backend\.venv\Scripts\python.exe" (
  py -3.12 -m venv backend\.venv
  if errorlevel 1 goto failed
  "backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
  if errorlevel 1 goto failed
)
"backend\.venv\Scripts\python.exe" demo\run.py %*
exit /b %ERRORLEVEL%

:failed
echo Python 3.12 and an internet connection are needed for first setup.
pause
exit /b 1
