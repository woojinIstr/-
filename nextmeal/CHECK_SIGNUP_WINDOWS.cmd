@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
  echo 먼저 START_WINDOWS.cmd를 한 번 실행해 주세요.
  pause
  exit /b 1
)
"backend\.venv\Scripts\python.exe" "backend\tools\check_auth_settings.py"
pause
