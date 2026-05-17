@echo off
setlocal
cd /d "%~dp0"

echo Building InversorIA Launcher...
python -m PyInstaller launcher.spec

if errorlevel 1 (
    echo.
    echo Build failed. Make sure dependencies are installed:
    echo pip install -r requirements.txt
    exit /b 1
)

copy /Y "dist\InversorIA.exe" "InversorIA.exe" >nul

echo.
echo Done:
echo - InversorIA.exe
echo - dist\InversorIA.exe
endlocal
