@echo off
echo Internet Archive Downloader Setup

REM Parse command line arguments
set RUN_MODE=local

if "%~1"=="" goto :continue
if /i "%~1"=="-d" set RUN_MODE=docker
if /i "%~1"=="--docker" set RUN_MODE=docker
if /i "%~1"=="-l" set RUN_MODE=local
if /i "%~1"=="--local" set RUN_MODE=local
if /i "%~1"=="-h" goto :help
if /i "%~1"=="--help" goto :help
if not "%~1"=="" echo Unknown option: %~1 & goto :help

:continue
if "%RUN_MODE%"=="docker" goto :docker_mode
goto :local_mode

:help
echo Internet Archive Downloader
echo Usage: run.bat [options]
echo.
echo Options:
echo   -d, --docker     Run using Docker (requires Docker and docker-compose)
echo   -l, --local      Run locally (default)
echo   -h, --help       Show this help message
echo.
exit /b

:docker_mode
REM Check if Docker is installed
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Docker is not installed. Please install Docker to use this option.
    pause
    exit /b
)

REM Check if docker-compose is installed
docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    echo docker-compose is not installed. Please install docker-compose to use this option.
    pause
    exit /b
)

echo Starting Internet Archive Downloader using Docker...
echo Downloads will be saved to the path configured in docker-compose.yml
docker-compose up -d
echo Services started. Access the web interface at http://localhost:9123/
goto :eof

:local_mode
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
echo Downloads will be saved to the 'downloads' directory in the current folder
echo Open your browser and navigate to http://127.0.0.1:5000/
python app.py 