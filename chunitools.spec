
# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None
platform_name = 'windows' if sys.platform.startswith('win') else 'macos' if sys.platform == 'darwin' else 'linux'
cli_name = 'vgmstream-cli.exe' if platform_name == 'windows' else 'vgmstream-cli'
cli_path = Path('vendor') / 'vgmstream' / platform_name / cli_name
vgmstream_binaries = [(str(cli_path), 'vgmstream')] if cli_path.exists() else []

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=vgmstream_binaries,
    datas=[],
    hiddenimports=[
        'qtawesome',
        'PySide6.QtSvg',
        'PySide6.QtXml',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='chunitools',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
