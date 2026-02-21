#!/bin/bash
# Stop Nexira
echo "Stopping Nexira..."
pkill -f "python3 main.py" && echo "Stopped." || echo "Process not found."
