#!/usr/bin/env python3
"""
SuprComopressr launcher
- Auto-installs zstandard if missing
- Asks: GUI or CLI
"""
import subprocess
import sys


def ensure_zstandard():
    try:
        import zstandard  # noqa: F401
    except ImportError:
        print("zstandard not found. Installing...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "zstandard"],
                stdout=subprocess.DEVNULL,
            )
            print("✅ zstandard installed.\n")
        except Exception as e:
            print(f"⚠️  Could not install zstandard: {e}")
            print("   Continuing without it (reduced compression).\n")


if __name__ == "__main__":
    ensure_zstandard()

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
