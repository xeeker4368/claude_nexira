#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  Nexira — Ultimate AI System v8.0
#  Bulletproof Installer
#  Created by Xeeker & Claude — February 2026
#
#  What this does:
#    1. Checks your system for Python 3.8+, pip, and Ollama
#    2. Creates a Python virtual environment
#    3. Installs all dependencies
#    4. Builds the correct directory structure
#    5. Creates a fresh config if none exists
#    6. Pulls the default Ollama model if needed
#    7. Makes start/stop scripts executable
#    8. Verifies everything works
#
#  Usage:
#    chmod +x install.sh
#    ./install.sh
#
#  Or if you want to install to a custom directory:
#    ./install.sh /path/to/install
# ═══════════════════════════════════════════════════════════════════

set -e  # Exit on any error

# ── Colors ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
info() { echo -e "  ${CYAN}ℹ${NC} $1"; }

# ── Banner ────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  ✦ Nexira — Ultimate AI System v8.0${NC}"
echo -e "${BOLD}    Installer${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo ""

# ── Determine install directory ───────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "$1" ]; then
    INSTALL_DIR="$(realpath "$1" 2>/dev/null || echo "$1")"
else
    INSTALL_DIR="$SCRIPT_DIR"
fi

echo -e "${BOLD}Install directory:${NC} $INSTALL_DIR"
echo ""

# If running from a different location, copy files first
if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    info "Copying files to $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    rsync -a --exclude='venv' --exclude='.venv' --exclude='__pycache__' \
          --exclude='*.pyc' --exclude='.git' \
          "$SCRIPT_DIR"/ "$INSTALL_DIR"/
    ok "Files copied"
fi

cd "$INSTALL_DIR" || { fail "Cannot access $INSTALL_DIR"; exit 1; }

# ══════════════════════════════════════════════════════════════════
#  STEP 1: System Requirements Check
# ══════════════════════════════════════════════════════════════════
echo -e "\n${BOLD}[1/7] Checking system requirements...${NC}"

ERRORS=0

# ── Python 3.8+ ───────────────────────────────────────────────────
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY_VERSION=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
        PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
        if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 8 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -n "$PYTHON_CMD" ]; then
    ok "Python: $($PYTHON_CMD --version)"
else
    fail "Python 3.8+ is required but not found"
    echo ""
    echo "  Install Python:"
    echo "    Ubuntu/Debian:  sudo apt install python3 python3-pip python3-venv"
    echo "    Fedora:         sudo dnf install python3 python3-pip"
    echo "    macOS:          brew install python3"
    echo "    Arch:           sudo pacman -S python python-pip"
    ERRORS=$((ERRORS + 1))
fi

# ── pip ───────────────────────────────────────────────────────────
if [ -n "$PYTHON_CMD" ]; then
    if $PYTHON_CMD -m pip --version &>/dev/null; then
        ok "pip: $($PYTHON_CMD -m pip --version 2>&1 | head -1)"
    else
        fail "pip not found"
        echo "    Install: $PYTHON_CMD -m ensurepip --upgrade"
        ERRORS=$((ERRORS + 1))
    fi
fi

# ── venv module ───────────────────────────────────────────────────
if [ -n "$PYTHON_CMD" ]; then
    if $PYTHON_CMD -c "import venv" &>/dev/null; then
        ok "venv module available"
    else
        fail "Python venv module not installed"
        echo "    Install: sudo apt install python3-venv"
        ERRORS=$((ERRORS + 1))
    fi
fi

# ── Ollama ────────────────────────────────────────────────────────
if command -v ollama &>/dev/null; then
    ok "Ollama: $(ollama --version 2>&1 | head -1)"
    OLLAMA_FOUND=true
else
    warn "Ollama not found — Nexira needs it for AI inference"
    echo ""
    echo "    Install Ollama:"
    echo "      Linux/macOS:  curl -fsSL https://ollama.ai/install.sh | sh"
    echo "      Or visit:     https://ollama.ai/download"
    echo ""
    OLLAMA_FOUND=false
fi

# ── Check if Ollama is running ────────────────────────────────────
if [ "$OLLAMA_FOUND" = true ]; then
    if curl -s http://localhost:11434/api/version &>/dev/null; then
        ok "Ollama server is running"
        OLLAMA_RUNNING=true
    else
        warn "Ollama is installed but not running"
        echo "    Start it:  ollama serve  (in another terminal)"
        OLLAMA_RUNNING=false
    fi
fi

# ── Bail out on critical errors ───────────────────────────────────
if [ $ERRORS -gt 0 ]; then
    echo ""
    fail "Fix the $ERRORS error(s) above and re-run this installer."
    exit 1
fi

# ══════════════════════════════════════════════════════════════════
#  STEP 2: Create Directory Structure
# ══════════════════════════════════════════════════════════════════
echo -e "\n${BOLD}[2/7] Creating directory structure...${NC}"

DIRS=(
    "config"
    "data/databases"
    "data/uploads"
    "data/backups"
    "data/images/generated"
    "data/images/styled"
    "web/templates"
    "web/static/css"
    "web/static/js"
    "web/static/images"
    "src/core"
    "src/services"
    "src/database"
    "docs"
)

for dir in "${DIRS[@]}"; do
    mkdir -p "$dir"
done
ok "All directories created"

# ── Ensure __init__.py files exist ────────────────────────────────
for init in src/__init__.py src/core/__init__.py src/services/__init__.py src/database/__init__.py; do
    if [ ! -f "$init" ]; then
        touch "$init"
    fi
done
ok "__init__.py files present"

# ══════════════════════════════════════════════════════════════════
#  STEP 3: Create Fresh Config (if none exists)
# ══════════════════════════════════════════════════════════════════
echo -e "\n${BOLD}[3/7] Checking configuration...${NC}"

CONFIG_FILE="config/default_config.json"

if [ -f "$CONFIG_FILE" ]; then
    ok "Config file exists — keeping your existing settings"
else
    info "Creating fresh configuration..."
    cat > "$CONFIG_FILE" << 'CONFIGEOF'
{
  "_comment": "Nexira / Ultimate AI System v8.0 — Created by Xeeker & Claude",
  "ai": {
    "model": "llama3.1:8b",
    "ollama_url": "http://localhost:11434",
    "first_launch": true,
    "ai_name": null,
    "ai_version": 1,
    "created_date": null,
    "awaiting_name": true,
    "user_name": ""
  },
  "hardware": {
    "gpu_enabled": true,
    "num_gpu": 1,
    "num_threads": 4,
    "context_window": 4096,
    "target_vram_gb": 7,
    "max_cpu_idle": 30,
    "max_gpu_idle": 70,
    "low_power_mode": false
  },
  "memory": {
    "short_term_messages": 50,
    "auto_cleanup_days": 30,
    "importance_threshold": 0.7,
    "emotional_weight_enabled": true,
    "context_truncation": true
  },
  "personality": {
    "auto_evolution": true,
    "evolution_speed": 0.02,
    "manual_evolution_enabled": true,
    "drift_alert_threshold": 0.3,
    "snapshot_frequency": "daily",
    "allow_emergent_traits": true
  },
  "intelligence": {
    "curiosity_enabled": true,
    "night_consolidation_enabled": true,
    "night_consolidation_time": "02:00",
    "night_consolidation": false
  },
  "autonomy": {
    "autonomous_tasks_enabled": true,
    "code_generation_enabled": true,
    "code_approval_required": true,
    "feature_creation_enabled": true,
    "max_features_per_week": 3,
    "creative_journaling_enabled": true,
    "philosophical_journaling_enabled": true,
    "hypothesis_testing_enabled": true,
    "goal_setting_enabled": true
  },
  "communication": {
    "email": {
      "enabled": false,
      "smtp_server": "",
      "smtp_port": 587,
      "imap_server": "",
      "imap_port": 993,
      "username": "",
      "password": "",
      "monitoring_enabled": false,
      "check_frequency_minutes": 30,
      "priority_keywords": ["urgent", "deadline", "client", "important"],
      "recipient": ""
    }
  },
  "daily_email": {
    "enabled": false,
    "reports": {
      "personality_changes": true,
      "goals_progress": true,
      "news_summary": false,
      "daily_summary": true,
      "tasks_completed": true,
      "learnings_and_insights": true
    },
    "send_time": "20:00",
    "recipient": ""
  },
  "web_interface": {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": false,
    "auto_reload": false
  },
  "safety": {
    "code_scanning_enabled": true,
    "sandbox_testing_available": true,
    "approval_required_for_code": true,
    "max_code_size_kb": 500
  },
  "monitoring": {
    "health_check_interval_seconds": 30,
    "performance_tracking_enabled": true,
    "quality_analysis_enabled": true,
    "log_level": "INFO"
  },
  "new_features": {
    "explanation_system": true,
    "nightly_backup": true,
    "backup_retention_days": 30,
    "nl_scheduling": true,
    "self_awareness": true,
    "philosophical_journal": true,
    "hypothesis_journal": true,
    "conversation_threading": true,
    "emotional_memory_weighting": true
  },
  "experimental": {
    "dream_mode": false,
    "multi_context": false,
    "voice_input": false
  },
  "moltbook": {
    "enabled": false,
    "api_key": "",
    "agent_name": "",
    "claim_url": "",
    "claimed": false,
    "auto_post_diary": false
  }
}
CONFIGEOF
    ok "Fresh config created — AI will choose its own name on first launch"
fi

# ══════════════════════════════════════════════════════════════════
#  STEP 4: Create Python Virtual Environment
# ══════════════════════════════════════════════════════════════════
echo -e "\n${BOLD}[4/7] Setting up Python virtual environment...${NC}"

VENV_DIR="venv"

if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/activate" ]; then
    ok "Virtual environment already exists"
else
    info "Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    ok "Virtual environment created"
fi

# Activate it
source "$VENV_DIR/bin/activate"
ok "Virtual environment activated"

# Upgrade pip first (silently)
pip install --upgrade pip --quiet 2>/dev/null
ok "pip upgraded"

# ══════════════════════════════════════════════════════════════════
#  STEP 5: Install Python Dependencies
# ══════════════════════════════════════════════════════════════════
echo -e "\n${BOLD}[5/7] Installing Python dependencies...${NC}"

# Core requirements (must succeed)
CORE_PACKAGES=(
    "Flask==3.0.0"
    "Flask-CORS==4.0.0"
    "Flask-SocketIO==5.3.6"
    "simple-websocket>=0.9.0"
    "ollama>=0.1.6"
    "requests>=2.31.0"
    "python-dateutil>=2.8.2"
    "pytz>=2023.3"
    "python-dotenv>=1.0.0"
    "croniter>=2.0.1"
    "psutil>=5.9.6"
)

# Optional packages (install but don't fail if missing)
OPTIONAL_PACKAGES=(
    "cryptography>=41.0.0"
    "PyPDF2>=3.0.1"
    "python-docx>=1.1.0"
    "Pillow>=10.1.0"
    "pytesseract>=0.3.10"
    "imapclient>=2.3.1"
)

# GPU/ML packages (only install if CUDA is available)
GPU_PACKAGES=(
    "torch"
    "diffusers"
    "transformers"
)

info "Installing core packages..."
CORE_FAILED=0
for pkg in "${CORE_PACKAGES[@]}"; do
    pkg_name=$(echo "$pkg" | cut -d'=' -f1 | cut -d'>' -f1)
    if pip install "$pkg" --quiet 2>/dev/null; then
        ok "$pkg_name"
    else
        fail "$pkg_name — REQUIRED"
        CORE_FAILED=$((CORE_FAILED + 1))
    fi
done

if [ $CORE_FAILED -gt 0 ]; then
    echo ""
    fail "$CORE_FAILED core package(s) failed to install. Nexira cannot run."
    echo "    Try: pip install -r requirements.txt"
    exit 1
fi

echo ""
info "Installing optional packages..."
for pkg in "${OPTIONAL_PACKAGES[@]}"; do
    pkg_name=$(echo "$pkg" | cut -d'=' -f1 | cut -d'>' -f1)
    if pip install "$pkg" --quiet 2>/dev/null; then
        ok "$pkg_name"
    else
        warn "$pkg_name — skipped (feature will be disabled)"
    fi
done

# Check for NVIDIA GPU before attempting ML packages
echo ""
HAS_GPU=false
if command -v nvidia-smi &>/dev/null; then
    if nvidia-smi &>/dev/null; then
        HAS_GPU=true
        ok "NVIDIA GPU detected"
    fi
fi

if [ "$HAS_GPU" = true ]; then
    info "Installing GPU/ML packages (this may take a few minutes)..."
    for pkg in "${GPU_PACKAGES[@]}"; do
        if pip install "$pkg" --quiet 2>/dev/null; then
            ok "$pkg"
        else
            warn "$pkg — skipped (image generation will be disabled)"
        fi
    done
else
    # Check for Apple Silicon (MLX)
    if [ "$(uname)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
        info "Apple Silicon detected — GPU packages skipped (use MLX in future)"
    else
        info "No NVIDIA GPU detected — GPU packages skipped"
    fi
    warn "Image generation requires an NVIDIA GPU with CUDA"
fi

# ══════════════════════════════════════════════════════════════════
#  STEP 6: Pull Ollama Model
# ══════════════════════════════════════════════════════════════════
echo -e "\n${BOLD}[6/7] Checking Ollama model...${NC}"

# Read model from config
DEFAULT_MODEL="llama3.1:8b"
if [ -f "$CONFIG_FILE" ]; then
    CONFIGURED_MODEL=$(python3 -c "
import json
with open('$CONFIG_FILE') as f:
    cfg = json.load(f)
print(cfg.get('ai', {}).get('model', '$DEFAULT_MODEL'))
" 2>/dev/null || echo "$DEFAULT_MODEL")
else
    CONFIGURED_MODEL="$DEFAULT_MODEL"
fi

info "Configured model: $CONFIGURED_MODEL"

if [ "$OLLAMA_RUNNING" = true ]; then
    # Check if model is already pulled
    if ollama list 2>/dev/null | grep -q "${CONFIGURED_MODEL%%:*}"; then
        ok "Model '$CONFIGURED_MODEL' is already available"
    else
        info "Pulling model '$CONFIGURED_MODEL' — this may take several minutes..."
        echo "    (Models are typically 4-8 GB)"
        echo ""
        if ollama pull "$CONFIGURED_MODEL"; then
            ok "Model pulled successfully"
        else
            warn "Could not pull model — you can do this manually later:"
            echo "    ollama pull $CONFIGURED_MODEL"
        fi
    fi
elif [ "$OLLAMA_FOUND" = true ]; then
    warn "Ollama is not running — start it first, then pull the model:"
    echo "    ollama serve  (in another terminal)"
    echo "    ollama pull $CONFIGURED_MODEL"
else
    warn "Ollama not installed — install from https://ollama.ai/download"
    echo "    Then: ollama pull $CONFIGURED_MODEL"
fi

# ══════════════════════════════════════════════════════════════════
#  STEP 7: Final Setup & Verification
# ══════════════════════════════════════════════════════════════════
echo -e "\n${BOLD}[7/7] Final setup...${NC}"

# ── Make scripts executable ───────────────────────────────────────
for script in start.sh stop.sh install.sh clear_cache.sh fix_modules.sh; do
    if [ -f "$script" ]; then
        chmod +x "$script"
    fi
done
ok "Scripts made executable"

# ── Generate start.sh if missing ──────────────────────────────────
if [ ! -f "start.sh" ]; then
    cat > start.sh << STARTEOF
#!/bin/bash
# Start Nexira
INSTALL_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
cd "\$INSTALL_DIR" || exit 1

echo "Starting Nexira..."

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "✓ Virtual environment activated"
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "✓ Virtual environment activated"
else
    echo "⚠  No virtual environment found"
fi

export PYTHONPATH="\$INSTALL_DIR/src:\$PYTHONPATH"

python3 main.py
STARTEOF
    chmod +x start.sh
    ok "start.sh created"
fi

# ── Generate stop.sh if missing ──────────────────────────────────
if [ ! -f "stop.sh" ]; then
    cat > stop.sh << 'STOPEOF'
#!/bin/bash
# Stop Nexira
echo "Stopping Nexira..."
pkill -f "python3 main.py" 2>/dev/null && echo "✓ Stopped" || echo "Not running"
STOPEOF
    chmod +x stop.sh
    ok "stop.sh created"
fi

# ── Verify core imports ──────────────────────────────────────────
echo ""
info "Verifying Python imports..."

IMPORT_CHECK=$($PYTHON_CMD -c "
import sys
errors = []
try:
    import flask; print(f'  ✓ Flask {flask.__version__}')
except: errors.append('Flask')
try:
    import flask_cors; print('  ✓ Flask-CORS')
except: errors.append('Flask-CORS')
try:
    import flask_socketio; print('  ✓ Flask-SocketIO')
except: errors.append('Flask-SocketIO')
try:
    import ollama; print('  ✓ ollama')
except: errors.append('ollama')
try:
    import requests; print(f'  ✓ requests {requests.__version__}')
except: errors.append('requests')

# Optional
try:
    from cryptography.fernet import Fernet; print('  ✓ cryptography (encryption)')
except: print('  ⚠ cryptography — encryption disabled')
try:
    import PyPDF2; print('  ✓ PyPDF2 (PDF uploads)')
except: print('  ⚠ PyPDF2 — PDF uploads disabled')
try:
    import docx; print('  ✓ python-docx (DOCX uploads)')
except: print('  ⚠ python-docx — DOCX uploads disabled')

if errors:
    print(f'\n  ✗ MISSING CORE: {errors}')
    sys.exit(1)
else:
    print('\n  ✓ All core imports OK')
" 2>&1)
echo "$IMPORT_CHECK"

if [ $? -ne 0 ]; then
    fail "Some core imports failed. Try reinstalling:"
    echo "    source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# ── Initialize database ──────────────────────────────────────────
info "Initializing database..."
$PYTHON_CMD -c "
import sys, os
sys.path.insert(0, os.path.join('$INSTALL_DIR', 'src'))
from database.schema import DatabaseSchema
db = DatabaseSchema(base_dir='$INSTALL_DIR')
db.connect()
db.initialize_schema()
db.initialize_core_personality()
db.close()
print('  ✓ Database ready')
" 2>&1

# ══════════════════════════════════════════════════════════════════
#  Done!
# ══════════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✦ Installation Complete!${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}To start Nexira:${NC}"
echo ""
echo -e "    cd $INSTALL_DIR"
echo -e "    ./start.sh"
echo ""
echo -e "  ${BOLD}Then open:${NC} ${CYAN}http://localhost:5000${NC}"
echo ""

if [ "$OLLAMA_RUNNING" != true ]; then
    echo -e "  ${YELLOW}⚠  Remember to start Ollama first:${NC}"
    echo -e "     ollama serve"
    echo ""
fi

echo -e "  ${BOLD}Quick reference:${NC}"
echo -e "    Start:           ./start.sh"
echo -e "    Stop:            ./stop.sh"
echo -e "    Debug mode:      ./start.sh --debug"
echo -e "    Manual venv:     source venv/bin/activate"
echo -e "    Re-install deps: pip install -r requirements.txt"
echo ""
echo -e "  ${BOLD}Need help?${NC} Check docs/HANDOFF.md for the full project overview."
echo ""
