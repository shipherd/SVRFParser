"""Tier 1 unit tests: Layer operations."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_one, assert_node_type
from svrf_parser.ast_nodes import *


class TestLayerDef:
    def test_layer_def(self):
        node = parse_one("LAYER M1 10")
        assert_node_type(node, LayerDef, name="M1")
        assert node.numbers == [10]

    def test_layer_def_multi(self):
        node = parse_one("LAYER M1 10 11")
        assert_node_type(node, LayerDef, name="M1")
        assert node.numbers == [10, 11]


class TestLayerMap:
    def test_layer_map_datatype(self):
        node = parse_one("LAYER MAP 62 DATATYPE 0 1062")
        assert_node_type(node, LayerMap, map_type="DATATYPE")
        assert node.gds_num == 62

    def test_layer_map_texttype(self):
        node = parse_one("LAYER MAP 10 TEXTTYPE 0 1010")
        assert_node_type(node, LayerMap, map_type="TEXTTYPE")
        assert node.gds_num == 10


class TestLayerAssignment:
    def test_layer_assignment(self):
        node = parse_one("M1_sized = SIZE M1 BY 0.1")
        assert_node_type(node, LayerAssignment, name="M1_sized")
        assert node.expression is not None

    def test_digit_prefix_name(self):
        node = parse_one("15V_GATE = M1 AND M2")
        assert_node_type(node, LayerAssignment, name="15V_GATE")
        assert isinstance(node.expression, BinaryOp)
