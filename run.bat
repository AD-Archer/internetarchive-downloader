@echo off
echo Internet Archive Downloader Setup

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed or not in PATH. Please install Python 3.7 or later.
    pause
    exit /b
)

REM Create virtual environment if it doesn't exist
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if uv is installed, if not install it
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing uv package installer...
    powershell -Command "Invoke-WebRequest -Uri https://astral.sh/uv/install.ps1 -OutFile install-uv.ps1; .\install-uv.ps1"
    REM Add uv to PATH for this session
    set PATH=%USERPROFILE%\.cargo\bin;%PATH%
)

REM Install dependencies using uv
echo Installing dependencies with uv...
uv pip install -r requirements.txt

REM Create necessary directories
if not exist downloads mkdir downloads
if not exist ia_downloader_logs\logs mkdir ia_downloader_logs\logs
if not exist ia_downloader_logs\cache mkdir ia_downloader_logs\cache

REM Run the application
echo Starting Internet Archive Downloader web interface...
echo Open your browser and navigate to http://127.0.0.1:5000/
python app.py 