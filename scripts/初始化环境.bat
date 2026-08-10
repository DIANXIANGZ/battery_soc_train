@echo off
setlocal
cd /d "%~dp0.."
set "PROJECT_ROOT=%CD%"
set "RUNTIME_PYTHON=%PROJECT_ROOT%\..\..\work\soc_venv\Scripts\python.exe"

if not exist "%RUNTIME_PYTHON%" (
  py -3.12 -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    py -3.12 -m venv "%PROJECT_ROOT%\..\..\work\soc_venv" || goto :failed
  ) else (
    echo Python 3.12 was not found. Install Python 3.12, then run this file again.
    pause
    exit /b 1
  )
)

"%RUNTIME_PYTHON%" -m pip install --upgrade pip || goto :failed
"%RUNTIME_PYTHON%" -m pip install -r requirements.txt || goto :failed
"%RUNTIME_PYTHON%" -c "import torch, numpy, openpyxl, PIL; print('Environment ready')" || goto :failed

echo Initialization completed. You can now double-click 启动训练平台.bat.
pause
exit /b 0

:failed
echo Initialization failed. Read the message above.
pause
exit /b 1
