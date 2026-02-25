"""Shared test utility functions for SVRF parser tests."""

import sys
from pathlib import Path
from collections import Counter
from typing import Iterator

sys.path.insert(0, str(Path(__file__).parent.parent))

from svrf_parser import parse, parse_with_diagnostics
from svrf_parser.ast_nodes import *


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
    """Depth-first traversal of all AST nodes."""
    yield node
    if isinstance(node, Program):
        for s in node.statements:
            yield from walk_ast(s)
    elif isinstance(node, IfDef):
        for s in node.then_body:
            yield from walk_ast(s)
        for s in node.else_body:
            yield from walk_ast(s)
    elif isinstance(node, RuleCheckBlock):
        for s in node.body:
            yield from walk_ast(s)
        if node.description:
            yield from walk_ast(node.description)
    elif isinstance(node, DMacro):
        for s in node.body:
            yield from walk_ast(s)
    elif isinstance(node, PropertyBlock):
        for s in node.body:
            yield from walk_ast(s)
    elif isinstance(node, IfExpr):
        if node.condition:
            yield from walk_ast(node.condition)
        for s in node.then_body:
            yield from walk_ast(s)
        for cond, body in node.elseifs:
            yield from walk_ast(cond)
            for s in body:
                yield from walk_ast(s)
        for s in node.else_body:
            yield from walk_ast(s)
    elif isinstance(node, BinaryOp):
        if node.left:
            yield from walk_ast(node.left)
        if node.right:
            yield from walk_ast(node.right)
    elif isinstance(node, UnaryOp):
        if node.operand:
            yield from walk_ast(node.operand)
    elif isinstance(node, ConstrainedExpr):
        if node.expr:
            yield from walk_ast(node.expr)
        for c in node.constraints:
            yield from walk_ast(c)
    elif isinstance(node, DRCOp):
        for o in node.operands:
            if isinstance(o, AstNode):
                yield from walk_ast(o)
        for c in node.constraints:
            yield from walk_ast(c)
    elif isinstance(node, LayerAssignment):
        if node.expression:
            yield from walk_ast(node.expression)
    elif isinstance(node, FuncCall):
        for a in node.args:
            if isinstance(a, AstNode):
                yield from walk_ast(a)
    elif isinstance(node, Directive):
        if node.property_block:
            yield from walk_ast(node.property_block)
    elif isinstance(node, VariableDef):
        if node.expr:
            yield from walk_ast(node.expr)


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
    if isinstance(a, Program):
        if len(a.statements) != len(b.statements):
            return False
        return all(ast_equal(x, y) for x, y in zip(a.statements, b.statements))
    # Compare all __slots__ except line/col
    for cls in type(a).__mro__:
        for slot in getattr(cls, '__slots__', ()):
            if slot in ('line', 'col'):
                continue
            va = getattr(a, slot, None)
            vb = getattr(b, slot, None)
            if isinstance(va, AstNode) and isinstance(vb, AstNode):
                if not ast_equal(va, vb):
                    return False
            elif isinstance(va, list) and isinstance(vb, list):
                if len(va) != len(vb):
                    return False
                for x, y in zip(va, vb):
                    if isinstance(x, AstNode) and isinstance(y, AstNode):
                        if not ast_equal(x, y):
                            return False
                    elif isinstance(x, tuple) and isinstance(y, tuple):
                        if len(x) != len(y):
                            return False
                        for tx, ty in zip(x, y):
                            if isinstance(tx, AstNode) and isinstance(ty, AstNode):
                                if not ast_equal(tx, ty):
                                    return False
                            elif tx != ty:
                                return False
                    elif x != y:
                        return False
            elif va != vb:
                return False
    return True
