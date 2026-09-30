"""Privacy regressions using synthetic source names and temporary files."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import audit_sample_corpus
import baseline
import coverage_analysis
import test_samples
from report_privacy import ReportPrivacy
from svrf_parser import parse
from svrf_parser.ast import AstNode
from svrf_parser.diagnostics import Diagnostic, SEVERITY_WARNING


def _private_diagnostic(path):
    return Diagnostic(
        SEVERITY_WARNING,
        "semantic.reference.undefined",
        f"Unknown symbol CONFIDENTIAL_NET in {path}",
        filename=str(path),
        line=2,
        col=3,
        snippet="COPY CONFIDENTIAL_NET",
        include_stack=(str(path),),
        metadata={"symbol": "CONFIDENTIAL_NET", "nested": {str(path): "private"}},
    )


def _audit_summary(path):
    return audit_sample_corpus.audit_validation_result(
        path,
        SimpleNamespace(valid=True, errors=[], warnings=[_private_diagnostic(path)]),
    )


class ReportPrivacyTests(unittest.TestCase):
    def test_file_aliases_are_stable_distinct_and_do_not_include_names(self):
        privacy = ReportPrivacy()
        self.assertEqual("file-0001", privacy.path("restricted-deck.15a"))
        self.assertEqual("file-0001", privacy.path("restricted-deck.15a"))
        self.assertEqual("file-0002", privacy.path("another-deck.13a"))

    def test_symbol_aliases_are_stable_across_summaries(self):
        privacy = ReportPrivacy()
        self.assertEqual({"symbol-0001": 2}, privacy.symbol_counts({"CONFIDENTIAL_NET": 2}))
        self.assertEqual(
            {"symbol-0001": 1, "symbol-0002": 3},
            privacy.symbol_counts({"CONFIDENTIAL_NET": 1, "PRIVATE_LAYER": 3}),
        )

    def test_exception_messages_and_legacy_warning_strings_are_redacted(self):
        privacy = ReportPrivacy()
        self.assertEqual("PermissionError", privacy.exception(PermissionError("private-file")))
        self.assertEqual("parser.warning", privacy.diagnostic("private-source-text"))

    def test_structured_diagnostics_only_expose_codes(self):
        self.assertEqual(
            "semantic.reference.undefined",
            ReportPrivacy().diagnostic(_private_diagnostic("restricted-deck.15a")),
        )

    def test_private_output_requires_explicit_opt_in(self):
        privacy = ReportPrivacy(show_private_details=True)
        self.assertEqual("restricted-deck.15a", privacy.path("restricted-deck.15a"))
        self.assertEqual({"PRIVATE_LAYER": 1}, privacy.symbol_counts({"PRIVATE_LAYER": 1}))
        self.assertEqual("private-error", privacy.exception(ValueError("private-error")))
        self.assertIn("CONFIDENTIAL_NET", privacy.diagnostic(_private_diagnostic("deck")))


class RedactedSerializationTests(unittest.TestCase):
    def test_diagnostics_remove_all_source_text_and_metadata(self):
        diagnostic = _private_diagnostic("restricted-deck.15a")
        payload = diagnostic.to_dict(redact_source=True)
        self.assertEqual("semantic.reference.undefined", payload["code"])
        self.assertEqual((2, 3), (payload["line"], payload["col"]))
        self.assertEqual({}, payload["metadata"])
        self.assertEqual((), payload["include_stack"])
        rendered = json.dumps(payload)
        for private in ("CONFIDENTIAL_NET", "restricted-deck.15a", "COPY", "nested"):
            self.assertNotIn(private, rendered)
        self.assertIn("CONFIDENTIAL_NET", json.dumps(diagnostic.to_dict()))

    def test_ast_redaction_removes_names_literals_paths_and_opaque_payloads(self):
        tree = parse(
            'VARIABLE PRIVATE_VARIABLE 987.123\n'
            'INCLUDE "restricted-deck.15a"\n'
            'PRIVATE_RULE { COPY PRIVATE_LAYER }\n'
            '#ENCRYPT\nPRIVATE_OPAQUE_PAYLOAD\n#ENDCRYPT\n',
            filename="private-root.svrf",
        )
        payload = tree.to_dict(redact_source=True)
        self.assertEqual("Program", payload["type"])
        self.assertEqual(4, len(payload["statements"]))
        rendered = json.dumps(payload)
        for private in (
            "PRIVATE_VARIABLE", "987.123", "restricted-deck.15a", "PRIVATE_RULE",
            "PRIVATE_LAYER", "PRIVATE_OPAQUE_PAYLOAD", "private-root.svrf",
            "filename", "source_text", "include_stack",
        ):
            self.assertNotIn(private, rendered)
        original = json.dumps(tree.to_dict(include_position=False))
        self.assertIn("restricted-deck.15a", original)
        self.assertIn("PRIVATE_OPAQUE_PAYLOAD", original)

    def test_ast_redaction_does_not_mutate_original_tree(self):
        tree = parse("A = SIZE M1 BY 0.25\n")
        before = tree.to_dict()
        payload = tree.to_dict(include_position=True, redact_source=True)
        self.assertNotIn("line", payload)
        self.assertEqual(before, tree.to_dict())

    def test_unknown_scalar_metadata_does_not_escape_redaction(self):
        class MetadataNode(AstNode):
            __slots__ = ("payload",)

        node = MetadataNode()
        node.payload = {"restricted-file": ["private-value"]}
        self.assertIsNone(node.to_dict(redact_source=True)["payload"])


class CorpusCommandPrivacyTests(unittest.TestCase):
    def test_manual_inventory_errors_do_not_reveal_input_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "restricted-inventory.json"
            inventory.write_text("", encoding="utf-8")
            output = io.StringIO()
            with patch("coverage_analysis.DOCS_TOC", inventory), \
                    patch("coverage_analysis.extract_doc_constructs",
                          side_effect=ValueError(str(inventory))), redirect_stdout(output):
                self.assertEqual(1, coverage_analysis.main())
            self.assertIn("ValueError", output.getvalue())
            self.assertNotIn(str(inventory), output.getvalue())

    def test_coverage_write_errors_do_not_reveal_output_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory = root / "toc.json"
            inventory.write_text("", encoding="utf-8")
            missing_output = root / "missing" / "restricted-report.json"
            output = io.StringIO()
            with patch("coverage_analysis.DOCS_TOC", inventory), \
                    patch("coverage_analysis.MATRIX_PATH", missing_output), \
                    patch("coverage_analysis.extract_doc_constructs", return_value=[]), \
                    redirect_stdout(output):
                self.assertEqual(1, coverage_analysis.main())
            self.assertIn("FileNotFoundError", output.getvalue())
            self.assertNotIn(str(missing_output), output.getvalue())

    def test_parser_gate_redacts_warning_messages_and_source_paths(self):
        output = io.StringIO()
        with patch("test_samples.find_sample_files", return_value=["restricted-deck.15a"]), \
                patch("test_samples.os.path.getsize", return_value=1), \
                patch("test_samples.parse_file_with_diagnostics", return_value=(
                    parse("LAYER M1 1\n"), [_private_diagnostic("restricted-deck.15a")],
                )), redirect_stdout(output):
            status = test_samples.run_tests("private-root", fail_on_warnings=True)
        self.assertEqual(1, status)
        self.assertIn("file-0001", output.getvalue())
        self.assertIn("semantic.reference.undefined", output.getvalue())
        self.assertNotIn("restricted-deck", output.getvalue())
        self.assertNotIn("CONFIDENTIAL_NET", output.getvalue())

    def test_parser_gate_redacts_file_size_errors(self):
        output = io.StringIO()
        with patch("test_samples.find_sample_files", return_value=["restricted-deck.15a"]), \
                patch("test_samples.os.path.getsize", side_effect=OSError("restricted-deck.15a")), \
                redirect_stdout(output):
            self.assertEqual(1, test_samples.run_tests("private-root"))
        self.assertIn("OSError", output.getvalue())
        self.assertNotIn("restricted-deck", output.getvalue())

    def test_parser_gate_can_opt_in_to_private_details(self):
        output = io.StringIO()
        with patch("test_samples.find_sample_files", return_value=["restricted-deck.15a"]), \
                patch("test_samples.os.path.getsize", return_value=1), \
                patch("test_samples.parse_file_with_diagnostics", return_value=(
                    parse("LAYER M1 1\n"), [_private_diagnostic("restricted-deck.15a")],
                )), redirect_stdout(output):
            test_samples.run_tests("private-root", fail_on_warnings=True, show_private_details=True)
        self.assertIn("restricted-deck.15a", output.getvalue())
        self.assertIn("CONFIDENTIAL_NET", output.getvalue())

    def test_audit_redacts_paths_and_symbols_in_aggregate_and_per_file(self):
        output = io.StringIO()
        with redirect_stdout(output):
            audit_sample_corpus._print_summary([
                _audit_summary("restricted-deck.15a"), _audit_summary("second-deck.13a"),
            ])
        self.assertIn("symbol-0001=2", output.getvalue())
        self.assertIn("file-0001", output.getvalue())
        self.assertIn("file-0002", output.getvalue())
        self.assertNotIn("restricted-deck", output.getvalue())
        self.assertNotIn("second-deck", output.getvalue())
        self.assertNotIn("CONFIDENTIAL_NET", output.getvalue())

    def test_summary_only_audit_still_redacts_symbols(self):
        output = io.StringIO()
        with redirect_stdout(output):
            audit_sample_corpus._print_summary([_audit_summary("private-file")], include_files=False)
        self.assertIn("symbol-0001", output.getvalue())
        self.assertNotIn("CONFIDENTIAL_NET", output.getvalue())
        self.assertNotIn("private-file", output.getvalue())

    def test_audit_can_opt_in_to_private_details(self):
        output = io.StringIO()
        with redirect_stdout(output):
            audit_sample_corpus._print_summary(
                [_audit_summary("restricted-deck.15a")],
                privacy=ReportPrivacy(show_private_details=True),
            )
        self.assertIn("restricted-deck.15a", output.getvalue())
        self.assertIn("CONFIDENTIAL_NET", output.getvalue())

    def test_audit_redacts_manifest_load_errors(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("audit_sample_corpus.load_symbol_manifest",
                      side_effect=ValueError("restricted-manifest.json")):
            with self.assertRaises(SystemExit) as raised:
                audit_sample_corpus.main([directory, "--symbol-manifest", "restricted-manifest.json"])
        self.assertIn("ValueError", str(raised.exception))
        self.assertNotIn("restricted-manifest", str(raised.exception))

    def test_missing_audit_root_is_not_echoed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit) as raised:
                audit_sample_corpus.main([str(Path(directory) / "restricted-missing-root")])
        self.assertNotIn("restricted-missing-root", str(raised.exception))

    def test_baseline_redacts_json_and_console_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = root / "restricted-deck.15a"
            deck.write_text("LAYER PRIVATE_LAYER 1\n", encoding="utf-8")
            report = root / "metrics.json"
            output = io.StringIO()
            with patch("baseline.REPORT_PATH", report), redirect_stdout(output):
                self.assertEqual(0, baseline.main([str(deck)]))
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(payload["source_details_redacted"])
            self.assertEqual("<redacted>", payload["samples_dir"])
            self.assertEqual("file-0001", payload["files"][0]["file"])
            rendered = json.dumps(payload) + output.getvalue()
            for private in (str(root), "restricted-deck", "PRIVATE_LAYER"):
                self.assertNotIn(private, rendered)

    def test_baseline_redacts_exception_text_in_json_and_console(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = root / "restricted-deck.13a"
            deck.write_text("", encoding="utf-8")
            report = root / "metrics.json"
            output = io.StringIO()
            with patch("baseline.REPORT_PATH", report), \
                    patch("baseline.analyze_file", side_effect=ValueError("CONFIDENTIAL_NET")), \
                    redirect_stdout(output):
                baseline.main([str(deck)])
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual("ValueError", payload["files"][0]["error"])
            self.assertNotIn("CONFIDENTIAL_NET", json.dumps(payload) + output.getvalue())

    def test_baseline_private_mode_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = root / "restricted-deck.15a"
            deck.write_text("LAYER M1 1\n", encoding="utf-8")
            report = root / "metrics.json"
            with patch("baseline.REPORT_PATH", report), redirect_stdout(io.StringIO()):
                baseline.main([str(deck), "--show-private-details"])
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(payload["source_details_redacted"])
            self.assertEqual(str(deck), payload["files"][0]["file"])


if __name__ == "__main__":
    unittest.main()
