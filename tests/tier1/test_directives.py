"""Tier 1 unit tests: Directives."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_one, assert_node_type
from svrf_parser.ast_nodes import *


class TestDirectives:
    def test_layout_path(self):
        node = parse_one('LAYOUT PATH "design.gds"')
        assert_node_type(node, Directive)
        assert "LAYOUT" in [k.upper() for k in node.keywords]

    def test_layout_primary(self):
        node = parse_one('LAYOUT PRIMARY "top"')
        assert_node_type(node, Directive)

    def test_drc_results(self):
        node = parse_one('DRC RESULTS DATABASE "out.db"')
        assert_node_type(node, Directive)

    def test_lvs_report(self):
        node = parse_one('LVS REPORT "report.txt"')
        assert_node_type(node, Directive)

    def test_precision(self):
        node = parse_one("PRECISION 1000")
        assert_node_type(node, Directive)

    def test_resolution(self):
        node = parse_one("RESOLUTION 5")
        assert_node_type(node, Directive)

    def test_title(self):
        node = parse_one('TITLE "My DRC Deck"')
        assert_node_type(node, Directive)

    def test_unit_capacitance(self):
        node = parse_one("UNIT CAPACITANCE FF")
        assert_node_type(node, Directive)

    def test_hcell(self):
        node = parse_one('HCELL "cellname" FLATTEN')
        assert_node_type(node, Directive)


class TestVariable:
    def test_variable(self):
        node = parse_one("VARIABLE WIDTH 0.1")
        assert_node_type(node, VariableDef, name="WIDTH")


class TestRdbDirective:
    def test_rdb_basic(self):
        node = parse_one('RDB "./output/report.RDB" M1 GATE')
        assert_node_type(node, Directive)
        assert "RDB" in [k.upper() for k in node.keywords]
