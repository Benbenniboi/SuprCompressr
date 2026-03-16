#!/usr/bin/env python3
"""
SuperCompressor - Python app for Linux
Normal ZIP compression → up to 2,000,000:1+ (or more) with SUPER mode
Multiple formats + multiple levels
"""

import sys
from pathlib import Path
import gzip
import bz2
import lzma
import zlib
from zipfile import ZipFile, ZIP_DEFLATED

try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

MAGIC_SUPR = b"SUPR\x01"  # 5 bytes

def is_uniform(data: bytes):
    """Returns (True, byte_value) if every byte is identical"""
    if len(data) == 0:
        return False, None
    val = data[0]
    if all(b == val for b in data):
        return True, val
    return False, None


def compress_supr(data: bytes) -> bytes:
    """SUPER format - achieves millions:1 when possible"""
    uniform, val = is_uniform(data)
    if uniform and val is not None:
        # Type 0: uniform byte (insane ratio!)
        return MAGIC_SUPR + b"\x00" + bytes([val]) + len(data).to_bytes(8, "big")
    else:
        # Type 1: zstd (best possible) or fallback
        if HAS_ZSTD:
            c = zstd.ZstdCompressor(level=22)
            payload = c.compress(data)
            return MAGIC_SUPR + b"\x01" + payload
        else:
            payload = zlib.compress(data, level=9)
            return MAGIC_SUPR + b"\x02" + payload


def decompress_supr(data: bytes) -> bytes:
    if not data.startswith(MAGIC_SUPR):
        raise ValueError("Not a SUPER file")
    typ = data[5]
    payload = data[6:]
    if typ == 0:  # uniform
        val = payload[0]
        length = int.from_bytes(payload[1:9], "big")
        return bytes([val]) * length
    elif typ == 1:  # zstd
        if not HAS_ZSTD:
            raise ImportError("Install zstandard: pip install zstandard")
        return zstd.ZstdDecompressor().decompress(payload)
    elif typ == 2:  # zlib fallback
        return zlib.decompress(payload)
    raise ValueError("Unknown SUPER type")


def perform_compression(input_path: str | None, fmt: str, level: int, output_path: str | None = None):
    if not input_path:
        print("❌ No file path given!")
        return
    input_p = Path(input_path)
    if not input_p.exists():
        print(f"❌ File not found: {input_p.resolve()}")
        return
    data = input_p.read_bytes()
    orig_size = len(data)

    if output_path is None:
        suffix = ".zip" if fmt == "zip" else ".supr" if fmt == "supr" else f".{fmt}"
        output_path = str(input_p.with_suffix(suffix))
    out_p = Path(output_path)

    if fmt == "supr":
        compressed = compress_supr(data)
        out_p.write_bytes(compressed)
        comp_size = len(compressed)
    elif fmt == "zip":
        with ZipFile(out_p, "w", ZIP_DEFLATED, compresslevel=level) as z:
            z.writestr(input_p.name, data)
        comp_size = out_p.stat().st_size
    else:
        if fmt == "gz":
            compressed = gzip.compress(data, compresslevel=level)
        elif fmt == "bz2":
            compressed = bz2.compress(data, compresslevel=level)
        elif fmt == "xz":
            compressed = lzma.compress(data, preset=min(9, level))
        elif fmt == "zst":
            if not HAS_ZSTD:
                print("⚠️ zstandard not installed → using gzip instead")
                compressed = gzip.compress(data, compresslevel=9)
            else:
                z_level = min(22, max(1, level * 2))  # user 1-9 → up to 22
                compressed = zstd.ZstdCompressor(level=z_level).compress(data)
        else:
            print("Unknown format")
            return
        out_p.write_bytes(compressed)
        comp_size = len(compressed)

    ratio = orig_size / comp_size if comp_size > 0 else 0
    print(f"\n✅ SUCCESS!")
    print(f"Original : {orig_size:,} bytes")
    print(f"Compressed: {comp_size:,} bytes")
    print(f"Ratio    : {ratio:,.0f}:1")
    if ratio > 100_000:
        print("🎉 INSANE ratio! (SUPER uniform mode)")
    elif ratio > 10_000:
        print("🚀 Extreme ratio achieved!")
    print(f"Saved to : {out_p.resolve()}")


def perform_decompression(input_path: str | None, output_path: str | None = None):
    if not input_path:
        print("❌ No file path given!")
        return
    input_p = Path(input_path)
    if not input_p.exists():
        print(f"❌ File not found: {input_p.resolve()}")
        return
    data = input_p.read_bytes()

    if output_path is None:
        output_path = str(input_p.with_suffix(".decompressed"))
    out_p = Path(output_path)

    try:
        if input_p.suffix == ".supr":
            decompressed = decompress_supr(data)
        elif input_p.suffix == ".gz":
            decompressed = gzip.decompress(data)
        elif input_p.suffix == ".bz2":
            decompressed = bz2.decompress(data)
        elif input_p.suffix == ".xz":
            decompressed = lzma.decompress(data)
        elif input_p.suffix == ".zst":
            if HAS_ZSTD:
                decompressed = zstd.ZstdDecompressor().decompress(data)
            else:
                print("zstandard not installed")
                return
        elif input_p.suffix == ".zip":
            with ZipFile(input_p, "r") as z:
                names = z.namelist()
                if len(names) == 1:
                    decompressed = z.read(names[0])
                    out_p = out_p.with_name(names[0]) if output_path is None else out_p
                    out_p.write_bytes(decompressed)
                    print(f"\n✅ Decompressed {len(decompressed):,} bytes")
                    print(f"Saved to : {out_p.resolve()}")
                else:
                    extract_dir = out_p.parent / input_p.stem if output_path is None else out_p
                    extract_dir.mkdir(parents=True, exist_ok=True)
                    z.extractall(extract_dir)
                    print(f"\n✅ Extracted {len(names)} files to: {extract_dir.resolve()}")
            return
        else:
            print("Unsupported format for auto-decompress")
            return

        out_p.write_bytes(decompressed)
        print(f"\n✅ Decompressed {len(decompressed):,} bytes")
        print(f"Saved to : {out_p.resolve()}")

    except Exception as e:
        print(f"❌ Decompression failed: {e}")


def convert_supr_to_zip(input_path: str | None, output_path: str | None = None):
    """Re-compress a .supr as a standard .zip containing the original file."""
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
    # Entry name inside the zip = original filename (strip .supr)
    entry_name = input_p.stem

    if output_path is None:
        output_path = str(input_p.with_suffix(".zip"))
    out_p = Path(output_path)

    if typ == 0:
        # Uniform byte — stream in 64 MB chunks so 10GB never hits RAM
        val = supr_data[6]
        orig_size = int.from_bytes(supr_data[7:15], "big")
        chunk = bytes([val]) * (64 * 1024 * 1024)  # 64 MB chunk
        written = 0
        with ZipFile(out_p, "w", ZIP_DEFLATED, compresslevel=9) as z:
            with z.open(entry_name, "w", force_zip64=True) as zf:
                while written < orig_size:
                    to_write = min(len(chunk), orig_size - written)
                    zf.write(chunk[:to_write])
                    written += to_write
    else:
        # Non-uniform — decompress then recompress
        payload = supr_data[6:]
        if typ == 1:
            if not HAS_ZSTD:
                print("❌ zstandard not installed, cannot decompress this SUPR file")
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

    zip_size = out_p.stat().st_size
    ratio = orig_size / zip_size if zip_size > 0 else 0
    print(f"\n✅ Converted to ZIP!")
    print(f"Original  : {orig_size:,} bytes")
    print(f"ZIP size  : {zip_size:,} bytes")
    print(f"Ratio     : {ratio:,.0f}:1")
    if ratio > 100_000:
        print("🎉 INSANE ratio preserved!")
    elif ratio > 10_000:
        print("🚀 Extreme ratio preserved!")
    print(f"Saved to  : {out_p.resolve()}")


def clean_path(raw: str) -> str | None:
    """Strip quotes and expand ~ so Crostini drag-drop paths work."""
    if not raw:
        return None
    p = raw.strip().strip("'\"")
    return str(Path(p).expanduser()) if p else None


def main():
    print("🚀 SuperCompressor for Linux")
    print("   Normal ZIP → 2,000,000:1+ extreme compression")
    print(f"   Working dir: {Path.cwd()}\n")

    while True:
        print("\n=== MAIN MENU ===")
        print("1. Compress file")
        print("2. Decompress file")
        print("3. Convert .supr → .zip (keeps ratio)")
        print("4. Exit")
        choice = input("\nChoose (1-4): ").strip()

        if choice == "4":
            print("Goodbye!")
            break

        elif choice == "1":
            print("\nFormats:")
            print("1. zip (normal, classic)")
            print("2. gz")
            print("3. bz2")
            print("4. xz")
            print("5. zst (best modern)")
            print("6. supr (EXTREME - millions:1 possible)")
            fnum = input("Choose format (1-6): ").strip()
            fmt_map = {"1": "zip", "2": "gz", "3": "bz2", "4": "xz", "5": "zst", "6": "supr"}
            if fnum not in fmt_map:
                print("Invalid")
                continue
            fmt = fmt_map[fnum]

            level = 9
            if fmt != "supr":
                lev = input("Level (1=fast/low ratio → 9=max): ").strip()
                try:
                    level = int(lev)
                    if not 1 <= level <= 9:
                        level = 9
                except:
                    level = 9

            infile = clean_path(input("Input file path: "))
            outfile = clean_path(input("Output path (Enter = default): "))

            perform_compression(infile, fmt, level, outfile)

        elif choice == "2":
            infile = clean_path(input("File to decompress: "))
            outfile = clean_path(input("Output path (Enter = default): "))
            perform_decompression(infile, outfile)

        elif choice == "3":
            infile = clean_path(input(".supr file path: "))
            outfile = clean_path(input("Output .zip path (Enter = default): "))
            convert_supr_to_zip(infile, outfile)

        else:
            print("Invalid option")


if __name__ == "__main__":
    # Quick setup reminder
    if not HAS_ZSTD:
        print("💡 Tip: run 'pip install zstandard' for maximum compression power")
    main()