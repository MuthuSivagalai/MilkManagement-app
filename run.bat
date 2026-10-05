@echo off
title Milk Delivery Management
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    py -m venv .venv
    if errorlevel 1 (
        echo.
        echo Python was not found. Please install Python 3.11 or newer.
        pause
        exit /b 1
    )
)

echo Installing/updating required package...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo Starting Milk Delivery Management...
echo Open the browser page shown by Streamlit.
".venv\Scripts\python.exe" -m streamlit run app.py

pause
