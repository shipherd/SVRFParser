"""Tier 1 unit tests: Boolean operations."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_expr, assert_node_type
from svrf_parser.ast_nodes import *


class TestBinaryBoolOps:
    def test_and(self):
        node = parse_expr("M1 AND M2")
        assert_node_type(node, BinaryOp, op="AND")

    def test_or(self):
        node = parse_expr("M1 OR M2")
        assert_node_type(node, BinaryOp, op="OR")

    def test_not_infix(self):
        node = parse_expr("M1 NOT M2")
        assert_node_type(node, BinaryOp, op="NOT")

    def test_precedence_and_or(self):
        node = parse_expr("M1 OR M2 AND M3")
        # AND binds tighter than OR
        assert_node_type(node, BinaryOp, op="OR")
        assert isinstance(node.right, BinaryOp)
        assert node.right.op == "AND"

    def test_parenthesized(self):
        node = parse_expr("(M1 OR M2) AND M3")
        assert_node_type(node, BinaryOp, op="AND")
        assert isinstance(node.left, BinaryOp)
        assert node.left.op == "OR"


class TestUnaryBoolOps:
    def test_not_unary(self):
        node = parse_expr("NOT M1")
        assert_node_type(node, UnaryOp, op="NOT")

    def test_copy(self):
        node = parse_expr("COPY M1")
        assert_node_type(node, UnaryOp, op="COPY")


class TestPrefixOr:
    def test_prefix_or(self):
        node = parse_expr("OR M1 M2 M3")
        # Should build a chain of OR BinaryOps
        assert_node_type(node, BinaryOp, op="OR")


class TestXor:
    def test_xor_infix(self):
        node = parse_expr("M1 XOR M2")
        assert_node_type(node, BinaryOp, op="XOR")

    def test_xor_prefix(self):
        node = parse_expr("XOR A B")
        assert_node_type(node, BinaryOp, op="XOR")

    def test_xor_prefix_chain(self):
        node = parse_expr("XOR A B C")
        assert_node_type(node, BinaryOp, op="XOR")
        # Left-associative chain: (A XOR B) XOR C
        assert isinstance(node.left, BinaryOp)
        assert node.left.op == "XOR"


class TestPrefixAnd:
    def test_prefix_and(self):
        node = parse_expr("AND M1 M2")
        assert_node_type(node, BinaryOp, op="AND")

    def test_prefix_and_chain(self):
        node = parse_expr("AND M1 M2 M3")
        assert_node_type(node, BinaryOp, op="AND")
        assert isinstance(node.left, BinaryOp)
