"""Normalize operation-level CST into AST nodes."""

from __future__ import annotations

from . import ast
from .operation_cst import OperationCst


def normalize_operation_cst(operation_cst: OperationCst, *, location):
    """Build the canonical AST node for a DRC operation CST."""

    return ast.DRCOp(
        op=operation_cst.op,
        operands=list(operation_cst.operands),
        constraints=list(operation_cst.constraints),
        modifiers=list(operation_cst.modifiers),
        **location,
    )


def normalize_operation_parts(
    op,
    *,
    operands=(),
    constraints=(),
    modifiers=(),
    strategy="default",
    location,
):
    """Convenience helper for handlers that already collected operation parts."""

    operation_cst = OperationCst(
        op=op,
        operands=tuple(operands or ()),
        constraints=tuple(constraints or ()),
        modifiers=tuple(modifiers or ()),
        strategy=strategy,
    )
    return normalize_operation_cst(operation_cst, location=location)

