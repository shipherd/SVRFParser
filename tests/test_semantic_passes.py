"""Tests for the staged semantic validation pipeline."""

from __future__ import annotations

import unittest

from svrf_parser import parse
from svrf_parser.semantic_passes import (
    classify_semantic_diagnostic,
    run_semantic_validation_pass,
    run_symbol_table_pass,
)


class SemanticPassTests(unittest.TestCase):
    def test_semantic_validation_pass_exposes_stage_buckets(self):
        program = parse(
            "\n".join(
                [
                    "DRC RESULTS DATABASE",
                    "GROUP EMPTY_GROUP",
                    "M1 = NO_SUCH_LAYER",
                    "RULE1 { PATHCHK }",
                ]
            )
        )
        symbol_pass = run_symbol_table_pass(program.statements)
        semantic_pass = run_semantic_validation_pass(
            program,
            symbol_table=symbol_pass.symbol_table,
        )

        all_codes = {diagnostic.code for diagnostic in semantic_pass.diagnostics}
        self.assertIn("semantic.directive.missing_argument", all_codes)
        self.assertIn("semantic.group.empty", all_codes)
        self.assertIn("semantic.reference.undefined", all_codes)
        self.assertIn("semantic.drc.missing_operand", all_codes)

        self.assertIn(
            "semantic.directive.missing_argument",
            {diagnostic.code for diagnostic in semantic_pass.buckets.directive_contract},
        )
        self.assertIn(
            "semantic.group.empty",
            {diagnostic.code for diagnostic in semantic_pass.buckets.scope_resolution},
        )
        self.assertIn(
            "semantic.reference.undefined",
            {diagnostic.code for diagnostic in semantic_pass.buckets.reference_classification},
        )
        self.assertIn(
            "semantic.drc.missing_operand",
            {diagnostic.code for diagnostic in semantic_pass.buckets.drc_operation},
        )

    def test_classify_semantic_diagnostic_keeps_unknown_codes_isolated(self):
        class DiagnosticLike:
            code = "semantic.future.manual_exception"

        self.assertEqual("other", classify_semantic_diagnostic(DiagnosticLike()))


if __name__ == "__main__":
    unittest.main()
