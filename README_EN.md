<div align="center">

<img src="docs/screenshots/logo.png" width="128" alt="HashTool logo">

# HashTool

**File Hash Calculator & Verifier — compute, verify, and batch-check in one place**

[![Release](https://img.shields.io/github/v/release/WanQTs/HashTool)](https://github.com/WanQTs/HashTool/releases)
[![CI](https://github.com/WanQTs/HashTool/actions/workflows/ci.yml/badge.svg)](https://github.com/WanQTs/HashTool/actions)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11%20x64-0078D6)](https://github.com/WanQTs/HashTool)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[中文](README.md) · **English**

[✨ Features](#-features) · [📸 Screenshots](#-screenshots) · [📥 Download](#-download) · [🚀 Usage](#-usage) · [⚡ Performance](#-performance) · [❓ FAQ](#-faq)

</div>

---

A Windows 10/11 64-bit desktop tool: compute file hashes (MD5 / SHA-1 / SHA-256 / SHA-512 / CRC32) and verify them with three comparison modes. Built with the Python standard library only (tkinter), **zero third-party runtime dependencies**, delivered as a **64-bit single-file exe**.

## ✨ Features

### 🔢 Hash computation
- Five algorithms, selectable together: MD5, SHA-1, SHA-256, SHA-512, CRC32
- Three ways to add files: file picker (multi-select), drag & drop files/folders into the window, add a whole folder (recursive)
- Large files are read in **8MB chunks** (pre-allocated buffer, never loaded into memory at once)
- **Parallel computation**: background thread pool, up to 4 threads; thread count selectable in the UI (Auto / 1 / 2 / 4)
- Result table: file name, full path, size, hash per algorithm, elapsed time, status (zebra striping; double-click or right-click to copy)
- Progress bar + cancel button; the UI never freezes
- **Bauhaus-style UI**: warm paper background, ink-black header band with a red circle / yellow triangle / blue square geometric logo, flat buttons (solid blue primary action), black table header, Microsoft YaHei font, zero third-party dependencies
- **Bilingual UI (Chinese / English)**: switch instantly via the "Language" menu (main window, compare window, messages, and export headers all update); auto-detected from the system on first launch; the choice is saved to `%APPDATA%\HashTool\config.json`

### 🔍 Hash comparison (key feature, menu: Tools → Hash Compare)

| Mode | Description |
| --- | --- |
| Verify single file | Paste a hash; the algorithm is auto-detected by length (32=MD5, 40=SHA-1, 64=SHA-256, 128=SHA-512, 8=CRC32); shows "✔ Match / ✘ Mismatch" with red highlight on mismatch |
| Compare two files | Pick two files and compare the selected algorithms hash by hash |
| Batch verify | Import a hash list (one `hash  filename` per line, MD5Sum / SHA256SUM / certutil compatible) and verify files in a folder; reports "Passed / Failed / Missing / Bad format" |

Result colors: **match=green, mismatch=red, missing=orange**.

### 📤 Export results
- CSV (with BOM, opens directly in Excel)
- TXT (standard SUM format, recognizable by other verification tools)
- Copy a single hash with a double-click on the cell or right-click → "Copy This Cell"

## 📸 Screenshots

<div align="center">

| Main window (中文) | Main window (English) |
| :---: | :---: |
| <img src="docs/screenshots/main_zh.png" width="480" alt="Main window (Chinese)"> | <img src="docs/screenshots/main_en.png" width="480" alt="Main window (English)"> |
| **Batch verify (中文)** | **Batch verify (English)** |
| <img src="docs/screenshots/compare_zh.png" width="480" alt="Batch verify (Chinese)"> | <img src="docs/screenshots/compare_en.png" width="480" alt="Batch verify (English)"> |

</div>

## 📥 Download

Grab the latest version from [**Releases**](https://github.com/WanQTs/HashTool/releases) — a single 64-bit executable for Windows 10/11, no Python installation required (the release notes include a SHA-256 checksum you can verify with the tool itself).

## 🚀 Usage

- Run the downloaded `HashTool.exe` directly (no Python required).
- Development mode: `python main.py`
- `python main.py --selftest` runs a headless self-check of the built-in algorithms.
- Switch language: menu "Language" → 中文 / English; auto-detected from the system on first launch.

## ✅ Running the tests

```bat
python -m pip install pytest
python -m pytest
```

The tests verify every algorithm against official known values (e.g. SHA-256 of `"abc"` = `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`) and cover chunked reading, cancellation, algorithm detection, list parsing, batch verification, and export; GUI smoke tests cover the main flow and the three compare modes (auto-skipped without a display).

## 🧹 Static analysis (ruff)

```bat
python -m pip install ruff
python -m ruff check
```

Rule sets are defined in `ruff.toml` (tailored for a desktop GUI: E/F/I/UP/B/PIE etc.; the BLE/S security-audit sets are intentionally not enabled).

## ⚡ Performance

Measured on this machine with `python benchmark.py` (6 × 128MB files, 768MB total; MD5+SHA-256+SHA-512; best of 2 rounds per config; 32 logical cores):

| Threads | Time | Throughput | Speedup |
| ---: | ---: | ---: | ---: |
| 1 | 1.55 s | 494 MB/s | x1.00 |
| 2 | 0.99 s | 779 MB/s | x1.58 |
| 4 | 0.65 s | 1190 MB/s | x2.41 |

The speedup comes from hashlib releasing the GIL for large buffers; gains are smaller on slower random-read media (e.g. HDDs) — set "Threads" to 1 in that case.

## 🛠️ Packaging (PyInstaller)

```bat
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --noconsole ^
  --name "HashTool" --icon "%CD%\app.ico" ^
  --distpath dist --workpath build --specpath build main.py
```

Or simply run `build.bat`. Requires **64-bit Python (3.11+)**; the output is the single file `dist\HashTool.exe` for Windows 10/11 64-bit.

## 🗂️ Directory structure

```
HashTool/
├── main.py                # Entry point (--selftest self-check / --smoke GUI smoke test)
├── app.py                 # tkinter GUI (main window + three compare modes)
├── hash_core.py           # Hash core logic (GUI-independent, unit-testable)
├── i18n.py                # Chinese/English string table, language detection, config persistence
├── dnd.py                 # Windows native drag & drop (ctypes, zero dependencies)
├── make_icon.py           # Icon generator (pure Python, Bauhaus geometric design)
├── benchmark.py           # Parallel benchmark script (1/2/4 threads)
├── conftest.py            # pytest fixtures (project-local temp dir)
├── tests/
│   ├── test_hash_core.py  # Core logic unit tests (official known values)
│   ├── test_app_worker.py # Parallel worker tests (no GUI needed)
│   ├── test_i18n.py       # Bilingual completeness / English-mode behavior
│   └── test_gui_smoke.py  # GUI smoke tests (main flow + three modes; auto-skip without a display)
├── pytest.ini             # pytest config
├── ruff.toml              # ruff static-analysis config
├── build.bat              # One-click build script
├── .github/workflows/ci.yml   # GitHub Actions: pytest + ruff on push/PR
├── docs/screenshots/      # README screenshots (Chinese & English)
├── README.md / README_EN.md / CHANGELOG.md
└── dist/
    └── HashTool.exe        # Packaged artifact (64-bit single file)
```

## ❓ FAQ

<details>
<summary><b>Antivirus false positives?</b></summary>

PyInstaller `--onefile` binaries are occasionally flagged; add an exclusion, or use `--onedir` instead if it bothers you.
</details>

<details>
<summary><b>Drag &amp; drop unavailable?</b></summary>

Based on native Windows messages (WM_DROPFILES), Windows-only; it is disabled automatically on other platforms.
</details>

<details>
<summary><b>Batch list format requirements?</b></summary>

One `hash  filename` per line (spaces or tabs); `#`/`;` comments and the `MD5 (filename) = hash` (certutil) form are supported; filenames may contain relative subdirectories.
</details>

<details>
<summary><b>Can I change the UI theme?</b></summary>

The default is the Bauhaus style (warm paper, ink-black header band, primary-color geometric icon, flat controls) with Microsoft YaHei, zebra-striped table, and window icon; after `pip install ttkbootstrap`, ttk widgets switch to the cosmo theme automatically (brand elements such as the header band keep the Bauhaus style).
</details>

<details>
<summary><b>Where is the language setting stored?</b></summary>

Saved to `%APPDATA%\HashTool\config.json` (configs in the legacy Chinese directory are migrated and cleaned up automatically at startup); delete the file to restore auto-detection. Error messages keep the language they were produced in; new messages follow the new language after switching.
</details>

---

<div align="center">

**If this little tool helps you, a ⭐ star is appreciated!**

[Changelog](CHANGELOG.md) · [Releases](https://github.com/WanQTs/HashTool/releases) · [MIT License](LICENSE)

</div>
