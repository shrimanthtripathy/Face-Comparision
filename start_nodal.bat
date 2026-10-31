@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe goto nosetup
.venv\Scripts\python.exe launcher.py
if errorlevel 1 pause
exit /b 0
:nosetup
echo Please double-click setup_windows.bat first.
pause
