"""Tier 1 unit tests: Size, Grow, Shrink operations."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_expr, assert_node_type
from svrf_parser.ast_nodes import *


class TestSizeOps:
    def test_size_basic(self):
        node = parse_expr("SIZE M1 BY 0.1")
        assert_node_type(node, DRCOp, op="SIZE")
        assert len(node.operands) == 1

    def test_size_underover(self):
        node = parse_expr("SIZE M1 BY 0.1 UNDEROVER")
        assert_node_type(node, DRCOp, op="SIZE")
        assert any(
            str(m).upper() == "UNDEROVER"
            for m in node.modifiers
        )

    def test_size_inside_of(self):
        node = parse_expr("SIZE M1 BY 0.1 INSIDE OF M2")
        assert_node_type(node, DRCOp, op="SIZE")


class TestGrowShrink:
    def test_grow_basic(self):
        node = parse_expr("GROW M1 TOP BY 0.1 BOTTOM BY 0.2")
        assert_node_type(node, DRCOp, op="GROW")

    def test_shrink_basic(self):
        node = parse_expr("SHRINK M1 LEFT BY 0.1")
        assert_node_type(node, DRCOp, op="SHRINK")


class TestMiscUnary:
    def test_holes(self):
        node = parse_expr("HOLES M1")
        assert node.op in ("HOLES",) or isinstance(node, UnaryOp)

    def test_donut(self):
        node = parse_expr("DONUT M1")
        assert_node_type(node, UnaryOp, op="DONUT")

    def test_extent(self):
        node = parse_expr("EXTENT DRAWN")
        assert_node_type(node, DRCOp, op="EXTENT")

    def test_stamp(self):
        node = parse_expr("STAMP M1 BY M2")
        assert_node_type(node, BinaryOp, op="STAMP")
