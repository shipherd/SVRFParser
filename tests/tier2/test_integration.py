"""Tier 2 integration tests: end-to-end parsing of real sample files."""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from svrf_parser import parse_with_diagnostics
from sample_corpus import iter_sample_files
from svrf_parser.svrf_constructs import count_svrf_constructs

SAMPLES_DIR = Path(os.environ.get("SVRF_SAMPLES_DIR", ""))


def _collect_samples():
    if not os.environ.get("SVRF_SAMPLES_DIR") or not SAMPLES_DIR.exists():
        return []
    return list(iter_sample_files(SAMPLES_DIR))


_ALL_SAMPLES = _collect_samples()


@unittest.skipUnless(_ALL_SAMPLES, "No candidate files found")
class TestSampleParsing(unittest.TestCase):
    """Basic parsing assertions for every sample file."""

    def test_parses_without_exception(self):
        for sample_path in _ALL_SAMPLES:
            with self.subTest(sample=sample_path.name):
                text = sample_path.read_text(encoding="utf-8", errors="replace")
                tree, warnings = parse_with_diagnostics(text, filename=str(sample_path))
                self.assertIsNotNone(tree)
                self.assertEqual([], [warning.code for warning in warnings])

    def test_has_statements(self):
        for sample_path in _ALL_SAMPLES:
            with self.subTest(sample=sample_path.name):
                text = sample_path.read_text(encoding="utf-8", errors="replace")
                tree, _ = parse_with_diagnostics(text, filename=str(sample_path))
                self.assertGreater(len(tree.statements), 0)

    def test_svrf_node_ratio(self):
        """At least 20% of top-level statements should be SVRF constructs."""
        for sample_path in _ALL_SAMPLES:
            with self.subTest(sample=sample_path.name):
                text = sample_path.read_text(encoding="utf-8", errors="replace")
                tree, _ = parse_with_diagnostics(text, filename=str(sample_path))
                total = len(tree.statements)
                svrf_count = count_svrf_constructs(tree.statements)
                ratio = svrf_count / total if total else 0
                self.assertGreaterEqual(
                    ratio,
                    0.20,
                    f"SVRF ratio {ratio:.1%} < 20% ({svrf_count}/{total} statements)",
                )


if __name__ == "__main__":
    unittest.main()
