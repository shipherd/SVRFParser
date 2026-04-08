import json
import unittest
from pathlib import Path

from svrf_parser import parse, validate_svrf


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "golden"
EXPECTED = json.loads((FIXTURE_DIR / "expected_snapshots.json").read_text(encoding="utf-8"))
SOURCE_FILES = {
    "layer_reference": "layer_reference.svrf",
    "limited_support": "limited_support.svrf",
    "operation_width": "operation_width.svrf",
    "ordered_directive_invalid": "ordered_directive_invalid.svrf",
    "ordered_directive_valid": "ordered_directive_valid.svrf",
    "property_scalar": "property_scalar.svrf",
}


class GoldenSnapshotTests(unittest.TestCase):
    maxDiff = None

    def _read_source(self, filename):
        return (FIXTURE_DIR / filename).read_text(encoding="utf-8")

    def _snapshot(self, source):
        tree = parse(source, filename="<golden>", strict=True)
        result = validate_svrf(
            source,
            filename="<golden>",
            strict=False,
            follow_includes=False,
        )
        return {
            "ast": tree.to_dict(include_position=False),
            "diagnostic_codes": [diag.code for diag in result.diagnostics],
        }

    def test_golden_ast_and_diagnostic_code_snapshots(self):
        for case_name, filename in SOURCE_FILES.items():
            with self.subTest(case_name=case_name):
                self.assertEqual(EXPECTED[case_name], self._snapshot(self._read_source(filename)))

    def test_operation_snapshot_is_stable_across_whitespace_variant(self):
        baseline = self._snapshot(self._read_source("operation_width.svrf"))
        variant = self._snapshot(self._read_source("operation_width_whitespace.svrf"))

        self.assertEqual(EXPECTED["operation_width"], baseline)
        self.assertEqual(EXPECTED["operation_width"], variant)

    def test_ordered_directive_snapshots_preserve_order_semantics(self):
        valid = self._snapshot(self._read_source("ordered_directive_valid.svrf"))
        invalid = self._snapshot(self._read_source("ordered_directive_invalid.svrf"))

        self.assertEqual([], valid["diagnostic_codes"])
        self.assertEqual(["semantic.directive.invalid_value"], invalid["diagnostic_codes"])

    def test_snapshot_fixture_does_not_store_local_paths(self):
        snapshot_text = json.dumps(EXPECTED, sort_keys=True)

        self.assertNotIn("C:\\", snapshot_text)
        self.assertNotIn("/Users/", snapshot_text)


if __name__ == "__main__":
    unittest.main()
