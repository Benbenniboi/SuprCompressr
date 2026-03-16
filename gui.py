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

# ─── Colour palette ───────────────────────────────────────────────────────────

C = {
    "bg":           "#0f0f1a",
    "surface":      "#1a1a2e",
    "card":         "#16213e",
    "border":       "#2a2a4a",
    "accent":       "#6366f1",
    "accent_hover": "#4f46e5",
    "accent_dim":   "#312e81",
    "text":         "#f1f5f9",
    "subtext":      "#94a3b8",
    "entry_bg":     "#1e1e3a",
}


def _apply_theme(root):
    root.configure(bg=C["bg"])
    s = ttk.Style(root)
    s.theme_use("clam")

    s.configure(".",
                background=C["bg"], foreground=C["text"],
                font=("Helvetica", 10), borderwidth=0, relief="flat")

    s.configure("TFrame",    background=C["bg"])
    s.configure("TLabel",    background=C["bg"], foreground=C["text"])
    s.configure("Sub.TLabel",background=C["bg"], foreground=C["subtext"],
                font=("Helvetica", 9))

    s.configure("TButton",
                background=C["accent"], foreground="white",
                font=("Helvetica", 10, "bold"), padding=(14, 8),
                borderwidth=0, focusthickness=0, focuscolor="none",
                relief="flat")
    s.map("TButton",
          background=[("active",   C["accent_hover"]),
                      ("disabled", C["accent_dim"]),
                      ("pressed",  C["accent_hover"])],
          foreground=[("disabled", C["subtext"])])

    s.configure("Small.TButton",
                font=("Helvetica", 9), padding=(8, 5))
    s.map("Small.TButton",
          background=[("active",   C["accent_hover"]),
                      ("disabled", C["accent_dim"])])

    s.configure("TEntry",
                fieldbackground=C["entry_bg"], foreground=C["text"],
                insertcolor=C["text"], bordercolor=C["border"],
                lightcolor=C["border"], darkcolor=C["border"],
                padding=(6, 5))
    s.map("TEntry",
          fieldbackground=[("focus", C["card"])])

    s.configure("TCombobox",
                fieldbackground=C["entry_bg"], foreground=C["text"],
                selectbackground=C["accent"], selectforeground="white",
                bordercolor=C["border"], arrowcolor=C["text"],
                padding=(4, 4))
    s.map("TCombobox",
          fieldbackground=[("readonly", C["entry_bg"])],
          foreground=[("readonly", C["text"])])

    s.configure("TNotebook",
                background=C["surface"], borderwidth=0,
                tabmargins=(0, 0, 0, 0))
    s.configure("TNotebook.Tab",
                background=C["surface"], foreground=C["subtext"],
                padding=(18, 10), font=("Helvetica", 10))
    s.map("TNotebook.Tab",
          background=[("selected", C["bg"])],
          foreground=[("selected", C["text"])],
          expand=[("selected", (0, 0, 0, 0))])

    s.configure("TProgressbar",
                troughcolor=C["border"], background=C["accent"],
                borderwidth=0, lightcolor=C["accent"], darkcolor=C["accent"],
                thickness=5)

    s.configure("TScale",
                background=C["bg"], troughcolor=C["border"],
                sliderlength=14, sliderthickness=14)
    s.map("TScale",
          troughcolor=[("active", C["border"])])

    s.configure("TScrollbar",
                background=C["card"], troughcolor=C["bg"],
                arrowcolor=C["subtext"], borderwidth=0)
    s.map("TScrollbar",
          background=[("active", C["accent"])])

    s.configure("TSeparator", background=C["border"])

    # Make Combobox popup list dark
    root.option_add("*TCombobox*Listbox.background",  C["card"])
    root.option_add("*TCombobox*Listbox.foreground",  C["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", "white")


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
    while not _result_queue.empty():
        _result_queue.get_nowait()
    while not _progress_queue.empty():
        _progress_queue.get_nowait()

    btn.config(state="disabled")
    status_label.config(text="Working…")
    progress_bar.config(mode="indeterminate")
    progress_bar.start(10)

    threading.Thread(
        target=_run_in_thread, args=(target_fn, *args), kwargs=kwargs, daemon=True
    ).start()
    root.after(100, _poll, root, btn, status_label, progress_bar)


def _poll(root, btn, status_label, progress_bar):
    try:
        while True:
            pct = _progress_queue.get_nowait()
            if progress_bar.cget("mode") == "indeterminate":
                progress_bar.stop()
                progress_bar.config(mode="determinate")
            progress_bar["value"] = pct
    except queue.Empty:
        pass

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
    if HAS_DND:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", lambda e: var.set(e.data.strip("{}")))


def _row(frame, row, label_text, widget, browse_btn=None, pady=8):
    """Helper: label | widget | optional browse button on one grid row."""
    ttk.Label(frame, text=label_text).grid(
        row=row, column=0, sticky="w", pady=pady, padx=(0, 12))
    widget.grid(row=row, column=1, sticky="ew", padx=(0, 8))
    if browse_btn:
        browse_btn.grid(row=row, column=2, sticky="e")
    frame.columnconfigure(1, weight=1)


# ─── Compress tab ─────────────────────────────────────────────────────────────

def _build_compress_tab(frame, root, status_label, progress_bar):
    infile_var  = tk.StringVar()
    outfile_var = tk.StringVar()
    fmt_var     = tk.StringVar(value="supr")
    level_var   = tk.IntVar(value=9)

    ALL_FMTS = ["supr", "zip", "gz", "bz2", "xz", "zst", "tar.gz", "tar.xz", "7z"]

    def browse_in():
        p = filedialog.askopenfilename(title="Select file")
        if p:
            infile_var.set(p)

    def browse_folder():
        p = filedialog.askdirectory(title="Select folder")
        if p:
            infile_var.set(p)

    def browse_out():
        ext_map = {"zip":".zip","supr":".supr","gz":".gz","bz2":".bz2",
                   "xz":".xz","zst":".zst","tar.gz":".tar.gz",
                   "tar.xz":".tar.xz","7z":".7z"}
        p = filedialog.asksaveasfilename(
            defaultextension=ext_map.get(fmt_var.get(), ""))
        if p:
            outfile_var.set(p)

    def on_fmt_change(*_):
        state = "disabled" if fmt_var.get() in ("supr", "7z") else "normal"
        level_slider.config(state=state)
        level_lbl.config(state=state)

    # Input row with two browse buttons
    ttk.Label(frame, text="Input:").grid(row=0, column=0, sticky="w",
                                         pady=8, padx=(0, 12))
    in_entry = ttk.Entry(frame, textvariable=infile_var)
    in_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
    _bind_drop(in_entry, infile_var)
    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=0, column=2, sticky="e")
    ttk.Button(btn_frame, text="File",   style="Small.TButton",
               command=browse_in).pack(side="left", padx=(0, 4))
    ttk.Button(btn_frame, text="Folder", style="Small.TButton",
               command=browse_folder).pack(side="left")

    # Format
    ttk.Label(frame, text="Format:").grid(row=1, column=0, sticky="w",
                                           pady=8, padx=(0, 12))
    fmt_cb = ttk.Combobox(frame, textvariable=fmt_var, width=12,
                          values=ALL_FMTS, state="readonly")
    fmt_cb.grid(row=1, column=1, sticky="w", padx=(0, 8))
    fmt_cb.bind("<<ComboboxSelected>>", on_fmt_change)

    # Level
    ttk.Label(frame, text="Level (1–9):").grid(row=2, column=0, sticky="w",
                                                pady=8, padx=(0, 12))
    level_row = ttk.Frame(frame)
    level_row.grid(row=2, column=1, sticky="w", padx=(0, 8))
    level_slider = ttk.Scale(level_row, from_=1, to=9, variable=level_var,
                             orient="horizontal", length=140, state="disabled",
                             command=lambda v: level_var.set(int(float(v))))
    level_slider.pack(side="left")
    level_lbl = ttk.Label(level_row, textvariable=level_var, width=2,
                          state="disabled")
    level_lbl.pack(side="left", padx=(8, 0))

    # Output
    ttk.Label(frame, text="Output (opt):").grid(row=3, column=0, sticky="w",
                                                 pady=8, padx=(0, 12))
    out_entry = ttk.Entry(frame, textvariable=outfile_var)
    out_entry.grid(row=3, column=1, sticky="ew", padx=(0, 8))
    _bind_drop(out_entry, outfile_var)
    ttk.Button(frame, text="Browse", style="Small.TButton",
               command=browse_out).grid(row=3, column=2, sticky="e")

    ttk.Separator(frame, orient="horizontal").grid(
        row=4, column=0, columnspan=3, sticky="ew", pady=14)

    btn = ttk.Button(frame, text="Compress", command=lambda: _start_operation(
        root, btn, status_label, progress_bar,
        core.perform_compression,
        _clean(infile_var.get()), fmt_var.get(), level_var.get(),
        _clean(outfile_var.get()), _progress_cb
    ))
    btn.grid(row=5, column=0, columnspan=3)
    frame.columnconfigure(1, weight=1)


# ─── Decompress tab ───────────────────────────────────────────────────────────

def _build_decompress_tab(frame, root, status_label, progress_bar):
    infile_var  = tk.StringVar()
    outfile_var = tk.StringVar()

    def browse_in():
        p = filedialog.askopenfilename(
            filetypes=[("Archives",
                        "*.supr *.zip *.gz *.bz2 *.xz *.zst *.7z *.tar.gz *.tar.xz"),
                       ("All", "*")])
        if p:
            infile_var.set(p)

    def browse_out():
        p = filedialog.asksaveasfilename()
        if p:
            outfile_var.set(p)

    def do_preview():
        path = _clean(infile_var.get())
        if not path:
            messagebox.showerror("Error", "Select a file first.")
            return
        _show_text_dialog(frame.winfo_toplevel(), "Preview",
                          core.preview_archive(path))

    def do_verify():
        path = _clean(infile_var.get())
        if not path:
            messagebox.showerror("Error", "Select a file first.")
            return
        ok, msg = core.verify_archive(path)
        (messagebox.showinfo if ok else messagebox.showerror)("Verify", msg)

    ttk.Label(frame, text="Input:").grid(row=0, column=0, sticky="w",
                                          pady=8, padx=(0, 12))
    in_entry = ttk.Entry(frame, textvariable=infile_var)
    in_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
    _bind_drop(in_entry, infile_var)
    ttk.Button(frame, text="Browse", style="Small.TButton",
               command=browse_in).grid(row=0, column=2, sticky="e")

    ttk.Label(frame, text="Output (opt):").grid(row=1, column=0, sticky="w",
                                                 pady=8, padx=(0, 12))
    out_entry = ttk.Entry(frame, textvariable=outfile_var)
    out_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8))
    _bind_drop(out_entry, outfile_var)
    ttk.Button(frame, text="Browse", style="Small.TButton",
               command=browse_out).grid(row=1, column=2, sticky="e")

    ttk.Separator(frame, orient="horizontal").grid(
        row=2, column=0, columnspan=3, sticky="ew", pady=14)

    btn_row = ttk.Frame(frame)
    btn_row.grid(row=3, column=0, columnspan=3)
    btn = ttk.Button(btn_row, text="Decompress", command=lambda: _start_operation(
        root, btn, status_label, progress_bar,
        core.perform_decompression,
        _clean(infile_var.get()), _clean(outfile_var.get())
    ))
    btn.pack(side="left", padx=(0, 8))
    ttk.Button(btn_row, text="Preview", style="Small.TButton",
               command=do_preview).pack(side="left", padx=(0, 8))
    ttk.Button(btn_row, text="Verify",  style="Small.TButton",
               command=do_verify).pack(side="left")

    frame.columnconfigure(1, weight=1)


# ─── Batch tab ────────────────────────────────────────────────────────────────

def _build_batch_tab(frame, root, status_label, progress_bar):
    files_var  = tk.StringVar(value="No files selected")
    outdir_var = tk.StringVar()
    fmt_var    = tk.StringVar(value="zip")
    level_var  = tk.IntVar(value=9)
    file_list: list[str] = []

    def browse_files():
        paths = filedialog.askopenfilenames(title="Select files")
        if paths:
            file_list.clear()
            file_list.extend(paths)
            files_var.set(f"{len(file_list)} file(s) selected")

    def browse_outdir():
        p = filedialog.askdirectory(title="Output directory")
        if p:
            outdir_var.set(p)

    ttk.Label(frame, text="Files:").grid(row=0, column=0, sticky="w",
                                          pady=8, padx=(0, 12))
    ttk.Label(frame, textvariable=files_var, style="Sub.TLabel").grid(
        row=0, column=1, sticky="w", padx=(0, 8))
    ttk.Button(frame, text="Select Files", style="Small.TButton",
               command=browse_files).grid(row=0, column=2, sticky="e")

    ttk.Label(frame, text="Format:").grid(row=1, column=0, sticky="w",
                                           pady=8, padx=(0, 12))
    ttk.Combobox(frame, textvariable=fmt_var, width=12,
                 values=core.ALL_FORMATS, state="readonly").grid(
        row=1, column=1, sticky="w", padx=(0, 8))

    ttk.Label(frame, text="Level (1–9):").grid(row=2, column=0, sticky="w",
                                                pady=8, padx=(0, 12))
    lr = ttk.Frame(frame)
    lr.grid(row=2, column=1, sticky="w", padx=(0, 8))
    ttk.Scale(lr, from_=1, to=9, variable=level_var, orient="horizontal",
              length=140, command=lambda v: level_var.set(int(float(v)))).pack(
        side="left")
    ttk.Label(lr, textvariable=level_var, width=2).pack(side="left", padx=(8, 0))

    ttk.Label(frame, text="Output dir (opt):").grid(row=3, column=0, sticky="w",
                                                     pady=8, padx=(0, 12))
    ttk.Entry(frame, textvariable=outdir_var).grid(row=3, column=1, sticky="ew",
                                                    padx=(0, 8))
    ttk.Button(frame, text="Browse", style="Small.TButton",
               command=browse_outdir).grid(row=3, column=2, sticky="e")

    ttk.Separator(frame, orient="horizontal").grid(
        row=4, column=0, columnspan=3, sticky="ew", pady=14)

    btn = ttk.Button(frame, text="Batch Compress",
                     command=lambda: _start_operation(
                         root, btn, status_label, progress_bar,
                         core.perform_batch_compression,
                         list(file_list), fmt_var.get(), level_var.get(),
                         _clean(outdir_var.get()), _progress_cb))
    btn.grid(row=5, column=0, columnspan=3)
    frame.columnconfigure(1, weight=1)


# ─── Convert tab ──────────────────────────────────────────────────────────────

def _build_convert_tab(frame, root, status_label, progress_bar):
    infile_var  = tk.StringVar()
    outfile_var = tk.StringVar()

    def browse_in():
        p = filedialog.askopenfilename(
            filetypes=[("SUPR files", "*.supr"), ("All", "*")])
        if p:
            infile_var.set(p)

    def browse_out():
        p = filedialog.asksaveasfilename(
            defaultextension=".zip", filetypes=[("ZIP", "*.zip")])
        if p:
            outfile_var.set(p)

    ttk.Label(frame, text=".supr file:").grid(row=0, column=0, sticky="w",
                                               pady=8, padx=(0, 12))
    in_entry = ttk.Entry(frame, textvariable=infile_var)
    in_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
    _bind_drop(in_entry, infile_var)
    ttk.Button(frame, text="Browse", style="Small.TButton",
               command=browse_in).grid(row=0, column=2, sticky="e")

    ttk.Label(frame, text="Output .zip (opt):").grid(row=1, column=0, sticky="w",
                                                      pady=8, padx=(0, 12))
    out_entry = ttk.Entry(frame, textvariable=outfile_var)
    out_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8))
    _bind_drop(out_entry, outfile_var)
    ttk.Button(frame, text="Browse", style="Small.TButton",
               command=browse_out).grid(row=1, column=2, sticky="e")

    note = ttk.Label(frame,
                     text="Warning: the resulting ZIP expands to the full original size.",
                     style="Sub.TLabel")
    note.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

    ttk.Separator(frame, orient="horizontal").grid(
        row=3, column=0, columnspan=3, sticky="ew", pady=14)

    btn = ttk.Button(frame, text="Convert", command=lambda: _start_operation(
        root, btn, status_label, progress_bar,
        core.convert_supr_to_zip,
        _clean(infile_var.get()), _clean(outfile_var.get()), _progress_cb
    ))
    btn.grid(row=4, column=0, columnspan=3)
    frame.columnconfigure(1, weight=1)


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
        result_text.insert("end", "Running benchmark…\n")
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
                _result_queue.put((kind, msg))
        except queue.Empty:
            root.after(200, _poll_benchmark)

    ttk.Label(frame, text="File:").grid(row=0, column=0, sticky="w",
                                         pady=8, padx=(0, 12))
    in_entry = ttk.Entry(frame, textvariable=infile_var)
    in_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
    _bind_drop(in_entry, infile_var)
    ttk.Button(frame, text="Browse", style="Small.TButton",
               command=browse_in).grid(row=0, column=2, sticky="e")

    ttk.Button(frame, text="Run Benchmark", command=do_benchmark).grid(
        row=1, column=0, columnspan=3, pady=(14, 10))

    result_text = tk.Text(
        frame, height=11, state="disabled",
        font=("Monospace", 9),
        bg=C["card"], fg=C["text"],
        insertbackground=C["text"],
        selectbackground=C["accent"], selectforeground="white",
        relief="flat", padx=10, pady=8,
        borderwidth=0)
    result_text.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(0, 4))
    frame.rowconfigure(2, weight=1)
    frame.columnconfigure(1, weight=1)


# ─── Preview / text dialog ────────────────────────────────────────────────────

def _show_text_dialog(parent, title: str, text: str):
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=C["bg"])
    win.resizable(True, True)
    win.minsize(500, 340)

    txt = tk.Text(
        win, font=("Monospace", 9),
        bg=C["card"], fg=C["text"],
        insertbackground=C["text"],
        selectbackground=C["accent"], selectforeground="white",
        wrap="none", width=80, height=20,
        relief="flat", padx=10, pady=8, borderwidth=0)
    sy = ttk.Scrollbar(win, command=txt.yview)
    sx = ttk.Scrollbar(win, orient="horizontal", command=txt.xview)
    txt.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)

    txt.grid(row=0, column=0, sticky="nsew")
    sy.grid(row=0, column=1, sticky="ns")
    sx.grid(row=1, column=0, sticky="ew")

    close_bar = tk.Frame(win, bg=C["bg"], pady=8)
    close_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
    ttk.Button(close_bar, text="Close", command=win.destroy).pack()

    win.rowconfigure(0, weight=1)
    win.columnconfigure(0, weight=1)

    txt.insert("1.0", text)
    txt.config(state="disabled")


# ─── Main launcher ────────────────────────────────────────────────────────────

def launch_gui():
    RootClass = TkinterDnD.Tk if HAS_DND else tk.Tk
    root = RootClass()
    root.title("SuprCompressr")
    root.minsize(620, 420)
    root.resizable(True, True)

    _apply_theme(root)

    # Header banner
    header = tk.Frame(root, bg=C["accent"], pady=14)
    header.pack(fill="x")
    tk.Label(header, text="SuprCompressr",
             bg=C["accent"], fg="white",
             font=("Helvetica", 16, "bold")).pack()
    tk.Label(header, text="extreme compression for Linux",
             bg=C["accent"], fg="#c7d2fe",
             font=("Helvetica", 9)).pack()

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)

    # Status bar
    bar = tk.Frame(root, bg=C["surface"], pady=7)
    bar.pack(fill="x")
    status_label = ttk.Label(bar, text="Ready", style="Sub.TLabel",
                              background=C["surface"])
    status_label.pack(side="left", padx=14)
    progress_bar = ttk.Progressbar(bar, mode="determinate", length=210)
    progress_bar.pack(side="right", padx=14)

    tab_defs = [
        ("  Compress  ",  _build_compress_tab),
        (" Decompress ",  _build_decompress_tab),
        ("   Batch    ",  _build_batch_tab),
        (".supr → .zip",  _build_convert_tab),
        (" Benchmark  ",  _build_benchmark_tab),
    ]
    for label, builder in tab_defs:
        f = ttk.Frame(notebook, padding=16)
        notebook.add(f, text=label)
        builder(f, root, status_label, progress_bar)

    root.mainloop()


if __name__ == "__main__":
    launch_gui()
