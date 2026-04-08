import unittest

from svrf_parser.lexer import Lexer
from svrf_parser.parser import Parser
from svrf_parser.tokens import TokenType

TT = TokenType


def _make_segmenter(text):
    lexer = Lexer(text, filename="<segmenter>")
    parser = Parser(lexer.tokens(), filename="<segmenter>", source_text=text)
    return parser._segmenter, parser.tokens


def _nth_token_index(tokens, value, occurrence=1):
    seen = 0
    for idx, token in enumerate(tokens):
        if token.value == value:
            seen += 1
            if seen == occurrence:
                return idx
    raise AssertionError(f"Token {value!r} occurrence {occurrence} not found")


def _nth_token_type_index(tokens, token_type, occurrence=1):
    seen = 0
    for idx, token in enumerate(tokens):
        if token.type == token_type:
            seen += 1
            if seen == occurrence:
                return idx
    raise AssertionError(f"Token type {token_type!r} occurrence {occurrence} not found")


class SegmenterTests(unittest.TestCase):
    def test_statement_slices_exclude_eof_without_trailing_newline(self):
        cases = (
            ("CONNECT M1 M2", "top"),
            ("CMACRO MACRO1 M1", "top"),
            ('LAYOUT PATH "a.gds"', "top"),
            ("TMP = SIZE M1 BY 0.1", "top"),
            ("RULE1 { INT M1 < 1 }", "top"),
            ("[PROPERTY P1\n  X = 1\n]", "top"),
        )
        for text, mode in cases:
            with self.subTest(text=text):
                segmenter, tokens = _make_segmenter(text)
                eof_idx = _nth_token_type_index(tokens, TT.EOF)
                statement_slice = segmenter.next_statement_slice(0, mode)
                statement_cst = segmenter.next_statement_cst(0, mode)

                self.assertIsNotNone(statement_slice)
                self.assertIsNotNone(statement_cst)
                self.assertEqual(statement_slice.end, eof_idx)
                self.assertEqual(statement_cst.end, eof_idx)
                slice_token_types = {
                    token.type
                    for token in tokens[statement_slice.start:statement_slice.end]
                }
                self.assertNotIn(TT.EOF, slice_token_types)

    def test_next_statement_slice_skips_leading_newlines(self):
        segmenter, tokens = _make_segmenter("\n\nGROUP G1 A\n")
        statement_slice = segmenter.next_statement_slice(0, "top")
        self.assertIsNotNone(statement_slice)
        self.assertEqual(statement_slice.start, _nth_token_index(tokens, "GROUP"))

    def test_next_statement_slice_respects_stop_symbol(self):
        segmenter, tokens = _make_segmenter("]\nGROUP G1 A\n")
        self.assertIsNone(segmenter.next_statement_slice(0, "property", stop_symbols={"]"}))
        statement_slice = segmenter.next_statement_slice(1, "top")
        self.assertIsNotNone(statement_slice)
        self.assertEqual(statement_slice.start, _nth_token_index(tokens, "GROUP"))

    def test_statement_slice_keeps_multiline_assignment_continuation(self):
        text = "X =\n  M1 OR M2\nGROUP G1 A\n"
        segmenter, tokens = _make_segmenter(text)
        group_idx = _nth_token_index(tokens, "GROUP")
        statement_slice = segmenter.next_statement_slice(0, "top")
        self.assertIsNotNone(statement_slice)
        self.assertEqual(statement_slice.start, _nth_token_index(tokens, "X"))
        self.assertEqual(statement_slice.end, group_idx)

    def test_next_statement_unit_classifies_multiline_assignment(self):
        text = "X =\n  M1 OR M2\nGROUP G1 A\n"
        segmenter, tokens = _make_segmenter(text)
        group_idx = _nth_token_index(tokens, "GROUP")
        statement_unit = segmenter.next_statement_unit(0, "top")
        self.assertIsNotNone(statement_unit)
        self.assertEqual(statement_unit.parse_kind, "assignment")
        self.assertEqual(statement_unit.start, _nth_token_index(tokens, "X"))
        self.assertEqual(statement_unit.end, group_idx)
        self.assertEqual(statement_unit.head_kind, "assignment")
        self.assertEqual(statement_unit.head_value, "X")
        self.assertIsNone(statement_unit.leading_delimiter)
        self.assertEqual(statement_unit.boundary_kind, "next_statement")
        self.assertEqual(statement_unit.boundary_value, "GROUP")
        self.assertTrue(statement_unit.continued_across_newline)

    def test_rhs_continuation_allows_multiline_assignment_expression(self):
        text = "X =\n  M1 OR M2\nGROUP G1 A\n"
        segmenter, tokens = _make_segmenter(text)
        newline_idx = _nth_token_type_index(tokens, TT.NEWLINE, 1)
        self.assertTrue(segmenter.continues_rhs_across_newline(newline_idx))

    def test_rhs_continuation_stops_before_following_top_level_statement(self):
        text = "X =\nGROUP G1 A\n"
        segmenter, tokens = _make_segmenter(text)
        newline_idx = _nth_token_type_index(tokens, TT.NEWLINE, 1)
        self.assertFalse(segmenter.continues_rhs_across_newline(newline_idx))

    def test_directive_continuation_allows_bracket_block(self):
        text = 'LVS REDUCE PARALLEL MOS YES\n  [ TOLERANCE l 0 ]\n'
        segmenter, tokens = _make_segmenter(text)
        newline_idx = _nth_token_type_index(tokens, TT.NEWLINE, 1)
        self.assertTrue(segmenter.continues_directive_across_newline(newline_idx))

    def test_property_header_newline_action_stops_at_body_assignment(self):
        text = "[PROPERTY L,W\n  NFIN = COUNT(L1)\n]\n"
        segmenter, tokens = _make_segmenter(text)
        newline_idx = _nth_token_type_index(tokens, TT.NEWLINE, 1)
        action, next_idx = segmenter.property_header_newline_action(newline_idx)
        self.assertEqual(action, "body")
        self.assertEqual(next_idx, _nth_token_index(tokens, "NFIN"))

    def test_property_header_newline_action_stops_at_preprocessor(self):
        text = "[PROPERTY L,W\n  #ENDIF\n]\n"
        segmenter, tokens = _make_segmenter(text)
        newline_idx = _nth_token_type_index(tokens, TT.NEWLINE, 1)
        action, next_idx = segmenter.property_header_newline_action(
            newline_idx,
            stop_preprocessors={"#ENDIF"},
        )
        self.assertEqual(action, "stop_preprocessor")
        self.assertEqual(next_idx, _nth_token_index(tokens, "#ENDIF"))

    def test_statement_slice_keeps_rule_modifier_continuation(self):
        text = "CHK {\n  INT M1 < 1\n  GOOD OPPOSITE\n}\n"
        segmenter, tokens = _make_segmenter(text)
        start = _nth_token_index(tokens, "INT")
        close_brace = _nth_token_index(tokens, "}")
        statement_slice = segmenter.statement_slice(start, "rule")
        self.assertEqual(statement_slice.start, start)
        self.assertEqual(statement_slice.end, close_brace)

    def test_statement_unit_tracks_rule_delimiter_context(self):
        text = "CHK {\n  INT M1 < 1\n  GOOD OPPOSITE\n}\n"
        segmenter, tokens = _make_segmenter(text)
        start = _nth_token_index(tokens, "INT")
        statement_unit = segmenter.statement_unit(start, "rule")
        self.assertEqual(statement_unit.parse_kind, "statement_head")
        self.assertEqual(statement_unit.head_kind, "statement_head")
        self.assertEqual(statement_unit.head_value, "INT")
        self.assertEqual(statement_unit.leading_delimiter, "{")
        self.assertEqual(statement_unit.boundary_kind, "closing_delimiter")
        self.assertEqual(statement_unit.boundary_value, "}")
        self.assertTrue(statement_unit.continued_across_newline)

    def test_expression_continuation_keeps_rule_modifier_line(self):
        text = "CHK {\n  INT M1 < 1\n  GOOD OPPOSITE\n}\n"
        segmenter, tokens = _make_segmenter(text)
        newline_idx = _nth_token_type_index(tokens, TT.NEWLINE, 2)
        self.assertTrue(segmenter.continues_across_newline(newline_idx))

    def test_operation_continuation_allows_modifier_line(self):
        text = "CHK {\n  INT M1 < 1\n  GOOD OPPOSITE\n}\n"
        segmenter, tokens = _make_segmenter(text)
        newline_idx = _nth_token_type_index(tokens, TT.NEWLINE, 2)
        self.assertTrue(segmenter.continues_operation_across_newline(newline_idx))

    def test_indented_expression_continuation_allows_parenthesized_no_indent(self):
        text = "(OR \nVIA_A\n)\n"
        segmenter, tokens = _make_segmenter(text)
        newline_idx = _nth_token_type_index(tokens, TT.NEWLINE, 1)
        or_idx = _nth_token_index(tokens, "OR")
        anchor_col = tokens[or_idx].col
        self.assertFalse(
            segmenter.continues_indented_expression_across_newline(
                newline_idx,
                anchor_col,
                allow_parenthesized=False,
            )
        )
        self.assertTrue(
            segmenter.continues_indented_expression_across_newline(
                newline_idx,
                anchor_col,
                allow_parenthesized=True,
            )
        )

    def test_nonstatement_expression_continuation_stops_before_expression_statement(self):
        text = "X = DFM PROPERTY M1_LC\nALL_CPO_S1\n"
        segmenter, tokens = _make_segmenter(text)
        newline_idx = _nth_token_type_index(tokens, TT.NEWLINE, 1)
        self.assertFalse(segmenter.continues_nonstatement_expression_across_newline(newline_idx, "top"))

    def test_nonstatement_expression_continuation_allows_dfm_property_operand_line(self):
        text = "X = DFM PROPERTY M1_LC\nA B C\n"
        segmenter, tokens = _make_segmenter(text)
        newline_idx = _nth_token_type_index(tokens, TT.NEWLINE, 1)
        self.assertTrue(segmenter.continues_nonstatement_expression_across_newline(newline_idx, "top"))

    def test_next_statement_unit_classifies_property_block(self):
        text = "[PROPERTY P1\n  X = 1\n]\nGROUP G1 A\n"
        segmenter, tokens = _make_segmenter(text)
        statement_unit = segmenter.next_statement_unit(0, "top")
        self.assertIsNotNone(statement_unit)
        self.assertEqual(statement_unit.parse_kind, "property_block")
        self.assertEqual(statement_unit.head_kind, "property_block")
        self.assertEqual(statement_unit.head_value, "PROPERTY")
        self.assertIsNone(statement_unit.leading_delimiter)
        self.assertEqual(statement_unit.boundary_kind, "next_statement")
        self.assertEqual(statement_unit.boundary_value, "GROUP")
        self.assertEqual(statement_unit.end, _nth_token_index(tokens, "GROUP"))

    def test_statement_unit_classifies_macro_if_as_statement_head(self):
        text = "DMACRO M {\n  IF A > 0\n}\n"
        segmenter, tokens = _make_segmenter(text)
        start = _nth_token_index(tokens, "IF")
        statement_unit = segmenter.statement_unit(start, "macro")
        self.assertEqual(statement_unit.parse_kind, "statement_head")
        self.assertEqual(statement_unit.head_kind, "statement_head")
        self.assertEqual(statement_unit.head_value, "IF")
        self.assertEqual(statement_unit.leading_delimiter, "{")

    def test_statement_unit_classifies_top_level_bare_name_as_expression_statement(self):
        text = "ALL_CPO_S1\n"
        segmenter, tokens = _make_segmenter(text)
        start = _nth_token_index(tokens, "ALL_CPO_S1")
        statement_unit = segmenter.next_statement_unit(0, "top")
        self.assertIsNotNone(statement_unit)
        self.assertEqual(statement_unit.start, start)
        self.assertEqual(statement_unit.parse_kind, "expression_statement")
        self.assertEqual(statement_unit.head_kind, "expression")
        self.assertTrue(segmenter.starts_statement_at(start, "top"))
        self.assertTrue(segmenter.looks_like_expression_statement_at(start, "top"))

    def test_statement_unit_classifies_unknown_top_level_content(self):
        text = "DEVI C(CPM) PMCAP METAL1 PMCAP [6.760E-2 0]\n"
        segmenter, _tokens = _make_segmenter(text)
        statement_unit = segmenter.next_statement_unit(0, "top")
        self.assertIsNotNone(statement_unit)
        self.assertEqual(statement_unit.parse_kind, "unknown")
        self.assertEqual(statement_unit.head_kind, "expression")

    def test_statement_unit_classifies_parenthesized_top_level_expression(self):
        text = "(COUNT(A) > 0) ? 1 : 0\n"
        segmenter, tokens = _make_segmenter(text)
        start = _nth_token_index(tokens, "(")
        statement_unit = segmenter.next_statement_unit(0, "top")
        self.assertIsNotNone(statement_unit)
        self.assertEqual(statement_unit.start, start)
        self.assertEqual(statement_unit.parse_kind, "expression_statement")
        self.assertEqual(statement_unit.head_kind, "expression")
        self.assertTrue(segmenter.starts_statement_at(start, "top"))
        self.assertTrue(segmenter.looks_like_expression_statement_at(start, "top"))

    def test_statement_unit_classifies_tvf_as_top_level_statement_head(self):
        text = "TVF FUNCTION Perc_ADP_properties [/* body */]\n"
        segmenter, tokens = _make_segmenter(text)
        statement_unit = segmenter.next_statement_unit(0, "top")
        self.assertIsNotNone(statement_unit)
        self.assertEqual(statement_unit.start, _nth_token_index(tokens, "TVF"))
        self.assertEqual(statement_unit.parse_kind, "statement_head")
        self.assertEqual(statement_unit.head_kind, "statement_head")
        self.assertEqual(statement_unit.head_value, "TVF")
        self.assertEqual(statement_unit.head_words, ("TVF", "FUNCTION"))

    def test_statement_unit_tracks_directive_keyword_run(self):
        text = 'LVS IGNORE PORTS YES\n'
        segmenter, tokens = _make_segmenter(text)
        statement_unit = segmenter.next_statement_unit(0, "top")
        self.assertIsNotNone(statement_unit)
        self.assertEqual(statement_unit.parse_kind, "directive")
        self.assertEqual(statement_unit.head_words, ("LVS", "IGNORE", "PORTS", "YES"))
        self.assertEqual(statement_unit.head_end, _nth_token_index(tokens, "YES") + 1)

    def test_next_statement_cst_tracks_directive_head_and_body_start(self):
        text = 'LVS IGNORE PORTS YES "dev"\n'
        segmenter, tokens = _make_segmenter(text)
        statement_cst = segmenter.next_statement_cst(0, "top")
        self.assertIsNotNone(statement_cst)
        self.assertEqual(statement_cst.parse_kind, "directive")
        self.assertIsNotNone(statement_cst.head)
        self.assertEqual(statement_cst.head.words, ("LVS", "IGNORE", "PORTS", "YES"))
        self.assertEqual(statement_cst.body_start, _nth_token_index(tokens, "YES") + 1)
        self.assertEqual(tokens[statement_cst.body_start].type, TT.STRING)

    def test_statement_cst_leaves_expression_body_start_at_statement_start(self):
        text = "ALL_CPO_S1\n"
        segmenter, tokens = _make_segmenter(text)
        statement_cst = segmenter.next_statement_cst(0, "top")
        self.assertIsNotNone(statement_cst)
        self.assertEqual(statement_cst.parse_kind, "expression_statement")
        self.assertIsNone(statement_cst.head)
        self.assertEqual(statement_cst.body_start, _nth_token_index(tokens, "ALL_CPO_S1"))

    def test_statement_cst_tracks_trace_property_keyword_prefix(self):
        text = "TRACE PROPERTY DEV X\n"
        segmenter, _tokens = _make_segmenter(text)
        statement_cst = segmenter.next_statement_cst(0, "top")
        self.assertIsNotNone(statement_cst)
        self.assertIsNotNone(statement_cst.head)
        self.assertEqual(statement_cst.head.words[:2], ("TRACE", "PROPERTY"))
        self.assertTrue(statement_cst.head.matches_prefix("TRACE", "PROPERTY"))

    def test_statement_cst_tracks_property_block_header_start(self):
        text = "[PROPERTY L,W\n  X = 1\n]\n"
        segmenter, tokens = _make_segmenter(text)
        statement_cst = segmenter.next_statement_cst(0, "top")
        self.assertIsNotNone(statement_cst)
        self.assertEqual(statement_cst.parse_kind, "property_block")
        self.assertIsNotNone(statement_cst.head)
        self.assertEqual(statement_cst.head.words, ("[", "PROPERTY"))
        self.assertEqual(statement_cst.body_start, _nth_token_index(tokens, "PROPERTY") + 1)

    def test_statement_cst_tracks_rule_check_header_metadata(self):
        text = "RULE1:CHK {\n  @ cmt\n  INT M1 < 1\n}\n"
        segmenter, tokens = _make_segmenter(text)
        statement_cst = segmenter.next_statement_cst(0, "top")
        self.assertIsNotNone(statement_cst)
        self.assertEqual(statement_cst.parse_kind, "rule_check")
        self.assertIsNotNone(statement_cst.rule_check_header)
        self.assertEqual(statement_cst.rule_check_header.name, "RULE1:CHK")
        self.assertEqual(statement_cst.rule_check_header.body_start, _nth_token_type_index(tokens, TT.RULE_COMMENT))

    def test_rule_check_header_preserves_compact_voltage_label(self):
        text = "CHECK.2.1:0.2V__1.250V {\n  @ cmt\n  INT M1 < 1\n}\n"
        segmenter, tokens = _make_segmenter(text)
        statement_cst = segmenter.next_statement_cst(0, "top")
        self.assertIsNotNone(statement_cst)
        self.assertEqual(statement_cst.parse_kind, "rule_check")
        self.assertIsNotNone(statement_cst.rule_check_header)
        self.assertEqual(statement_cst.rule_check_header.name, "CHECK.2.1:0.2V__1.250V")
        self.assertEqual(statement_cst.rule_check_header.body_start, _nth_token_type_index(tokens, TT.RULE_COMMENT))

    def test_statement_cst_tracks_property_block_header_metadata(self):
        text = "[PROPERTY L,W\n  X = 1\n]\n"
        segmenter, tokens = _make_segmenter(text)
        statement_cst = segmenter.next_statement_cst(0, "top")
        self.assertIsNotNone(statement_cst)
        self.assertIsNotNone(statement_cst.property_block_header)
        self.assertEqual(statement_cst.property_block_header.properties, ("L", "W"))
        self.assertEqual(statement_cst.property_block_header.body_start, _nth_token_index(tokens, "X"))

    def test_property_block_header_scan_stops_at_stop_preprocessor(self):
        text = "[PROPERTY L,W\n  #ENDIF\n]\n"
        segmenter, tokens = _make_segmenter(text)
        header = segmenter.scan_property_block_header(0, stop_preprocessors={"#ENDIF"})
        self.assertIsNotNone(header)
        self.assertEqual(header.properties, ("L", "W"))
        self.assertEqual(header.body_start, _nth_token_index(tokens, "#ENDIF"))

    def test_statement_slice_stops_before_same_line_top_statement(self):
        segmenter, tokens = _make_segmenter("GROUP G1 M1 GROUP G2 M2\n")
        start = _nth_token_index(tokens, "GROUP", 1)
        second = _nth_token_index(tokens, "GROUP", 2)
        statement_slice = segmenter.statement_slice(start, "top")
        self.assertEqual(statement_slice.start, start)
        self.assertEqual(statement_slice.end, second)

    def test_same_line_top_directive_boundary(self):
        segmenter, tokens = _make_segmenter('LAYOUT PATH "a.gds" LAYOUT PRIMARY "top"\n')
        idx = _nth_token_index(tokens, "LAYOUT", 2)
        self.assertTrue(segmenter.looks_like_same_line_top_directive_at(idx))
        self.assertTrue(segmenter.starts_same_line_statement_at(idx, "top"))
        self.assertTrue(segmenter.at_directive_boundary(idx))

    def test_same_line_top_device_boundary_requires_same_line_mode(self):
        segmenter, tokens = _make_segmenter("DEVICE NMOS M1 G S DEVICE PMOS M2 D S\n")
        idx = _nth_token_index(tokens, "DEVICE", 2)
        self.assertTrue(segmenter.starts_same_line_statement_at(idx, "top"))
        self.assertFalse(segmenter.at_statement_boundary(idx, "top", allow_same_line_statement=False))
        self.assertTrue(segmenter.at_statement_boundary(idx, "top", allow_same_line_statement=True))

    def test_same_line_rule_body_boundary(self):
        segmenter, tokens = _make_segmenter("CHK { INT M1 < 1 EXT M2 < 2 }\n")
        idx = _nth_token_index(tokens, "EXT")
        self.assertTrue(segmenter.starts_same_line_statement_at(idx, "rule"))
        self.assertTrue(segmenter.at_statement_boundary(idx, "rule", allow_same_line_statement=True))

    def test_trace_requires_property_for_same_line_top_boundary(self):
        segmenter, tokens = _make_segmenter("TRACE PROPERTY DEV A TRACE DEV B\n")
        idx = _nth_token_index(tokens, "TRACE", 2)
        self.assertFalse(segmenter.starts_same_line_statement_at(idx, "top"))


if __name__ == "__main__":
    unittest.main()
