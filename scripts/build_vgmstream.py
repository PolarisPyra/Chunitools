from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "build" / "vgmstream-src"
BUILD_DIR = ROOT / "build" / "vgmstream"
INSTALL_DIR = ROOT / "vendor" / "vgmstream"
VGMSTREAM_REPO = "https://github.com/vgmstream/vgmstream.git"
VGMSTREAM_REF = "master"


def _zig_executable() -> Path | None:
    exe = shutil.which("zig")
    return Path(exe) if exe else None


def _cmake_configure_command() -> list[str]:
    command = [
        "cmake",
        "-S",
        str(SOURCE_DIR),
        "-B",
        str(BUILD_DIR),
        "-DBUILD_SHARED_LIBS=ON",
        "-DBUILD_CLI=OFF",
        "-DUSE_VORBIS=OFF",
        "-DUSE_FFMPEG=OFF",
        "-DUSE_G719=OFF",
        "-DUSE_ATRAC9=OFF",
        "-DUSE_CELT=OFF",
        "-DUSE_SPEEX=OFF",
    ]

    zig = _zig_executable()
    if sys.platform == "win32" and zig is not None:
        command.extend(
            [
                "-G",
                "Ninja",
                f"-DCMAKE_C_COMPILER={zig}",
                "-DCMAKE_C_COMPILER_ARG1=cc",
                "-DCMAKE_C_COMPILER_TARGET=x86_64-windows-gnu",
                f"-DCMAKE_CXX_COMPILER={zig}",
                "-DCMAKE_CXX_COMPILER_ARG1=c++",
                "-DCMAKE_CXX_COMPILER_TARGET=x86_64-windows-gnu",
            ]
        )

    return command


def _cmake_build_command() -> list[str]:
    return [
        "cmake",
        "--build",
        str(BUILD_DIR),
        "--config",
        "Release",
        "--target",
        "libvgmstream_shared",
    ]


def _run_command(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _ensure_source() -> None:
    if SOURCE_DIR.exists():
        _run_command(["git", "fetch", "--depth", "1", "origin", VGMSTREAM_REF], cwd=SOURCE_DIR)
        _run_command(["git", "reset", "--hard", "FETCH_HEAD"], cwd=SOURCE_DIR)
        _run_command(["git", "clean", "-fdx"], cwd=SOURCE_DIR)
        return

    SOURCE_DIR.parent.mkdir(parents=True, exist_ok=True)
    _run_command(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            VGMSTREAM_REF,
            VGMSTREAM_REPO,
            str(SOURCE_DIR),
        ]
    )


def main() -> None:
    _ensure_source()
    _run_command(_cmake_configure_command())
    _run_command(_cmake_build_command())


if __name__ == "__main__":
    main()
