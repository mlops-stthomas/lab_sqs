import sys
from pathlib import Path


def pytest_configure(config):
    # Ensure repository root is on sys.path so package imports work when pytest
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
