"""Textual INCLUDE expansion and original-source diagnostic coverage."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from svrf_parser import ast, parse_file, validate_svrf, validate_svrf_file, is_valid_svrf_file


class IncludeExpansionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def validate(self, text, *, strict=True):
        root = self.write("deck.15a", text)
        return validate_svrf_file(root, strict=strict, run_directory=self.root)

    def assertValid(self, result):
        self.assertTrue(result.valid, result.diagnostics)

    def test_rule_body_fragment_is_inserted_before_parsing(self):
        child = self.write("body.13a", "TMP = COPY M1\nINT TMP < WIDTH")
        result = self.validate('LAYER M1 1\nVARIABLE WIDTH 0.1\nR {\nINCLUDE "body.13a"\n}\n')
        self.assertValid(result)
        operation = result.program.statements[2].body[1]
        self.assertEqual(str(child), operation.filename)
        self.assertEqual(2, operation.line)
        self.assertEqual("INT TMP < WIDTH", operation.source_text)
        self.assertEqual(len("TMP = COPY M1\n"), operation.start_offset)

    def test_include_can_supply_partial_rule_header_and_numeric_expression(self):
        self.write("header", "R {\n")
        self.write("expression", "(2 + 3) * 4")
        self.assertValid(self.validate('LAYER M1 1\nINCLUDE header\nCOPY M1\n}\n'))
        result = self.validate('LAYER M1 1\nVARIABLE X (\nINCLUDE expression\n)\n')
        self.assertValid(result)
        self.assertEqual("*", result.program.statements[1].values[0].op)

    def test_nested_include_uses_one_run_directory(self):
        self.write("sub/first", "INCLUDE second\n")
        self.write("second", "LAYER M1 1\n")
        self.assertValid(self.validate('INCLUDE sub/first\nR { COPY M1 }\n'))

    def test_default_include_base_is_cwd_not_the_rule_file_directory(self):
        run_dir = self.root / "run"
        run_dir.mkdir()
        self.write("run/defs", "LAYER M1 1\n")
        deck = self.write("rules/deck", "INCLUDE defs\nR { COPY M1 }\n")
        original_cwd = Path.cwd()
        try:
            os.chdir(run_dir)
            self.assertTrue(is_valid_svrf_file(deck, strict=True))
        finally:
            os.chdir(original_cwd)

    def test_missing_include_is_reported_inside_conditional_macro_and_plaintext_block(self):
        for text in (
            '#IFDEF ENABLE\nINCLUDE missing\n#ENDIF\nLAYER M1 1\n',
            'DMACRO CHECK {\nINCLUDE missing\n}\nLAYER M1 1\n',
            '#ENCRYPT\nINCLUDE missing\nLAYER M1 1\n#ENDCRYPT\n',
        ):
            with self.subTest(text=text):
                result = self.validate(text)
                self.assertIn("validation.include.missing_file", {d.code for d in result.errors})

    def test_nested_semantic_diagnostic_preserves_original_location_and_stack(self):
        middle = self.write("mid", "INCLUDE leaf\n")
        leaf = self.write("leaf", "// comment\nVARIABLE SECOND FIRST * 0.5\n")
        result = self.validate('INCLUDE mid\nVARIABLE FIRST 4\n')
        diagnostic = next(d for d in result.errors if d.code == "semantic.variable.before_definition")
        self.assertEqual(str(leaf), diagnostic.filename)
        self.assertEqual(2, diagnostic.line)
        self.assertIn("FIRST", diagnostic.snippet)
        self.assertEqual((str(self.root / "deck.15a"), str(middle)), diagnostic.include_stack)

    def test_parse_and_lexer_errors_are_mapped_to_child_file(self):
        for content, expected_code in (("VARIABLE X (\n", "validation.parse_error"), ("LAYER M1 1\n|\n", "validation.lexer_error")):
            with self.subTest(content=content):
                child = self.write("bad", content)
                result = self.validate('LAYER M2 2\nINCLUDE bad\n')
                diagnostic = next(d for d in result.errors if d.code == expected_code)
                self.assertEqual(str(child), diagnostic.filename)
                self.assertEqual((str(self.root / "deck.15a"),), diagnostic.include_stack)

    def test_repeated_include_has_occurrence_specific_stack(self):
        first = self.write("first", "INCLUDE leaf\n")
        second = self.write("second", "INCLUDE leaf\n")
        leaf = self.write("leaf", "TMP = COPY MISSING\n")
        result = self.validate('INCLUDE first\nINCLUDE second\n', strict=False)
        diagnostics = [d for d in result.warnings if (d.metadata or {}).get("symbol") == "MISSING"]
        self.assertEqual(2, len(diagnostics))
        self.assertEqual(str(leaf), diagnostics[0].filename)
        self.assertEqual((str(self.root / "deck.15a"), str(first)), diagnostics[0].include_stack)
        self.assertEqual((str(self.root / "deck.15a"), str(second)), diagnostics[1].include_stack)

    def test_include_precedes_block_comments_but_not_line_comments(self):
        result = self.validate('/*\nINCLUDE missing\n*/\nLAYER M1 1\n')
        self.assertIn("validation.include.missing_file", {d.code for d in result.errors})
        self.assertValid(self.validate('// INCLUDE missing\nLAYER M1 1\n'))
        self.write("commented", "LAYER M2 2\n")
        result = self.validate('/*\nINCLUDE commented\n*/\nLAYER M1 1\n')
        self.assertValid(result)
        self.assertEqual(["M1"], [s.name for s in result.program.statements])

    def test_plaintext_encrypted_include_is_parsed_and_keeps_raw_payload(self):
        child = self.write("defs", "LAYER M1 1\n")
        result = self.validate('#DECRYPT\nINCLUDE defs\n#ENDCRYPT\nR { COPY M1 }\n')
        self.assertValid(result)
        block = result.program.statements[0]
        self.assertEqual("INCLUDE defs", block.content)
        self.assertEqual("plaintext", block.parse_status)
        self.assertEqual(str(child), block.body[0].filename)
        self.assertEqual((str(self.root / "deck.15a"),), block.body[0].include_stack)

    def test_opaque_encrypted_payload_is_not_expanded(self):
        result = self.validate('#ENCRYPT\nabc@!xyz\nINCLUDE missing\n#ENDCRYPT\nLAYER M1 1\n')
        self.assertValid(result)
        self.assertEqual("opaque", result.program.statements[0].parse_status)

    def test_embedded_cell_list_and_filename_includes_are_not_rule_files(self):
        result = self.validate('VARIABLE CELLS\nINCLUDE absent.list\nDRC RESULTS DATABASE\nINCLUDE absent.config\nLAYER M1 1\n')
        self.assertValid(result)
        self.assertTrue(result.program.statements[0].values[0].embedded)
        self.assertTrue(result.program.statements[1].arguments[0].embedded)

    def test_follow_includes_false_and_parse_file_preserve_include_nodes(self):
        deck = self.write("deck.15a", "INCLUDE absent\nLAYER M1 1\n")
        result = validate_svrf_file(deck, strict=True, follow_includes=False)
        self.assertValid(result)
        self.assertIsInstance(result.program.statements[0], ast.Include)
        self.assertIsInstance(parse_file(deck).statements[0], ast.Include)

    def test_anonymous_text_can_use_explicit_run_directory(self):
        self.write("defs", "LAYER M1 1\n")
        self.assertValid(validate_svrf("INCLUDE defs\nR { COPY M1 }\n", strict=True, run_directory=self.root))

    def test_environment_path_preserves_case(self):
        self.write("defs", "LAYER M1 1\n")
        with patch.dict(os.environ, {"MixedEnv": str(self.root)}):
            self.assertValid(self.validate('INCLUDE "$MixedEnv/defs"\n'))

    def test_invalid_include_syntax_is_a_diagnostic(self):
        for include in ('INCLUDE ""', 'INCLUDE "broken', 'INCLUDE one two', 'INCLUDE "one" "two"'):
            with self.subTest(include=include):
                result = self.validate(include + "\nLAYER M1 1\n")
                self.assertIn("validation.include.invalid_syntax", {d.code for d in result.errors})

    def test_newline_variants_preserve_include_locations(self):
        self.write("defs", "LAYER M1 1\n")
        for newline in ("\n", "\r\n", "\r"):
            with self.subTest(newline=newline):
                text = newline.join(("VARIABLE WIDTH 0.1", "INCLUDE defs", "R { COPY M1 }", ""))
                self.assertValid(validate_svrf(text, run_directory=self.root, strict=True))

    def test_variable_order_is_checked_across_include_boundaries(self):
        self.write("defs", "VARIABLE WIDTH 0.1\n")
        self.assertValid(self.validate('INCLUDE defs\nLAYER M1 1\nR { INT M1 < WIDTH }\n'))
        result = self.validate('LAYER M1 1\nR { INT M1 < WIDTH }\nINCLUDE defs\n')
        self.assertIn("semantic.variable.before_definition", {d.code for d in result.errors})

    def test_empty_and_comment_only_include_files_are_allowed(self):
        self.write("empty", "")
        self.write("comment", "// no statements\n")
        self.assertValid(self.validate('INCLUDE empty\nINCLUDE comment\nLAYER M1 1\n'))

    def test_missing_include_in_rule_body_is_not_silently_ignored(self):
        result = self.validate('LAYER M1 1\nR {\nINCLUDE missing\nCOPY M1\n}\n')
        self.assertIn("validation.include.missing_file", {d.code for d in result.errors})

    def test_parent_locations_after_include_are_not_shifted(self):
        self.write("defs", "// extra lines\n\nLAYER M1 1\n")
        result = self.validate('INCLUDE defs\nVARIABLE X FUTURE * 2\nVARIABLE FUTURE 1\n')
        diagnostic = next(d for d in result.errors if d.code == "semantic.variable.before_definition")
        self.assertEqual(str(self.root / "deck.15a"), diagnostic.filename)
        self.assertEqual(2, diagnostic.line)
        self.assertEqual((), diagnostic.include_stack)

    def test_include_target_must_be_a_regular_file(self):
        (self.root / "directory").mkdir()
        result = self.validate('INCLUDE directory\nLAYER M1 1\n')
        self.assertIn("validation.include.missing_file", {d.code for d in result.errors})

    def test_point_diagnostic_at_child_boundary_is_not_the_entire_file(self):
        child = self.write("bad", "|\nLAYER M1 1\n")
        result = self.validate('LAYER M2 2\nINCLUDE bad\n')
        diagnostic = next(d for d in result.errors if d.code == "validation.lexer_error")
        self.assertEqual(str(child), diagnostic.filename)
        self.assertEqual((1, 1, 1, 1), (diagnostic.line, diagnostic.col, diagnostic.end_line, diagnostic.end_col))
        self.assertEqual((0, 0), (diagnostic.start_offset, diagnostic.end_offset))
        self.assertEqual("|", diagnostic.snippet)


if __name__ == "__main__":
    unittest.main()
