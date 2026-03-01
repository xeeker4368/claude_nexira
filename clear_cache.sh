#!/bin/bash
echo "Clearing Python cache..."
find "$(dirname "$0")" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find "$(dirname "$0")" -name "*.pyc" -delete 2>/dev/null
echo "✓ Cache cleared"
