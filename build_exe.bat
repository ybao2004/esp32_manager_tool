@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ============================================================================
echo   CONG CU DONG GOI ESP32 MANAGER TOOL v1.10 THANH FILE .EXE DOC LAP
echo ============================================================================
echo.

cd /d "%~dp0"

:: Tu dong tim trinh thong dich Python (uu tien py launcher tren Windows)
set "PY_CMD="
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 -c "import sys" >nul 2>nul
    if !ERRORLEVEL! EQU 0 set "PY_CMD=py -3"
)
if "%PY_CMD%"=="" (
    where python >nul 2>nul
    if !ERRORLEVEL! EQU 0 (
        python -c "import sys" >nul 2>nul
        if !ERRORLEVEL! EQU 0 set "PY_CMD=python"
    )
)

if "%PY_CMD%"=="" (
    echo [LOI] Khong tim thay Python tren he thong! Vui long cai dat Python 3.10+.
    if "%1"=="" pause
    exit /b 1
)

echo [1/4] Kiem tra thu vien PyInstaller...
%PY_CMD% -c "import PyInstaller" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo       Dang cai dat PyInstaller...
    %PY_CMD% -m pip install pyinstaller
    if !ERRORLEVEL! NEQ 0 (
        echo [LOI] Khong the cai dat PyInstaller!
        if "%1"=="" pause
        exit /b 1
    )
)

echo [2/4] Don dep thu muc build tam cu...
if exist "build" rmdir /s /q "build"
if exist "dist\Esp32_manager_tool.exe" del /f /q "dist\Esp32_manager_tool.exe"

echo [3/4] Dang tao banner Splash va dong goi file .exe (One-File GUI)...
%PY_CMD% -c "from PyQt6.QtWidgets import QApplication; app=QApplication([]); from modules.ui.splash import generate_pyi_splash_image; generate_pyi_splash_image('icons/splash_v110.png')" >nul 2>&1
%PY_CMD% -m PyInstaller --noconfirm --clean esp32_manager_tool.spec
if %ERRORLEVEL% NEQ 0 (
    echo [LOI] Qua trinh dong goi PyInstaller that bai!
    if "%1"=="" pause
    exit /b 1
)

echo [4/4] Don dep thu muc tam sau khi dong goi...
if exist "build" rmdir /s /q "build"

if exist "dist\Esp32_manager_tool.exe" (
    echo.
    echo ============================================================================
    echo   [THANH CONG] Da tao file thuc thi tai: dist\Esp32_manager_tool.exe
    echo ============================================================================
) else (
    echo [LOI] Khong tim thay file dist\Esp32_manager_tool.exe sau khi build!
    if "%1"=="" pause
    exit /b 1
)

if "%1"=="" pause
exit /b 0
