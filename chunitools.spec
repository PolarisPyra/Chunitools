# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for chunitools.
#
# Build with:
#   uv run pyinstaller --noconfirm chunitools.spec
#
# vgmstream-cli is auto-downloaded by scripts/download_vgmstream.py
# or build.py.  The `--add-data` below bundles the whole vgmstream/
# directory so the app can find it at runtime via sys._MEIPASS.

import platform
import sys
from pathlib import Path

# ── Detect target OS ──────────────────────────────────────────────────
OS = "windows" if sys.platform.startswith("win") else \
     "macos"   if sys.platform.startswith("darwin") else "linux"
CLI = "vgmstream-cli.exe" if OS == "windows" else "vgmstream-cli"

# ── Vendor vgmstream path ────────────────────────────────────────────
VENDOR_VGM = Path(__file__).parent / "vendor" / "vgmstream"
VGM_DIR = VENDOR_VGM / OS

# Check that vgmstream-cli exists (download script should have been run first)
if not (VGM_DIR / CLI).exists():
    print(f"WARNING: vgmstream-cli not found at {VGM_DIR / CLI}")
    print("Run `python3 scripts/download_vgmstream.py` first, "
          "or use build.py which does this automatically.")
    VGM_SRC = str(VENDOR_VGM)  # bundle whole dir even if empty
else:
    VGM_SRC = str(VGM_DIR)

# ── Analysis ──────────────────────────────────────────────────────────
a = Analysis(
    ["src/main.py"],
    pathex=[],
    binaries=[],
    datas=[
        (VGM_SRC, "vgmstream"),
    ],
    hiddenimports=[
        "qtawesome",
        "pyflac",
        "PIL",
        "PIL._imaging",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="chunitools",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,           # terminal output for debugging / CLI mode
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
