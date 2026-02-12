"""Pytest configuration and shared fixtures for SVRF parser tests."""

import sys
import os
from pathlib import Path

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from svrf_parser import parse, parse_with_diagnostics
from svrf_parser.ast_nodes import Program


def pytest_addoption(parser):
    parser.addoption(
        "--samples-dir",
        action="store",
        default=os.environ.get("SVRF_SAMPLES_DIR", ""),
        help="Path to SVRF sample files directory",
    )
    parser.addoption(
        "--update-baseline",
        action="store_true",
        default=False,
        help="Update regression thresholds from current results",
    )


@pytest.fixture
def parse_snippet():
    """Parse SVRF text and return a Program node."""
    def _parse(text):
        return parse(text, filename="<test>")
    return _parse


@pytest.fixture
def parse_snippet_with_warnings():
    """Parse SVRF text and return (Program, warnings)."""
    def _parse(text):
        return parse_with_diagnostics(text, filename="<test>")
    return _parse


@pytest.fixture
def samples_dir(request):
    """Path to the SVRF samples directory."""
    return Path(request.config.getoption("--samples-dir"))


@pytest.fixture
def sample_files(samples_dir):
    """List of all sample file paths."""
    if not samples_dir.is_dir():
        pytest.skip(f"Samples dir not found: {samples_dir}")
    files = []
    for dirpath, _, filenames in os.walk(samples_dir):
        for fn in sorted(filenames):
            files.append(Path(dirpath) / fn)
    return files
