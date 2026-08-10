@echo off
setlocal
cd /d "%~dp0.."

if not exist "%~dp0..\..\work\soc_venv\Scripts\python.exe" (
  echo Environment is not ready. Please double-click 初始化环境.bat first.
  pause
  exit /b 1
)

"%~dp0..\..\work\soc_venv\Scripts\python.exe" -m src.desktop.app
