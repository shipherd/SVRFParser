"""Tests for AST traversal helpers used by tooling."""

from __future__ import annotations

import unittest

import baseline
from svrf_parser import parse
from svrf_parser.diagnostics import Diagnostic, SEVERITY_WARNING
from tests.helpers import count_node_types, walk_ast


class AstTraversalHelperTests(unittest.TestCase):
    def test_baseline_walker_matches_canonical_ast_walk(self):
        tree = parse(
            "VARIABLE WIDTH 0.1\n"
            "M1.W.1 {\n"
            "  @ Minimum width ^WIDTH\n"
            "  INT M1 < WIDTH\n"
            "}\n"
        )

        self.assertEqual(
            [type(node).__name__ for node in tree.walk()],
            [type(node).__name__ for node in baseline.walk_ast(tree)],
        )

    def test_test_helper_counts_description_varrefs(self):
        tree = parse(
            "VARIABLE WIDTH 0.1\n"
            "M1.W.1 {\n"
            "  @ Minimum width ^WIDTH\n"
            "  INT M1 < WIDTH\n"
            "}\n"
        )

        self.assertEqual(
            [type(node).__name__ for node in tree.walk()],
            [type(node).__name__ for node in walk_ast(tree)],
        )
        self.assertEqual(1, count_node_types(tree)["VarRef"])

    def test_baseline_warning_categories_use_diagnostic_codes(self):
        categories = baseline.categorize_warnings(
            [
                Diagnostic(SEVERITY_WARNING, "parser.unrecognized_statement", "opaque"),
                Diagnostic(SEVERITY_WARNING, "parser.assignment.empty", "opaque"),
                Diagnostic(SEVERITY_WARNING, "parser.future_code", "opaque"),
            ]
        )

        self.assertEqual(1, categories["unrecognized"])
        self.assertEqual(1, categories["assignment_empty"])
        self.assertEqual(1, categories["parser_other"])


if __name__ == "__main__":
    unittest.main()
