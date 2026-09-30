"""Shared helpers for recognizing SVRF-specific AST constructs."""

from __future__ import annotations

from . import ast


SVRF_NODE_TYPES = (
    ast.LayerDef,
    ast.LayerMap,
    ast.LayerAssignment,
    ast.Directive,
    ast.DfmSpec,
    ast.DfmClause,
    ast.PercLoad,
    ast.RuleCheckBlock,
    ast.Connect,
    ast.Device,
    ast.DMacro,
    ast.MacroCall,
    ast.Define,
    ast.IfDef,
    ast.Include,
    ast.EncryptedBlock,
    ast.Group,
    ast.Attach,
    ast.TraceProperty,
    ast.VariableDef,
)


def is_svrf_construct(node):
    """Return True for top-level nodes that count toward SVRF corpus quality."""

    return isinstance(node, SVRF_NODE_TYPES)


def count_svrf_constructs(statements):
    """Count SVRF-specific statements in an iterable of AST nodes."""

    return sum(1 for statement in statements if is_svrf_construct(statement))
