"""Shared test utility functions for SVRF parser tests."""

import sys
from pathlib import Path
from collections import Counter
from typing import Iterator

sys.path.insert(0, str(Path(__file__).parent.parent))

from svrf_parser import parse, parse_with_diagnostics
from svrf_parser.ast_nodes import AstNode, LayerAssignment, Program


def parse_one(text: str) -> AstNode:
    """Parse text, assert exactly 1 top-level statement, return it."""
    tree = parse(text, filename="<test>")
    assert len(tree.statements) == 1, \
        f"Expected 1 statement, got {len(tree.statements)}: {[type(s).__name__ for s in tree.statements]}"
    return tree.statements[0]


def parse_expr(text: str) -> AstNode:
    """Wrap input as '_TEST_ = {text}', trigger expression parse, return expr node."""
    stmt = parse_one(f"_TEST_ = {text}")
    assert isinstance(stmt, LayerAssignment), \
        f"Expected LayerAssignment, got {type(stmt).__name__}"
    return stmt.expression


def assert_node_type(node, expected_type, **field_checks):
    """Assert node type and optionally check field values."""
    assert isinstance(node, expected_type), \
        f"Expected {expected_type.__name__}, got {type(node).__name__}"
    for field, expected in field_checks.items():
        actual = getattr(node, field, None)
        assert actual == expected, \
            f"{field}: expected {expected!r}, got {actual!r}"


def walk_ast(node) -> Iterator:
    """Yield AST nodes using the parser's canonical iterative traversal."""

    yield from node.walk()


def count_node_types(tree: Program) -> Counter:
    """Recursively count all AST node types."""
    return Counter(type(n).__name__ for n in walk_ast(tree))


def collect_warnings(text: str) -> list:
    """Parse text and return only the warnings list."""
    _, warnings = parse_with_diagnostics(text, filename="<test>")
    return warnings


def ast_equal(a, b) -> bool:
    """Recursively compare two AST nodes for structural equality.

    Ignores line/col position info and whitespace differences.
    """
    if type(a) != type(b):
        return False
    return a.structurally_equal(b, include_position=False)
