"""Shared fixtures. Model tests read the snapshot unless CAPTURE_TEST_DATA points elsewhere."""

import os
from pathlib import Path

import pytest

from capture.config import DATA_SNAPSHOT


@pytest.fixture(scope="session")
def data_dir() -> Path:
    override = os.environ.get("CAPTURE_TEST_DATA")
    return Path(override) if override else DATA_SNAPSHOT
