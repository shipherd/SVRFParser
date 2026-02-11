"""Tier 1 unit tests: DRC operations."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_expr, assert_node_type
from svrf_parser.ast_nodes import *


class TestDRCBasic:
    def test_int_basic(self):
        node = parse_expr("INT M1 < 0.1")
        assert_node_type(node, DRCOp, op="INT")
        assert len(node.operands) >= 1
        assert len(node.constraints) >= 1

    def test_int_two_layers(self):
        node = parse_expr("INT M1 M2 < 0.1")
        assert_node_type(node, DRCOp, op="INT")
        assert len(node.operands) == 2

    def test_ext_basic(self):
        node = parse_expr("EXT M1 M2 < 0.1")
        assert_node_type(node, DRCOp, op="EXT")

    def test_enc_basic(self):
        node = parse_expr("ENC M1 M2 < 0.1")
        assert_node_type(node, DRCOp, op="ENC")

    def test_enc_rectangle(self):
        node = parse_expr("ENC RECTANGLE M1 M2 < 0.1")
        assert node.op in ("ENC RECTANGLE", "ENCLOSE RECTANGLE")

    def test_density(self):
        node = parse_expr("DENSITY M1 < 0.5 > 0.1")
        assert_node_type(node, DRCOp, op="DENSITY")


class TestDRCModifiers:
    def test_drc_with_modifiers(self):
        node = parse_expr("INT M1 < 0.1 OPPOSITE REGION")
        assert_node_type(node, DRCOp, op="INT")
        assert len(node.modifiers) >= 1

    def test_drc_bracket_operand(self):
        node = parse_expr("INT [M1 AND M2] < 0.1")
        assert_node_type(node, DRCOp, op="INT")


class TestOffgrid:
    def test_offgrid_basic(self):
        node = parse_expr("OFFGRID M1 (100) (50) INSIDE OF LAYER M2 ABSOLUTE")
        assert_node_type(node, DRCOp, op="OFFGRID")
        assert len(node.operands) >= 1
        assert "INSIDE" in node.modifiers
        assert "OF" in node.modifiers
        assert "LAYER" in node.modifiers


class TestRotate:
    def test_rotate_by(self):
        node = parse_expr("ROTATE M1 BY 45")
        assert_node_type(node, DRCOp, op="ROTATE")
        assert len(node.operands) == 1
        assert "BY" in node.modifiers
        assert "45" in node.modifiers


class TestExpandEdgeLED:
    def test_expand_edge_postfix(self):
        node = parse_expr("(LENGTH M1 < 0.238) EXPAND EDGE INSIDE BY 0.001")
        assert_node_type(node, DRCOp, op="EXPAND EDGE")

    def test_expand_edge_arithmetic_value(self):
        node = parse_expr("EXPAND EDGE M1 INSIDE BY 0.05+TOL OUTSIDE BY 0.02+TOL")
        assert_node_type(node, DRCOp, op="EXPAND EDGE")
        # Should have INSIDE, BY, expr, OUTSIDE, BY, expr in modifiers
        mod_strs = [str(m) if not hasattr(m, 'op') else m.op for m in node.modifiers]
        assert "INSIDE" in mod_strs
        assert "OUTSIDE" in mod_strs


class TestDeviceLayer:
    def test_device_layer(self):
        node = parse_expr("DEVICE LAYER MN(nmos) ANNOTATE AA_netid")
        assert_node_type(node, DRCOp, op="DEVICE LAYER")
        assert "MN(nmos)" in node.modifiers
        assert "ANNOTATE" in node.modifiers


class TestRectangleConstraints:
    def test_rectangle_no_operand(self):
        """RECTANGLE == val BY == val (no operand before constraints)."""
        node = parse_expr("NOT RECTANGLE == 4.128 BY == 4.128 ORTHOGONAL ONLY")
        # NOT is unary prefix, RECTANGLE is its operand
        assert_node_type(node, UnaryOp, op="NOT")

    def test_rectangle_paren_constraint(self):
        """RECTANGLE with parenthesized constraint values."""
        node = parse_expr("RECTANGLE M1 >= (W-TOL) <= (W+TOL)")
        assert_node_type(node, DRCOp, op="RECTANGLE")

    def test_rectangle_aspect(self):
        """RECTANGLE with ASPECT modifier and constraint."""
        node = parse_expr("RECTANGLE M1 ASPECT > 1")
        assert_node_type(node, DRCOp, op="RECTANGLE")
        mod_strs = [str(m) for m in node.modifiers]
        assert "ASPECT" in mod_strs
