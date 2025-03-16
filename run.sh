#!/bin/bash

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Please install Python 3.7 or later."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if uv is installed, if not install it
if ! command -v uv &> /dev/null; then
    echo "Installing uv package installer..."
    curl -sSf https://astral.sh/uv/install.sh | sh
    # Add uv to PATH for this session if it's not already there
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Install dependencies using uv
echo "Installing dependencies with uv..."
uv pip install -r requirements.txt

# Create necessary directories
mkdir -p downloads ia_downloader_logs/logs ia_downloader_logs/cache

# Run the application
echo "Starting Internet Archive Downloader web interface..."
echo "Open your browser and navigate to http://127.0.0.1:5000/"
python app.py 