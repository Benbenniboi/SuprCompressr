# SuprComopressr

A Linux file compression tool written in Python. Supports standard formats plus a custom **SUPR** format capable of millions-to-one compression ratios on uniform data.

## Features

- Compress and decompress files in 6 formats: `zip`, `gz`, `bz2`, `xz`, `zst`, `supr`
- Convert `.supr` files to standard `.zip` while preserving the compression ratio
- Streams large files (e.g. 10 GB+) in chunks — no out-of-memory crashes
- Works on Chromebook Linux (Crostini) — handles drag-and-drop paths with quotes automatically

## Requirements

- Python 3.11+
- `zstandard` (optional, but recommended for maximum compression)

```bash
pip install zstandard
```

## Usage

```bash
python3 suprcompressr.py
```

Then follow the interactive menu:

```
=== MAIN MENU ===
1. Compress file
2. Decompress file
3. Convert .supr → .zip (keeps ratio)
4. Exit
```

## Formats

| Format | Extension | Notes |
|--------|-----------|-------|
| zip | `.zip` | Standard DEFLATE, levels 1–9 |
| gz | `.gz` | gzip, levels 1–9 |
| bz2 | `.bz2` | bzip2, levels 1–9 |
| xz | `.xz` | LZMA, levels 1–9 |
| zst | `.zst` | Zstandard (best general-purpose), requires `zstandard` |
| supr | `.supr` | Custom format, see below |

## The SUPR Format

SUPR is a custom binary format designed for extreme compression ratios.

**How it works:**

- If the file consists entirely of one repeated byte (e.g. a file of all zeros), SUPR stores just the byte value and the original length — **14 bytes total**, regardless of file size. A 10 GB file of zeros becomes 14 bytes.
- Otherwise it falls back to Zstandard level 22 (or zlib level 9 if `zstandard` is not installed).

**File structure:**

```
[5 bytes] Magic: SUPR\x01
[1 byte]  Type: 0=uniform, 1=zstd, 2=zlib
--- Type 0 ---
[1 byte]  The repeated byte value
[8 bytes] Original file length (big-endian uint64)
--- Type 1/2 ---
[N bytes] Compressed payload
```

> **Note:** Millions-to-one ratios only occur for uniform-byte files. Real-world files will see ratios typical of zstd/zlib.

## Convert .supr to .zip

Option 3 re-packages a `.supr` file as a standard `.zip` that any unzip tool can open, while preserving the compression ratio:

- For uniform files (type 0): streams data in 64 MB chunks directly into the ZIP compressor — works on files larger than available RAM
- For type 1/2: decompresses then recompresses with DEFLATE level 9

The ZIP entry uses the original filename (`.supr` extension stripped), so extracting it gives back the original file.

## License

MIT
