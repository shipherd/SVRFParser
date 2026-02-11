"""Tier 1 unit tests: Edge operations."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_expr, assert_node_type
from svrf_parser.ast_nodes import *


class TestConvexEdge:
    def test_convex_edge(self):
        node = parse_expr("CONVEX EDGE M1 ANGLE >= 90")
        assert_node_type(node, DRCOp, op="CONVEX EDGE")


class TestExpandEdge:
    def test_expand_edge(self):
        node = parse_expr("EXPAND EDGE M1 INSIDE BY 0.1")
        assert_node_type(node, DRCOp, op="EXPAND EDGE")


class TestMeasurementPrefix:
    def test_angle_prefix(self):
        node = parse_expr("ANGLE M1 == 45")
        assert_node_type(node, ConstrainedExpr)
        assert isinstance(node.expr, UnaryOp)
        assert node.expr.op == "ANGLE"

    def test_length_prefix(self):
        node = parse_expr("LENGTH M1 >= 0.1")
        assert_node_type(node, ConstrainedExpr)
        assert isinstance(node.expr, UnaryOp)
        assert node.expr.op == "LENGTH"

    def test_area_prefix(self):
        node = parse_expr("AREA M1 >= 0.01")
        assert_node_type(node, ConstrainedExpr)
        assert isinstance(node.expr, UnaryOp)
        assert node.expr.op == "AREA"

    def test_vertex(self):
        node = parse_expr("VERTEX M1 >= 8")
        assert_node_type(node, ConstrainedExpr)
        assert isinstance(node.expr, UnaryOp)
        assert node.expr.op == "VERTEX"
