#!/usr/bin/env python3
"""
SuprComopressr launcher
- Auto-installs zstandard if missing
- Asks: GUI or CLI
"""
import subprocess
import sys


def _try_install(package: str):
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package],
            stdout=subprocess.DEVNULL,
        )
        print(f"✅ {package} installed.")
    except Exception as e:
        print(f"⚠️  Could not install {package}: {e} (continuing without it)")


def ensure_dependencies():
    for module, package in [
        ("zstandard",  "zstandard"),
        ("py7zr",      "py7zr"),
        ("tkinterdnd2","tkinterdnd2"),
    ]:
        try:
            __import__(module)
        except ImportError:
            print(f"{package} not found. Installing...")
            _try_install(package)
    print()


if __name__ == "__main__":
    ensure_dependencies()

    print("SuprComopressr")
    print("1. GUI")
    print("2. CLI")
    choice = input("Choose (1/2, default 1): ").strip()

    if choice == "2":
        from suprcompressr import main
        main()
    else:
        from gui import launch_gui
        launch_gui()
