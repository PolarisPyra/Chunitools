from __future__ import annotations

import scripts.build_vgmstream as build_vgmstream
from scripts.build_vgmstream import _cmake_build_command, _cmake_configure_command


def test_vgmstream_configure_disables_nonessential_optional_codecs_for_app_bundle() -> None:
    command = _cmake_configure_command()

    assert "-DBUILD_SHARED_LIBS=ON" in command
    assert "-DBUILD_CLI=OFF" in command
    assert "-DUSE_VORBIS=OFF" in command
    assert "-DUSE_FFMPEG=OFF" in command
    assert "-DUSE_G719=OFF" in command
    assert "-DUSE_ATRAC9=OFF" in command
    assert "-DUSE_CELT=OFF" in command
    assert "-DUSE_SPEEX=OFF" in command


def test_vgmstream_build_uses_release_config_for_windows_generators() -> None:
    command = _cmake_build_command()

    assert command[:2] == ["cmake", "--build"]
    assert "--config" in command
    assert "Release" in command
    assert "--target" in command
    assert "libvgmstream_shared" in command


def test_vgmstream_configure_can_use_project_managed_windows_toolchain(
    monkeypatch,
) -> None:
    monkeypatch.setattr(build_vgmstream.sys, "platform", "win32")
    monkeypatch.setattr(
        build_vgmstream,
        "_zig_executable",
        lambda: build_vgmstream.Path("C:/toolchain/zig.exe"),
    )

    command = _cmake_configure_command()

    assert "-G" in command
    assert "Ninja" in command
    assert any(option.startswith("-DCMAKE_C_COMPILER=") for option in command)
    assert "-DCMAKE_C_COMPILER_ARG1=cc" in command
    assert "-DCMAKE_C_COMPILER_TARGET=x86_64-windows-gnu" in command
    assert any(option.startswith("-DCMAKE_CXX_COMPILER=") for option in command)
    assert "-DCMAKE_CXX_COMPILER_ARG1=c++" in command
    assert "-DCMAKE_CXX_COMPILER_TARGET=x86_64-windows-gnu" in command


def test_existing_vgmstream_source_is_hard_reset_and_cleaned(monkeypatch, tmp_path) -> None:
    source_dir = tmp_path / "vgmstream-src"
    source_dir.mkdir()
    commands: list[tuple[list[str], object]] = []

    def fake_run_command(command: list[str], *, cwd=None) -> None:
        commands.append((command, cwd))

    monkeypatch.setattr(build_vgmstream, "SOURCE_DIR", source_dir)
    monkeypatch.setattr(build_vgmstream, "_run_command", fake_run_command)

    build_vgmstream._ensure_source()

    assert commands == [
        (["git", "fetch", "--depth", "1", "origin", build_vgmstream.VGMSTREAM_REF], source_dir),
        (["git", "reset", "--hard", "FETCH_HEAD"], source_dir),
        (["git", "clean", "-fdx"], source_dir),
    ]
