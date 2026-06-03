#!/bin/bash
INSTALL_DIR="$HOME/.deepresearch"
REPO_DIR="$INSTALL_DIR/deep-research"

echo "--- Setting up DeepResearch Pipeline ---"

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR" || exit

if [ ! -d "$REPO_DIR" ]; then
    echo "Cloning repository..."
    git clone https://github.com/rAdvirtua/deep-research.git "$REPO_DIR"
else
    echo "Updating repository..."
    cd "$REPO_DIR" && git pull && cd "$INSTALL_DIR"
fi

echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "Installing requirements..."
python3 -m pip install --upgrade pip
if [ -f "$REPO_DIR/deep-research/requirements.txt" ]; then
    pip install -r "$REPO_DIR/deep-research/requirements.txt"
elif [ -f "$REPO_DIR/requirements.txt" ]; then
    pip install -r "$REPO_DIR/requirements.txt"
else
    echo "Warning: requirements.txt not found!"
fi

# Add command locally
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"

# Check if orchestrator is in root or subfolder
SCRIPT_PATH="$REPO_DIR/orchestrator.py"
if [ ! -f "$SCRIPT_PATH" ]; then
    SCRIPT_PATH="$REPO_DIR/deep-research/orchestrator.py"
fi

cat <<EOF > "$LOCAL_BIN/deep-research"
#!/bin/bash
source "$INSTALL_DIR/venv/bin/activate"
cd "$REPO_DIR" && python3 "$SCRIPT_PATH" "\$@"
EOF
chmod +x "$LOCAL_BIN/deep-research"

# Verify path
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    echo ""
    echo "NOTE: $LOCAL_BIN is not in your PATH."
    echo "Add 'export PATH="\$HOME/.local/bin:\$PATH"' to your ~/.bashrc or ~/.zshrc."
fi

echo "--- Setup complete! ---"
echo "You can now run 'deep-research' from anywhere."
