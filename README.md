# Chunitools

A high-performance CHUNITHM chart parser, viewer, and editor built with Python 3.10-3.13 and PySide6 (Qt6).

## Quick start

```bash
# Install dependencies
uv sync

# Run the GUI
uv run python src/main.py

# Run tests
uv run pytest
```

The repository includes a `.python-version` file so `uv` uses Python 3.13 by default.
Python 3.14 is not currently supported because some audio dependencies do not publish
compatible Windows wheels yet.

Custom WAV, MP3, FLAC, and AWB music playback works on Windows without Visual Studio
Build Tools. FLAC decoding uses `soundfile`/libsndfile instead of `pyflac`, avoiding a
local C/C++ extension build during setup.

## Building a standalone executable

The project uses **PyInstaller** to build a single-file executable that bundles everything (Python, Qt, and vgmstream).

### Prerequisites

- Python 3.10-3.13
- [uv](https://docs.astral.sh/uv/) (package manager)

### Build for your platform

```bash
# This downloads the latest vgmstream and runs PyInstaller
uv run python build.py

# The archive lands in builds/
#   builds/chunitools_linux.tar.gz
#   builds/chunitools_macos_apple_silicon.tar.gz
#   builds/chunitools_windows.zip
```

### Options

```bash
# Build for a specific platform (cross-build)
uv run python build.py --platform windows

# Pin a specific vgmstream release
uv run python build.py --tag r2117
```

## How to release

Pushing a tag triggers CI to build for all platforms and uploads to GitHub Releases.

```bash
# 1. Make sure everything is committed
git status

# 2. Tag the release
git tag v<VERSION>

# 3. Push the tag
git push origin v<VERSION>

# That's it — the Release workflow at .github/workflows/release.yml
# will build for Linux, macOS (Apple Silicon), and Windows, then create
# a GitHub Release with the compiled binaries attached.
```

### CI / CD workflow

| Trigger | What runs |
|---|---|
| Push to `main` | `ci.yml` — lint, typecheck, build, test |
| Pull request to `main` | `ci.yml` — same checks |
| Tag push `v*.*.*` or `v*.*.*-*` | `release.yml` — build all platforms, upload to Release |

### Notes

- **vgmstream** is auto-downloaded by `scripts/download_vgmstream.py` during the build — no manual vendor setup needed.
- The `chunitools.spec` file defines the PyInstaller build; you can also run `uv run pyinstaller --noconfirm chunitools.spec` directly.
- The config file lives at one of the following paths depending on your platform (TOML format with sections — see `src/config.py`):
  - **Linux**: `~/.config/chunitools/config.toml`
  - **macOS**: `~/Library/Application Support/chunitools/config.toml`
  - **Windows**: `%LOCALAPPDATA%\chunitools\config.toml`
