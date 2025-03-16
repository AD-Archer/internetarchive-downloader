@echo off
echo Internet Archive Downloader Update

REM Check if virtual environment exists
if not exist venv (
    echo Virtual environment not found. Please run run.bat first.
    pause
    exit /b
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

REM Update dependencies using uv
echo Updating dependencies with uv...
uv pip install --upgrade -r requirements.txt

echo Update complete. Run run.bat to start the application.
pause 