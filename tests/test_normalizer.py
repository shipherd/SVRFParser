import unittest

from svrf_parser import parse
from svrf_parser.lexer import Lexer
from svrf_parser.normalizer import (
    normalize_property_block_clause_shell,
    normalize_rule_check_clause_shell,
    normalize_statement_clause_cst,
)
from svrf_parser.parser import Parser


def _make_clause_cst(text, *, mode="top", token_value=None):
    lexer = Lexer(text, filename="<normalizer>")
    parser = Parser(lexer.tokens(), filename="<normalizer>", source_text=text)
    if token_value is None:
        return parser._segmenter.next_statement_clause_cst(0, mode)
    start = next(i for i, token in enumerate(parser.tokens) if token.value == token_value)
    return parser._segmenter.statement_clause_cst(start, mode)


class NormalizerTests(unittest.TestCase):
    def test_normalize_directive_matches_parser_ast(self):
        text = 'LVS IGNORE PORTS YES "dev"\n'
        normalized = normalize_statement_clause_cst(_make_clause_cst(text))
        parsed = parse(text).statements[0]
        self.assertTrue(normalized.structurally_equal(parsed))

    def test_normalize_directive_keeps_contract_words_that_look_like_statements(self):
        for text in (
            "DRC INCREMENTAL CONNECT WARNING DISABLE\n",
            "PEX NETLIST VIRTUAL CONNECT YES\n",
            "PEX NETLIST UNSHORT DEVICE PINS NO\n",
        ):
            with self.subTest(text=text):
                normalized = normalize_statement_clause_cst(_make_clause_cst(text))
                parsed = parse(text).statements[0]
                self.assertTrue(normalized.structurally_equal(parsed))

    def test_normalize_directive_keeps_multiline_bracket_option_block(self):
        text = (
            "LVS REDUCE PARALLEL MOS YES\n"
            "    [   TOLERANCE l 0\n"
            "        effective l,nfin\n"
            "    ]\n"
        )
        normalized = normalize_statement_clause_cst(_make_clause_cst(text))
        parsed = parse(text).statements[0]
        self.assertTrue(normalized.structurally_equal(parsed))

    def test_normalize_directive_stops_before_next_same_line_directive(self):
        text = "LAYOUT PATH top.gds DRC RESULTS DATABASE out ASCII\n"
        tree = parse(text)
        self.assertEqual(2, len(tree.statements))
        normalized = normalize_statement_clause_cst(_make_clause_cst(text))
        self.assertTrue(normalized.structurally_equal(tree.statements[0]))

    def test_normalize_group_matches_parser_ast(self):
        text = "GROUP G1 A B *\n"
        normalized = normalize_statement_clause_cst(_make_clause_cst(text))
        parsed = parse(text).statements[0]
        self.assertTrue(normalized.structurally_equal(parsed))

    def test_normalize_connect_matches_parser_ast(self):
        text = "CONNECT M1 M2 BY VIA1\n"
        normalized = normalize_statement_clause_cst(_make_clause_cst(text))
        parsed = parse(text).statements[0]
        self.assertTrue(normalized.structurally_equal(parsed))

    def test_normalize_include_matches_parser_ast(self):
        text = 'INCLUDE "rules/deck.svrf"\n'
        normalized = normalize_statement_clause_cst(_make_clause_cst(text))
        parsed = parse(text).statements[0]
        self.assertTrue(normalized.structurally_equal(parsed))

    def test_normalize_attach_matches_parser_ast(self):
        text = "ATTACH M1 VDD\n"
        normalized = normalize_statement_clause_cst(_make_clause_cst(text))
        parsed = parse(text).statements[0]
        self.assertTrue(normalized.structurally_equal(parsed))

    def test_normalize_device_matches_parser_ast(self):
        text = "DEVICE NMOS M1 G S CMACRO DEVX NETLIST ELEMENT X\n"
        normalized = normalize_statement_clause_cst(_make_clause_cst(text))
        parsed = parse(text).statements[0]
        self.assertTrue(normalized.structurally_equal(parsed))

    def test_normalize_macro_call_matches_parser_ast(self):
        text = "DMACRO M {\n  CMACRO WIDTH_CHECK M1 M2 VIA1\n}\n"
        normalized = normalize_statement_clause_cst(
            _make_clause_cst(text, mode="macro", token_value="CMACRO")
        )
        parsed = parse(text).statements[0].body[0]
        self.assertTrue(normalized.structurally_equal(parsed))

    def test_normalize_macro_call_preserves_scalar_arguments(self):
        text = "CMACRO WIDTH_CHECK poly 0.5\n"
        normalized = normalize_statement_clause_cst(_make_clause_cst(text))
        parsed = parse(text).statements[0]
        self.assertTrue(normalized.structurally_equal(parsed))

    def test_normalize_property_block_matches_parser_ast(self):
        text = "[PROPERTY L,W\n  X = 1\n]\n"
        normalized = normalize_statement_clause_cst(_make_clause_cst(text))
        parsed = parse(text).statements[0]
        self.assertTrue(normalized.structurally_equal(parsed))

    def test_normalize_rule_check_matches_parser_ast(self):
        text = "RULE1 {\n  @ cmt\n  INT M1 < 1\n}\n"
        normalized = normalize_statement_clause_cst(_make_clause_cst(text))
        parsed = parse(text).statements[0]
        self.assertTrue(normalized.structurally_equal(parsed))

    def test_rule_check_shell_normalizer_preserves_complex_subparsed_body(self):
        text = "RULE1 {\n  @ cmt\n  OUT = M1 AND M2\n}\n"
        clause_cst = _make_clause_cst(text)
        parsed = parse(text).statements[0]
        normalized = normalize_rule_check_clause_shell(
            clause_cst,
            comments=parsed.comments,
            body=parsed.body,
        )
        self.assertTrue(normalized.structurally_equal(parsed))

    def test_property_block_shell_normalizer_preserves_complex_subparsed_body(self):
        text = "[PROPERTY L,W\n  X = (COUNT(A)>0) ? 1 : 0\n]\n"
        clause_cst = _make_clause_cst(text)
        parsed = parse(text).statements[0]
        normalized = normalize_property_block_clause_shell(
            clause_cst,
            body=parsed.body,
        )
        self.assertTrue(normalized.structurally_equal(parsed))

    def test_normalize_connect_equivalent_whitespace_forms_match(self):
        first = normalize_statement_clause_cst(_make_clause_cst("CONNECT M1 M2 BY VIA1\n"))
        second = normalize_statement_clause_cst(
            _make_clause_cst("CONNECT   M1  M2\n  BY   VIA1\n")
        )
        self.assertTrue(first.structurally_equal(second))

    def test_normalize_connect_link_form_matches_parser_ast(self):
        text = "CONNECT M1 M2 LINK VIA1\n"
        normalized = normalize_statement_clause_cst(_make_clause_cst(text))
        parsed = parse(text).statements[0]
        self.assertTrue(normalized.structurally_equal(parsed))

    def test_normalize_property_block_equivalent_whitespace_forms_match(self):
        first = normalize_statement_clause_cst(_make_clause_cst("[PROPERTY L,W\n  X = 1\n]\n"))
        second = normalize_statement_clause_cst(
            _make_clause_cst("[PROPERTY L , W\nX = 1\n]\n")
        )
        self.assertTrue(first.structurally_equal(second))


if __name__ == "__main__":
    unittest.main()
