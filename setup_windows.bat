@echo off
cd /d "%~dp0"
set PY=
py -3.11 --version >nul 2>nul && set PY=py -3.11
if defined PY goto havepy
python --version 2>nul | findstr /b /c:"Python 3.11" >nul && set PY=python
if defined PY goto havepy
goto nopython
:havepy
if not exist .venv\Scripts\python.exe %PY% -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
echo Setup finished. Double-click start_nodal.bat to run Nodal.
pause
exit /b 0
:nopython
echo Python 3.11 was not found. Install Python 3.11 from python.org and tick "Add python.exe to PATH", then run this file again.
echo Newer Python versions such as 3.12 or 3.13 do not work with the face libraries.
pause
