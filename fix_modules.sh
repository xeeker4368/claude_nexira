#!/bin/bash

#############################################################################
# QUICK FIX - Module Not Found Error
# Run this if you get: ModuleNotFoundError: No module named 'core.ai_engine'
#############################################################################

echo "🔧 Fixing Python module structure..."
echo ""

# Get to installation directory
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "Current directory: $(pwd)"
echo ""

# Check if src folder exists
if [ ! -d "src" ]; then
    echo "❌ ERROR: src/ folder not found!"
    echo "   You need to copy all project files here."
    exit 1
fi

echo "✓ src/ folder exists"

# Create all __init__.py files
echo "Creating __init__.py files..."

touch src/__init__.py
touch src/core/__init__.py
touch src/services/__init__.py
touch src/intelligence/__init__.py
touch src/evolution/__init__.py
touch src/autonomy/__init__.py
touch src/monitoring/__init__.py
touch src/safety/__init__.py
touch src/database/__init__.py

echo "✓ __init__.py files created"
echo ""

# Verify critical files exist
echo "Checking critical files..."

MISSING_FILES=0

if [ ! -f "src/core/ai_engine.py" ]; then
    echo "❌ MISSING: src/core/ai_engine.py"
    MISSING_FILES=$((MISSING_FILES + 1))
else
    echo "✓ src/core/ai_engine.py exists"
fi

if [ ! -f "src/database/schema.py" ]; then
    echo "❌ MISSING: src/database/schema.py"
    MISSING_FILES=$((MISSING_FILES + 1))
else
    echo "✓ src/database/schema.py exists"
fi

if [ ! -f "main.py" ]; then
    echo "❌ MISSING: main.py"
    MISSING_FILES=$((MISSING_FILES + 1))
else
    echo "✓ main.py exists"
fi

echo ""

if [ $MISSING_FILES -gt 0 ]; then
    echo "❌ ERROR: $MISSING_FILES critical files are missing!"
    echo ""
    echo "You need to copy these files from your source folder:"
    echo "  - src/core/ai_engine.py"
    echo "  - src/database/schema.py"
    echo "  - main.py"
    echo ""
    echo "Either:"
    echo "  1. Run the installer properly: ./idiot_proof_installer.sh"
    echo "  2. Or manually copy all files from source"
    exit 1
fi

# Show directory structure
echo "Directory structure:"
echo ""
tree -L 2 src/ 2>/dev/null || find src/ -maxdepth 2 -type f -name "*.py"
echo ""

echo "✅ Fix complete!"
echo ""
echo "Try starting again:"
echo "  ./start.sh --debug"
echo ""
