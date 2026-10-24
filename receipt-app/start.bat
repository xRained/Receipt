@echo off
setlocal
cd /d "%~dp0"
set "RECEIPT_PYTHON=python"
python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 goto python_ready
set "RECEIPT_PYTHON=py -3"
py -3 -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 goto python_ready
echo Python 3.10 or newer is required. Install Python, then run start.bat again.
pause
exit /b 1

:python_ready
%RECEIPT_PYTHON% -c "import flask, openpyxl, PIL" >nul 2>&1
if not errorlevel 1 goto launch
echo Installing required packages...
%RECEIPT_PYTHON% -m pip install -r requirements.txt
if errorlevel 1 goto failed

:launch
%RECEIPT_PYTHON% launcher.py
if errorlevel 1 goto failed
exit /b 0

:failed
echo Startup failed. Check the message above and data\server-error.log.
pause
exit /b 1
