"""Tier 2 integration tests: end-to-end parsing of real sample files."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from svrf_parser import parse_with_diagnostics
from svrf_parser.ast_nodes import *

SAMPLES_DIR = Path(os.environ.get("SVRF_SAMPLES_DIR", ""))

_SVRF_NODE_TYPES = (
    LayerDef, LayerMap, LayerAssignment,
    Directive, RuleCheckBlock,
    Connect, Device, DMacro,
    Define, IfDef, Include, EncryptedBlock,
    Group, Attach, TraceProperty,
    VariableDef,
)


def _collect_samples():
    """Collect all sample files for parametrize."""
    files = []
    if not SAMPLES_DIR.is_dir():
        return files
    for dirpath, _, filenames in os.walk(SAMPLES_DIR):
        for fn in sorted(filenames):
            files.append(Path(dirpath) / fn)
    return files


_ALL_SAMPLES = _collect_samples()
_SAMPLE_IDS = [
    f.name for f in _ALL_SAMPLES
] if _ALL_SAMPLES else []


@pytest.mark.skipif(not _ALL_SAMPLES, reason="No sample files found")
class TestSampleParsing:
    """Basic parsing assertions for every sample file."""

    @pytest.mark.parametrize("sample_path", _ALL_SAMPLES, ids=_SAMPLE_IDS)
    def test_parses_without_exception(self, sample_path):
        text = sample_path.read_text(encoding='utf-8', errors='replace')
        tree, warnings = parse_with_diagnostics(text, filename=str(sample_path))
        assert tree is not None

    @pytest.mark.parametrize("sample_path", _ALL_SAMPLES, ids=_SAMPLE_IDS)
    def test_has_statements(self, sample_path):
        text = sample_path.read_text(encoding='utf-8', errors='replace')
        tree, _ = parse_with_diagnostics(text, filename=str(sample_path))
        assert len(tree.statements) > 0

    @pytest.mark.parametrize("sample_path", _ALL_SAMPLES, ids=_SAMPLE_IDS)
    def test_svrf_node_ratio(self, sample_path):
        """At least 20% of top-level statements should be SVRF constructs."""
        text = sample_path.read_text(encoding='utf-8', errors='replace')
        tree, _ = parse_with_diagnostics(text, filename=str(sample_path))
        total = len(tree.statements)
        svrf_count = sum(
            1 for s in tree.statements if isinstance(s, _SVRF_NODE_TYPES)
        )
        ratio = svrf_count / total if total else 0
        assert ratio >= 0.20, (
            f"SVRF ratio {ratio:.1%} < 20% "
            f"({svrf_count}/{total} statements)"
        )
