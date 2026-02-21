#!/bin/bash
# Start Nexira - Ultimate AI System v8.0
# Install directory: /home/localadmin/claude_nexira

INSTALL_DIR="/home/localadmin/claude_nexira"
cd "$INSTALL_DIR" || { echo "Error: Cannot find $INSTALL_DIR"; exit 1; }

echo "Starting Nexira..."

# Activate virtual environment - handles both venv and .venv
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "✓ Activated .venv"
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "✓ Activated venv"
else
    echo "⚠  No virtual environment found, using system Python"
fi

# Debug mode flag
if [ "$1" == "--debug" ]; then
    export FLASK_DEBUG=1
    echo "Debug mode enabled"
fi

# Set PYTHONPATH explicitly so src/ is always on the path
export PYTHONPATH="$INSTALL_DIR/src:$PYTHONPATH"

python3 main.py
