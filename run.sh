#!/bin/bash

# Function to display help message
show_help() {
    echo "Internet Archive Downloader"
    echo "Usage: ./run.sh [options]"
    echo ""
    echo "Options:"
    echo "  -d, --docker     Run using Docker (requires Docker and docker-compose)"
    echo "  -l, --local      Run locally (default)"
    echo "  -o, --output     Specify custom download directory (default: ./downloads)"
    echo "  -h, --help       Show this help message"
    echo ""
}

# Default to local mode
RUN_MODE="local"
# Default download directory
DOWNLOAD_DIR="./downloads"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--docker)
            RUN_MODE="docker"
            shift
            ;;
        -l|--local)
            RUN_MODE="local"
            shift
            ;;
        -o|--output)
            DOWNLOAD_DIR="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

if [ "$RUN_MODE" = "docker" ]; then
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        echo "Docker is not installed. Please install Docker to use this option."
        exit 1
    fi
    
    # Check if docker-compose is installed
    if ! command -v docker-compose &> /dev/null; then
        echo "docker-compose is not installed. Please install docker-compose to use this option."
        exit 1
    fi
    
    echo "Starting Internet Archive Downloader using Docker..."
    echo "Downloads will be saved to the path configured in docker-compose.yml"
    docker-compose up -d
    echo "Services started. Access the web interface at http://localhost:9123/"
    
else
    # Local mode
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
    mkdir -p "$DOWNLOAD_DIR" ia_downloader_logs/logs ia_downloader_logs/cache

    # Run the application
    echo "Starting Internet Archive Downloader web interface..."
    echo "Downloads will be saved to: $DOWNLOAD_DIR"
    echo "Open your browser and navigate to http://127.0.0.1:9123/"
    python app.py --download-dir "$DOWNLOAD_DIR"
fi 