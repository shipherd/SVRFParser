"""Tier 1 unit tests: Connectivity statements."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_one, assert_node_type
from svrf_parser.ast_nodes import *


class TestConnect:
    def test_connect_two(self):
        node = parse_one("CONNECT M1 M2")
        assert_node_type(node, Connect, soft=False)
        assert node.layers == ["M1", "M2"]

    def test_connect_by(self):
        node = parse_one("CONNECT M1 M2 BY VIA1")
        assert_node_type(node, Connect)
        assert node.via_layer == "VIA1"

    def test_sconnect(self):
        node = parse_one("SCONNECT M1 M2")
        assert_node_type(node, Connect, soft=True)


class TestAttach:
    def test_attach(self):
        node = parse_one("ATTACH M1 VDD")
        assert_node_type(node, Attach, layer="M1", net="VDD")


class TestGroup:
    def test_group(self):
        node = parse_one("GROUP grp1 pattern")
        assert_node_type(node, Group, name="grp1")
