#!/usr/bin/env python3
"""
SuprCompressr - Python app for Linux
Extreme compression with SUPER mode, folder support, batch, preview, verify, benchmark.
"""

import gzip
import bz2
import lzma
import tarfile
import tempfile
import time
import zlib
from pathlib import Path
from typing import Callable, Optional
from zipfile import ZIP_DEFLATED, ZipFile

try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

try:
    import py7zr
    HAS_7Z = True
except ImportError:
    HAS_7Z = False

MAGIC_SUPR = b"SUPR\x01"  # 5 bytes
ProgressCB = Callable[[int, int], None]  # (current, total)

ALL_FORMATS = ["supr", "zip", "gz", "bz2", "xz", "zst", "tar.gz", "tar.xz", "7z"]
FOLDER_FORMATS = ["zip", "tar.gz", "tar.xz", "7z"]


# ─── SUPR format ──────────────────────────────────────────────────────────────

def is_uniform(data: bytes):
    if len(data) == 0:
        return False, None
    val = data[0]
    return (True, val) if all(b == val for b in data) else (False, None)


def compress_supr(data: bytes) -> bytes:
    uniform, val = is_uniform(data)
    if uniform and val is not None:
        return MAGIC_SUPR + b"\x00" + bytes([val]) + len(data).to_bytes(8, "big")
    if HAS_ZSTD:
        return MAGIC_SUPR + b"\x01" + zstd.ZstdCompressor(level=22).compress(data)
    return MAGIC_SUPR + b"\x02" + zlib.compress(data, level=9)


def decompress_supr(data: bytes) -> bytes:
    if not data.startswith(MAGIC_SUPR):
        raise ValueError("Not a SUPER file")
    typ = data[5]
    payload = data[6:]
    if typ == 0:
        val = payload[0]
        length = int.from_bytes(payload[1:9], "big")
        return bytes([val]) * length
    if typ == 1:
        if not HAS_ZSTD:
            raise ImportError("Install zstandard: pip install zstandard")
        return zstd.ZstdDecompressor().decompress(payload)
    if typ == 2:
        return zlib.decompress(payload)
    raise ValueError("Unknown SUPER type")


# ─── Path helpers ──────────────────────────────────────────────────────────────

def clean_path(raw: str) -> Optional[str]:
    if not raw:
        return None
    p = raw.strip().strip("'\"")
    return str(Path(p).expanduser()) if p else None


def get_archive_type(path: Path) -> str:
    """Return canonical archive type string, handling double extensions."""
    name = path.name.lower()
    for ext in (".tar.gz", ".tar.xz", ".tar.bz2"):
        if name.endswith(ext):
            return ext[1:]  # "tar.gz", etc.
    return path.suffix.lstrip(".").lower()


def _output_path(input_p: Path, fmt: str, output_path: Optional[str]) -> Path:
    if output_path:
        return Path(output_path)
    suffix_map = {
        "zip": ".zip", "supr": ".supr", "gz": ".gz", "bz2": ".bz2",
        "xz": ".xz", "zst": ".zst", "tar.gz": ".tar.gz",
        "tar.xz": ".tar.xz", "tar.bz2": ".tar.bz2", "7z": ".7z",
    }
    suffix = suffix_map.get(fmt, f".{fmt}")
    base = input_p if not input_p.is_dir() else input_p
    return Path(str(base) + suffix) if input_p.is_dir() else input_p.with_suffix(suffix)


def _print_ratio(orig: int, comp: int):
    ratio = orig / comp if comp > 0 else 0
    print(f"Original  : {orig:,} bytes")
    print(f"Compressed: {comp:,} bytes")
    print(f"Ratio     : {ratio:,.0f}:1")
    if ratio > 100_000:
        print("🎉 INSANE ratio!")
    elif ratio > 10_000:
        print("🚀 Extreme ratio!")


# ─── Compression ──────────────────────────────────────────────────────────────

def _compress_zip(input_p: Path, out_p: Path, level: int, cb: Optional[ProgressCB]):
    with ZipFile(out_p, "w", ZIP_DEFLATED, compresslevel=level) as z:
        if input_p.is_dir():
            files = [f for f in input_p.rglob("*") if f.is_file()]
            for i, f in enumerate(files):
                z.write(f, f.relative_to(input_p.parent))
                if cb:
                    cb(i + 1, len(files))
        else:
            z.write(input_p, input_p.name)
            if cb:
                cb(1, 1)


def _compress_tar(input_p: Path, out_p: Path, fmt: str, cb: Optional[ProgressCB]):
    mode_map = {"tar.gz": "w:gz", "tar.xz": "w:xz", "tar.bz2": "w:bz2"}
    mode = mode_map.get(fmt, "w:gz")
    items = [input_p] if input_p.is_file() else [f for f in input_p.rglob("*") if f.is_file()]
    with tarfile.open(out_p, mode) as tar:
        for i, f in enumerate(items):
            tar.add(f, arcname=f.relative_to(input_p.parent) if input_p.is_dir() else f.name)
            if cb:
                cb(i + 1, len(items))


def _compress_7z(input_p: Path, out_p: Path, cb: Optional[ProgressCB]):
    with py7zr.SevenZipFile(out_p, "w") as z:
        if input_p.is_dir():
            files = [f for f in input_p.rglob("*") if f.is_file()]
            for i, f in enumerate(files):
                z.write(f, f.relative_to(input_p.parent))
                if cb:
                    cb(i + 1, len(files))
        else:
            z.write(input_p, input_p.name)
            if cb:
                cb(1, 1)


def perform_compression(input_path: Optional[str], fmt: str, level: int,
                        output_path: Optional[str] = None, progress_cb: Optional[ProgressCB] = None):
    if not input_path:
        print("❌ No file path given!")
        return
    input_p = Path(input_path)
    if not input_p.exists():
        print(f"❌ Not found: {input_p.resolve()}")
        return

    if input_p.is_dir() and fmt not in FOLDER_FORMATS:
        print(f"❌ Folders can only be compressed with: {', '.join(FOLDER_FORMATS)}")
        return

    if fmt == "7z" and not HAS_7Z:
        print("❌ py7zr not installed. Run: pip install py7zr")
        return

    out_p = _output_path(input_p, fmt, output_path)

    # Get original size
    if input_p.is_dir():
        orig_size = sum(f.stat().st_size for f in input_p.rglob("*") if f.is_file())
    else:
        orig_size = input_p.stat().st_size

    if fmt == "supr":
        data = input_p.read_bytes()
        compressed = compress_supr(data)
        out_p.write_bytes(compressed)
        comp_size = len(compressed)
    elif fmt == "zip":
        _compress_zip(input_p, out_p, level, progress_cb)
        comp_size = out_p.stat().st_size
    elif fmt in ("tar.gz", "tar.xz", "tar.bz2"):
        _compress_tar(input_p, out_p, fmt, progress_cb)
        comp_size = out_p.stat().st_size
    elif fmt == "7z":
        _compress_7z(input_p, out_p, progress_cb)
        comp_size = out_p.stat().st_size
    elif fmt == "gz":
        out_p.write_bytes(gzip.compress(input_p.read_bytes(), compresslevel=level))
        comp_size = out_p.stat().st_size
    elif fmt == "bz2":
        out_p.write_bytes(bz2.compress(input_p.read_bytes(), compresslevel=level))
        comp_size = out_p.stat().st_size
    elif fmt == "xz":
        out_p.write_bytes(lzma.compress(input_p.read_bytes(), preset=min(9, level)))
        comp_size = out_p.stat().st_size
    elif fmt == "zst":
        if not HAS_ZSTD:
            print("⚠️  zstandard not installed → using gzip instead")
            out_p.write_bytes(gzip.compress(input_p.read_bytes(), compresslevel=9))
        else:
            z_level = min(22, max(1, level * 2))
            out_p.write_bytes(zstd.ZstdCompressor(level=z_level).compress(input_p.read_bytes()))
        comp_size = out_p.stat().st_size
    else:
        print("❌ Unknown format")
        return

    print(f"\n✅ SUCCESS!")
    _print_ratio(orig_size, comp_size)
    print(f"Saved to  : {out_p.resolve()}")


# ─── Batch compression ────────────────────────────────────────────────────────

def perform_batch_compression(file_list: list[str], fmt: str, level: int,
                               output_dir: Optional[str] = None,
                               progress_cb: Optional[ProgressCB] = None):
    if not file_list:
        print("❌ No files given!")
        return

    out_dir = Path(output_dir) if output_dir else None
    total = len(file_list)

    print(f"\nBatch compressing {total} file(s) to {fmt}...")
    success, failed = 0, 0

    for i, path in enumerate(file_list):
        input_p = Path(path)
        if not input_p.exists():
            print(f"  ⚠️  Skipping (not found): {path}")
            failed += 1
        else:
            dest_dir = out_dir or input_p.parent
            out_p = str(_output_path(input_p, fmt, str(dest_dir / (input_p.name + ".tmp"))))
            out_p = str(_output_path(input_p, fmt, None))
            if out_dir:
                out_p = str(out_dir / Path(out_p).name)
            try:
                perform_compression(str(input_p), fmt, level, out_p)
                success += 1
            except Exception as e:
                print(f"  ❌ Failed {input_p.name}: {e}")
                failed += 1

        if progress_cb:
            progress_cb(i + 1, total)

    print(f"\nBatch done: {success} succeeded, {failed} failed.")


# ─── Decompression ────────────────────────────────────────────────────────────

def perform_decompression(input_path: Optional[str], output_path: Optional[str] = None):
    if not input_path:
        print("❌ No file path given!")
        return
    input_p = Path(input_path)
    if not input_p.exists():
        print(f"❌ File not found: {input_p.resolve()}")
        return

    archive_type = get_archive_type(input_p)

    if output_path is None:
        if archive_type in ("tar.gz", "tar.xz", "tar.bz2"):
            output_path = str(input_p.parent / input_p.name.replace(".tar.gz", "")
                              .replace(".tar.xz", "").replace(".tar.bz2", ""))
        else:
            output_path = str(input_p.with_suffix(".decompressed"))
    out_p = Path(output_path)

    try:
        if archive_type == "supr":
            out_p.write_bytes(decompress_supr(input_p.read_bytes()))
            print(f"\n✅ Decompressed to: {out_p.resolve()}")

        elif archive_type == "zip":
            with ZipFile(input_p, "r") as z:
                names = z.namelist()
                if len(names) == 1:
                    out_p.write_bytes(z.read(names[0]))
                    print(f"\n✅ Decompressed {len(z.read(names[0])):,} bytes → {out_p.resolve()}")
                else:
                    out_p.mkdir(parents=True, exist_ok=True)
                    z.extractall(out_p)
                    print(f"\n✅ Extracted {len(names)} files → {out_p.resolve()}")

        elif archive_type in ("tar.gz", "tar.xz", "tar.bz2"):
            out_p.mkdir(parents=True, exist_ok=True)
            with tarfile.open(input_p, "r:*") as tar:
                tar.extractall(out_p)
                print(f"\n✅ Extracted {len(tar.getmembers())} files → {out_p.resolve()}")

        elif archive_type == "7z":
            if not HAS_7Z:
                print("❌ py7zr not installed. Run: pip install py7zr")
                return
            out_p.mkdir(parents=True, exist_ok=True)
            with py7zr.SevenZipFile(input_p, "r") as z:
                z.extractall(out_p)
            print(f"\n✅ Extracted → {out_p.resolve()}")

        elif archive_type == "gz":
            out_p.write_bytes(gzip.decompress(input_p.read_bytes()))
            print(f"\n✅ Decompressed → {out_p.resolve()}")

        elif archive_type == "bz2":
            out_p.write_bytes(bz2.decompress(input_p.read_bytes()))
            print(f"\n✅ Decompressed → {out_p.resolve()}")

        elif archive_type == "xz":
            out_p.write_bytes(lzma.decompress(input_p.read_bytes()))
            print(f"\n✅ Decompressed → {out_p.resolve()}")

        elif archive_type == "zst":
            if not HAS_ZSTD:
                print("❌ zstandard not installed.")
                return
            out_p.write_bytes(zstd.ZstdDecompressor().decompress(input_p.read_bytes()))
            print(f"\n✅ Decompressed → {out_p.resolve()}")

        else:
            print("❌ Unsupported format")

    except Exception as e:
        print(f"❌ Decompression failed: {e}")


# ─── SUPR → ZIP conversion ────────────────────────────────────────────────────

def convert_supr_to_zip(input_path: Optional[str], output_path: Optional[str] = None,
                        progress_cb: Optional[ProgressCB] = None):
    if not input_path:
        print("❌ No file path given!")
        return
    input_p = Path(input_path)
    if not input_p.exists():
        print(f"❌ File not found: {input_p.resolve()}")
        return
    if input_p.suffix != ".supr":
        print("❌ Input must be a .supr file")
        return

    supr_data = input_p.read_bytes()
    if not supr_data.startswith(MAGIC_SUPR):
        print("❌ Not a valid SUPR file")
        return

    typ = supr_data[5]
    entry_name = input_p.stem
    out_p = Path(output_path) if output_path else input_p.with_suffix(".zip")

    if typ == 0:
        val = supr_data[6]
        orig_size = int.from_bytes(supr_data[7:15], "big")
        chunk_size = 64 * 1024 * 1024
        chunk = bytes([val]) * chunk_size
        written = 0
        with ZipFile(out_p, "w", ZIP_DEFLATED, compresslevel=9) as z:
            with z.open(entry_name, "w", force_zip64=True) as zf:
                while written < orig_size:
                    to_write = min(chunk_size, orig_size - written)
                    zf.write(chunk[:to_write])
                    written += to_write
                    if progress_cb:
                        progress_cb(written, orig_size)
    else:
        payload = supr_data[6:]
        if typ == 1:
            if not HAS_ZSTD:
                print("❌ zstandard not installed.")
                return
            original = zstd.ZstdDecompressor().decompress(payload)
        elif typ == 2:
            original = zlib.decompress(payload)
        else:
            print("❌ Unknown SUPR type")
            return
        orig_size = len(original)
        with ZipFile(out_p, "w", ZIP_DEFLATED, compresslevel=9) as z:
            z.writestr(entry_name, original)
        if progress_cb:
            progress_cb(1, 1)

    zip_size = out_p.stat().st_size
    ratio = orig_size / zip_size if zip_size > 0 else 0
    print(f"\n✅ Converted to ZIP!")
    _print_ratio(orig_size, zip_size)
    print(f"Saved to  : {out_p.resolve()}")


# ─── Preview ──────────────────────────────────────────────────────────────────

def preview_archive(input_path: Optional[str]) -> str:
    if not input_path:
        return "❌ No file path given."
    input_p = Path(input_path)
    if not input_p.exists():
        return f"❌ File not found: {input_p.resolve()}"

    archive_type = get_archive_type(input_p)
    lines = [f"Archive: {input_p.name}", f"Format : {archive_type}", ""]

    try:
        if archive_type == "supr":
            data = input_p.read_bytes()
            if not data.startswith(MAGIC_SUPR):
                return "❌ Not a valid SUPR file."
            typ = data[5]
            type_names = {0: "Uniform byte (RLE)", 1: "Zstandard", 2: "Zlib"}
            lines.append(f"Type   : {type_names.get(typ, 'Unknown')}")
            if typ == 0:
                val = data[6]
                orig_size = int.from_bytes(data[7:15], "big")
                lines.append(f"Byte   : 0x{val:02X} ({val})")
                lines.append(f"Expands to: {orig_size:,} bytes")
                ratio = orig_size / len(data)
                lines.append(f"Ratio  : {ratio:,.0f}:1")
            else:
                lines.append(f"Compressed size: {len(data):,} bytes")
                lines.append("(Decompress to see original size)")

        elif archive_type == "zip":
            with ZipFile(input_p, "r") as z:
                infos = z.infolist()
                lines.append(f"{'Name':<40} {'Compressed':>12} {'Original':>12}")
                lines.append("-" * 66)
                for info in infos:
                    lines.append(f"{info.filename:<40} {info.compress_size:>12,} {info.file_size:>12,}")
                total_orig = sum(i.file_size for i in infos)
                total_comp = sum(i.compress_size for i in infos)
                lines.append("-" * 66)
                lines.append(f"{'TOTAL':<40} {total_comp:>12,} {total_orig:>12,}")

        elif archive_type in ("tar.gz", "tar.xz", "tar.bz2"):
            with tarfile.open(input_p, "r:*") as tar:
                members = [m for m in tar.getmembers() if m.isfile()]
                lines.append(f"{'Name':<50} {'Size':>12}")
                lines.append("-" * 64)
                for m in members:
                    lines.append(f"{m.name:<50} {m.size:>12,}")
                lines.append("-" * 64)
                lines.append(f"{'TOTAL':<50} {sum(m.size for m in members):>12,}")

        elif archive_type == "7z":
            if not HAS_7Z:
                return "❌ py7zr not installed."
            with py7zr.SevenZipFile(input_p, "r") as z:
                infos = z.list()
                lines.append(f"{'Name':<50} {'Size':>12}")
                lines.append("-" * 64)
                for info in infos:
                    size = info.uncompressed if info.uncompressed else 0
                    lines.append(f"{info.filename:<50} {size:>12,}")

        else:
            return f"Preview not supported for .{archive_type} files."

    except Exception as e:
        return f"❌ Preview failed: {e}"

    return "\n".join(lines)


# ─── Verify ───────────────────────────────────────────────────────────────────

def verify_archive(input_path: Optional[str]) -> tuple[bool, str]:
    if not input_path:
        return False, "No file path given."
    input_p = Path(input_path)
    if not input_p.exists():
        return False, f"File not found: {input_p.resolve()}"

    archive_type = get_archive_type(input_p)

    try:
        if archive_type == "supr":
            data = input_p.read_bytes()
            if not data.startswith(MAGIC_SUPR):
                return False, "Invalid SUPR magic bytes."
            typ = data[5]
            if typ == 0:
                if len(data) < 15:
                    return False, "SUPR header too short."
                return True, f"✅ SUPR file OK (uniform byte, type 0)"
            elif typ in (1, 2):
                # Attempt partial decompression (first 1 MB)
                payload = data[6:]
                if typ == 1:
                    if not HAS_ZSTD:
                        return False, "zstandard not installed."
                    zstd.ZstdDecompressor().decompress(payload[:min(len(payload), 1024*1024)])
                else:
                    zlib.decompress(payload)
                return True, f"✅ SUPR file OK (type {typ})"
            return False, "Unknown SUPR type byte."

        elif archive_type == "zip":
            with ZipFile(input_p, "r") as z:
                bad = z.testzip()
                if bad:
                    return False, f"❌ Bad file in ZIP: {bad}"
                return True, f"✅ ZIP OK — {len(z.namelist())} file(s) verified"

        elif archive_type in ("tar.gz", "tar.xz", "tar.bz2"):
            with tarfile.open(input_p, "r:*") as tar:
                count = sum(1 for m in tar.getmembers() if m.isfile())
            return True, f"✅ TAR OK — {count} file(s)"

        elif archive_type == "7z":
            if not HAS_7Z:
                return False, "py7zr not installed."
            with py7zr.SevenZipFile(input_p, "r") as z:
                if not z.test():
                    return False, "❌ 7z integrity check failed."
            return True, "✅ 7Z OK"

        elif archive_type == "gz":
            gzip.decompress(input_p.read_bytes())
            return True, "✅ GZ OK"

        elif archive_type == "bz2":
            bz2.decompress(input_p.read_bytes())
            return True, "✅ BZ2 OK"

        elif archive_type == "xz":
            lzma.decompress(input_p.read_bytes())
            return True, "✅ XZ OK"

        elif archive_type == "zst":
            if not HAS_ZSTD:
                return False, "zstandard not installed."
            zstd.ZstdDecompressor().decompress(input_p.read_bytes())
            return True, "✅ ZST OK"

        else:
            return False, f"Verify not supported for .{archive_type}"

    except Exception as e:
        return False, f"❌ Verification failed: {e}"


# ─── Benchmark ────────────────────────────────────────────────────────────────

def benchmark_file(input_path: Optional[str]) -> str:
    if not input_path:
        return "❌ No file path given."
    input_p = Path(input_path)
    if not input_p.exists():
        return f"❌ File not found: {input_p.resolve()}"
    if input_p.is_dir():
        return "❌ Benchmark works on single files only."

    data = input_p.read_bytes()
    orig_size = len(data)
    results = []

    candidates = [
        ("supr",   lambda: compress_supr(data)),
        ("zip",    lambda: _bench_zip(data, input_p.name)),
        ("gz",     lambda: gzip.compress(data, compresslevel=9)),
        ("bz2",    lambda: bz2.compress(data, compresslevel=9)),
        ("xz",     lambda: lzma.compress(data, preset=9)),
    ]
    if HAS_ZSTD:
        candidates.append(("zst", lambda: zstd.ZstdCompressor(level=22).compress(data)))
    if HAS_7Z:
        candidates.append(("7z", lambda: _bench_7z(data, input_p.name)))

    for fmt, fn in candidates:
        try:
            t0 = time.perf_counter()
            out = fn()
            elapsed = time.perf_counter() - t0
            comp_size = len(out)
            ratio = orig_size / comp_size if comp_size > 0 else 0
            results.append((fmt, comp_size, ratio, elapsed))
        except Exception as e:
            results.append((fmt, 0, 0, 0))

    results.sort(key=lambda r: r[1])

    lines = [
        f"Benchmark: {input_p.name}  ({orig_size:,} bytes)",
        "",
        f"{'Format':<8} {'Compressed':>14} {'Ratio':>12} {'Time':>8}",
        "-" * 46,
    ]
    for fmt, comp_size, ratio, elapsed in results:
        if comp_size == 0:
            lines.append(f"{fmt:<8} {'ERROR':>14}")
        else:
            lines.append(f"{fmt:<8} {comp_size:>14,} {ratio:>11,.0f}:1 {elapsed:>7.2f}s")

    return "\n".join(lines)


def _bench_zip(data: bytes, name: str) -> bytes:
    import io
    buf = io.BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(name, data)
    return buf.getvalue()


def _bench_7z(data: bytes, name: str) -> bytes:
    import io
    buf = io.BytesIO()
    with py7zr.SevenZipFile(buf, "w") as z:
        z.writestr({name: io.BytesIO(data)})
    return buf.getvalue()


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    print("🚀 SuprCompressr for Linux")
    print(f"   Working dir: {Path.cwd()}\n")

    while True:
        print("\n=== MAIN MENU ===")
        print("1. Compress file/folder")
        print("2. Decompress file")
        print("3. Convert .supr → .zip")
        print("4. Batch compress")
        print("5. Preview archive")
        print("6. Verify archive")
        print("7. Benchmark file")
        print("8. Exit")
        choice = input("\nChoose (1-8): ").strip()

        if choice == "8":
            print("Goodbye!")
            break

        elif choice == "1":
            print("\nFormats (single files): supr, zip, gz, bz2, xz, zst, tar.gz, tar.xz, 7z")
            print("Formats (folders):       zip, tar.gz, tar.xz, 7z")
            fmt = input("Format: ").strip().lower()
            if fmt not in ALL_FORMATS:
                print("Invalid format")
                continue
            level = 9
            if fmt not in ("supr", "7z"):
                try:
                    level = max(1, min(9, int(input("Level (1-9): ").strip())))
                except ValueError:
                    level = 9
            infile = clean_path(input("Input path: "))
            outfile = clean_path(input("Output path (Enter = default): "))
            perform_compression(infile, fmt, level, outfile)

        elif choice == "2":
            infile = clean_path(input("File to decompress: "))
            outfile = clean_path(input("Output path (Enter = default): "))
            perform_decompression(infile, outfile)

        elif choice == "3":
            infile = clean_path(input(".supr file: "))
            outfile = clean_path(input("Output .zip (Enter = default): "))
            convert_supr_to_zip(infile, outfile)

        elif choice == "4":
            print("Enter file paths one per line, empty line to finish:")
            files = []
            while True:
                p = clean_path(input("  File: "))
                if not p:
                    break
                files.append(p)
            if not files:
                print("No files entered.")
                continue
            fmt = input("Format: ").strip().lower()
            level = 9
            try:
                level = max(1, min(9, int(input("Level (1-9): ").strip())))
            except ValueError:
                pass
            outdir = clean_path(input("Output directory (Enter = same as each file): "))
            perform_batch_compression(files, fmt, level, outdir)

        elif choice == "5":
            infile = clean_path(input("Archive path: "))
            print("\n" + preview_archive(infile))

        elif choice == "6":
            infile = clean_path(input("Archive path: "))
            ok, msg = verify_archive(infile)
            print(f"\n{msg}")

        elif choice == "7":
            infile = clean_path(input("File to benchmark: "))
            print("\n" + benchmark_file(infile))

        else:
            print("Invalid option")


if __name__ == "__main__":
    if not HAS_ZSTD:
        print("💡 Tip: pip install zstandard  for better compression")
    if not HAS_7Z:
        print("💡 Tip: pip install py7zr       for 7z support")
    main()
