from pathlib import Path

import pytest

from tests.support import Project, make_project


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return make_project(tmp_path)
