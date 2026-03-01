#!/bin/bash
# Start Nexira - Nexira v12
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

# Set PYTHONPATH explicitly so src/ is always on the path
export PYTHONPATH="$INSTALL_DIR/src:$PYTHONPATH"

# ── Logging level ──────────────────────────────────────────────
# Default: INFO (chat activity, personality changes, background tasks)
# --debug   : Full debug output + Flask reloader
# --quiet   : Startup messages only, suppress request logs
# --log     : Also write everything to logs/nexira.log

LOG_LEVEL="INFO"
WRITE_LOG=0

for arg in "$@"; do
    case $arg in
        --debug)
            export FLASK_DEBUG=1
            LOG_LEVEL="DEBUG"
            echo "🐛 Debug mode enabled"
            ;;
        --quiet)
            LOG_LEVEL="WARNING"
            echo "🔇 Quiet mode — suppressing request logs"
            ;;
        --log)
            WRITE_LOG=1
            mkdir -p "$INSTALL_DIR/logs"
            echo "📄 Logging to logs/nexira.log"
            ;;
    esac
done

export NEXIRA_LOG_LEVEL="$LOG_LEVEL"

# ── Run ────────────────────────────────────────────────────────
if [ "$WRITE_LOG" == "1" ]; then
    LOG_FILE="$INSTALL_DIR/logs/nexira_$(date +%Y%m%d_%H%M%S).log"
    echo "📄 Log file: $LOG_FILE"
    python3 main.py 2>&1 | tee "$LOG_FILE"
else
    python3 main.py
fi
