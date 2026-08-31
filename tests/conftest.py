from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def tmp_path() -> Path:
    """Use a repository-local fixture directory on restricted Windows hosts."""
    path = Path(__file__).parent / ".runtime-tmp" / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path
