#!/bin/bash
# Nexira Installer
# Installs to /home/localadmin/claude_nexira

INSTALL_DIR="/home/localadmin/claude_nexira"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "======================================"
echo "  Nexira - Ultimate AI System v8.0"
echo "  Installer"
echo "======================================"
echo ""

# Create install dir if different from script location
if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    echo "Copying files to $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    cp -r "$SCRIPT_DIR"/. "$INSTALL_DIR/"
fi

cd "$INSTALL_DIR" || exit 1

# Create required directories
mkdir -p data/databases data/uploads web/static/css web/static/js web/static/images

# Set up Python virtual environment
echo "Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Make scripts executable
chmod +x start.sh stop.sh

echo ""
echo "======================================"
echo "  Installation complete!"
echo ""
echo "  To start Nexira:"
echo "    cd $INSTALL_DIR"
echo "    ./start.sh"
echo ""
echo "  Then open: http://localhost:5000"
echo "======================================"
