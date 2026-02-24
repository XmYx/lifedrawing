#!/bin/bash

set -e

APP_NAME="Live Drawing Timer"
PYTHON_VERSION="3.11"
VENV_DIR=".venv"
RUN_FILE="run.command"
MAIN_FILE="main.py"   # <-- change if your file is named differently

echo "========================================"
echo "  $APP_NAME - macOS Installer"
echo "========================================"

# ----------------------------------------
# Check Homebrew
# ----------------------------------------
if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew not found."
    echo "Please install Homebrew first:"
    echo "https://brew.sh/"
    exit 1
fi

echo "Homebrew found."

# ----------------------------------------
# Install Python 3.11 if needed
# ----------------------------------------
if ! brew list python@$PYTHON_VERSION >/dev/null 2>&1; then
    echo "Installing Python $PYTHON_VERSION via Homebrew..."
    brew install python@$PYTHON_VERSION
else
    echo "Python $PYTHON_VERSION already installed."
fi

PYTHON_BIN="$(brew --prefix)/opt/python@$PYTHON_VERSION/bin/python3.11"

if [ ! -f "$PYTHON_BIN" ]; then
    echo "Could not find python3.11 at expected location."
    exit 1
fi

echo "Using Python: $PYTHON_BIN"

# ----------------------------------------
# Create virtual environment
# ----------------------------------------
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists."
fi

# ----------------------------------------
# Activate and install requirements
# ----------------------------------------
echo "Installing requirements..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# ----------------------------------------
# Create run.command
# ----------------------------------------
echo "Creating run.command..."

cat <<EOF > "$RUN_FILE"
#!/bin/bash
cd "\$(dirname "\$0")"
source "$VENV_DIR/bin/activate"
python "$MAIN_FILE"
EOF

chmod +x "$RUN_FILE"

echo "========================================"
echo " Installation Complete"
echo "========================================"
echo ""
echo "To run the app:"
echo "  Double-click: $RUN_FILE"
echo ""
echo "Or from terminal:"
echo "  source $VENV_DIR/bin/activate"
echo "  python $MAIN_FILE"
echo ""
