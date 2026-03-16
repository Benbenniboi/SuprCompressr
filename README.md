# SuprComopressr

A Linux file compression tool written in Python with both a CLI and a GUI. Supports standard formats plus a custom **SUPR** format capable of millions-to-one compression ratios on uniform data.

## Features

- Compress and decompress **files and folders** in 9 formats: `supr`, `zip`, `gz`, `bz2`, `xz`, `zst`, `tar.gz`, `tar.xz`, `7z`
- **Batch compress** multiple files at once
- **Preview** archive contents without extracting
- **Verify** archive integrity
- **Benchmark** a file across all formats to find the best one
- Convert `.supr` → `.zip` while preserving the compression ratio
- Streams large files in chunks — no out-of-memory crashes
- GUI with drag-and-drop support
- Works on Chromebook Linux (Crostini)

## Requirements

- Python 3.11+

Optional dependencies (auto-installed on first run via `main.py`):

| Package | Purpose |
|---------|---------|
| `zstandard` | zst format + SUPR fallback compression |
| `py7zr` | 7z format support |
| `tkinterdnd2` | Drag-and-drop in the GUI |

```bash
pip install zstandard py7zr tkinterdnd2
```

## Usage

### GUI + CLI launcher (recommended)

```bash
python3 main.py
```

Automatically installs missing dependencies, then asks:
```
1. GUI
2. CLI
```

### CLI only

```bash
python3 suprcompressr.py
```

```
=== MAIN MENU ===
1. Compress file/folder
2. Decompress file
3. Convert .supr → .zip
4. Batch compress
5. Preview archive
6. Verify archive
7. Benchmark file
8. Exit
```

## GUI

The GUI has five tabs:

| Tab | What it does |
|-----|-------------|
| **Compress** | Compress a file or folder, choose format and level |
| **Decompress** | Decompress with Preview and Verify buttons |
| **Batch** | Select multiple files and compress them all at once |
| **.supr→.zip** | Convert a `.supr` file to a standard `.zip` |
| **Benchmark** | Run all formats on a file and compare size, ratio, and speed |

All long operations run in a background thread with a live progress bar.

## Formats

| Format | Extension | Folder support | Notes |
|--------|-----------|:--------------:|-------|
| supr | `.supr` | — | Custom format, see below |
| zip | `.zip` | ✅ | Standard DEFLATE, levels 1–9 |
| gz | `.gz` | — | gzip, levels 1–9 |
| bz2 | `.bz2` | — | bzip2, levels 1–9 |
| xz | `.xz` | — | LZMA, levels 1–9 |
| zst | `.zst` | — | Zstandard, requires `zstandard` |
| tar.gz | `.tar.gz` | ✅ | Standard Linux archive |
| tar.xz | `.tar.xz` | ✅ | Standard Linux archive |
| 7z | `.7z` | ✅ | Requires `py7zr` |

## The SUPR Format

SUPR is a custom binary format designed for extreme compression ratios.

**How it works:**

- If every byte in the file is identical (e.g. a file of all zeros), SUPR stores just the byte value and the original length — **14 bytes total**, regardless of file size. A 10 GB file of zeros becomes 14 bytes.
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

> **Warning:** Converting a `.supr` uniform file to `.zip` produces a zip bomb — the ZIP will expand to its full original size when extracted. Make sure recipients have enough disk space.

## Building an executable

### Linux (Crostini)

```bash
bash build.sh
./dist/SuprComopressr
```

### Windows

```bat
build_windows.bat
dist\SuprComopressr.exe
```

### GitHub Actions (automated)

Push a version tag to build both automatically:

```bash
git tag v1.0
git push --tags
```

The Linux binary and Windows `.exe` will be attached to a GitHub Release.

## License

MIT
