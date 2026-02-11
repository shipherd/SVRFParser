"""Tier 1 unit tests: Expressions."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_expr, assert_node_type
from svrf_parser.ast_nodes import *


class TestConstraints:
    def test_constraint_chain(self):
        node = parse_expr("M1 > 0.1 < 0.5")
        assert_node_type(node, ConstrainedExpr)
        assert len(node.constraints) == 2

    def test_bangeq_constraint(self):
        node = parse_expr("M1 != 0")
        assert_node_type(node, ConstrainedExpr)
        assert node.constraints[0].op == "!="


class TestWithExpr:
    def test_with_width(self):
        node = parse_expr("M1 WITH WIDTH M2 == 0.1")
        assert_node_type(node, ConstrainedExpr)
        assert isinstance(node.expr, BinaryOp)
        assert "WITH" in node.expr.op

    def test_with_edge(self):
        node = parse_expr("M1 WITH EDGE M2 == 0.04")
        assert_node_type(node, ConstrainedExpr)
        assert isinstance(node.expr, BinaryOp)


class TestMiscExpr:
    def test_net_area_ratio(self):
        node = parse_expr("NET AREA RATIO M1 M2 > 1000")
        assert_node_type(node, DRCOp)
        assert "NET AREA RATIO" in node.op

    def test_dfm_property(self):
        node = parse_expr("DFM PROPERTY M1 M2")
        assert_node_type(node, DRCOp)
        assert "DFM" in node.op

    def test_func_call(self):
        # AREA(M1) parses as ConstrainedExpr(UnaryOp("AREA")), not FuncCall
        node = parse_expr("AREA(M1)")
        assert_node_type(node, ConstrainedExpr)
        assert isinstance(node.expr, UnaryOp)
        assert node.expr.op == "AREA"

    def test_negative_number(self):
        node = parse_expr("-0.5")
        assert_node_type(node, NumberLiteral)
        assert node.value == -0.5
