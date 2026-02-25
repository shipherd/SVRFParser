"""Tier 1 unit tests: Spatial operations."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_expr, assert_node_type
from svrf_parser.ast_nodes import *


class TestSpatialBinaryOps:
    def test_inside(self):
        node = parse_expr("M1 INSIDE M2")
        assert_node_type(node, BinaryOp, op="INSIDE")

    def test_outside(self):
        node = parse_expr("M1 OUTSIDE M2")
        assert_node_type(node, BinaryOp, op="OUTSIDE")

    def test_interact(self):
        node = parse_expr("M1 INTERACT M2")
        assert_node_type(node, BinaryOp, op="INTERACT")

    def test_touch(self):
        node = parse_expr("M1 TOUCH M2")
        assert_node_type(node, BinaryOp, op="TOUCH")

    def test_enclose(self):
        node = parse_expr("M1 ENCLOSE M2")
        assert_node_type(node, BinaryOp, op="ENCLOSE")

    def test_cut(self):
        node = parse_expr("M1 CUT M2")
        assert_node_type(node, BinaryOp, op="CUT")

    def test_interact_constraint(self):
        node = parse_expr("M1 INTERACT M2 > 1")
        assert_node_type(node, ConstrainedExpr)
        assert isinstance(node.expr, BinaryOp)
        assert node.expr.op == "INTERACT"


class TestEdgeBinaryOps:
    def test_inside_edge(self):
        node = parse_expr("M1 INSIDE EDGE M2")
        assert_node_type(node, BinaryOp, op="INSIDE EDGE")

    def test_outside_edge(self):
        node = parse_expr("M1 OUTSIDE EDGE M2")
        assert_node_type(node, BinaryOp, op="OUTSIDE EDGE")

    def test_coin_edge(self):
        node = parse_expr("M1 COIN EDGE M2")
        assert_node_type(node, BinaryOp, op="COIN EDGE")

    def test_in_edge(self):
        node = parse_expr("M1 IN EDGE M2")
        assert_node_type(node, BinaryOp, op="IN EDGE")


class TestTouchEdge:
    def test_touch_edge(self):
        node = parse_expr("M1 TOUCH EDGE M2")
        assert_node_type(node, BinaryOp, op="TOUCH EDGE")

    def test_or_edge(self):
        node = parse_expr("M1 OR EDGE M2")
        assert_node_type(node, BinaryOp, op="OR EDGE")


class TestNotCompound:
    def test_not_touch(self):
        node = parse_expr("M1 NOT TOUCH M2")
        assert_node_type(node, BinaryOp, op="NOT TOUCH")

    def test_not_touch_edge(self):
        node = parse_expr("M1 NOT TOUCH EDGE M2")
        assert_node_type(node, BinaryOp, op="NOT TOUCH EDGE")

    def test_not_in(self):
        node = parse_expr("M1 NOT IN M2")
        assert_node_type(node, BinaryOp, op="NOT IN")

    def test_not_inside(self):
        node = parse_expr("M1 NOT INSIDE M2")
        assert_node_type(node, BinaryOp, op="NOT INSIDE")

    def test_not_interact(self):
        node = parse_expr("M1 NOT INTERACT M2")
        assert_node_type(node, BinaryOp, op="NOT INTERACT")

    def test_not_enclose(self):
        node = parse_expr("M1 NOT ENCLOSE M2")
        assert_node_type(node, BinaryOp, op="NOT ENCLOSE")

    def test_not_cut(self):
        node = parse_expr("M1 NOT CUT M2")
        assert_node_type(node, BinaryOp, op="NOT CUT")

    def test_not_inside_edge(self):
        node = parse_expr("M1 NOT INSIDE EDGE M2")
        assert_node_type(node, BinaryOp, op="NOT INSIDE EDGE")

    def test_not_outside_edge(self):
        node = parse_expr("M1 NOT OUTSIDE EDGE M2")
        assert_node_type(node, BinaryOp, op="NOT OUTSIDE EDGE")
