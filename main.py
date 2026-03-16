#!/usr/bin/env python3
"""
SuprCompressr launcher
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


def fix_x11_auth():
    """On Crostini (and some Linux setups) the Xauthority file may be missing,
    causing 'No protocol specified' when launching any GUI app.
    This creates the file and adds a cookie if needed."""
    import os, pathlib, subprocess
    if sys.platform != "linux":
        return
    xauth_path = pathlib.Path.home() / ".Xauthority"
    display = os.environ.get("DISPLAY", ":0")
    if not xauth_path.exists() or xauth_path.stat().st_size == 0:
        try:
            xauth_path.touch()
            cookie = subprocess.check_output(["mcookie"], text=True).strip()
            subprocess.run(["xauth", "add", display, ".", cookie],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass  # xauth/mcookie not available — carry on


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


def install_desktop_entry(mode: str = ""):
    import os, subprocess, pathlib
    script_dir = pathlib.Path(__file__).parent.resolve()
    install_script = script_dir / "install.sh"
    if not install_script.exists():
        print("install.sh not found.")
        return
    os.chmod(install_script, 0o755)
    cmd = ["bash", str(install_script)]
    if mode:
        cmd.append(mode)
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""

    if arg == "--install":
        install_desktop_entry()
        sys.exit(0)

    if arg == "--install-gui":
        install_desktop_entry("gui")
        sys.exit(0)

    if arg == "--install-cli":
        install_desktop_entry("cli")
        sys.exit(0)

    if arg == "--gui":
        fix_x11_auth()
        ensure_dependencies()
        from gui import launch_gui
        launch_gui()
        sys.exit(0)

    if arg == "--cli":
        ensure_dependencies()
        from suprcompressr import main
        main()
        sys.exit(0)

    fix_x11_auth()
    ensure_dependencies()

    # When launched from an app launcher (no terminal), go straight to GUI
    if not sys.stdin.isatty():
        from gui import launch_gui
        launch_gui()
        sys.exit(0)

    print("SuprCompressr")
    print("1. GUI")
    print("2. CLI")
    print("3. Install to app launcher")
    choice = input("Choose (1-3, default 1): ").strip()

    if choice == "2":
        from suprcompressr import main
        main()
    elif choice == "3":
        install_desktop_entry()
    else:
        from gui import launch_gui
        launch_gui()
