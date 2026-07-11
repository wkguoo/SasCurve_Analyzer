@echo off
setlocal EnableExtensions
title SasCurve Analyzer

set "APP_DIR=%~dp0"
if not exist "%APP_DIR%main.py" (
    echo Cannot find SasCurve_Analyzer project next to this launcher.
    echo Expected main.py beside:
    echo   %APP_DIR%
    echo Place this bat file in the project root.
    pause
    exit /b 1
)

cd /d "%APP_DIR%"

set "PYTHON_CMD=python"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if /I "%~1"=="--check" (
    echo SasCurve_Analyzer launcher check OK.
    echo Project folder: %APP_DIR%
    echo Python command: %PYTHON_CMD%
    exit /b 0
)

%PYTHON_CMD% -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo PySide6 is required. Install with: %PYTHON_CMD% -m pip install -r requirements.txt
    pause
    exit /b 1
)

%PYTHON_CMD% main.py
if errorlevel 1 (
    echo SasCurve_Analyzer exited with an error.
    pause
    exit /b 1
)

