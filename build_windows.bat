@echo off
echo Installing build dependencies...
pip install pyinstaller zstandard py7zr tkinterdnd2

echo Building SuprComopressr.exe...
pyinstaller ^
  --onefile ^
  --name SuprComopressr ^
  --hidden-import zstandard ^
  --hidden-import py7zr ^
  --hidden-import tkinter ^
  --hidden-import tkinter.ttk ^
  --hidden-import tkinter.filedialog ^
  --hidden-import tkinter.messagebox ^
  --hidden-import tkinterdnd2 ^
  main.py

echo.
echo Done! Executable: dist\SuprComopressr.exe
pause
