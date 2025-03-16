#!/bin/bash

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Please run ./run.sh first."
    exit 1
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

# Update dependencies using uv
echo "Updating dependencies with uv..."
uv pip install --upgrade -r requirements.txt

echo "Update complete. Run ./run.sh to start the application." 