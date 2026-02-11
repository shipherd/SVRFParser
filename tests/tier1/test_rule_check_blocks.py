"""Tier 1 unit tests: Rule check blocks."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_one, assert_node_type
from svrf_parser.ast_nodes import *


class TestRuleCheckBlock:
    def test_basic_block(self):
        text = "check1 {\n  INT M1 < 0.1\n}"
        node = parse_one(text)
        assert_node_type(node, RuleCheckBlock, name="check1")
        assert len(node.body) >= 1

    def test_with_description(self):
        text = "check1 {\n  @ Description text\n  INT M1 < 0.1\n}"
        node = parse_one(text)
        assert_node_type(node, RuleCheckBlock, name="check1")
        assert node.description is not None

    def test_brace_next_line(self):
        text = "check1\n{\n  INT M1 < 0.1\n}"
        node = parse_one(text)
        assert_node_type(node, RuleCheckBlock, name="check1")
        assert len(node.body) >= 1

    def test_nested_ifdef(self):
        text = "check1 {\n  #IFDEF FOO\n  INT M1 < 0.1\n  #ENDIF\n}"
        node = parse_one(text)
        assert_node_type(node, RuleCheckBlock, name="check1")
        ifdef_nodes = [s for s in node.body if isinstance(s, IfDef)]
        assert len(ifdef_nodes) >= 1

    def test_multiple_ops(self):
        text = "check1 {\n  INT M1 < 0.1\n  EXT M1 M2 < 0.2\n}"
        node = parse_one(text)
        assert_node_type(node, RuleCheckBlock, name="check1")
        assert len(node.body) >= 2
