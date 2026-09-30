"""Node-dispatch stage for semantic validation."""

from __future__ import annotations

from . import ast
from .semantic_directives import _DIRECTIVE_ALLOWED_ARGUMENT_COUNTS, _DIRECTIVE_MIN_ARGUMENTS
from .semantic_drc_rules import (
    DRCOP_MIN_CONSTRAINTS,
    DRCOP_MIN_MODIFIERS,
    DRCOP_MIN_OPERANDS,
    WITH_OPS,
)
from .semantic_symbols import (
    _collect_dfm_text_placeholders,
    _collect_property_function_source_placeholders,
    _collect_property_modifier_placeholders,
    _collect_statement_placeholders,
    _directive_argument_skip_indexes,
    _normalized_scope_name,
    _PROPERTY_BLOCK_IMPLICIT_TERMINALS,
)


def validate_semantic_node(validator, node, scope, pending):
    """Validate one AST node by dispatching to the appropriate semantic rule."""

    if not isinstance(node, ast.AstNode):
        return

    if isinstance(node, ast.ErrorNode):
        validator.error(
            "semantic.error_node",
            node.message or "Recovered parser error",
            node,
        )
        return

    if isinstance(node, ast.Define):
        if not node.name:
            validator.error("semantic.define.missing_name", "Missing #DEFINE name", node)
        else:
            scope.define_preprocessor(node.name)
        validator._validate_value(node.value, scope)
        return

    if isinstance(node, ast.IfDef):
        if not node.name:
            validator.error(
                "semantic.ifdef.missing_name",
                "Missing preprocessor symbol name",
                node,
            )
        then_scope = scope.child((id(node), True))
        else_scope = scope.child((id(node), False))
        for name in _collect_statement_placeholders(node.then_body, include_conditionals=False):
            then_scope.define_placeholder(name)
        for name in _collect_statement_placeholders(node.else_body, include_conditionals=False):
            else_scope.define_placeholder(name)
        pending.append(("merge_branches", (scope, (then_scope, else_scope))))
        validator._push_statement_tasks(pending, node.else_body, else_scope)
        validator._push_statement_tasks(pending, node.then_body, then_scope)
        return

    if isinstance(node, ast.Include):
        if not node.path:
            validator.error("semantic.include.empty_path", "INCLUDE path is empty", node)
        return

    if isinstance(node, ast.EncryptedBlock):
        if node.body:
            validator._push_statement_tasks(pending, node.body, scope)
        return

    if isinstance(node, ast.DfmSpec):
        scope.define_placeholder(node.name)
        validator._validate_value(node.arguments, scope)
        validator._push_statement_tasks(pending, node.body, scope)
        return

    if isinstance(node, ast.PercLoad):
        validator._push_statement_tasks(pending, node.body, scope)
        return

    if isinstance(node, ast.DfmClause):
        validator._validate_value(node.arguments, scope)
        return

    if isinstance(node, ast.Directive):
        keyword_tuple = tuple(node.keywords)
        min_args = _DIRECTIVE_MIN_ARGUMENTS.get(keyword_tuple)
        if min_args is not None and len(node.arguments) < min_args:
            joined = " ".join(node.keywords)
            validator.error(
                "semantic.directive.missing_argument",
                f"Directive {joined} requires at least {min_args} argument(s)",
                node,
            )
        else:
            allowed_counts = _DIRECTIVE_ALLOWED_ARGUMENT_COUNTS.get(keyword_tuple)
            if allowed_counts is not None and len(node.arguments) not in allowed_counts:
                joined = " ".join(node.keywords)
                counts = ", ".join(str(count) for count in sorted(allowed_counts))
                validator.error(
                    "semantic.directive.argument_shape",
                    f"Directive {joined} expects argument count(s): {counts}",
                    node,
                )
        for index, argument in enumerate(node.arguments):
            if index in _directive_argument_skip_indexes(node):
                continue
            validator._validate_value(argument, scope)
        validator._validate_directive_arguments(node, scope)
        if keyword_tuple == ("LVS", "GROUND", "NAME"):
            scope.define_placeholder("LVS_GROUND_NAME")
        elif keyword_tuple == ("LVS", "POWER", "NAME"):
            scope.define_placeholder("LVS_POWER_NAME")
        if node.property_block is not None:
            validator._validate_value(node.property_block, scope.child())
        return

    if isinstance(node, ast.LayerDef):
        scope.define_layer(node.name)
        return

    if isinstance(node, ast.LayerAssignment):
        if node.expression is None:
            validator.error(
                "semantic.assignment.empty_expression",
                f"Assignment {node.name} has no expression",
                node,
            )
        else:
            validator._validate_value(node.expression, scope)
        scope.define_layer(node.name)
        return

    if isinstance(node, ast.VariableDef):
        for value in node.values:
            if not isinstance(value, ast.StringLiteral):
                validator._validate_value(value, scope)
        scope.define_variable(node.name)
        return

    if isinstance(node, ast.Group):
        if not node.members:
            validator.error(
                "semantic.group.empty",
                f"GROUP {node.name} has no members",
                node,
            )
        scope.define_group(node.name)
        validator._validate_value(node.members, scope)
        return

    if isinstance(node, ast.RuleCheckBlock):
        if not node.body:
            validator.warning(
                "semantic.rule.empty_body",
                f"Rule check {node.name} has an empty body",
                node,
            )
        elif not _rule_may_produce_output(node.body):
            validator.error(
                "semantic.rule.missing_output",
                f"Rule check {node.name} has no standalone result-producing layer operation",
                node,
            )
        scope.define_rule(node.name)
        rule_scope = scope.child()
        for name in _collect_statement_placeholders(node.body, include_conditionals=False):
            rule_scope.define_placeholder(name)
        validator._validate_value(node.comments, rule_scope)
        validator._push_statement_tasks(pending, node.body, rule_scope)
        return

    if isinstance(node, ast.Connect):
        if not node.layers:
            validator.error(
                "semantic.connect.too_few_layers",
                "CONNECT/SCONNECT requires at least one layer",
                node,
            )
        if node.soft:
            if len(node.layers) < 2:
                validator.error(
                    "semantic.connect.too_few_layers",
                    "SCONNECT requires an upper layer and at least one lower layer",
                    node,
                )
            if node.via_layer:
                if len(node.layers) > 33:
                    validator.error(
                        "semantic.connect.too_many_lower_layers",
                        "SCONNECT BY permits at most 32 lower layers",
                        node,
                    )
                if node.abut_also:
                    validator.error(
                        "semantic.connect.invalid_abut",
                        "SCONNECT ABUT ALSO cannot be combined with BY",
                        node,
                    )
            elif len(node.layers) > 2:
                validator.error(
                    "semantic.connect.invalid_layer_count",
                    "SCONNECT without BY requires exactly one upper and one lower layer",
                    node,
                )
        for layer_name in node.layers:
            validator._warn_unknown_layer(
                "semantic.connect.unknown_layer",
                layer_name,
                node,
                scope,
            )
        if node.via_layer:
            validator._warn_unknown_layer(
                "semantic.connect.unknown_via",
                node.via_layer,
                node,
                scope,
            )
        return

    if isinstance(node, ast.Attach):
        if not node.layer:
            validator.error(
                "semantic.attach.missing_layer",
                "ATTACH statement is missing a layer",
                node,
            )
        if not node.net:
            validator.error(
                "semantic.attach.missing_net",
                "ATTACH statement is missing a net",
                node,
            )
        return

    if isinstance(node, ast.TraceProperty):
        if not node.device:
            validator.error(
                "semantic.trace_property.missing_device",
                "TRACE PROPERTY statement is missing a device name",
                node,
            )
        if not node.args:
            validator.error(
                "semantic.trace_property.missing_args",
                "TRACE PROPERTY statement has no arguments",
                node,
            )
        validator._validate_value(node.args, scope)
        return

    if isinstance(node, ast.Device):
        if (
            node.device_name == "LAYER"
            and not node.seed_layer
            and not node.aux_layers
            and not node.pins
            and node.cmacro is None
        ):
            validator.error(
                "semantic.device_layer.missing_modifier",
                "DEVICE LAYER requires at least one layer or modifier argument",
                node,
            )
            return
        if not node.seed_layer:
            validator.error(
                "semantic.device.missing_seed",
                "DEVICE statement is missing a seed layer",
                node,
            )
        else:
            validator._warn_unknown_layer(
                "semantic.device.unknown_seed_layer",
                node.seed_layer,
                node,
                scope,
            )
        cmacro_arg_names = {
            _normalized_scope_name(argument)
            for argument in node.cmacro_args
            if isinstance(argument, str)
        }
        for aux in node.aux_layers:
            if isinstance(aux, str) and not aux.startswith("["):
                if _normalized_scope_name(aux) in cmacro_arg_names:
                    continue
                validator._warn_unknown_layer(
                    "semantic.device.unknown_aux_layer",
                    aux,
                    node,
                    scope,
                )
            else:
                validator._validate_value(aux, scope)
        if not node.pins and node.cmacro is None:
            validator.warning(
                "semantic.device.no_pins",
                "DEVICE statement has no parsed pins",
                node,
            )
        if node.cmacro:
            validator._validate_macro_reference(node.cmacro, node, scope, device=True)
        return

    if isinstance(node, ast.DMacro):
        scope.define_macro(node.name)
        body_scope = scope.child()
        # Macro bodies are expanded at invocation, not at their declaration.
        body_scope.defer_variable_order = True
        for param in node.params:
            body_scope.define_placeholder(param)
        for name in _collect_statement_placeholders(node.body, include_conditionals=False):
            body_scope.define_placeholder(name)
        validator._push_statement_tasks(pending, node.body, body_scope)
        return

    if isinstance(node, ast.MacroCall):
        validator._validate_macro_reference(node.name, node, scope)
        return

    if isinstance(node, ast.PropertyBlock):
        property_scope = scope.child()
        for name in node.properties:
            property_scope.define_placeholder(name)
        for name in _collect_statement_placeholders(node.body, include_conditionals=False):
            property_scope.define_placeholder(name)
        for name in _PROPERTY_BLOCK_IMPLICIT_TERMINALS:
            property_scope.define_placeholder(name)
        validator._push_statement_tasks(pending, node.body, property_scope)
        return

    if isinstance(node, ast.IfExpr):
        validator._validate_if_expr(node, scope, pending)
        return

    if isinstance(node, ast.DRCOp):
        if (
            node.op in WITH_OPS
            and not node.operands
            and not node.constraints
            and not node.modifiers
        ):
            validator.error(
                "semantic.drc.with_empty",
                f"{node.op} requires an operand, constraint, or modifier",
                node,
            )
        if node.op == "WITH TEXT" and not node.operands:
            validator.error(
                "semantic.drc.with_text.missing_filter",
                "WITH TEXT requires a text filter operand",
                node,
            )
        min_operands = DRCOP_MIN_OPERANDS.get(node.op)
        if min_operands is not None and len(node.operands) < min_operands:
            validator.error(
                "semantic.drc.missing_operand",
                f"{node.op} requires at least {min_operands} operand(s)",
                node,
            )
        min_constraints = DRCOP_MIN_CONSTRAINTS.get(node.op)
        if min_constraints is not None and len(node.constraints) < min_constraints:
            validator.error(
                "semantic.drc.missing_constraint",
                f"{node.op} requires at least {min_constraints} constraint(s)",
                node,
            )
        if node.op == "DEVICE LAYER" and not node.operands and not node.modifiers:
            validator.error(
                "semantic.device_layer.missing_modifier",
                "DEVICE LAYER requires at least one layer or modifier argument",
                node,
            )
        min_modifiers = DRCOP_MIN_MODIFIERS.get(node.op)
        if (
            min_modifiers is not None
            and len(node.modifiers) < min_modifiers
            and not (node.op == "DEVICE LAYER" and not node.operands and not node.modifiers)
        ):
            validator.error(
                "semantic.drc.missing_modifier",
                f"{node.op} requires at least {min_modifiers} modifier(s)",
                node,
            )
        op_scope = scope
        if node.op in {"DFM PROPERTY", "DFM PROPERTY NET", "DFM TEXT"}:
            op_scope = scope.child()
        if node.op in {"DFM PROPERTY", "DFM PROPERTY NET"}:
            for name in _collect_property_modifier_placeholders(node.modifiers):
                op_scope.define_placeholder(name)
            for name in _collect_property_function_source_placeholders(
                [node.constraints, node.modifiers]
            ):
                op_scope.define_placeholder(name)
        if node.op == "DFM TEXT":
            for name in _collect_dfm_text_placeholders(node.operands):
                op_scope.define_placeholder(name)
        validator._validate_value(node.operands, op_scope)
        validator._validate_value(node.constraints, op_scope)
        validator._validate_value(list(node.modifier_nodes), op_scope)
        return

    if isinstance(node, ast.LayerRef):
        validator._warn_unknown_reference(
            "semantic.reference.undefined",
            node.name,
            node,
            scope,
        )
        return

    if isinstance(node, ast.VarRef):
        if not scope.knows_variable(node.name) and not validator._warn_conditional_symbol(
            ("variables",), node.name, node, scope, context="scalar",
        ):
            validator.warning(
                "semantic.varref.undefined",
                f"Description variable reference ^{node.name} has no matching VARIABLE",
                node,
                metadata={"symbol": node.name},
            )
        return

    for _, value in node.iter_fields(include_position=False):
        validator._validate_value(value, scope)


def _rule_may_produce_output(statements):
    pending = list(statements)
    while pending:
        statement = pending.pop()
        if isinstance(statement, (ast.Expression, ast.MacroCall)):
            return True
        if isinstance(statement, ast.IfDef):
            pending.extend(statement.then_body)
            pending.extend(statement.else_body)
        elif isinstance(statement, ast.IfExpr):
            pending.extend(statement.then_body)
            pending.extend(statement.else_body)
            for _, body in statement.elseifs:
                pending.extend(body)
        elif isinstance(statement, ast.EncryptedBlock):
            if statement.parse_status == "opaque":
                return True
            pending.extend(statement.body)
    return False
