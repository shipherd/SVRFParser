"""Tier 1 unit tests: Complex compound expressions and edge cases."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_expr, parse_one, assert_node_type, collect_warnings
from svrf_parser.ast_nodes import *


class TestDeepNesting:
    def test_triple_nested_boolean(self):
        node = parse_expr("((A AND B) OR C) NOT D")
        assert isinstance(node, BinaryOp)
        assert node.op == "NOT"

    def test_chained_spatial(self):
        node = parse_expr("(A NOT B) NOT INTERACT C")
        assert isinstance(node, BinaryOp)
        assert node.op == "NOT INTERACT"

    def test_not_interact_in_parens(self):
        node = parse_expr("(A NOT INTERACT B) AND C")
        assert isinstance(node, BinaryOp)
        assert node.op == "AND"
        assert isinstance(node.left, BinaryOp)
        assert node.left.op == "NOT INTERACT"

    def test_double_not_inside(self):
        node = parse_expr("(A NOT INSIDE B) NOT INSIDE C")
        assert isinstance(node, BinaryOp)
        assert node.op == "NOT INSIDE"
        assert isinstance(node.left, BinaryOp)
        assert node.left.op == "NOT INSIDE"

    def test_or_chain(self):
        """OR chains: A OR B C D -> OR(OR(OR(A,B),C),D)"""
        node = parse_expr("A OR B C D")
        assert isinstance(node, BinaryOp)
        assert node.op == "OR"
        # Should be left-associative chain
        assert isinstance(node.left, BinaryOp)


class TestSamplePatterns:
    """Patterns extracted from real SVRF sample files."""

    def test_complex_not_chain(self):
        """From 7nm calibre.drc: X = (GT NOT FTGT) NOT INTERACT HRP"""
        node = parse_expr("(GT NOT FTGT) NOT INTERACT HRP")
        assert isinstance(node, BinaryOp)
        assert node.op == "NOT INTERACT"

    def test_int_abut_singular_region(self):
        """From 14nm DRC: INT MOS12 < 0.12 ABUT<90> SINGULAR REGION"""
        node = parse_expr("INT MOS12 < 0.12 ABUT<90> SINGULAR REGION")
        assert isinstance(node, DRCOp)
        assert 'ABUT<90>' in node.modifiers
        assert 'SINGULAR' in node.modifiers
        assert 'REGION' in node.modifiers

    def test_size_by_overunder(self):
        node = parse_expr("SIZE M1 BY 0.5 OVERUNDER")
        assert isinstance(node, DRCOp)
        assert node.op == "SIZE"
        by_items = [m for m in node.modifiers if isinstance(m, tuple) and m[0] == 'BY']
        assert len(by_items) == 1

    def test_not_enclose_rectangle(self):
        """From 14nm DRC: NOT ENCLOSE RECTANGLE with operands"""
        node = parse_expr("(A INTERACT B) NOT ENCLOSE RECTANGLE 0.001 30")
        assert isinstance(node, DRCOp)
        assert node.op == "NOT ENCLOSE RECTANGLE"

    def test_rectangle_eq_by_eq(self):
        """RECTANGLE == val BY == val ORTHOGONAL ONLY"""
        node = parse_expr("RECTANGLE M1 == 5.0 BY == 10.0 ORTHOGONAL ONLY")
        assert isinstance(node, DRCOp)
        assert node.op == "RECTANGLE"

    def test_density_window_step(self):
        node = parse_expr("DENSITY M1 > 0.70 WINDOW 25 STEP 12.5")
        assert isinstance(node, DRCOp)
        assert node.op == "DENSITY"


class TestNegativeCases:
    def test_unclosed_paren_no_crash(self):
        """Parser should not crash on unclosed parens."""
        warnings = collect_warnings("X = (A AND B")
        # Should parse without exception (may produce warnings)

    def test_empty_assignment(self):
        """Empty assignment should not crash."""
        warnings = collect_warnings("X =")
        # Should not crash

    def test_unknown_keyword_no_crash(self):
        """Unknown identifiers treated as layer refs."""
        node = parse_expr("FOOBAR")
        assert isinstance(node, LayerRef)
        assert node.name == "FOOBAR"
