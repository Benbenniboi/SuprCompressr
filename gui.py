#!/usr/bin/env python3
import contextlib
import io
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

import suprcompressr as core

_result_queue: queue.Queue = queue.Queue()


def _run_in_thread(target_fn, *args):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            target_fn(*args)
        _result_queue.put(("ok", buf.getvalue()))
    except Exception as e:
        _result_queue.put(("error", str(e)))


def _start_operation(root, btn, status_label, progress_bar, target_fn, *args):
    btn.config(state="disabled")
    status_label.config(text="Working...")
    progress_bar.start(10)
    threading.Thread(
        target=_run_in_thread, args=(target_fn, *args), daemon=True
    ).start()
    root.after(100, _poll_result, root, btn, status_label, progress_bar)


def _poll_result(root, btn, status_label, progress_bar):
    try:
        kind, msg = _result_queue.get_nowait()
        progress_bar.stop()
        btn.config(state="normal")
        if kind == "ok":
            status_label.config(text="Done.")
            messagebox.showinfo("Result", msg.strip() or "Complete.")
        else:
            status_label.config(text="Error.")
            messagebox.showerror("Error", msg)
    except queue.Empty:
        root.after(100, _poll_result, root, btn, status_label, progress_bar)


def _clean(val: str) -> str | None:
    v = val.strip().strip("'\"")
    return str(Path(v).expanduser()) if v else None


def _build_compress_tab(frame, root, status_label, progress_bar):
    infile_var = tk.StringVar()
    outfile_var = tk.StringVar()
    fmt_var = tk.StringVar(value="supr")
    level_var = tk.IntVar(value=9)

    def browse_in():
        p = filedialog.askopenfilename()
        if p:
            infile_var.set(p)

    def browse_out():
        ext = f".{fmt_var.get()}" if fmt_var.get() != "supr" else ".supr"
        p = filedialog.asksaveasfilename(defaultextension=ext)
        if p:
            outfile_var.set(p)

    def on_fmt_change(*_):
        state = "disabled" if fmt_var.get() == "supr" else "normal"
        level_slider.config(state=state)
        level_lbl.config(state=state)

    ttk.Label(frame, text="Input file:").grid(row=0, column=0, sticky="w", pady=6, padx=6)
    ttk.Entry(frame, textvariable=infile_var, width=42).grid(row=0, column=1, padx=4)
    ttk.Button(frame, text="Browse", command=browse_in).grid(row=0, column=2, padx=4)

    ttk.Label(frame, text="Format:").grid(row=1, column=0, sticky="w", pady=6, padx=6)
    fmt_cb = ttk.Combobox(
        frame, textvariable=fmt_var, width=8,
        values=["supr", "zip", "gz", "bz2", "xz", "zst"], state="readonly"
    )
    fmt_cb.grid(row=1, column=1, sticky="w", padx=4)
    fmt_cb.bind("<<ComboboxSelected>>", on_fmt_change)

    ttk.Label(frame, text="Level (1-9):").grid(row=2, column=0, sticky="w", pady=6, padx=6)
    level_row = ttk.Frame(frame)
    level_row.grid(row=2, column=1, sticky="w", padx=4)
    level_slider = ttk.Scale(
        level_row, from_=1, to=9, variable=level_var, orient="horizontal", length=140,
        command=lambda v: level_var.set(int(float(v))), state="disabled"
    )
    level_slider.pack(side="left")
    level_lbl = ttk.Label(level_row, textvariable=level_var, width=2, state="disabled")
    level_lbl.pack(side="left", padx=4)

    ttk.Label(frame, text="Output (optional):").grid(row=3, column=0, sticky="w", pady=6, padx=6)
    ttk.Entry(frame, textvariable=outfile_var, width=42).grid(row=3, column=1, padx=4)
    ttk.Button(frame, text="Browse", command=browse_out).grid(row=3, column=2, padx=4)

    btn = ttk.Button(frame, text="Compress", command=lambda: _start_operation(
        root, btn, status_label, progress_bar,
        core.perform_compression,
        _clean(infile_var.get()), fmt_var.get(), level_var.get(), _clean(outfile_var.get())
    ))
    btn.grid(row=4, column=0, columnspan=3, pady=14)


def _build_decompress_tab(frame, root, status_label, progress_bar):
    infile_var = tk.StringVar()
    outfile_var = tk.StringVar()

    def browse_in():
        p = filedialog.askopenfilename(
            filetypes=[("Compressed files", "*.supr *.gz *.bz2 *.xz *.zst *.zip"), ("All", "*")]
        )
        if p:
            infile_var.set(p)

    def browse_out():
        p = filedialog.asksaveasfilename()
        if p:
            outfile_var.set(p)

    ttk.Label(frame, text="Input file:").grid(row=0, column=0, sticky="w", pady=6, padx=6)
    ttk.Entry(frame, textvariable=infile_var, width=42).grid(row=0, column=1, padx=4)
    ttk.Button(frame, text="Browse", command=browse_in).grid(row=0, column=2, padx=4)

    ttk.Label(frame, text="Output (optional):").grid(row=1, column=0, sticky="w", pady=6, padx=6)
    ttk.Entry(frame, textvariable=outfile_var, width=42).grid(row=1, column=1, padx=4)
    ttk.Button(frame, text="Browse", command=browse_out).grid(row=1, column=2, padx=4)

    btn = ttk.Button(frame, text="Decompress", command=lambda: _start_operation(
        root, btn, status_label, progress_bar,
        core.perform_decompression,
        _clean(infile_var.get()), _clean(outfile_var.get())
    ))
    btn.grid(row=2, column=0, columnspan=3, pady=14)


def _build_convert_tab(frame, root, status_label, progress_bar):
    infile_var = tk.StringVar()
    outfile_var = tk.StringVar()

    def browse_in():
        p = filedialog.askopenfilename(filetypes=[("SUPR files", "*.supr"), ("All", "*")])
        if p:
            infile_var.set(p)

    def browse_out():
        p = filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("ZIP", "*.zip")])
        if p:
            outfile_var.set(p)

    ttk.Label(frame, text=".supr file:").grid(row=0, column=0, sticky="w", pady=6, padx=6)
    ttk.Entry(frame, textvariable=infile_var, width=42).grid(row=0, column=1, padx=4)
    ttk.Button(frame, text="Browse", command=browse_in).grid(row=0, column=2, padx=4)

    ttk.Label(frame, text="Output .zip (optional):").grid(row=1, column=0, sticky="w", pady=6, padx=6)
    ttk.Entry(frame, textvariable=outfile_var, width=42).grid(row=1, column=1, padx=4)
    ttk.Button(frame, text="Browse", command=browse_out).grid(row=1, column=2, padx=4)

    btn = ttk.Button(frame, text="Convert", command=lambda: _start_operation(
        root, btn, status_label, progress_bar,
        core.convert_supr_to_zip,
        _clean(infile_var.get()), _clean(outfile_var.get())
    ))
    btn.grid(row=2, column=0, columnspan=3, pady=14)


def launch_gui():
    root = tk.Tk()
    root.title("SuprComopressr")
    root.resizable(False, False)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)

    compress_tab   = ttk.Frame(notebook); notebook.add(compress_tab,   text="  Compress  ")
    decompress_tab = ttk.Frame(notebook); notebook.add(decompress_tab, text=" Decompress ")
    convert_tab    = ttk.Frame(notebook); notebook.add(convert_tab,    text=" Convert .supr→.zip ")

    status_frame = ttk.Frame(root)
    status_frame.pack(fill="x", padx=10, pady=(0, 10))
    status_label = ttk.Label(status_frame, text="Ready")
    status_label.pack(side="left")
    progress_bar = ttk.Progressbar(status_frame, mode="indeterminate", length=160)
    progress_bar.pack(side="right")

    _build_compress_tab(compress_tab, root, status_label, progress_bar)
    _build_decompress_tab(decompress_tab, root, status_label, progress_bar)
    _build_convert_tab(convert_tab, root, status_label, progress_bar)

    root.mainloop()


if __name__ == "__main__":
    launch_gui()
