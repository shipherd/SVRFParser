"""Tests for the real-sample parser harness CLI."""

from __future__ import annotations

import io
import os
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from test_samples import _parse_cli_args, find_sample_files, run_tests


class SampleHarnessTests(unittest.TestCase):
    def test_parse_cli_args_accepts_sample_root_only(self):
        self.assertEqual(("samples", None, False, False), _parse_cli_args(["samples"]))

    def test_parse_cli_args_accepts_strict_warning_gate(self):
        self.assertEqual(
            ("samples", None, True, False),
            _parse_cli_args(["samples", "--fail-on-warnings"]),
        )

    def test_parse_cli_args_preserves_single_file_argument(self):
        self.assertEqual(
            ("samples", "one.drc", True, False),
            _parse_cli_args(["samples", "one.drc", "--fail-on-warnings"]),
        )

    def test_parse_cli_args_rejects_unknown_options(self):
        with self.assertRaises(SystemExit):
            _parse_cli_args(["samples", "--unknown"])

    def test_parse_cli_args_accepts_explicit_private_details(self):
        self.assertEqual(
            ("samples", None, False, True),
            _parse_cli_args(["samples", "--show-private-details"]),
        )

    def test_find_sample_files_accepts_direct_file_without_extension_filter(self):
        root = Path(__file__).resolve().parent / f"tmp_sample_harness_{os.getpid()}"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        try:
            path = root / "deck_without_extension"
            path.write_text("LAYER M1 1\n", encoding="utf-8")
            self.assertEqual([str(path)], find_sample_files(path))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_run_tests_fails_when_no_sample_files_are_selected(self):
        with patch("test_samples.find_sample_files", return_value=[]):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(1, run_tests("samples"))


if __name__ == "__main__":
    unittest.main()
