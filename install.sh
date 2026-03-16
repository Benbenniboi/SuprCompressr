#!/usr/bin/env bash
# Installs SuprCompressr into the Linux app launcher

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "SuprCompressr Installer"
echo "========================"
echo ""

# Allow passing mode as argument (used by main.py --install gui/cli)
if [[ "$1" == "gui" ]]; then
    MODE="gui"
elif [[ "$1" == "cli" ]]; then
    MODE="cli"
else
    echo "Install mode:"
    echo "  1. GUI  — opens the graphical window"
    echo "  2. CLI  — opens a terminal with the text interface"
    echo ""
    read -rp "Choose (1/2, default 1): " choice
    case "$choice" in
        2) MODE="cli" ;;
        *) MODE="gui" ;;
    esac
fi

echo ""
echo "Installing in $MODE mode..."

# Directories
mkdir -p ~/.local/share/applications
mkdir -p ~/.local/share/icons/hicolor/scalable/apps

# Icon
cp "$SCRIPT_DIR/suprcompressr.svg" \
   ~/.local/share/icons/hicolor/scalable/apps/suprcompressr.svg

# Build desktop entry based on mode
if [[ "$MODE" == "cli" ]]; then
    cat > ~/.local/share/applications/suprcompressr.desktop << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=SuprCompressr
Comment=Extreme file compression for Linux (CLI)
Exec=bash -c "python3 $SCRIPT_DIR/main.py --cli; echo 'Press Enter to close...'; read"
Icon=suprcompressr
Terminal=true
Categories=Utility;Archiving;
Keywords=compress;zip;archive;supr;gz;7z;
EOF
else
    cat > ~/.local/share/applications/suprcompressr.desktop << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=SuprCompressr
Comment=Extreme file compression for Linux
Exec=python3 $SCRIPT_DIR/main.py --gui
Icon=suprcompressr
Terminal=false
Categories=Utility;Archiving;
Keywords=compress;zip;archive;supr;gz;7z;
EOF
fi

# Refresh caches (errors ignored — not all distros need these)
update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
gtk-update-icon-cache -f ~/.local/share/icons/hicolor/ 2>/dev/null || true

echo "Done! SuprCompressr ($MODE) should appear in your app launcher shortly."
echo "(On Crostini you may need to wait a few seconds or restart the launcher.)"
