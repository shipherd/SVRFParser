"""Expression context annotation for semantic validation."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import ast

LAYER_EXPRESSION = "layer_expression"
SCALAR_EXPRESSION = "scalar_expression"
DIRECTIVE_ARGUMENT = "directive_argument"
PROPERTY_EXPRESSION = "property_expression"
RULE_BODY_OPERATION = "rule_body_operation"

_SCALAR_CONTEXTS = frozenset({SCALAR_EXPRESSION, DIRECTIVE_ARGUMENT})
_LAYER_CONTEXTS = frozenset({LAYER_EXPRESSION, PROPERTY_EXPRESSION, RULE_BODY_OPERATION})


@dataclass(slots=True)
class ExpressionContextAnnotations:
    """Context tags keyed by AST node identity."""

    _tags_by_id: dict[int, set[str]] = field(default_factory=dict)

    def add(self, node, tag):
        if isinstance(node, ast.AstNode):
            self._tags_by_id.setdefault(id(node), set()).add(tag)

    def get(self, node):
        return frozenset(self._tags_by_id.get(id(node), ()))

    def semantic_context_for(self, node, fallback="generic"):
        tags = self.get(node)
        if not tags:
            return fallback
        if fallback != "generic":
            return fallback
        if tags & _SCALAR_CONTEXTS:
            return "scalar"
        if RULE_BODY_OPERATION in tags:
            return "rule_body_operation"
        if PROPERTY_EXPRESSION in tags:
            return "property_expression"
        if tags & _LAYER_CONTEXTS:
            return "layer"
        return fallback


def annotate_expression_contexts(program):
    """Return expression context annotations for *program* without mutating it."""

    annotations = ExpressionContextAnnotations()
    pending = [("statement", stmt, "top") for stmt in reversed(getattr(program, "statements", ()))]
    visited = set()

    while pending:
        kind, node, context = pending.pop()
        if node is None:
            continue
        if isinstance(node, (ast.AstNode, list, tuple)):
            visit_key = (kind, id(node), context)
            if visit_key in visited:
                continue
            visited.add(visit_key)
        if kind == "statement":
            _push_statement_contexts(pending, annotations, node, context)
            continue
        if kind == "value":
            _push_value_contexts(pending, annotations, node, context)

    return annotations


def _push_statement_contexts(pending, annotations, node, context):
    if isinstance(node, ast.Expression):
        pending.append(("value", node, _statement_expression_context(context)))
        return
    if isinstance(node, ast.LayerAssignment):
        pending.append(("value", node.expression, _statement_expression_context(context)))
        return
    if isinstance(node, ast.VariableDef):
        pending.append(("value", node.values, SCALAR_EXPRESSION))
        return
    if isinstance(node, ast.Directive):
        pending.append(("value", node.arguments, DIRECTIVE_ARGUMENT))
        if node.property_block is not None:
            pending.append(("statement", node.property_block, PROPERTY_EXPRESSION))
        return
    if isinstance(node, ast.RuleCheckBlock):
        for stmt in reversed(node.body):
            pending.append(("statement", stmt, RULE_BODY_OPERATION))
        pending.append(("value", node.comments, DIRECTIVE_ARGUMENT))
        return
    if isinstance(node, ast.PropertyBlock):
        for stmt in reversed(node.body):
            pending.append(("statement", stmt, PROPERTY_EXPRESSION))
        return
    if isinstance(node, ast.DMacro):
        for stmt in reversed(node.body):
            pending.append(("statement", stmt, RULE_BODY_OPERATION))
        return
    if isinstance(node, ast.IfDef):
        for stmt in reversed(node.else_body):
            pending.append(("statement", stmt, context))
        for stmt in reversed(node.then_body):
            pending.append(("statement", stmt, context))
        pending.append(("value", node.value, DIRECTIVE_ARGUMENT))
        return
    if isinstance(node, ast.IfExpr):
        pending.append(("value", node.condition, SCALAR_EXPRESSION))
        for stmt in reversed(node.else_body):
            pending.append(("statement", stmt, context))
        for branch in reversed(node.elseifs):
            if isinstance(branch, tuple) and len(branch) == 2:
                condition, body = branch
                pending.append(("value", condition, SCALAR_EXPRESSION))
                for stmt in reversed(body):
                    pending.append(("statement", stmt, context))
            else:
                pending.append(("value", branch, context))
        for stmt in reversed(node.then_body):
            pending.append(("statement", stmt, context))
        return
    _push_node_field_contexts(pending, node, context)


def _push_value_contexts(pending, annotations, value, context):
    if isinstance(value, ast.Expression):
        annotations.add(value, context)
    if isinstance(value, ast.LayerRef):
        return
    if isinstance(value, ast.NumberLiteral):
        return
    if isinstance(value, ast.StringLiteral):
        return
    if isinstance(value, ast.VarRef):
        annotations.add(value, context)
        return
    if isinstance(value, ast.BinaryOp):
        child_context = SCALAR_EXPRESSION if value.op in {"+", "-", "*", "/", "%", "?:", ":"} else context
        pending.append(("value", value.right, child_context))
        pending.append(("value", value.left, child_context))
        return
    if isinstance(value, ast.UnaryOp):
        child_context = SCALAR_EXPRESSION if value.op in {"+", "-", "~"} else context
        pending.append(("value", value.operand, child_context))
        return
    if isinstance(value, ast.Constraint):
        pending.append(("value", value.value, SCALAR_EXPRESSION))
        return
    if isinstance(value, ast.ConstrainedExpr):
        for modifier in reversed(value.modifiers):
            pending.append(("value", modifier, context))
        for constraint in reversed(value.constraints):
            pending.append(("value", constraint, SCALAR_EXPRESSION))
        pending.append(("value", value.expr, context))
        return
    if isinstance(value, ast.DRCOp):
        for modifier in reversed(value.modifiers):
            pending.append(("value", modifier, context))
        for constraint in reversed(value.constraints):
            pending.append(("value", constraint, SCALAR_EXPRESSION))
        for operand in reversed(value.operands):
            pending.append(("value", operand, context))
        return
    if isinstance(value, ast.FuncCall):
        for arg in reversed(value.args):
            pending.append(("value", arg, context))
        return
    if isinstance(value, ast.Expression):
        _push_node_field_contexts(pending, value, context)
        return
    if isinstance(value, ast.AstNode):
        _push_statement_contexts(pending, annotations, value, context)
        return
    if isinstance(value, list):
        for item in reversed(value):
            pending.append(("value", item, context))
        return
    if isinstance(value, tuple):
        if len(value) == 2 and isinstance(value[0], str):
            tuple_context = SCALAR_EXPRESSION if str(value[0]).upper() in {"BY", "LENGTH", "WIDTH"} else context
            pending.append(("value", value[1], tuple_context))
            return
        for item in reversed(value):
            pending.append(("value", item, context))


def _push_node_field_contexts(pending, node, context):
    for _, child in reversed(list(node.iter_fields(include_position=False))):
        pending.append(("value", child, context))


def _statement_expression_context(context):
    if context == PROPERTY_EXPRESSION:
        return PROPERTY_EXPRESSION
    if context == RULE_BODY_OPERATION:
        return RULE_BODY_OPERATION
    return LAYER_EXPRESSION
