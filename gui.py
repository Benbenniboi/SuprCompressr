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

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

_result_queue: queue.Queue = queue.Queue()
_progress_queue: queue.Queue = queue.Queue()

# ─── Colour palette (matches mockup) ──────────────────────────────────────────

BG      = "#252830"   # main window
PANEL   = "#1d1f27"   # panel / sidebar
HEADER  = "#2a2d3a"   # panel header strip
BORDER  = "#3a3d4f"   # borders & separators
ACCENT  = "#4a8fd4"   # blue highlight
TEXT    = "#e8eaf0"   # primary text
SUBTEXT = "#7a7e9a"   # secondary / inactive
ENTRY   = "#1a1c24"   # input fields
BTN     = "#3d7fc4"   # button fill
BTN_HOV = "#2d6ab4"   # button hover

# ─── Format / level maps ──────────────────────────────────────────────────────

LEVEL_OPTS = [
    ("Fast (Lowest)",    1),
    ("Low",              3),
    ("Medium",           5),
    ("High",             7),
    ("Ultra (Highest)",  9),
]
LEVEL_NAMES = [n for n, _ in LEVEL_OPTS]
LEVEL_MAP   = {n: v for n, v in LEVEL_OPTS}

FMT_OPTS = [
    ("SUPR (Extreme)", "supr"),
    ("ZIP",            "zip"),
    ("GZ",             "gz"),
    ("BZ2",            "bz2"),
    ("XZ",             "xz"),
    ("ZST",            "zst"),
    ("TAR.GZ",         "tar.gz"),
    ("TAR.XZ",         "tar.xz"),
    ("7Z",             "7z"),
]
FMT_NAMES = [n for n, _ in FMT_OPTS]
FMT_MAP   = {n: v for n, v in FMT_OPTS}


# ─── Tiny style helpers ────────────────────────────────────────────────────────

def _lbl(parent, text, size=10, bold=False, color=TEXT, **kw):
    font = ("Helvetica", size, "bold" if bold else "normal")
    return tk.Label(parent, text=text, bg=kw.pop("bg", parent["bg"]),
                    fg=color, font=font, **kw)

def _btn(parent, text, cmd, wide=False, small=False, **kw):
    size = 9 if small else 11
    pad  = (10, 5) if small else (18, 10)
    b = tk.Button(parent, text=text, command=cmd,
                  bg=BTN, fg="white", activebackground=BTN_HOV,
                  activeforeground="white", relief="flat", bd=0,
                  font=("Helvetica", size, "bold"),
                  padx=pad[0], pady=pad[1], cursor="hand2", **kw)
    return b

def _sep(parent, orient="horizontal"):
    return tk.Frame(parent,
                    bg=BORDER,
                    height=1 if orient == "horizontal" else 0,
                    width=0 if orient == "horizontal" else 1)

def _combo(parent, var, values, width=22):
    style = ttk.Style()
    style.configure("Dark.TCombobox",
                    fieldbackground=ENTRY, background=HEADER,
                    foreground=TEXT, selectbackground=ACCENT,
                    selectforeground="white", arrowcolor=TEXT,
                    bordercolor=BORDER, lightcolor=BORDER,
                    darkcolor=BORDER, insertcolor=TEXT)
    style.map("Dark.TCombobox",
              fieldbackground=[("readonly", ENTRY)],
              foreground=[("readonly", TEXT)])
    cb = ttk.Combobox(parent, textvariable=var, values=values,
                      state="readonly", width=width, style="Dark.TCombobox")
    parent.option_add("*TCombobox*Listbox.background",       ENTRY)
    parent.option_add("*TCombobox*Listbox.foreground",       TEXT)
    parent.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    parent.option_add("*TCombobox*Listbox.selectForeground", "white")
    return cb

def _entry(parent, var, width=28):
    e = tk.Entry(parent, textvariable=var, bg=ENTRY, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 font=("Helvetica", 10), bd=0,
                 highlightbackground=BORDER, highlightthickness=1,
                 highlightcolor=ACCENT)
    return e


# ─── Threading helpers ─────────────────────────────────────────────────────────

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

def _start_op(root, btn, status_var, pbar, fn, *args, **kwargs):
    while not _result_queue.empty():
        _result_queue.get_nowait()
    while not _progress_queue.empty():
        _progress_queue.get_nowait()
    btn.config(state="disabled")
    status_var.set("Working…")
    pbar.config(mode="indeterminate")
    pbar.start(10)
    threading.Thread(target=_run_in_thread, args=(fn, *args),
                     kwargs=kwargs, daemon=True).start()
    root.after(100, _poll, root, btn, status_var, pbar)

def _poll(root, btn, status_var, pbar):
    try:
        while True:
            pct = _progress_queue.get_nowait()
            if pbar.cget("mode") == "indeterminate":
                pbar.stop()
                pbar.config(mode="determinate")
            pbar["value"] = pct
    except queue.Empty:
        pass
    try:
        kind, msg = _result_queue.get_nowait()
        pbar.stop()
        pbar.config(mode="determinate", value=0)
        btn.config(state="normal")
        if kind == "ok":
            status_var.set("Done.")
            messagebox.showinfo("Result", msg.strip() or "Complete.")
        else:
            status_var.set("Error.")
            messagebox.showerror("Error", msg)
    except queue.Empty:
        root.after(100, _poll, root, btn, status_var, pbar)


# ─── Shared file-list helpers ──────────────────────────────────────────────────

def _clean(val: str) -> Optional[str]:
    v = val.strip().strip("'\"")
    return str(Path(v).expanduser()) if v else None

def _fmt_size(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"

def _update_info(file_list: list, info_var: tk.StringVar):
    n = len(file_list)
    if n == 0:
        info_var.set("No files selected")
        return
    total = sum(Path(f).stat().st_size for f in file_list if Path(f).exists())
    info_var.set(f"Files: {n}  |  Original Size: {_fmt_size(total)}")


# ─── Drop zone ────────────────────────────────────────────────────────────────

def _make_drop_zone(parent, on_browse, on_drop=None):
    canvas = tk.Canvas(parent, bg=PANEL, highlightthickness=0,
                       height=130, cursor="hand2")

    def _draw(event=None):
        canvas.delete("all")
        w = canvas.winfo_width() or 420
        h = canvas.winfo_height() or 130
        # Dashed border
        canvas.create_rectangle(10, 10, w - 10, h - 10,
                                 outline=ACCENT, dash=(8, 5), width=1)
        # Icon (simple up-arrow)
        cx = w // 2
        canvas.create_text(cx, h // 2 - 20, text="Select Files to Compress",
                            fill=TEXT, font=("Helvetica", 12, "bold"))
        canvas.create_text(cx, h // 2 + 10,
                            text="\u2191  Drag & Drop or Browse Files",
                            fill=ACCENT, font=("Helvetica", 10))

    canvas.bind("<Configure>", _draw)
    canvas.bind("<Button-1>", lambda e: on_browse())

    if HAS_DND and on_drop:
        canvas.drop_target_register(DND_FILES)
        canvas.dnd_bind("<<Drop>>", on_drop)

    return canvas


# ─── Panel header ─────────────────────────────────────────────────────────────

def _panel_header(parent, title):
    h = tk.Frame(parent, bg=HEADER, pady=10)
    h.pack(fill="x")
    tk.Label(h, text=f"  {title}", bg=HEADER, fg=TEXT,
             font=("Helvetica", 11, "bold")).pack(side="left")
    return h


# ─── File listbox ─────────────────────────────────────────────────────────────

def _make_file_listbox(parent):
    sub = tk.Frame(parent, bg=HEADER, pady=7)
    sub.pack(fill="x")
    tk.Label(sub, text="  Files to Compress", bg=HEADER, fg=SUBTEXT,
             font=("Helvetica", 9, "bold")).pack(side="left")

    frame = tk.Frame(parent, bg=PANEL)
    frame.pack(fill="both", expand=True)

    sb = tk.Scrollbar(frame, bg=PANEL, troughcolor=PANEL,
                      activebackground=ACCENT, relief="flat", bd=0)
    sb.pack(side="right", fill="y")

    lb = tk.Listbox(frame, bg=PANEL, fg=TEXT,
                    selectbackground=ACCENT, selectforeground="white",
                    font=("Helvetica", 10), borderwidth=0,
                    highlightthickness=0, activestyle="none",
                    yscrollcommand=sb.set, relief="flat")
    lb.pack(fill="both", expand=True, padx=(8, 0), pady=4)
    sb.config(command=lb.yview)
    return lb


# ─── Settings row helper ───────────────────────────────────────────────────────

def _setting_row(parent, label, pady=8):
    row = tk.Frame(parent, bg=PANEL)
    row.pack(fill="x", padx=16, pady=(pady, 0))
    tk.Label(row, text=label, bg=PANEL, fg=SUBTEXT,
             font=("Helvetica", 9), width=20, anchor="w").pack(side="left")
    widget_frame = tk.Frame(row, bg=PANEL)
    widget_frame.pack(side="left", fill="x", expand=True)
    return widget_frame


# ─── Compress mode ─────────────────────────────────────────────────────────────

def _build_compress(parent, root, status_var, info_var, pbar):
    file_list: list[str] = []

    # ── Left panel ──
    left = tk.Frame(parent, bg=PANEL, width=380)
    left.pack(side="left", fill="both", expand=True)
    left.pack_propagate(False)
    _panel_header(left, "File Selection")

    def browse():
        paths = filedialog.askopenfilenames(title="Select files or a folder")
        if paths:
            for p in paths:
                if p not in file_list:
                    file_list.append(p)
                    lb.insert("end", f"  {Path(p).name}")
            _update_info(file_list, info_var)

    def browse_folder():
        p = filedialog.askdirectory(title="Select folder")
        if p and p not in file_list:
            file_list.append(p)
            lb.insert("end", f"  {Path(p).name}")
            _update_info(file_list, info_var)

    def on_drop(event):
        raw = event.data.strip()
        paths = raw.split("} {") if "{" in raw else raw.split()
        paths = [p.strip("{}") for p in paths]
        for p in paths:
            if p not in file_list:
                file_list.append(p)
                lb.insert("end", f"  {Path(p).name}")
        _update_info(file_list, info_var)

    drop = _make_drop_zone(left, browse, on_drop if HAS_DND else None)
    drop.pack(fill="x", padx=14, pady=12)

    folder_btn = tk.Button(left, text="+ Add Folder", command=browse_folder,
                           bg=HEADER, fg=ACCENT, relief="flat", bd=0,
                           font=("Helvetica", 9), padx=10, pady=4,
                           cursor="hand2", activebackground=HEADER,
                           activeforeground=TEXT)
    folder_btn.pack(anchor="e", padx=14, pady=(0, 6))

    _sep(left).pack(fill="x", padx=14)

    lb = _make_file_listbox(left)

    def remove_selected(event=None):
        sel = lb.curselection()
        for i in reversed(sel):
            lb.delete(i)
            file_list.pop(i)
        _update_info(file_list, info_var)

    def clear_all():
        lb.delete(0, "end")
        file_list.clear()
        _update_info(file_list, info_var)

    action_row = tk.Frame(left, bg=PANEL)
    action_row.pack(fill="x", padx=10, pady=6)
    tk.Button(action_row, text="Remove Selected", command=remove_selected,
              bg=PANEL, fg=SUBTEXT, relief="flat", bd=0,
              font=("Helvetica", 8), cursor="hand2",
              activebackground=PANEL, activeforeground=TEXT).pack(side="left")
    tk.Button(action_row, text="Clear All", command=clear_all,
              bg=PANEL, fg=SUBTEXT, relief="flat", bd=0,
              font=("Helvetica", 8), cursor="hand2",
              activebackground=PANEL, activeforeground=TEXT).pack(side="right")
    lb.bind("<Delete>", remove_selected)

    # ── Divider ──
    _sep(parent, "vertical").pack(side="left", fill="y")

    # ── Right panel ──
    right = tk.Frame(parent, bg=PANEL, width=300)
    right.pack(side="left", fill="both", expand=True)
    right.pack_propagate(False)
    _panel_header(right, "Compression Settings")

    fmt_var   = tk.StringVar(value="ZIP")
    level_var = tk.StringVar(value="Ultra (Highest)")
    out_var   = tk.StringVar()

    tk.Frame(right, bg=PANEL, height=10).pack()

    # Format
    wf = _setting_row(right, "Compression Format:")
    _combo(wf, fmt_var, FMT_NAMES).pack(side="left")

    # Level
    wl = _setting_row(right, "Compression Level:")
    _combo(wl, level_var, LEVEL_NAMES).pack(side="left")

    # Output dir
    wo = _setting_row(right, "Output Directory:")
    _entry(wo, out_var, width=18).pack(side="left", fill="x", expand=True)
    tk.Button(wo, text="Browse",
              command=lambda: out_var.set(filedialog.askdirectory() or out_var.get()),
              bg=HEADER, fg=TEXT, relief="flat", bd=0,
              font=("Helvetica", 9), padx=8, pady=4, cursor="hand2",
              activebackground=BORDER, activeforeground=TEXT).pack(side="left", padx=(6, 0))

    tk.Frame(right, bg=PANEL, height=18).pack()
    _sep(right).pack(fill="x", padx=16, pady=0)
    tk.Frame(right, bg=PANEL, height=18).pack()

    def do_compress():
        if not file_list:
            messagebox.showerror("Error", "No files selected.")
            return
        fmt   = FMT_MAP.get(fmt_var.get(), "zip")
        level = LEVEL_MAP.get(level_var.get(), 9)
        out   = _clean(out_var.get())
        if len(file_list) == 1:
            out_path = None
            if out:
                name = Path(file_list[0]).name
                ext  = {"supr": ".supr","zip": ".zip","gz": ".gz","bz2": ".bz2",
                        "xz": ".xz","zst": ".zst","tar.gz": ".tar.gz",
                        "tar.xz": ".tar.xz","7z": ".7z"}.get(fmt, "")
                out_path = str(Path(out) / (name + ext))
            _start_op(root, start_btn, status_var, pbar,
                      core.perform_compression,
                      file_list[0], fmt, level, out_path, _progress_cb)
        else:
            _start_op(root, start_btn, status_var, pbar,
                      core.perform_batch_compression,
                      list(file_list), fmt, level, out, _progress_cb)

    start_btn = _btn(right, "Start Compression", do_compress)
    start_btn.pack(fill="x", padx=16, pady=(0, 6))


# ─── Decompress mode ───────────────────────────────────────────────────────────

def _build_decompress(parent, root, status_var, info_var, pbar):
    left = tk.Frame(parent, bg=PANEL, width=380)
    left.pack(side="left", fill="both", expand=True)
    left.pack_propagate(False)
    _panel_header(left, "File Selection")

    in_var  = tk.StringVar()
    out_var = tk.StringVar()

    def browse_in():
        p = filedialog.askopenfilename(
            filetypes=[("Archives", "*.supr *.zip *.gz *.bz2 *.xz *.zst *.7z"),
                       ("All", "*")])
        if p:
            in_var.set(p)
            info_var.set(f"Selected: {Path(p).name}")

    def on_drop(event):
        p = event.data.strip("{}").strip()
        in_var.set(p)
        info_var.set(f"Selected: {Path(p).name}")

    drop = _make_drop_zone(left, browse_in, on_drop if HAS_DND else None)
    drop.pack(fill="x", padx=14, pady=12)

    row1 = tk.Frame(left, bg=PANEL)
    row1.pack(fill="x", padx=14, pady=6)
    tk.Label(row1, text="File:", bg=PANEL, fg=SUBTEXT,
             font=("Helvetica", 9), width=12, anchor="w").pack(side="left")
    _entry(row1, in_var).pack(side="left", fill="x", expand=True, padx=(0, 6))

    row2 = tk.Frame(left, bg=PANEL)
    row2.pack(fill="x", padx=14, pady=6)
    tk.Label(row2, text="Output (opt):", bg=PANEL, fg=SUBTEXT,
             font=("Helvetica", 9), width=12, anchor="w").pack(side="left")
    _entry(row2, out_var).pack(side="left", fill="x", expand=True, padx=(0, 6))
    tk.Button(row2, text="Browse",
              command=lambda: out_var.set(filedialog.asksaveasfilename() or out_var.get()),
              bg=HEADER, fg=TEXT, relief="flat", bd=0,
              font=("Helvetica", 9), padx=8, pady=4, cursor="hand2",
              activebackground=BORDER, activeforeground=TEXT).pack(side="left")

    _sep(parent, "vertical").pack(side="left", fill="y")

    right = tk.Frame(parent, bg=PANEL, width=300)
    right.pack(side="left", fill="both", expand=True)
    right.pack_propagate(False)
    _panel_header(right, "Actions")

    tk.Frame(right, bg=PANEL, height=20).pack()

    def do_decompress():
        _start_op(root, decomp_btn, status_var, pbar,
                  core.perform_decompression,
                  _clean(in_var.get()), _clean(out_var.get()))

    def do_preview():
        p = _clean(in_var.get())
        if not p:
            messagebox.showerror("Error", "Select a file first.")
            return
        _show_text("Preview", core.preview_archive(p))

    def do_verify():
        p = _clean(in_var.get())
        if not p:
            messagebox.showerror("Error", "Select a file first.")
            return
        ok, msg = core.verify_archive(p)
        (messagebox.showinfo if ok else messagebox.showerror)("Verify", msg)

    decomp_btn = _btn(right, "Decompress", do_decompress)
    decomp_btn.pack(fill="x", padx=16, pady=(0, 8))

    preview_btn = tk.Button(right, text="Preview Contents",
                            command=do_preview, bg=HEADER, fg=ACCENT,
                            relief="flat", bd=0, font=("Helvetica", 10),
                            padx=18, pady=8, cursor="hand2",
                            activebackground=BORDER, activeforeground=TEXT)
    preview_btn.pack(fill="x", padx=16, pady=(0, 8))

    verify_btn = tk.Button(right, text="Verify Integrity",
                           command=do_verify, bg=HEADER, fg=ACCENT,
                           relief="flat", bd=0, font=("Helvetica", 10),
                           padx=18, pady=8, cursor="hand2",
                           activebackground=BORDER, activeforeground=TEXT)
    verify_btn.pack(fill="x", padx=16)


# ─── Convert mode ──────────────────────────────────────────────────────────────

def _build_convert(parent, root, status_var, info_var, pbar):
    left = tk.Frame(parent, bg=PANEL, width=380)
    left.pack(side="left", fill="both", expand=True)
    left.pack_propagate(False)
    _panel_header(left, "SUPR to ZIP Conversion")

    in_var  = tk.StringVar()
    out_var = tk.StringVar()

    def browse_in():
        p = filedialog.askopenfilename(filetypes=[("SUPR", "*.supr"), ("All", "*")])
        if p:
            in_var.set(p)
            info_var.set(f"Selected: {Path(p).name}")

    def on_drop(event):
        p = event.data.strip("{}").strip()
        in_var.set(p)

    drop = _make_drop_zone(left, browse_in, on_drop if HAS_DND else None)
    drop.pack(fill="x", padx=14, pady=12)

    row1 = tk.Frame(left, bg=PANEL)
    row1.pack(fill="x", padx=14, pady=6)
    tk.Label(row1, text=".supr file:", bg=PANEL, fg=SUBTEXT,
             font=("Helvetica", 9), width=14, anchor="w").pack(side="left")
    _entry(row1, in_var).pack(side="left", fill="x", expand=True)

    row2 = tk.Frame(left, bg=PANEL)
    row2.pack(fill="x", padx=14, pady=6)
    tk.Label(row2, text="Output .zip:", bg=PANEL, fg=SUBTEXT,
             font=("Helvetica", 9), width=14, anchor="w").pack(side="left")
    _entry(row2, out_var).pack(side="left", fill="x", expand=True, padx=(0, 6))
    tk.Button(row2, text="Browse",
              command=lambda: out_var.set(
                  filedialog.asksaveasfilename(defaultextension=".zip") or out_var.get()),
              bg=HEADER, fg=TEXT, relief="flat", bd=0,
              font=("Helvetica", 9), padx=8, pady=4, cursor="hand2",
              activebackground=BORDER, activeforeground=TEXT).pack(side="left")

    tk.Label(left,
             text="  Warning: resulting ZIP expands to full original size.",
             bg=PANEL, fg=SUBTEXT, font=("Helvetica", 8),
             wraplength=340, justify="left").pack(anchor="w", padx=14, pady=(8, 0))

    _sep(parent, "vertical").pack(side="left", fill="y")

    right = tk.Frame(parent, bg=PANEL, width=300)
    right.pack(side="left", fill="both", expand=True)
    right.pack_propagate(False)
    _panel_header(right, "Convert")

    tk.Frame(right, bg=PANEL, height=20).pack()

    def do_convert():
        _start_op(root, conv_btn, status_var, pbar,
                  core.convert_supr_to_zip,
                  _clean(in_var.get()), _clean(out_var.get()), _progress_cb)

    conv_btn = _btn(right, "Convert to ZIP", do_convert)
    conv_btn.pack(fill="x", padx=16)


# ─── Benchmark mode ────────────────────────────────────────────────────────────

def _build_benchmark(parent, root, status_var, info_var, pbar):
    left = tk.Frame(parent, bg=PANEL, width=320)
    left.pack(side="left", fill="y")
    left.pack_propagate(False)
    _panel_header(left, "File Selection")

    in_var = tk.StringVar()

    def browse():
        p = filedialog.askopenfilename()
        if p:
            in_var.set(p)
            info_var.set(f"Selected: {Path(p).name}")

    def on_drop(event):
        p = event.data.strip("{}").strip()
        in_var.set(p)

    drop = _make_drop_zone(left, browse, on_drop if HAS_DND else None)
    drop.pack(fill="x", padx=14, pady=12)

    row = tk.Frame(left, bg=PANEL)
    row.pack(fill="x", padx=14, pady=6)
    tk.Label(row, text="File:", bg=PANEL, fg=SUBTEXT,
             font=("Helvetica", 9), width=6, anchor="w").pack(side="left")
    _entry(row, in_var).pack(side="left", fill="x", expand=True)

    tk.Frame(left, bg=PANEL, height=16).pack()

    def do_bench():
        p = _clean(in_var.get())
        if not p:
            messagebox.showerror("Error", "Select a file first.")
            return
        status_var.set("Benchmarking…")
        result_txt.config(state="normal")
        result_txt.delete("1.0", "end")
        result_txt.insert("end", "Running…\n")
        result_txt.config(state="disabled")

        def run():
            result = core.benchmark_file(p)
            _result_queue.put(("benchmark", result))

        threading.Thread(target=run, daemon=True).start()
        root.after(200, _poll_bench)

    def _poll_bench():
        try:
            kind, msg = _result_queue.get_nowait()
            if kind == "benchmark":
                result_txt.config(state="normal")
                result_txt.delete("1.0", "end")
                result_txt.insert("end", msg)
                result_txt.config(state="disabled")
                status_var.set("Benchmark complete.")
            else:
                _result_queue.put((kind, msg))
        except queue.Empty:
            root.after(200, _poll_bench)

    bench_btn = _btn(left, "Run Benchmark", do_bench)
    bench_btn.pack(fill="x", padx=14)

    _sep(parent, "vertical").pack(side="left", fill="y")

    right = tk.Frame(parent, bg=PANEL)
    right.pack(side="left", fill="both", expand=True)
    _panel_header(right, "Results")

    result_txt = tk.Text(right, bg=ENTRY, fg=TEXT, font=("Monospace", 9),
                         relief="flat", bd=0, padx=12, pady=10,
                         insertbackground=TEXT, state="disabled",
                         selectbackground=ACCENT, selectforeground="white")
    result_txt.pack(fill="both", expand=True, padx=10, pady=10)


# ─── Text viewer dialog ────────────────────────────────────────────────────────

def _show_text(title: str, text: str):
    win = tk.Toplevel()
    win.title(title)
    win.configure(bg=BG)
    win.minsize(520, 360)

    txt = tk.Text(win, bg=ENTRY, fg=TEXT, font=("Monospace", 9),
                  relief="flat", bd=0, padx=12, pady=10, wrap="none",
                  selectbackground=ACCENT, selectforeground="white")
    sy = tk.Scrollbar(win, bg=PANEL, troughcolor=PANEL, command=txt.yview)
    sx = tk.Scrollbar(win, orient="horizontal", bg=PANEL,
                      troughcolor=PANEL, command=txt.xview)
    txt.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
    txt.grid(row=0, column=0, sticky="nsew")
    sy.grid(row=0, column=1, sticky="ns")
    sx.grid(row=1, column=0, sticky="ew")

    bar = tk.Frame(win, bg=BG, pady=8)
    bar.grid(row=2, column=0, columnspan=2, sticky="ew")
    tk.Button(bar, text="Close", command=win.destroy,
              bg=BTN, fg="white", relief="flat", bd=0,
              font=("Helvetica", 10, "bold"), padx=20, pady=6,
              cursor="hand2", activebackground=BTN_HOV,
              activeforeground="white").pack()

    win.rowconfigure(0, weight=1)
    win.columnconfigure(0, weight=1)
    txt.insert("1.0", text)
    txt.config(state="disabled")


# ─── Nav bar ──────────────────────────────────────────────────────────────────

def _make_nav(root_frame, modes: list, on_select):
    nav = tk.Frame(root_frame, bg=PANEL, pady=0)
    nav.pack(fill="x")

    # Logo
    logo = tk.Frame(nav, bg=PANEL, padx=16)
    logo.pack(side="left")
    tk.Label(logo, text="SuprCompressr", bg=PANEL, fg=TEXT,
             font=("Helvetica", 12, "bold")).pack(pady=12)

    _sep(nav, "vertical").pack(side="left", fill="y", pady=8)

    btns: dict = {}

    def select(name):
        for n, (b, ind) in btns.items():
            active = (n == name)
            b.config(fg=ACCENT if active else SUBTEXT)
            ind.config(bg=ACCENT if active else PANEL)
        on_select(name)

    for name in modes:
        col = tk.Frame(nav, bg=PANEL)
        col.pack(side="left")
        b = tk.Button(col, text=name, bg=PANEL, fg=SUBTEXT,
                      relief="flat", bd=0, padx=18, pady=14,
                      font=("Helvetica", 10), cursor="hand2",
                      activebackground=PANEL, activeforeground=ACCENT,
                      command=lambda n=name: select(n))
        b.pack(fill="x")
        ind = tk.Frame(col, bg=PANEL, height=2)
        ind.pack(fill="x")
        btns[name] = (b, ind)

    select(modes[0])
    return select


# ─── Main launcher ─────────────────────────────────────────────────────────────

def launch_gui():
    RootClass = TkinterDnD.Tk if HAS_DND else tk.Tk
    root = RootClass()
    root.title("SuprCompressr")
    root.configure(bg=BG)
    root.minsize(700, 500)
    root.resizable(True, True)

    # ttk style for progressbar
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TProgressbar",
                    troughcolor=BORDER, background=ACCENT,
                    borderwidth=0, lightcolor=ACCENT, darkcolor=ACCENT,
                    thickness=4)

    # ── Status / info vars (shared across modes) ──
    status_var = tk.StringVar(value="Ready to Compress")
    info_var   = tk.StringVar(value="No files selected")

    # ── Nav bar ──
    MODES = ["Compress", "Decompress", ".supr → .zip", "Benchmark"]

    _sep(root).pack(fill="x")  # top border under nav

    # ── Content area ──
    content = tk.Frame(root, bg=BG)
    content.pack(fill="both", expand=True)

    mode_frames: dict[str, tk.Frame] = {}

    def show_mode(name):
        for n, f in mode_frames.items():
            if n == name:
                f.pack(fill="both", expand=True)
            else:
                f.pack_forget()
        if name == "Compress":
            status_var.set("Ready to Compress")
        else:
            status_var.set("Ready")

    # Build all mode frames
    builders = {
        "Compress":      _build_compress,
        "Decompress":    _build_decompress,
        ".supr → .zip":  _build_convert,
        "Benchmark":     _build_benchmark,
    }

    # Build progress bar (needed by builders)
    pbar = ttk.Progressbar(root, mode="determinate", style="TProgressbar")

    for name, builder in builders.items():
        outer = tk.Frame(content, bg=PANEL)
        mode_frames[name] = outer
        builder(outer, root, status_var, info_var, pbar)

    # Nav (built after frames so show_mode works)
    _make_nav(root, MODES, show_mode)
    _sep(root).pack(fill="x")

    # Reorder: nav → sep → content → status
    # (pack order: nav first, then content, then status bar)
    # Fix pack order by using place or rebuilding — easier: just show first mode
    show_mode("Compress")

    # ── Status bar ──
    sbar = tk.Frame(root, bg=PANEL, pady=0)
    sbar.pack(fill="x", side="bottom")

    _sep(sbar).pack(fill="x")

    inner = tk.Frame(sbar, bg=PANEL)
    inner.pack(fill="x", padx=14, pady=7)

    tk.Label(inner, textvariable=status_var, bg=PANEL, fg=TEXT,
             font=("Helvetica", 9, "bold"), width=18,
             anchor="w").pack(side="left")

    pbar.pack(side="left", fill="x", expand=True, padx=14)

    tk.Label(inner, textvariable=info_var, bg=PANEL, fg=SUBTEXT,
             font=("Helvetica", 8)).pack(side="right")

    # Rebuild pack order: nav needs to be at top
    # Destroy and rebuild nav in correct position
    for widget in root.pack_slaves():
        widget.pack_forget()

    nav_frame = tk.Frame(root, bg=PANEL)
    nav_frame.pack(fill="x", side="top")
    _make_nav(nav_frame, MODES, show_mode)

    _sep(root).pack(fill="x", side="top")
    content.pack(fill="both", expand=True, side="top")
    sbar.pack(fill="x", side="bottom")

    show_mode("Compress")

    root.mainloop()


if __name__ == "__main__":
    launch_gui()
