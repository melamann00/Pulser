@echo off
setlocal

echo Installing/upgrading build dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo pip install failed - make sure this "pip" is your Windows Python's pip,
    echo not one from WSL/Linux, or the build below will produce a Linux binary.
    pause
    exit /b 1
)

echo.
echo Building HealthTracker.exe ...
pyinstaller --noconfirm --onefile --windowed --name HealthTracker --collect-all customtkinter app.py
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
