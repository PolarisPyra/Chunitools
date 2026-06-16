"""Download and install vgmstream-cli into the app config directory."""

from __future__ import annotations

import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import platformdirs

from src.utils.audio import find_vgmstream_cli

VGMSTREAM_DOWNLOAD_BASE_URL = (
    "https://github.com/vgmstream/vgmstream-releases/releases/download/nightly"
)
VGMSTREAM_INSTALL_DIR_NAME = "vgmstream"


class VgmstreamDownloadError(RuntimeError):
    """Raised when vgmstream-cli cannot be downloaded or installed."""


@dataclass(frozen=True, slots=True)
class VgmstreamDownloadAsset:
    """Download metadata for the current OS-specific vgmstream-cli archive."""

    filename: str
    url: str


def default_vgmstream_install_dir() -> Path:
    """Return the app-managed vgmstream install directory."""
    return Path(platformdirs.user_config_dir("chunitools")) / VGMSTREAM_INSTALL_DIR_NAME


def select_vgmstream_asset(
    platform_name: str = sys.platform,
    machine_name: str | None = None,
) -> VgmstreamDownloadAsset:
    """Return the vgmstream archive matching the current operating system."""
    machine = (machine_name or platform.machine()).lower()

    if platform_name.startswith("win"):
        filename = (
            "vgmstream-win64.zip" if "64" in machine or machine == "amd64" else "vgmstream-win.zip"
        )
    elif platform_name.startswith("linux"):
        filename = "vgmstream-linux-cli.tar.gz"
    elif platform_name == "darwin":
        filename = "vgmstream-mac-cli.tar.gz"
    else:
        raise VgmstreamDownloadError(f"Unsupported OS for vgmstream download: {platform_name}")

    return VgmstreamDownloadAsset(
        filename=filename,
        url=f"{VGMSTREAM_DOWNLOAD_BASE_URL}/{filename}",
    )


def download_vgmstream_cli(
    install_dir: Path | None = None,
    asset: VgmstreamDownloadAsset | None = None,
) -> Path:
    """Download, extract, and validate vgmstream-cli.

    Returns the directory that should be saved to ``vgstreamcli_path``.
    """
    target_dir = install_dir or default_vgmstream_install_dir()
    selected_asset = asset or select_vgmstream_asset()

    target_dir.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="chunitools-vgmstream-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        archive_path = temp_dir / selected_asset.filename
        staging_dir = temp_dir / "extracted"
        staging_dir.mkdir()

        _download_file(selected_asset.url, archive_path)
        _extract_archive(archive_path, staging_dir)

        cli_path = find_vgmstream_cli(str(staging_dir))
        if cli_path is None:
            raise VgmstreamDownloadError(
                f"Downloaded archive does not contain vgmstream-cli: {selected_asset.filename}"
            )
        _make_executable(cli_path)

        replacement_dir = temp_dir / VGMSTREAM_INSTALL_DIR_NAME
        staging_dir.rename(replacement_dir)
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.move(str(replacement_dir), str(target_dir))

    validated_cli = find_vgmstream_cli(str(target_dir))
    if validated_cli is None:
        raise VgmstreamDownloadError(f"Installed vgmstream-cli could not be found in {target_dir}")
    _make_executable(validated_cli)
    return target_dir


def _download_file(url: str, destination: Path) -> None:
    try:
        with urlopen(url, timeout=60) as response:
            with destination.open("wb") as fh:
                shutil.copyfileobj(response, fh)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise VgmstreamDownloadError(f"Could not download vgmstream from {url}: {exc}") from exc


def _extract_archive(archive_path: Path, destination: Path) -> None:
    if archive_path.suffix == ".zip":
        _extract_zip(archive_path, destination)
        return

    if archive_path.name.endswith(".tar.gz") or archive_path.suffix == ".tgz":
        _extract_tar(archive_path, destination)
        return

    raise VgmstreamDownloadError(f"Unsupported vgmstream archive type: {archive_path.name}")


def _extract_zip(archive_path: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                target_path = _safe_archive_target(destination, member.filename)
                if member.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src:
                    with target_path.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
    except (OSError, zipfile.BadZipFile) as exc:
        raise VgmstreamDownloadError(f"Could not extract {archive_path.name}: {exc}") from exc


def _extract_tar(archive_path: Path, destination: Path) -> None:
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                target_path = _safe_archive_target(destination, member.name)
                if member.isdir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    continue
                target_path.parent.mkdir(parents=True, exist_ok=True)
                src = archive.extractfile(member)
                if src is None:
                    continue
                with src:
                    with target_path.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
    except (OSError, tarfile.TarError) as exc:
        raise VgmstreamDownloadError(f"Could not extract {archive_path.name}: {exc}") from exc


def _safe_archive_target(destination: Path, member_name: str) -> Path:
    destination_root = destination.resolve()
    target_path = (destination / member_name).resolve()
    if not target_path.is_relative_to(destination_root):
        raise VgmstreamDownloadError(f"Archive contains unsafe path: {member_name}")
    return target_path


def _make_executable(path: Path) -> None:
    if sys.platform == "win32":
        return
    current_mode = path.stat().st_mode
    path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
