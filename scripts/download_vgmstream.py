#!/usr/bin/env python3
"""Download the latest vgmstream release for one or all platforms.

Usage:
    python scripts/download_vgmstream.py              # all platforms
    python scripts/download_vgmstream.py linux         # Linux only
    python scripts/download_vgmstream.py windows       # Windows (64-bit) only
    python scripts/download_vgmstream.py macos         # macOS only
    python scripts/download_vgmstream.py --tag r2117   # specific tag
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen

REPO = "vgmstream/vgmstream"
GITHUB_API = f"https://api.github.com/repos/{REPO}/releases"

# Maps our platform name → GitHub asset suffix and target dir
PLATFORM_ASSETS: dict[str, dict[str, str]] = {
    "linux": {
        "asset": "vgmstream-linux.zip",
        "dir": "linux",
    },
    "macos": {
        "asset": "vgmstream-mac.zip",
        "dir": "macos",
    },
    "windows": {
        "asset": "vgmstream-win64.zip",
        "dir": "windows",
    },
}

ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = ROOT / "vendor" / "vgmstream"


def _latest_tag(accept: str = "application/vnd.github+json") -> str:
    """Return the tag name of the latest vgmstream release."""
    url = f"{GITHUB_API}/latest"
    req = urlopen(url)  # noqa: S310
    data = json.loads(req.read().decode())
    return data["tag_name"]


def _asset_url(tag: str, platform: str) -> str:
    """Return the download URL for the given platform's asset at *tag*."""
    asset_name = PLATFORM_ASSETS[platform]["asset"]
    return f"https://github.com/{REPO}/releases/download/{tag}/{asset_name}"


def download(platform: str, tag: str) -> Path:
    """Download and extract the vgmstream release for *platform*, return the target path."""
    target = VENDOR_DIR / PLATFORM_ASSETS[platform]["dir"]
    target.mkdir(parents=True, exist_ok=True)

    asset_url = _asset_url(tag, platform)
    asset_name = PLATFORM_ASSETS[platform]["asset"]
    print(f"  Downloading {asset_name} ({tag}) ...", end=" ", flush=True)

    with TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        zip_path = tmp_dir / asset_name

        # Download
        with urlopen(asset_url) as resp:  # noqa: S310
            zip_path.write_bytes(resp.read())
        print("done")

        # Extract
        print(f"  Extracting to {target} ...", end=" ", flush=True)
        with zipfile.ZipFile(zip_path) as zf:
            # Check if all files are in a single root directory
            members = zf.namelist()
            root_dirs = {
                Path(m).parts[0] for m in members if Path(m).parts
            }
            # If the zip has a single top-level folder, strip it
            if len(root_dirs) == 1 and all(len(Path(m).parts) > 1 for m in members):
                prefix = f"{root_dirs.pop()}/"
                for member in members:
                    if member.endswith("/"):
                        continue
                    rel = Path(member).relative_to(prefix)
                    (target / rel.parent).mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, (target / rel).open("wb") as dst:
                        shutil.copyfileobj(src, dst)
            else:
                zf.extractall(target)
        print("done")

        # Make CLI executable on Unix
        cli_name = "vgmstream-cli.exe" if platform == "windows" else "vgmstream-cli"
        cli_path = target / cli_name
        if cli_path.exists():
            cli_path.chmod(cli_path.stat().st_mode | 0o111)

    # Write version marker
    (target / ".version").write_text(f"{tag}\n", encoding="utf-8")
    return target


def main() -> None:  # noqa: PLR0915
    parser = argparse.ArgumentParser(description="Download vgmstream for PyInstaller bundle")
    parser.add_argument(
        "platforms",
        nargs="*",
        default=list(PLATFORM_ASSETS),
        choices=list(PLATFORM_ASSETS) + ["all"],
        help="Target platform(s) to download for (default: all)",
    )
    parser.add_argument("--tag", help="Specific release tag (default: latest)")
    args = parser.parse_args()

    platforms: list[str] = args.platforms
    if "all" in platforms:
        platforms = list(PLATFORM_ASSETS)

    tag = args.tag or _latest_tag()
    print(f"vgmstream release: {tag}")
    print(f"Target platforms:   {', '.join(platforms)}")

    for platform in platforms:
        print(f"\n── {platform} ──")
        target = download(platform, tag)
        print(f"  Files in {target}:")
        for p in sorted(target.iterdir()):
            print(f"    {p.name}  ({p.stat().st_size / 1024:.0f} KB)" if p.is_file() else f"    {p.name}/")

    print("\nDone.")


if __name__ == "__main__":
    main()
