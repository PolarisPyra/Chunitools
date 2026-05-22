import shutil
import subprocess
import sys
from pathlib import Path

def build() -> None:
    root = Path(__file__).parent.resolve()
    
    os_name = "windows"
    if sys.platform.startswith("linux"):
        os_name = "linux"
    elif sys.platform.startswith("darwin"):
        os_name = "macos"
        
    print(f"Building chunitools for {os_name}...")
    
    # Run PyInstaller
    subprocess.run(["uv", "run", "pyinstaller", "--noconfirm", "chunitools.spec"], check=True)
    
    # Determine executable name and archive format
    exe_name = "chunitools.exe" if os_name == "windows" else "chunitools"
    dist_exe = root / "dist" / exe_name
    archive_format = "zip" if os_name == "windows" else "gztar"
    
    if not dist_exe.exists():
        print(f"Error: Could not find generated executable at {dist_exe}")
        sys.exit(1)
        
    # Stage and pack
    staging = root / f"chunitools_{os_name}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    
    shutil.copy2(dist_exe, staging / exe_name)
    
    builds_dir = root / "builds"
    builds_dir.mkdir(exist_ok=True)
    
    archive_path = shutil.make_archive(str(builds_dir / f"chunitools_{os_name}"), archive_format, str(staging))
    
    # Cleanup
    shutil.rmtree(staging)
    shutil.rmtree(root / "dist", ignore_errors=True)
    shutil.rmtree(root / "build", ignore_errors=True)
    
    print(f"Build complete: {archive_path}")

if __name__ == "__main__":
    build()
