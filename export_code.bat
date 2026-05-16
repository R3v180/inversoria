@echo off
setlocal

cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

echo Generando codigo_completo.txt...
echo.

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py export_code.py
) else (
    python export_code.py
)

echo.
pause
