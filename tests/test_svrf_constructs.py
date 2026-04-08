"""Tests for shared SVRF construct classification."""

from __future__ import annotations

import unittest

from svrf_parser import parse, validate_svrf
from svrf_parser.ast import ErrorNode
from svrf_parser.svrf_constructs import count_svrf_constructs, is_svrf_construct


class SvrfConstructTests(unittest.TestCase):
    def test_counts_macro_calls_as_svrf_constructs(self):
        tree = parse("CMACRO WIDTH_CHECK poly 0.5\n")

        self.assertEqual(1, count_svrf_constructs(tree.statements))
        self.assertTrue(is_svrf_construct(tree.statements[0]))

    def test_error_nodes_do_not_count_as_svrf_constructs(self):
        self.assertFalse(is_svrf_construct(ErrorNode("bad", "???")))

    def test_macro_only_input_is_not_labeled_as_no_svrf_constructs(self):
        result = validate_svrf("CMACRO NO_SUCH_MACRO ARG1\n")

        self.assertFalse(result.valid)
        self.assertIn("semantic.macro.undefined", {diag.code for diag in result.errors})
        self.assertNotIn("validation.no_svrf_constructs", {diag.code for diag in result.errors})


if __name__ == "__main__":
    unittest.main()
