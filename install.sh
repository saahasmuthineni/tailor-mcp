#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
# Strava Run Coach — One-Click Installer (Mac/Linux)
# Usage: curl -sSL https://raw.githubusercontent.com/saahasmuthineni/strava-run-coach/main/install.sh | bash
# ═══════════════════════════════════════════════════════════════

REPO="saahasmuthineni/strava-run-coach"

INSTALL_DIR="$HOME/.biosensor-mcp"
VENV_DIR="$INSTALL_DIR/venv"
SRC_DIR="$INSTALL_DIR/src"

echo "╔══════════════════════════════════════╗"
echo "║  Strava Run Coach — Installer v3.0   ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ─── Check Python ───
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌ Python 3.10+ not found."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  Install: brew install python3"
    else
        echo "  Install: sudo apt install python3 python3-pip python3-venv"
    fi
    exit 1
fi

PY_VERSION=$($PYTHON --version 2>&1)
echo "✓ Python found: $PY_VERSION"

# ─── Backup ───
if [ -d "$INSTALL_DIR" ]; then
    BACKUP="$INSTALL_DIR.backup.$(date +%Y%m%d_%H%M%S)"
    echo "⚙ Backing up existing installation to $BACKUP"
    cp -r "$INSTALL_DIR" "$BACKUP"
fi

mkdir -p "$INSTALL_DIR" "$SRC_DIR" "$INSTALL_DIR/data" "$INSTALL_DIR/logs"

# ─── Download source ───
echo "⬇ Downloading latest source..."
if command -v git &>/dev/null; then
    if [ -d "$SRC_DIR/.git" ]; then
        cd "$SRC_DIR" && git pull --quiet
    else
        rm -rf "$SRC_DIR"
        git clone --quiet "https://github.com/$REPO.git" "$SRC_DIR"
    fi
else
    curl -sSL "https://github.com/$REPO/archive/main.tar.gz" | tar -xz -C "$INSTALL_DIR"
    rm -rf "$SRC_DIR"
    mv "$INSTALL_DIR/strava-run-coach-main" "$SRC_DIR"
fi
echo "✓ Source downloaded"

# ─── Venv + install ───
echo "⚙ Setting up Python environment..."
$PYTHON -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet "$SRC_DIR"
echo "✓ Dependencies installed"

# ─── OAuth ───
TOKEN_FILE="$INSTALL_DIR/tokens.json"
if [ ! -f "$TOKEN_FILE" ]; then
    echo ""
    echo "═══════════════════════════════════════"
    echo "  Strava OAuth Setup"
    echo "═══════════════════════════════════════"
    echo ""
    echo "  1. Go to https://www.strava.com/settings/api"
    echo "  2. Create an app ('localhost' as callback)"
    echo "  3. Note your Client ID and Client Secret"
    echo ""
    "$VENV_DIR/bin/python" -m biosensor_mcp setup
else
    echo "✓ Existing Strava tokens found"
fi

# ─── Claude Desktop ───
echo "⚙ Registering with Claude Desktop..."

if [[ "$OSTYPE" == "darwin"* ]]; then
    CLAUDE_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
else
    CLAUDE_CONFIG="$HOME/.config/Claude/claude_desktop_config.json"
fi

mkdir -p "$(dirname "$CLAUDE_CONFIG")"
VENV_PYTHON="$VENV_DIR/bin/python"

if [ -f "$CLAUDE_CONFIG" ]; then
    cp "$CLAUDE_CONFIG" "$CLAUDE_CONFIG.backup.$(date +%Y%m%d_%H%M%S)"
    $PYTHON -c "
import json, sys
config_path, venv_python, install_dir = sys.argv[1], sys.argv[2], sys.argv[3]
with open(config_path) as f:
    config = json.load(f)
config.setdefault('mcpServers', {})
config['mcpServers']['biosensor-mcp'] = {
    'command': venv_python,
    'args': ['-m', 'biosensor_mcp', 'serve'],
    'env': {'BIOSENSOR_CONFIG_DIR': install_dir, 'BIOSENSOR_DATA_DIR': install_dir + '/data'}
}
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
" "$CLAUDE_CONFIG" "$VENV_PYTHON" "$INSTALL_DIR"
    echo "✓ Claude Desktop config updated"
else
    cat > "$CLAUDE_CONFIG" << JSONEOF
{
  "mcpServers": {
    "biosensor-mcp": {
      "command": "$VENV_PYTHON",
      "args": ["-m", "biosensor_mcp", "serve"],
      "env": {
        "BIOSENSOR_CONFIG_DIR": "$INSTALL_DIR",
        "BIOSENSOR_DATA_DIR": "$INSTALL_DIR/data"
      }
    }
  }
}
JSONEOF
    echo "✓ Claude Desktop config created"
fi

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   ✅ Installation Complete!           ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Restart Claude Desktop"
echo "  2. Ask Claude: 'Sync my Strava data and analyze my last run'"
echo ""
