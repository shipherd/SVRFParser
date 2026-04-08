import unittest

from svrf_parser.clause_cst import (
    DelimitedGroupClause,
    KeywordRunClause,
    ModifierClause,
    OpaqueEmbeddedLanguageChunk,
    OperandClause,
    ScalarClause,
)
from svrf_parser.lexer import Lexer
from svrf_parser.parser import Parser


def _make_segmenter(text):
    lexer = Lexer(text, filename="<clause-cst>")
    parser = Parser(lexer.tokens(), filename="<clause-cst>", source_text=text)
    return parser._segmenter, parser.tokens


def _nth_token_index(tokens, value, occurrence=1):
    seen = 0
    for idx, token in enumerate(tokens):
        if token.value == value:
            seen += 1
            if seen == occurrence:
                return idx
    raise AssertionError(f"Token {value!r} occurrence {occurrence} not found")


class ClauseCstTests(unittest.TestCase):
    def test_directive_clause_cst_tracks_head_and_scalar_body(self):
        segmenter, _tokens = _make_segmenter('LVS IGNORE PORTS YES "dev"\n')
        clause_cst = segmenter.next_statement_clause_cst(0, "top")
        self.assertIsNotNone(clause_cst)
        self.assertEqual("directive", clause_cst.parse_kind)
        self.assertEqual(1, len(clause_cst.header_clauses))
        self.assertIsInstance(clause_cst.header_clauses[0], KeywordRunClause)
        self.assertEqual(
            ("LVS", "IGNORE", "PORTS", "YES"),
            clause_cst.header_clauses[0].words,
        )
        self.assertEqual(1, len(clause_cst.body_clauses))
        self.assertIsInstance(clause_cst.body_clauses[0], ScalarClause)
        self.assertEqual(("dev",), clause_cst.body_clauses[0].values)

    def test_directive_clause_cst_keeps_contract_words_that_look_like_statements(self):
        segmenter, _tokens = _make_segmenter("PEX NETLIST UNSHORT DEVICE PINS NO\n")
        clause_cst = segmenter.next_statement_clause_cst(0, "top")
        self.assertIsNotNone(clause_cst)
        self.assertEqual(("PEX", "NETLIST"), clause_cst.header_clauses[0].words)
        self.assertEqual(1, len(clause_cst.body_clauses))
        self.assertEqual(("UNSHORT", "DEVICE", "PINS", "NO"), clause_cst.body_clauses[0].values)

    def test_directive_clause_cst_stops_before_next_same_line_directive(self):
        segmenter, tokens = _make_segmenter("LAYOUT PATH top.gds DRC RESULTS DATABASE out ASCII\n")
        first = segmenter.next_statement_clause_cst(0, "top")
        self.assertIsNotNone(first)
        self.assertEqual(("LAYOUT", "PATH"), first.header_clauses[0].words)
        self.assertEqual(("TOP.GDS",), first.body_clauses[0].values)
        second_start = _nth_token_index(tokens, "DRC")
        second = segmenter.statement_clause_cst(second_start, "top")
        self.assertIsNotNone(second)
        self.assertEqual(("DRC", "RESULTS", "DATABASE"), second.header_clauses[0].words)

    def test_directive_clause_cst_keeps_multiline_bracket_option_block(self):
        text = (
            "LVS REDUCE PARALLEL MOS YES\n"
            "  [ TOLERANCE l 0\n"
            "    effective l,nfin\n"
            "  ]\n"
        )
        segmenter, _tokens = _make_segmenter(text)
        clause_cst = segmenter.next_statement_clause_cst(0, "top")
        self.assertIsNotNone(clause_cst)
        self.assertEqual(1, len(clause_cst.body_clauses))
        self.assertIsInstance(clause_cst.body_clauses[0], DelimitedGroupClause)
        self.assertEqual("[", clause_cst.body_clauses[0].open_symbol)
        self.assertEqual("]", clause_cst.body_clauses[0].close_symbol)

    def test_group_clause_cst_keeps_body_as_operand_run(self):
        segmenter, _tokens = _make_segmenter("GROUP G1 A B *\n")
        clause_cst = segmenter.next_statement_clause_cst(0, "top")
        self.assertIsNotNone(clause_cst)
        self.assertEqual("group", clause_cst.parse_kind)
        self.assertEqual(("GROUP",), clause_cst.header_clauses[0].words)
        self.assertEqual(1, len(clause_cst.body_clauses))
        self.assertIsInstance(clause_cst.body_clauses[0], OperandClause)
        self.assertEqual(("G1", "A", "B", "*"), clause_cst.body_clauses[0].values)

    def test_include_clause_cst_tracks_path_scalar(self):
        segmenter, _tokens = _make_segmenter('INCLUDE "rules/deck.svrf"\n')
        clause_cst = segmenter.next_statement_clause_cst(0, "top")
        self.assertIsNotNone(clause_cst)
        self.assertEqual("include", clause_cst.parse_kind)
        self.assertEqual(("INCLUDE",), clause_cst.header_clauses[0].words)
        self.assertEqual(1, len(clause_cst.body_clauses))
        self.assertIsInstance(clause_cst.body_clauses[0], ScalarClause)
        self.assertEqual(("rules/deck.svrf",), clause_cst.body_clauses[0].values)

    def test_attach_clause_cst_tracks_operand_run(self):
        segmenter, _tokens = _make_segmenter("ATTACH M1 VDD\n")
        clause_cst = segmenter.next_statement_clause_cst(0, "top")
        self.assertIsNotNone(clause_cst)
        self.assertEqual("attach", clause_cst.parse_kind)
        self.assertEqual(("ATTACH",), clause_cst.header_clauses[0].words)
        self.assertEqual(1, len(clause_cst.body_clauses))
        self.assertIsInstance(clause_cst.body_clauses[0], OperandClause)
        self.assertEqual(("M1", "VDD"), clause_cst.body_clauses[0].values)

    def test_connect_clause_cst_splits_by_modifier(self):
        segmenter, _tokens = _make_segmenter("CONNECT M1 M2 BY VIA1\n")
        clause_cst = segmenter.next_statement_clause_cst(0, "top")
        self.assertIsNotNone(clause_cst)
        self.assertEqual("connect", clause_cst.parse_kind)
        self.assertEqual(("CONNECT",), clause_cst.header_clauses[0].words)
        self.assertEqual(2, len(clause_cst.body_clauses))
        self.assertIsInstance(clause_cst.body_clauses[0], OperandClause)
        self.assertEqual(("M1", "M2"), clause_cst.body_clauses[0].values)
        self.assertIsInstance(clause_cst.body_clauses[1], ModifierClause)
        self.assertEqual(("BY", "VIA1"), clause_cst.body_clauses[1].values)

    def test_device_clause_cst_splits_modifier_runs(self):
        segmenter, _tokens = _make_segmenter(
            "DEVICE NMOS M1 G S CMACRO DEVX NETLIST ELEMENT X\n"
        )
        clause_cst = segmenter.next_statement_clause_cst(0, "top")
        self.assertIsNotNone(clause_cst)
        self.assertEqual("device", clause_cst.parse_kind)
        self.assertEqual(("DEVICE",), clause_cst.header_clauses[0].words)
        self.assertEqual(4, len(clause_cst.body_clauses))
        self.assertEqual(("NMOS", "M1", "G", "S"), clause_cst.body_clauses[0].values)
        self.assertEqual(("CMACRO", "DEVX"), clause_cst.body_clauses[1].values)
        self.assertEqual(("NETLIST",), clause_cst.body_clauses[2].values)
        self.assertEqual(("ELEMENT", "X"), clause_cst.body_clauses[3].values)

    def test_macro_call_clause_cst_keeps_operands(self):
        text = "DMACRO M {\n  CMACRO WIDTH_CHECK M1 M2 VIA1\n}\n"
        segmenter, tokens = _make_segmenter(text)
        start = _nth_token_index(tokens, "CMACRO")
        clause_cst = segmenter.statement_clause_cst(start, "macro")
        self.assertIsNotNone(clause_cst)
        self.assertEqual("macro_call", clause_cst.parse_kind)
        self.assertEqual(("CMACRO",), clause_cst.header_clauses[0].words)
        self.assertEqual(1, len(clause_cst.body_clauses))
        self.assertIsInstance(clause_cst.body_clauses[0], OperandClause)
        self.assertEqual(
            ("WIDTH_CHECK", "M1", "M2", "VIA1"),
            clause_cst.body_clauses[0].values,
        )

    def test_rule_check_clause_cst_wraps_body_group(self):
        text = "RULE1 {\n  @ cmt\n  INT M1 < 1\n}\n"
        segmenter, _tokens = _make_segmenter(text)
        clause_cst = segmenter.next_statement_clause_cst(0, "top")
        self.assertIsNotNone(clause_cst)
        self.assertEqual("rule_check", clause_cst.parse_kind)
        self.assertEqual(1, len(clause_cst.body_clauses))
        body = clause_cst.body_clauses[0]
        self.assertIsInstance(body, DelimitedGroupClause)
        self.assertEqual("{", body.open_symbol)
        self.assertEqual("}", body.close_symbol)
        self.assertIsInstance(body.clauses[0], OpaqueEmbeddedLanguageChunk)
        self.assertEqual("comment", body.clauses[0].reason)

    def test_property_block_clause_cst_tracks_header_and_body_group(self):
        text = "[PROPERTY L,W\n  X = 1\n]\n"
        segmenter, _tokens = _make_segmenter(text)
        clause_cst = segmenter.next_statement_clause_cst(0, "top")
        self.assertIsNotNone(clause_cst)
        self.assertEqual("property_block", clause_cst.parse_kind)
        self.assertEqual(("[" , "PROPERTY"), clause_cst.header_clauses[0].words)
        self.assertEqual(("L",), clause_cst.header_clauses[1].values)
        self.assertEqual(("W",), clause_cst.header_clauses[2].values)
        self.assertEqual(1, len(clause_cst.body_clauses))
        body = clause_cst.body_clauses[0]
        self.assertIsInstance(body, DelimitedGroupClause)
        self.assertEqual("[", body.open_symbol)
        self.assertEqual("]", body.close_symbol)
        self.assertEqual(2, len(body.clauses))
        self.assertIsInstance(body.clauses[0], OperandClause)
        self.assertEqual(("X", "="), body.clauses[0].values)
        self.assertIsInstance(body.clauses[1], ScalarClause)
        self.assertEqual((1,), body.clauses[1].values)


if __name__ == "__main__":
    unittest.main()
