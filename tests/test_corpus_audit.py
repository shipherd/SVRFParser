"""Tests for sample-corpus audit helpers."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from svrf_parser.diagnostics import Diagnostic, SEVERITY_ERROR, SEVERITY_WARNING
from audit_sample_corpus import (
    audit_validation_result,
    classify_diagnostic,
    extract_undefined_symbol_name,
    has_audit_failures,
    iter_sample_files,
)


class _FakeAuditPath:
    def __init__(self, name, *, is_file=True):
        self.name = name
        self.suffix = Path(name).suffix
        self._is_file = is_file

    def is_file(self):
        return self._is_file

    def __lt__(self, other):
        return self.name < other.name


class _FakeAuditRoot:
    def __init__(self, names):
        self._paths = tuple(_FakeAuditPath(name) for name in names)
        self._paths += (_FakeAuditPath("subdir", is_file=False),)

    def is_file(self):
        return False

    def rglob(self, pattern):
        self.pattern = pattern
        return self._paths


class CorpusAuditTests(unittest.TestCase):
    def test_iter_sample_files_includes_all_regular_files(self):
        sample_names = [
            "a.drc",
            "b.lvs",
            "c.svrf",
            "d.ant",
            "e.13a",
            "f.15a",
            "g.13_1a",
            "h.13_1a.encrypt",
            "ignore.txt",
            "extensionless",
        ]
        root = _FakeAuditRoot(sample_names)
        selected = {path.name for path in iter_sample_files(root)}

        self.assertEqual(set(sample_names), selected)

    def test_classify_diagnostic_buckets(self):
        self.assertEqual(
            classify_diagnostic(
                Diagnostic(SEVERITY_WARNING, "parser.assignment.empty", "msg")
            ),
            "parser_related",
        )
        self.assertEqual(
            classify_diagnostic(
                Diagnostic(SEVERITY_ERROR, "validation.include.missing_file", "msg")
            ),
            "sample_setup_issue",
        )
        self.assertEqual(
            classify_diagnostic(
                Diagnostic(
                    SEVERITY_WARNING,
                    "validation.encrypted_blocks.possible_hidden_definitions",
                    "msg",
                )
            ),
            "encrypted_hidden_definition",
        )
        self.assertEqual(
            classify_diagnostic(
                Diagnostic(
                    SEVERITY_WARNING,
                    "validation.support.limited_feature",
                    "msg",
                )
            ),
            "limited_support_feature",
        )
        self.assertEqual(
            classify_diagnostic(
                Diagnostic(SEVERITY_WARNING, "semantic.reference.undefined", "msg")
            ),
            "semantic_unresolved_symbol",
        )
        self.assertEqual(
            classify_diagnostic(
                Diagnostic(SEVERITY_WARNING, "semantic.reference.companion_candidate", "msg")
            ),
            "semantic_companion_symbol",
        )
        self.assertEqual(
            classify_diagnostic(
                Diagnostic(SEVERITY_WARNING, "semantic.reference.external_candidate", "msg")
            ),
            "semantic_external_symbol",
        )
        self.assertEqual(
            classify_diagnostic(
                Diagnostic(SEVERITY_WARNING, "semantic.reference.scalar_undefined", "msg")
            ),
            "semantic_scalar_symbol",
        )
        self.assertEqual(
            classify_diagnostic(
                Diagnostic(SEVERITY_WARNING, "semantic.reference.local_scope_only", "msg")
            ),
            "semantic_local_scope_symbol",
        )
        self.assertEqual(
            classify_diagnostic(
                Diagnostic(SEVERITY_ERROR, "semantic.device.missing_seed", "msg")
            ),
            "semantic_rule_issue",
        )

    def test_extract_undefined_symbol_name(self):
        self.assertEqual(
            extract_undefined_symbol_name(
                Diagnostic(
                    SEVERITY_WARNING,
                    "semantic.reference.undefined",
                    "message text without a parseable symbol",
                    metadata={"symbol": "HIDDEN_LAYER"},
                )
            ),
            "HIDDEN_LAYER",
        )
        self.assertEqual(
            extract_undefined_symbol_name(
                Diagnostic(
                    SEVERITY_WARNING,
                    "semantic.reference.undefined",
                    "Unknown layer or variable reference FALLBACK_LAYER",
                )
            ),
            "FALLBACK_LAYER",
        )
        self.assertEqual(
            extract_undefined_symbol_name(
                Diagnostic(
                    SEVERITY_WARNING,
                    "semantic.reference.companion_candidate",
                    "Reference EXTERNAL_NET has no visible plaintext definition in this file but appears in sibling companion SVRF files (setup.ant)",
                )
            ),
            "EXTERNAL_NET",
        )
        self.assertEqual(
            extract_undefined_symbol_name(
                Diagnostic(
                    SEVERITY_WARNING,
                    "semantic.reference.external_candidate",
                    "Reference RUNTIME_LAYER has no visible plaintext definition in this file or sibling companion decks; it may come from omitted include, tool runtime global",
                )
            ),
            "RUNTIME_LAYER",
        )
        self.assertEqual(
            extract_undefined_symbol_name(
                Diagnostic(
                    SEVERITY_WARNING,
                    "semantic.reference.scalar_undefined",
                    "Unresolved scalar parameter-like identifier WIDTH_CONST",
                )
            ),
            "WIDTH_CONST",
        )
        self.assertEqual(
            extract_undefined_symbol_name(
                Diagnostic(
                    SEVERITY_WARNING,
                    "semantic.reference.local_scope_only",
                    "Reference LOCAL_TMP is only defined in local rule, macro, or property scopes elsewhere in this file",
                )
            ),
            "LOCAL_TMP",
        )
        self.assertEqual(
            extract_undefined_symbol_name(
                Diagnostic(
                    SEVERITY_WARNING,
                    "semantic.varref.undefined",
                    "Description variable reference ^WIDTH has no matching VARIABLE",
                )
            ),
            "WIDTH",
        )
        self.assertIsNone(
            extract_undefined_symbol_name(
                Diagnostic(
                    SEVERITY_WARNING,
                    "semantic.connect.unknown_layer",
                    "msg",
                    metadata={"symbol": "MISSING_LAYER"},
                )
            )
        )

    def test_audit_validation_result_counts_categories_and_symbols(self):
        result = SimpleNamespace(
            valid=False,
            policy_summary=SimpleNamespace(
                policy="practical",
                raw_unresolved_count=5,
                deduped_unresolved_count=4,
                manifest_resolved_count=1,
                remaining_unresolved_count=3,
            ),
            errors=[
                Diagnostic(SEVERITY_ERROR, "validation.include.missing_file", "missing"),
                Diagnostic(SEVERITY_ERROR, "semantic.device.missing_seed", "missing seed"),
            ],
            warnings=[
                Diagnostic(
                    SEVERITY_WARNING,
                    "semantic.reference.undefined",
                    "Unknown layer or variable reference H1",
                ),
                Diagnostic(
                    SEVERITY_WARNING,
                    "semantic.reference.companion_candidate",
                    "Reference H2 has no visible plaintext definition in this file but appears in sibling companion SVRF files (companion.ant)",
                ),
                Diagnostic(
                    SEVERITY_WARNING,
                    "semantic.reference.external_candidate",
                    "Reference H3 has no visible plaintext definition in this file or sibling companion decks; it may come from omitted include, tool runtime global",
                ),
                Diagnostic(
                    SEVERITY_WARNING,
                    "semantic.reference.scalar_undefined",
                    "Unresolved scalar parameter-like identifier P1",
                ),
                Diagnostic(
                    SEVERITY_WARNING,
                    "semantic.reference.local_scope_only",
                    "Reference L1 is only defined in local rule, macro, or property scopes elsewhere in this file",
                ),
                Diagnostic(
                    SEVERITY_WARNING,
                    "validation.encrypted_blocks.possible_hidden_definitions",
                    "encrypted note",
                ),
            ],
        )
        summary = audit_validation_result(Path("sample.drc"), result)
        self.assertFalse(summary.valid)
        self.assertEqual(summary.error_count, 2)
        self.assertEqual(summary.warning_count, 6)
        self.assertEqual(summary.category_counts["sample_setup_issue"], 1)
        self.assertEqual(summary.category_counts["semantic_rule_issue"], 1)
        self.assertEqual(summary.category_counts["semantic_unresolved_symbol"], 1)
        self.assertEqual(summary.category_counts["semantic_companion_symbol"], 1)
        self.assertEqual(summary.category_counts["semantic_external_symbol"], 1)
        self.assertEqual(summary.category_counts["semantic_scalar_symbol"], 1)
        self.assertEqual(summary.category_counts["semantic_local_scope_symbol"], 1)
        self.assertEqual(summary.category_counts["encrypted_hidden_definition"], 1)
        self.assertEqual(summary.undefined_symbol_counts["H1"], 1)
        self.assertEqual(summary.undefined_symbol_counts["H2"], 1)
        self.assertEqual(summary.undefined_symbol_counts["H3"], 1)
        self.assertEqual(summary.undefined_symbol_counts["P1"], 1)
        self.assertEqual(summary.undefined_symbol_counts["L1"], 1)
        self.assertEqual(summary.dialects, ())
        self.assertEqual(summary.feature_families, ())
        self.assertEqual(summary.limited_support_features, ())
        self.assertEqual(summary.profile_tags, ())
        self.assertEqual(summary.unresolved_policy, "practical")
        self.assertEqual(summary.raw_unresolved_count, 5)
        self.assertEqual(summary.deduped_unresolved_count, 4)
        self.assertEqual(summary.manifest_resolved_count, 1)
        self.assertEqual(summary.remaining_unresolved_count, 3)

    def test_has_audit_failures_tracks_invalid_or_error_files(self):
        self.assertFalse(
            has_audit_failures(
                [
                    SimpleNamespace(valid=True, error_count=0),
                    SimpleNamespace(valid=True, error_count=0),
                ]
            )
        )
        self.assertTrue(
            has_audit_failures(
                [
                    SimpleNamespace(valid=True, error_count=0),
                    SimpleNamespace(valid=False, error_count=0),
                ]
            )
        )
        self.assertTrue(
            has_audit_failures(
                [
                    SimpleNamespace(valid=True, error_count=0),
                    SimpleNamespace(valid=True, error_count=1),
                ]
            )
        )


if __name__ == "__main__":
    unittest.main()
