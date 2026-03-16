#!/usr/bin/env python3
import contextlib
import io
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Optional

import suprcompressr as core

# Optional drag-and-drop
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

_result_queue: queue.Queue = queue.Queue()
_progress_queue: queue.Queue = queue.Queue()


# ─── Threading helpers ────────────────────────────────────────────────────────

def _run_in_thread(target_fn, *args, **kwargs):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            target_fn(*args, **kwargs)
        _result_queue.put(("ok", buf.getvalue()))
    except Exception as e:
        _result_queue.put(("error", str(e)))


def _progress_cb(current: int, total: int):
    if total > 0:
        _progress_queue.put(current / total * 100)


def _start_operation(root, btn, status_label, progress_bar, target_fn, *args, **kwargs):
    # Clear queues
    while not _result_queue.empty():
        _result_queue.get_nowait()
    while not _progress_queue.empty():
        _progress_queue.get_nowait()

    btn.config(state="disabled")
    status_label.config(text="Working...")
    progress_bar.config(mode="indeterminate")
    progress_bar.start(10)

    threading.Thread(
        target=_run_in_thread, args=(target_fn, *args), kwargs=kwargs, daemon=True
    ).start()
    root.after(100, _poll, root, btn, status_label, progress_bar)


def _poll(root, btn, status_label, progress_bar):
    # Drain progress updates
    try:
        while True:
            pct = _progress_queue.get_nowait()
            if progress_bar.cget("mode") == "indeterminate":
                progress_bar.stop()
                progress_bar.config(mode="determinate")
            progress_bar["value"] = pct
    except queue.Empty:
        pass

    # Check for completion
    try:
        kind, msg = _result_queue.get_nowait()
        progress_bar.stop()
        progress_bar.config(mode="determinate", value=0)
        btn.config(state="normal")
        if kind == "ok":
            status_label.config(text="Done.")
            messagebox.showinfo("Result", msg.strip() or "Complete.")
        else:
            status_label.config(text="Error.")
            messagebox.showerror("Error", msg)
    except queue.Empty:
        root.after(100, _poll, root, btn, status_label, progress_bar)


# ─── Path helpers ─────────────────────────────────────────────────────────────

def _clean(val: str) -> Optional[str]:
    v = val.strip().strip("'\"")
    return str(Path(v).expanduser()) if v else None


def _bind_drop(widget, var):
    """Bind drag-and-drop to an entry widget if tkinterdnd2 is available."""
    if HAS_DND:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", lambda e: var.set(e.data.strip("{}")))


# ─── Compress tab ─────────────────────────────────────────────────────────────

def _build_compress_tab(frame, root, status_label, progress_bar):
    infile_var = tk.StringVar()
    outfile_var = tk.StringVar()
    fmt_var = tk.StringVar(value="supr")
    level_var = tk.IntVar(value=9)

    ALL_FMTS = ["supr", "zip", "gz", "bz2", "xz", "zst", "tar.gz", "tar.xz", "7z"]

    def browse_in():
        # Try folder first choice dialog
        path = filedialog.askopenfilename(title="Select file")
        if path:
            infile_var.set(path)

    def browse_in_folder():
        path = filedialog.askdirectory(title="Select folder")
        if path:
            infile_var.set(path)

    def browse_out():
        fmt = fmt_var.get()
        ext_map = {"zip": ".zip", "supr": ".supr", "gz": ".gz", "bz2": ".bz2",
                   "xz": ".xz", "zst": ".zst", "tar.gz": ".tar.gz",
                   "tar.xz": ".tar.xz", "7z": ".7z"}
        ext = ext_map.get(fmt, "")
        p = filedialog.asksaveasfilename(defaultextension=ext)
        if p:
            outfile_var.set(p)

    def on_fmt_change(*_):
        fmt = fmt_var.get()
        s = "disabled" if fmt in ("supr", "7z") else "normal"
        level_slider.config(state=s)
        level_lbl.config(state=s)

    # Row 0 — input
    ttk.Label(frame, text="Input:").grid(row=0, column=0, sticky="w", pady=5, padx=6)
    in_entry = ttk.Entry(frame, textvariable=infile_var, width=38)
    in_entry.grid(row=0, column=1, padx=4)
    _bind_drop(in_entry, infile_var)
    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=0, column=2, padx=4)
    ttk.Button(btn_frame, text="File",   width=5, command=browse_in).pack(side="left", padx=1)
    ttk.Button(btn_frame, text="Folder", width=6, command=browse_in_folder).pack(side="left", padx=1)

    # Row 1 — format
    ttk.Label(frame, text="Format:").grid(row=1, column=0, sticky="w", pady=5, padx=6)
    fmt_cb = ttk.Combobox(frame, textvariable=fmt_var, width=10,
                          values=ALL_FMTS, state="readonly")
    fmt_cb.grid(row=1, column=1, sticky="w", padx=4)
    fmt_cb.bind("<<ComboboxSelected>>", on_fmt_change)

    # Row 2 — level
    ttk.Label(frame, text="Level (1-9):").grid(row=2, column=0, sticky="w", pady=5, padx=6)
    level_row = ttk.Frame(frame)
    level_row.grid(row=2, column=1, sticky="w", padx=4)
    level_slider = ttk.Scale(level_row, from_=1, to=9, variable=level_var,
                             orient="horizontal", length=130, state="disabled",
                             command=lambda v: level_var.set(int(float(v))))
    level_slider.pack(side="left")
    level_lbl = ttk.Label(level_row, textvariable=level_var, width=2, state="disabled")
    level_lbl.pack(side="left", padx=4)

    # Row 3 — output
    ttk.Label(frame, text="Output (opt):").grid(row=3, column=0, sticky="w", pady=5, padx=6)
    out_entry = ttk.Entry(frame, textvariable=outfile_var, width=38)
    out_entry.grid(row=3, column=1, padx=4)
    _bind_drop(out_entry, outfile_var)
    ttk.Button(frame, text="Browse", command=browse_out).grid(row=3, column=2, padx=4)

    # Row 4 — button
    btn = ttk.Button(frame, text="Compress", command=lambda: _start_operation(
        root, btn, status_label, progress_bar,
        core.perform_compression,
        _clean(infile_var.get()), fmt_var.get(), level_var.get(),
        _clean(outfile_var.get()), _progress_cb
    ))
    btn.grid(row=4, column=0, columnspan=3, pady=14)


# ─── Decompress tab ───────────────────────────────────────────────────────────

def _build_decompress_tab(frame, root, status_label, progress_bar):
    infile_var = tk.StringVar()
    outfile_var = tk.StringVar()

    def browse_in():
        p = filedialog.askopenfilename(
            filetypes=[("Archives", "*.supr *.zip *.gz *.bz2 *.xz *.zst *.7z *.tar.gz *.tar.xz"),
                       ("All", "*")])
        if p:
            infile_var.set(p)

    def browse_out():
        p = filedialog.asksaveasfilename()
        if p:
            outfile_var.set(p)

    def do_preview():
        path = _clean(infile_var.get())
        result = core.preview_archive(path)
        _show_text_dialog(frame.winfo_toplevel(), "Preview", result)

    def do_verify():
        path = _clean(infile_var.get())
        ok, msg = core.verify_archive(path)
        if ok:
            messagebox.showinfo("Verify", msg)
        else:
            messagebox.showerror("Verify Failed", msg)

    ttk.Label(frame, text="Input:").grid(row=0, column=0, sticky="w", pady=5, padx=6)
    in_entry = ttk.Entry(frame, textvariable=infile_var, width=38)
    in_entry.grid(row=0, column=1, padx=4)
    _bind_drop(in_entry, infile_var)
    ttk.Button(frame, text="Browse", command=browse_in).grid(row=0, column=2, padx=4)

    ttk.Label(frame, text="Output (opt):").grid(row=1, column=0, sticky="w", pady=5, padx=6)
    out_entry = ttk.Entry(frame, textvariable=outfile_var, width=38)
    out_entry.grid(row=1, column=1, padx=4)
    _bind_drop(out_entry, outfile_var)
    ttk.Button(frame, text="Browse", command=browse_out).grid(row=1, column=2, padx=4)

    btn_row = ttk.Frame(frame)
    btn_row.grid(row=2, column=0, columnspan=3, pady=14)

    btn = ttk.Button(btn_row, text="Decompress", command=lambda: _start_operation(
        root, btn, status_label, progress_bar,
        core.perform_decompression,
        _clean(infile_var.get()), _clean(outfile_var.get())
    ))
    btn.pack(side="left", padx=6)
    ttk.Button(btn_row, text="Preview",  command=do_preview).pack(side="left", padx=6)
    ttk.Button(btn_row, text="Verify",   command=do_verify).pack(side="left", padx=6)


# ─── Batch tab ────────────────────────────────────────────────────────────────

def _build_batch_tab(frame, root, status_label, progress_bar):
    files_var = tk.StringVar()
    outdir_var = tk.StringVar()
    fmt_var = tk.StringVar(value="zip")
    level_var = tk.IntVar(value=9)

    file_list: list[str] = []

    def browse_files():
        paths = filedialog.askopenfilenames(title="Select files to compress")
        if paths:
            file_list.clear()
            file_list.extend(paths)
            files_var.set(f"{len(file_list)} file(s) selected")

    def browse_outdir():
        p = filedialog.askdirectory(title="Output directory")
        if p:
            outdir_var.set(p)

    ttk.Label(frame, text="Files:").grid(row=0, column=0, sticky="w", pady=5, padx=6)
    ttk.Label(frame, textvariable=files_var, foreground="gray").grid(row=0, column=1, sticky="w", padx=4)
    ttk.Button(frame, text="Select Files", command=browse_files).grid(row=0, column=2, padx=4)

    ttk.Label(frame, text="Format:").grid(row=1, column=0, sticky="w", pady=5, padx=6)
    ttk.Combobox(frame, textvariable=fmt_var, width=10,
                 values=core.ALL_FORMATS, state="readonly").grid(row=1, column=1, sticky="w", padx=4)

    ttk.Label(frame, text="Level (1-9):").grid(row=2, column=0, sticky="w", pady=5, padx=6)
    level_row = ttk.Frame(frame)
    level_row.grid(row=2, column=1, sticky="w", padx=4)
    ttk.Scale(level_row, from_=1, to=9, variable=level_var, orient="horizontal", length=130,
              command=lambda v: level_var.set(int(float(v)))).pack(side="left")
    ttk.Label(level_row, textvariable=level_var, width=2).pack(side="left", padx=4)

    ttk.Label(frame, text="Output dir (opt):").grid(row=3, column=0, sticky="w", pady=5, padx=6)
    ttk.Entry(frame, textvariable=outdir_var, width=38).grid(row=3, column=1, padx=4)
    ttk.Button(frame, text="Browse", command=browse_outdir).grid(row=3, column=2, padx=4)

    btn = ttk.Button(frame, text="Batch Compress", command=lambda: _start_operation(
        root, btn, status_label, progress_bar,
        core.perform_batch_compression,
        list(file_list), fmt_var.get(), level_var.get(),
        _clean(outdir_var.get()), _progress_cb
    ))
    btn.grid(row=4, column=0, columnspan=3, pady=14)


# ─── Convert tab ──────────────────────────────────────────────────────────────

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

    ttk.Label(frame, text=".supr file:").grid(row=0, column=0, sticky="w", pady=5, padx=6)
    in_entry = ttk.Entry(frame, textvariable=infile_var, width=38)
    in_entry.grid(row=0, column=1, padx=4)
    _bind_drop(in_entry, infile_var)
    ttk.Button(frame, text="Browse", command=browse_in).grid(row=0, column=2, padx=4)

    ttk.Label(frame, text="Output .zip (opt):").grid(row=1, column=0, sticky="w", pady=5, padx=6)
    out_entry = ttk.Entry(frame, textvariable=outfile_var, width=38)
    out_entry.grid(row=1, column=1, padx=4)
    _bind_drop(out_entry, outfile_var)
    ttk.Button(frame, text="Browse", command=browse_out).grid(row=1, column=2, padx=4)

    btn = ttk.Button(frame, text="Convert", command=lambda: _start_operation(
        root, btn, status_label, progress_bar,
        core.convert_supr_to_zip,
        _clean(infile_var.get()), _clean(outfile_var.get()), _progress_cb
    ))
    btn.grid(row=2, column=0, columnspan=3, pady=14)


# ─── Benchmark tab ────────────────────────────────────────────────────────────

def _build_benchmark_tab(frame, root, status_label, progress_bar):
    infile_var = tk.StringVar()

    def browse_in():
        p = filedialog.askopenfilename()
        if p:
            infile_var.set(p)

    def do_benchmark():
        path = _clean(infile_var.get())
        if not path:
            messagebox.showerror("Error", "Please select a file.")
            return
        result_text.config(state="normal")
        result_text.delete("1.0", "end")
        result_text.insert("end", "Running benchmark...\n")
        result_text.config(state="disabled")

        def run():
            result = core.benchmark_file(path)
            _result_queue.put(("benchmark", result))

        threading.Thread(target=run, daemon=True).start()
        root.after(200, _poll_benchmark)

    def _poll_benchmark():
        try:
            kind, msg = _result_queue.get_nowait()
            if kind == "benchmark":
                result_text.config(state="normal")
                result_text.delete("1.0", "end")
                result_text.insert("end", msg)
                result_text.config(state="disabled")
                status_label.config(text="Benchmark complete.")
            else:
                # Put it back for the main poll to handle
                _result_queue.put((kind, msg))
        except queue.Empty:
            root.after(200, _poll_benchmark)

    ttk.Label(frame, text="File:").grid(row=0, column=0, sticky="w", pady=5, padx=6)
    in_entry = ttk.Entry(frame, textvariable=infile_var, width=38)
    in_entry.grid(row=0, column=1, padx=4)
    _bind_drop(in_entry, infile_var)
    ttk.Button(frame, text="Browse", command=browse_in).grid(row=0, column=2, padx=4)

    ttk.Button(frame, text="Run Benchmark", command=do_benchmark).grid(
        row=1, column=0, columnspan=3, pady=10)

    result_text = tk.Text(frame, height=12, state="disabled",
                          font=("Monospace", 9), bg="#1e1e1e", fg="#d4d4d4")
    result_text.grid(row=2, column=0, columnspan=3, padx=6, pady=4, sticky="nsew")
    frame.rowconfigure(2, weight=1)
    frame.columnconfigure(1, weight=1)


# ─── Preview dialog ───────────────────────────────────────────────────────────

def _show_text_dialog(parent, title: str, text: str):
    win = tk.Toplevel(parent)
    win.title(title)
    win.resizable(True, True)

    txt = tk.Text(win, font=("Monospace", 9), bg="#1e1e1e", fg="#d4d4d4",
                  wrap="none", width=80, height=24)
    scroll_y = ttk.Scrollbar(win, command=txt.yview)
    scroll_x = ttk.Scrollbar(win, orient="horizontal", command=txt.xview)
    txt.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

    txt.grid(row=0, column=0, sticky="nsew")
    scroll_y.grid(row=0, column=1, sticky="ns")
    scroll_x.grid(row=1, column=0, sticky="ew")
    ttk.Button(win, text="Close", command=win.destroy).grid(
        row=2, column=0, columnspan=2, pady=6)

    win.rowconfigure(0, weight=1)
    win.columnconfigure(0, weight=1)

    txt.insert("1.0", text)
    txt.config(state="disabled")


# ─── Main launcher ────────────────────────────────────────────────────────────

def launch_gui():
    RootClass = TkinterDnD.Tk if HAS_DND else tk.Tk
    root = RootClass()
    root.title("SuprComopressr")
    root.resizable(False, False)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=(10, 0))

    # Shared status bar below the notebook
    bar = ttk.Frame(root)
    bar.pack(fill="x", padx=10, pady=(4, 10))
    status_label = ttk.Label(bar, text="Ready")
    status_label.pack(side="left")
    progress_bar = ttk.Progressbar(bar, mode="determinate", length=180)
    progress_bar.pack(side="right")

    tab_defs = [
        ("  Compress  ",          _build_compress_tab),
        (" Decompress ",          _build_decompress_tab),
        ("  Batch     ",          _build_batch_tab),
        (" .supr→.zip ",          _build_convert_tab),
        (" Benchmark  ",          _build_benchmark_tab),
    ]
    for label, builder in tab_defs:
        f = ttk.Frame(notebook, padding=10)
        notebook.add(f, text=label)
        builder(f, root, status_label, progress_bar)

    root.mainloop()


if __name__ == "__main__":
    launch_gui()
