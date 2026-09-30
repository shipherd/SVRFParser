"""Iterative value-validation pass helpers for semantic validation."""

from __future__ import annotations

from . import ast
from .modifiers import NamedModifier, RawModifier, as_modifier
from .semantic_symbols import (
    _collect_statement_placeholders,
    _property_function_skipped_arg_indexes,
)

_SCALAR_BINARY_OPS = frozenset({"+", "-", "*", "/", "^", "%"})
_SCALAR_UNARY_OPS = frozenset({"+", "-", "~"})


_ITERATIVE_VALUE_NODES = (
    ast.BinaryOp,
    ast.ConstrainedExpr,
    ast.Constraint,
    ast.EncryptedBlock,
    ast.FuncCall,
    ast.NumberLiteral,
    ast.StringLiteral,
    ast.UnaryOp,
)


class ValueValidationMixin:
    """Expression/value traversal helpers used by SemanticValidator."""

    def _run_tasks(self, pending):
        while pending:
            task, payload = pending.pop()
            if task == "node":
                node, scope = payload
                self._validate_node(node, scope, pending)
                continue
            if task == "merge_branches":
                scope, branches = payload
                scope.merge_branches(branches)

    def _push_statement_tasks(self, pending, statements, scope):
        for statement in reversed(statements):
            pending.append(("node", (statement, scope)))

    def _validate_statement_list(self, statements, scope):
        pending = []
        self._push_statement_tasks(pending, statements, scope)
        self._run_tasks(pending)

    def _validate_value(self, value, scope, context="generic"):
        pending = [(value, context)]
        while pending:
            current, current_context = pending.pop()
            if isinstance(current, (NamedModifier, RawModifier)):
                pending.append((current.value, current.context(current_context)))
                continue
            if isinstance(current, ast.AstNode):
                current_context = self.expression_context_for(current, current_context)
                if isinstance(current, ast.ErrorNode):
                    self.error(
                        "semantic.error_node",
                        current.message or "Recovered parser error",
                        current,
                    )
                    continue
                if isinstance(current, ast.LayerRef):
                    self._warn_unknown_reference(
                        "semantic.reference.undefined",
                        current.name,
                        current,
                        scope,
                        context=current_context,
                    )
                    continue
                if isinstance(current, ast.StringLiteral):
                    tags = self.expression_contexts.get(current) if self.expression_contexts else ()
                    if current_context in {"layer", "rule_body_operation", "scalar"} and "directive_argument" not in tags:
                        self._warn_unknown_reference(
                            "semantic.reference.undefined", current.value, current, scope,
                            context=current_context, quoted=True,
                        )
                    continue
                if isinstance(current, ast.VarRef):
                    if not scope.knows_variable(current.name) and not self._warn_conditional_symbol(
                        ("variables",), current.name, current, scope, context="scalar",
                    ):
                        self.warning(
                            "semantic.varref.undefined",
                            f"Description variable reference ^{current.name} has no matching VARIABLE",
                            current,
                            metadata={"symbol": current.name},
                        )
                    continue
                if isinstance(current, ast.Constraint):
                    pending.append((current.value, "scalar"))
                    continue
                if isinstance(current, ast.BinaryOp):
                    child_context = "scalar" if current.op in _SCALAR_BINARY_OPS else current_context
                    pending.append((current.right, child_context))
                    pending.append((current.left, child_context))
                    continue
                if isinstance(current, ast.UnaryOp):
                    operand_context = "scalar" if current.op in _SCALAR_UNARY_OPS else current_context
                    pending.append((current.operand, operand_context))
                    continue
                if isinstance(current, ast.ConstrainedExpr):
                    for modifier in reversed(current.modifier_nodes):
                        pending.append((modifier, "generic"))
                    for constraint in reversed(current.constraints):
                        pending.append((constraint, "generic"))
                    pending.append((current.expr, current_context))
                    continue
                if isinstance(current, ast.FuncCall):
                    skipped_indexes = set(_property_function_skipped_arg_indexes(current))
                    for idx, arg in reversed(list(enumerate(current.args))):
                        if idx not in skipped_indexes:
                            pending.append((arg, "generic"))
                    continue
                if isinstance(current, _ITERATIVE_VALUE_NODES):
                    children = []
                    for _, child in current.iter_fields(include_position=False):
                        children.append((child, current_context))
                    pending.extend(reversed(children))
                    continue
                self._run_tasks([("node", (current, scope))])
                continue
            if isinstance(current, list):
                pending.extend((item, current_context) for item in reversed(current))
                continue
            if isinstance(current, tuple):
                if len(current) == 2 and isinstance(current[0], str):
                    pending.append((as_modifier(current), current_context))
                    continue
                pending.extend((item, current_context) for item in reversed(current))

    def _validate_if_expr(self, node, scope, pending):
        self._validate_value(node.condition, scope)
        bodies = [node.then_body]
        for branch in node.elseifs:
            if isinstance(branch, tuple) and len(branch) == 2:
                condition, body = branch
                self._validate_value(condition, scope)
                bodies.append(body)
            else:
                self._validate_value(branch, scope)
        bodies.append(node.else_body)
        branches = [scope.child() for _ in bodies]
        pending.append(("merge_branches", (scope, branches)))
        for body, branch_scope in reversed(list(zip(bodies, branches))):
            for name in _collect_statement_placeholders(body, include_conditionals=False):
                branch_scope.define_placeholder(name)
            self._push_statement_tasks(pending, body, branch_scope)
