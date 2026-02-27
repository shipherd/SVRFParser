"""Tier 1 unit tests: Multi-line descriptions and ^VARNAME references."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_one, assert_node_type
from svrf_parser.ast_nodes import *


class TestVarRefNode:
    """VarRef AST node basics."""

    def test_varref_exists(self):
        """VarRef node class should exist with a 'name' field."""
        node = VarRef(name='FOO', line=1, col=1)
        assert node.name == 'FOO'

    def test_varref_accept(self):
        """VarRef should support the visitor pattern."""
        node = VarRef(name='BAR', line=1, col=1)
        assert hasattr(node, 'accept')


class TestSingleLineDescription:
    """Rule check blocks with a single @ description line."""

    def test_plain_text(self):
        text = "check1 {\n  @ Simple description\n  INT M1 < 0.1\n}"
        node = parse_one(text)
        assert_node_type(node, RuleCheckBlock, name="check1")
        # description is now a list of lines
        assert isinstance(node.description, list)
        assert len(node.description) == 1
        line = node.description[0]
        # line is a list of segments (all strings here, no VarRef)
        assert isinstance(line, list)
        assert all(isinstance(seg, str) for seg in line)
        joined = ''.join(line)
        assert 'Simple description' in joined

    def test_with_varref(self):
        text = "check1 {\n  @ Space >= ^MIN_SPACE um\n  INT M1 < 0.1\n}"
        node = parse_one(text)
        desc = node.description
        assert len(desc) == 1
        line = desc[0]
        # Should contain text, VarRef, text
        var_refs = [seg for seg in line if isinstance(seg, VarRef)]
        assert len(var_refs) == 1
        assert var_refs[0].name == 'MIN_SPACE'

    def test_multiple_varrefs_one_line(self):
        text = "check1 {\n  @ Window ^WIN_W um x ^WIN_H um\n  INT M1 < 0.1\n}"
        node = parse_one(text)
        line = node.description[0]
        var_refs = [seg for seg in line if isinstance(seg, VarRef)]
        assert len(var_refs) == 2
        assert var_refs[0].name == 'WIN_W'
        assert var_refs[1].name == 'WIN_H'


class TestMultiLineDescription:
    """Rule check blocks with multiple @ description lines."""

    def test_two_lines(self):
        text = (
            "check1 {\n"
            "  @ First line\n"
            "  @ Second line\n"
            "  INT M1 < 0.1\n"
            "}"
        )
        node = parse_one(text)
        assert isinstance(node.description, list)
        assert len(node.description) == 2
        assert 'First line' in ''.join(node.description[0])
        assert 'Second line' in ''.join(node.description[1])

    def test_many_lines_with_varrefs(self):
        """Mimics M4.DN.6.1 style: multiple @ lines with ^VARNAME refs."""
        text = (
            "M4.DN.6.1 { @ Metal Density >= ^M4_DN_6_1 must be followed\n"
            "@ (A) Metal density [window ^M4_DN_6_1_W um] >= ^M4_DN_6_1\n"
            "@ (B) Max area <= ^M4_DN_6_1_A_B um2\n"
            "  EXC = M1 OR M2\n"
            "}"
        )
        node = parse_one(text)
        assert_node_type(node, RuleCheckBlock, name="M4.DN.6.1")
        assert len(node.description) == 3

        # First line has ^M4_DN_6_1
        vars_line1 = [s for s in node.description[0] if isinstance(s, VarRef)]
        assert len(vars_line1) == 1
        assert vars_line1[0].name == 'M4_DN_6_1'

        # Second line has ^M4_DN_6_1_W and ^M4_DN_6_1
        vars_line2 = [s for s in node.description[1] if isinstance(s, VarRef)]
        assert len(vars_line2) == 2

        # Third line has ^M4_DN_6_1_A_B
        vars_line3 = [s for s in node.description[2] if isinstance(s, VarRef)]
        assert len(vars_line3) == 1
        assert vars_line3[0].name == 'M4_DN_6_1_A_B'

        # Body should still parse
        assert len(node.body) >= 1

    def test_inline_description_on_brace_line(self):
        """@ on same line as { should be captured."""
        text = "check1 { @ Inline desc\n  INT M1 < 0.1\n}"
        node = parse_one(text)
        assert len(node.description) == 1
        assert 'Inline desc' in ''.join(node.description[0])

    def test_no_description(self):
        """Rule block without @ should have description=None."""
        text = "check1 {\n  INT M1 < 0.1\n}"
        node = parse_one(text)
        assert node.description is None


class TestDescriptionBodySeparation:
    """Ensure description lines don't leak into body and vice versa."""

    def test_body_after_descriptions(self):
        text = (
            "rule1 {\n"
            "@ Line one\n"
            "@ Line two\n"
            "  A = M1 OR M2\n"
            "  INT A < 0.1\n"
            "}"
        )
        node = parse_one(text)
        assert len(node.description) == 2
        # Body should have the assignment and the INT op
        assert len(node.body) >= 2


class TestLiteralTextPreservation:
    """Description text must be preserved verbatim, not re-tokenized."""

    def test_numbered_list(self):
        """'1.' should stay '1.', not become '1.0'."""
        text = "rule1 {\n@ 1. The following regions are excluded\n  INT M1 < 0.1\n}"
        node = parse_one(text)
        joined = ''.join(s for s in node.description[0] if isinstance(s, str))
        assert '1.' in joined
        assert '1.0' not in joined

    def test_operators_preserved(self):
        """>= and <= should appear as literal text, not as tokens."""
        text = "rule1 {\n@ Space >= 0.042 um and width <= 0.09 um\n  INT M1 < 0.1\n}"
        node = parse_one(text)
        joined = ''.join(s for s in node.description[0] if isinstance(s, str))
        assert '>=' in joined
        assert '<=' in joined

    def test_parentheses_preserved(self):
        text = "rule1 {\n@ (A) Metal density [window 10 um x 10 um]\n  INT M1 < 0.1\n}"
        node = parse_one(text)
        joined = ''.join(s for s in node.description[0] if isinstance(s, str))
        assert '(A)' in joined
        assert '[window 10 um x 10 um]' in joined

    def test_escaped_caret(self):
        r"""'\^' should be treated as literal ^, with backslash stripped."""
        text = "rule1 {\n@ Value is \\^NOT_A_VAR here\n  INT M1 < 0.1\n}"
        node = parse_one(text)
        line = node.description[0]
        var_refs = [s for s in line if isinstance(s, VarRef)]
        assert len(var_refs) == 0
        joined = ''.join(s for s in line if isinstance(s, str))
        # Backslash stripped, literal ^ preserved
        assert '^NOT_A_VAR' in joined
        assert '\\^' not in joined
