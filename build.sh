#!/usr/bin/env bash
set -euo pipefail

# On Crostini, tkinter may need: sudo apt install python3-tk
# Check for it before building
python3 -c "import tkinter" 2>/dev/null || {
    echo "tkinter not found. Installing..."
    sudo apt-get install -y python3-tk
}

echo "Installing build dependencies..."
pip install --quiet pyinstaller zstandard py7zr tkinterdnd2

echo "Building SuprComopressr..."
pyinstaller \
  --onefile \
  --name SuprComopressr \
  --hidden-import zstandard \
  --hidden-import py7zr \
  --hidden-import tkinter \
  --hidden-import tkinter.ttk \
  --hidden-import tkinter.filedialog \
  --hidden-import tkinter.messagebox \
  --hidden-import tkinterdnd2 \
  main.py

echo ""
echo "✅ Done! Executable: dist/SuprComopressr"
echo "   Run with: ./dist/SuprComopressr"
