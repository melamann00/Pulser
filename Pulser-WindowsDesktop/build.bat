@echo off
setlocal

where py >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python's "py" launcher was not found on PATH.
    echo Install Python from https://python.org and make sure both
    echo "Add python.exe to PATH" and "Install launcher for all users"
    echo are checked during setup. Then reopen this terminal and try again.
    pause
    exit /b 1
)

echo Installing/upgrading build dependencies...
py -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo pip install failed - see the messages above.
    pause
    exit /b 1
)

echo.
echo Building HealthTracker.exe ...
py -m PyInstaller --noconfirm --onefile --windowed --name HealthTracker --collect-all customtkinter app.py
REM To use a custom icon, add:  --icon=icon.ico   (must be a real .ico file)

if errorlevel 1 (
    echo.
    echo Build failed - see the messages above.
    pause
    exit /b 1
)

echo.
echo Done. Your exe is at: dist\HealthTracker.exe
pause
