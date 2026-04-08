"""Tier 1 unit tests: Device statements."""

import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_one, assert_node_type
from svrf_parser.ast_nodes import *


class TestDevice(unittest.TestCase):
    def test_device_mosfet(self):
        node = parse_one("DEVICE MOSFET(nmos) gate drain(D) source(S)")
        assert_node_type(node, Device)
        assert node.device_type == "MOSFET"
        assert node.device_name == "NMOS"

    def test_device_cmacro(self):
        node = parse_one("DEVICE MOSFET(nmos) gate drain source CMACRO extract")
        assert_node_type(node, Device)
        assert node.cmacro == "EXTRACT"


class TestDMacro(unittest.TestCase):
    def test_dmacro_basic(self):
        text = "DMACRO my_macro p1 p2 {\n  INT M1 < 0.1\n}"
        node = parse_one(text)
        assert_node_type(node, DMacro, name="MY_MACRO")
        assert node.params == ["P1", "P2"]
        assert len(node.body) >= 1


class TestTraceProperty(unittest.TestCase):
    def test_trace_property(self):
        node = parse_one("TRACE PROPERTY MOSFET(nmos) L W")
        assert_node_type(node, TraceProperty)
        assert "nmos" in node.device
