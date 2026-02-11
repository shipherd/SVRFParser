"""Tier 1 unit tests: Property blocks."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_one, assert_node_type
from svrf_parser.ast_nodes import *


class TestPropertyBlock:
    def test_basic(self):
        text = "[PROPERTY p1, p2\n  x = 1\n]"
        node = parse_one(text)
        assert_node_type(node, PropertyBlock)
        assert "p1" in node.properties


class TestIfExpr:
    def test_if_in_dmacro(self):
        # Parser currently handles IF without ELSE inside DMACRO
        text = "DMACRO test_m {\nIF (x==1) { y=2 }\n}"
        node = parse_one(text)
        assert_node_type(node, DMacro)
        assert len(node.body) >= 1
