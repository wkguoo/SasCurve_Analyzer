@echo off
setlocal
title SasCurve Analyzer

set "APP_DIR=E:\desktop\SasCurve_Analyzer"
if exist "%~dp0main.py" (
    set "APP_DIR=%~dp0"
)

if not exist "%APP_DIR%\main.py" (
    echo Cannot find SasCurve_Analyzer project at:
    echo   %APP_DIR%
    echo.
    echo Move this bat file into the project root, or edit APP_DIR in this file.
    pause
    exit /b 1
)

cd /d "%APP_DIR%"

set "PYTHON_CMD=python"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=py -3"
    )
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python was not found on PATH.
        echo Install Python 3, then run this launcher again.
        pause
        exit /b 1
    )
)

if /I "%PYTHON_CMD%"=="python" (
    python -c "import sys" >nul 2>nul
    if errorlevel 1 (
        echo Python was found on PATH but could not run.
        echo Install or repair Python 3, then run this launcher again.
        pause
        exit /b 1
    )
)

if /I "%~1"=="--check" (
    echo SasCurve_Analyzer launcher check OK.
    echo Project folder: %APP_DIR%
    echo Python command: %PYTHON_CMD%
    exit /b 0
)

%PYTHON_CMD% -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo PySide6 is required to start the GUI.
    echo.
    echo Install dependencies from this project folder with:
    echo   %PYTHON_CMD% -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

%PYTHON_CMD% main.py
if errorlevel 1 (
    echo.
    echo SasCurve_Analyzer exited with an error.
    pause
    exit /b 1
)

endlocal
