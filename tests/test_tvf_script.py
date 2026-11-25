import tempfile
import unittest
from pathlib import Path

from svrf_parser import ast, parse, parse_with_diagnostics, validate_svrf, validate_svrf_file
from svrf_parser.exceptions import LexerError, ParseError
from svrf_parser.printer import SvrfPrinter


class TvfScriptTests(unittest.TestCase):
    def test_multiple_literal_commands_original_coordinates_and_scope(self):
        text = ('#!tvf\r\n# comment\r\n::tvf::VERBATIM {LAYER A 1}; '
                'tvf::VERBATIM {\r\nR { COPY A }\r\n}\r\n')
        tree = parse(text, strict=True)
        wrapper, = tree.statements
        self.assertIsInstance(wrapper, ast.TvfScript)
        self.assertEqual(wrapper.parse_status, "literal")
        layer, rule = wrapper.body
        self.assertEqual((layer.line, layer.col, rule.line, rule.col), (3, 18, 4, 1))
        self.assertEqual((text[layer.start_offset:layer.end_offset], rule.source_text), ("LAYER A 1", "R { COPY A }"))
        self.assertEqual(SvrfPrinter().emit(tree), text)
        self.assertTrue(validate_svrf(text).valid)

    def test_opaque_remainder_not_reported_as_valid_or_executed(self):
        text = "#!tvf\ntvf::VERBATIM {LAYER A 1}\nset cmd 0\ntvf::VERBATIM {R {COPY A}}"
        tree, ds = parse_with_diagnostics(text)
        wrapper, = tree.statements
        self.assertEqual([x.name for x in wrapper.body], ["A"])
        self.assertEqual((wrapper.parse_status, wrapper.content), ("partial", text))
        self.assertEqual([(d.code, d.start_offset, d.end_offset) for d in ds],
                         [("parser.tvf.opaque_tcl", text.index("set"), text.index("set") + 1)])
        with self.assertRaises(ParseError):
            parse(text, strict=True)
        result = validate_svrf(text)
        self.assertFalse(result.valid)
        self.assertIn("semantic.tvf.incomplete", [d.code for d in result.diagnostics])

    def test_tcl_boundaries_not_substrings(self):
        for body in ('if {1} {tvf::VERBATIM {LAYER A 1}}', 'tvf::VERBATIM "LAYER A 1"',
                     "tvf::VERBATIM {LAYER A 1} extra", "tvf::verbatim {LAYER A 1}",
                     "tvf::VERBATIM {LAYER A\\\n 1}", "# continued\\\ntvf::VERBATIM {LAYER A 1}"):
            with self.subTest(body=body):
                wrapper, = parse("#!tvf\n" + body).statements
                self.assertEqual((wrapper.parse_status, wrapper.body), ("opaque", []))

    def test_balancing_includes_svrf_comments_but_not_escaped_braces(self):
        text = "#!tvf\ntvf::VERBATIM {\n// a pair { } and an escaped \\}\nLAYER A 1\n}"
        self.assertEqual(parse(text, strict=True).statements[0].body[0].name, "A")
        tree, ds = parse_with_diagnostics("#!tvf\ntvf::VERBATIM {\n// {\nLAYER A 1\n}")
        self.assertEqual((tree.statements[0].body, ds[0].code), ([], "parser.tvf.unterminated_verbatim"))

    def test_invalid_svrf_reports_original_location(self):
        with self.assertRaises(LexerError) as caught:
            parse("#!tvf\r\ntvf::VERBATIM {\r\n | }")
        self.assertEqual((caught.exception.line, caught.exception.col), (3, 2))

    def test_only_literal_prefix_can_supply_includes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "leaf").write_text("LAYER A 1\n")
            deck = root / "deck"
            deck.write_text("#!tvf\n#INCLUDE missing_before\ntvf::VERBATIM {\nINCLUDE leaf\n}\n"
                            "set cmd {\nINCLUDE missing_after\n}\n")
            result = validate_svrf_file(deck, run_directory=root)
            self.assertEqual(sorted(d.code for d in result.diagnostics),
                             ["parser.tvf.opaque_tcl", "semantic.tvf.incomplete"])
            layer, = result.program.statements[0].body
            self.assertEqual((layer.name, layer.line), ("A", 1))
