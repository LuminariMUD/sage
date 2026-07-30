#!/bin/bash
set -e

echo "=== Starting MCP Server ==="
echo "Current user: $(whoami)"
echo "Current directory: $(pwd)"
echo "PATH: $PATH"
echo "PYTHONPATH: $PYTHONPATH"
echo "Python version: $(python --version)"
echo "Python location: $(which python)"

# Check if uvicorn is importable
echo "Checking uvicorn import..."
python -c "import sys; print('Python path:', sys.path)" 2>&1
python -c "import uvicorn; print('Uvicorn version:', uvicorn.__version__)" 2>&1 || {
    echo "ERROR: Failed to import uvicorn"
    echo "Attempting to show installed packages:"
    pip list | grep -i uvicorn || echo "Uvicorn not found in pip list"
    exit 1
}

echo "Starting uvicorn..."
exec python -m uvicorn src.mcp.server:app --host 0.0.0.0 --port 8004
