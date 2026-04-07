@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found in PATH.
  pause
  exit /b 1
)

python app.py
if errorlevel 1 (
  echo.
  echo [INFO] If this is the first run, install dependencies with:
  echo python -m pip install -r requirements.txt
  pause
)
