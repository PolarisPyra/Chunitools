"""Build standalone executables with PyInstaller.

Usage:
    python build.py                          # build for current platform
    python build.py --platform linux         # build for Linux
    python build.py --platform windows       # cross-build for Windows
    python build.py --platform macos         # cross-build for macOS
    python build.py --tag r2117              # use a specific vgmstream tag
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _detect_platform() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform.startswith("darwin"):
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    msg = f"Unsupported platform: {sys.platform}"
    raise RuntimeError(msg)


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"+ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=cwd)


def build() -> None:
    parser = argparse.ArgumentParser(description="Build chunitools executable")
    parser.add_argument(
        "--platform",
        default=_detect_platform(),
        choices=["linux", "macos", "windows"],
        help="Target platform (default: auto-detect)",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="vgmstream release tag (default: latest)",
    )
    args = parser.parse_args()

    root = Path(__file__).parent.resolve()
    platform = args.platform

    print(f"Building chunitools for {platform}...")

    # ── Step 1: Download vgmstream if not present or missing files ──
    vendor_dir = root / "vendor" / "vgmstream" / platform
    cli_name = "vgmstream-cli.exe" if platform == "windows" else "vgmstream-cli"
    if not (vendor_dir / cli_name).exists():
        print("vgmstream-cli not found in vendor directory, downloading...")
        dl_args = [sys.executable, "scripts/download_vgmstream.py", platform]
        if args.tag:
            dl_args.extend(["--tag", args.tag])
        _run(dl_args, cwd=root)
    else:
        print(f"vgmstream-cli already present at {vendor_dir / cli_name}")

    # ── Step 2: Run PyInstaller ──
    spec = root / "chunitools.spec"
    if spec.exists():
        _run(["uv", "run", "pyinstaller", "--noconfirm", str(spec)], cwd=root)
    else:
        # Build a one-file executable with sensible defaults
        _run(
            [
                "uv",
                "run",
                "pyinstaller",
                "--noconfirm",
                "--onefile",
                "--name", "chunitools",
                "--add-data", f"{vendor_dir}{';' if platform == 'windows' else ':'}vgmstream",
                "--collect-all", "PySide6",
                "--collect-all", "PIL",
                "--hidden-import", "qtawesome",
                "--hidden-import", "pyflac",
                str(root / "src" / "main.py"),
            ],
            cwd=root,
        )

    # ── Step 3: Stage and archive ──
    exe_name = "chunitools.exe" if platform == "windows" else "chunitools"
    dist_dir = root / "dist"
    dist_exe = dist_dir / exe_name

    if not dist_exe.exists():
        # PyInstaller puts it in dist/chunitools/chunitools when using --onedir
        fallback = dist_dir / "chunitools" / exe_name
        if fallback.exists():
            dist_exe = fallback
        else:
            print(f"Error: Could not find executable at {dist_exe} or {fallback}")
            sys.exit(1)

    staging = root / f"chunitools_{platform}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    shutil.copy2(dist_exe, staging / exe_name)

    builds_dir = root / "builds"
    builds_dir.mkdir(exist_ok=True)

    archive_format = "zip" if platform == "windows" else "gztar"
    archive_path = shutil.make_archive(
        str(builds_dir / f"chunitools_{platform}"),
        archive_format,
        str(staging),
    )

    # Cleanup
    shutil.rmtree(staging)
    shutil.rmtree(dist_dir, ignore_errors=True)
    shutil.rmtree(root / "build", ignore_errors=True)

    print(f"Build complete: {archive_path}")


if __name__ == "__main__":
    build()
