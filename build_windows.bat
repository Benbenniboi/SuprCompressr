@echo off
echo Installing build dependencies...
pip install pyinstaller zstandard

echo Building SuprComopressr.exe...
pyinstaller ^
  --onefile ^
  --name SuprComopressr ^
  --hidden-import zstandard ^
  --hidden-import tkinter ^
  --hidden-import tkinter.ttk ^
  --hidden-import tkinter.filedialog ^
  --hidden-import tkinter.messagebox ^
  main.py

echo.
echo Done! Executable: dist\SuprComopressr.exe
pause
