"""Tests for the auto-discovered manual audit helpers."""

from __future__ import annotations

import unittest

try:
    from tools.extract_doc_all_functions import (
        _collect_titles_from_subtree,
        _looks_like_function_root,
    )
except ModuleNotFoundError:
    _collect_titles_from_subtree = None
    _looks_like_function_root = None


@unittest.skipIf(_collect_titles_from_subtree is None, "local tools directory is not available")
class DocAuditTests(unittest.TestCase):
    def test_function_root_title_filter(self):
        self.assertTrue(_looks_like_function_root("Math Function Summary"))
        self.assertTrue(_looks_like_function_root("Trace Property Built-In Language Functions"))
        self.assertFalse(_looks_like_function_root("Unsupported Functionality Errors and Warnings"))
        self.assertFalse(_looks_like_function_root("Simple Example TVF Function and TVF Layer Operation Call"))

    def test_collect_titles_from_subtree_uses_identifier_titles(self):
        node = {
            "title": "Measurement Function Summary",
            "children": [
                {
                    "title": "EC Group: Edge Projections",
                    "children": [
                        {"title": "EC"},
                        {"title": "ECX"},
                        {"title": "ECYP"},
                    ],
                },
                {"title": "STRING_COMPare Return Values"},
                {"title": "Property Access Function Summary"},
                {"title": "DEVICE::DEBUG"},
            ],
        }
        names = _collect_titles_from_subtree(node)
        self.assertIn("EC", names)
        self.assertIn("ECX", names)
        self.assertIn("ECYP", names)
        self.assertIn("STRING_COMPARE", names)
        self.assertIn("DEVICE::DEBUG", names)


if __name__ == "__main__":
    unittest.main()
