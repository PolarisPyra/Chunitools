import sys
from pathlib import Path

# Ensure project root is in sys.path for direct script execution
if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.app.bootstrap import run


def run_app() -> int:
    """Entry point for the application."""
    return run()


if __name__ == "__main__":
    sys.exit(run_app())
