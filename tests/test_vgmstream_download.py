from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from src.utils.vgmstream import (
    VgmstreamDownloadAsset,
    VgmstreamDownloadError,
    download_vgmstream_cli,
    select_vgmstream_asset,
)


def test_select_vgmstream_asset_uses_current_os_downloads() -> None:
    assert select_vgmstream_asset("linux").filename == "vgmstream-linux-cli.tar.gz"
    assert select_vgmstream_asset("darwin").filename == "vgmstream-mac-cli.tar.gz"
    assert select_vgmstream_asset("win32", "AMD64").filename == "vgmstream-win64.zip"
    assert select_vgmstream_asset("win32", "x86").filename == "vgmstream-win.zip"


def test_select_vgmstream_asset_rejects_unsupported_os() -> None:
    with pytest.raises(VgmstreamDownloadError):
        select_vgmstream_asset("freebsd")


def test_download_vgmstream_cli_extracts_and_returns_install_dir(tmp_path: Path) -> None:
    archive_path = tmp_path / "vgmstream-test.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("vgmstream-test/vgmstream-cli", b"#!/bin/sh\n")

    install_dir = tmp_path / "config" / "chunitools" / "vgmstream"
    asset = VgmstreamDownloadAsset(
        filename=archive_path.name,
        url=archive_path.as_uri(),
    )

    resolved_dir = download_vgmstream_cli(install_dir=install_dir, asset=asset)

    cli_path = resolved_dir / "vgmstream-test" / "vgmstream-cli"
    assert resolved_dir == install_dir
    assert cli_path.exists()
    assert cli_path.stat().st_mode & stat.S_IXUSR


def test_download_vgmstream_cli_rejects_unsafe_archive_paths(tmp_path: Path) -> None:
    archive_path = tmp_path / "vgmstream-bad.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../vgmstream-cli", b"bad")

    asset = VgmstreamDownloadAsset(
        filename=archive_path.name,
        url=archive_path.as_uri(),
    )

    with pytest.raises(VgmstreamDownloadError):
        download_vgmstream_cli(install_dir=tmp_path / "install", asset=asset)
