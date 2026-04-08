"""Normalize clause-level CST into canonical AST nodes."""

from __future__ import annotations

from . import ast
from .clause_cst import (
    DelimitedGroupClause,
    KeywordRunClause,
    ModifierClause,
    OpaqueEmbeddedLanguageChunk,
    OperandClause,
    ScalarClause,
    StatementClauseCst,
)


def normalize_statement_clause_cst(clause_cst: StatementClauseCst):
    parse_kind = clause_cst.parse_kind
    if parse_kind == "directive":
        return _normalize_directive(clause_cst)
    if parse_kind == "group":
        return _normalize_group(clause_cst)
    if parse_kind in {"connect", "sconnect"}:
        return _normalize_connect(clause_cst)
    if parse_kind == "include":
        return _normalize_include(clause_cst)
    if parse_kind == "attach":
        return _normalize_attach(clause_cst)
    if parse_kind == "device":
        return _normalize_device(clause_cst)
    if parse_kind == "macro_call":
        return _normalize_macro_call(clause_cst)
    if parse_kind == "property_block":
        return _normalize_property_block(clause_cst)
    if parse_kind == "rule_check":
        return _normalize_rule_check(clause_cst)
    raise ValueError(f"Unsupported clause CST parse_kind for normalization: {parse_kind}")


def normalize_rule_check_clause_shell(clause_cst: StatementClauseCst, *, comments, body, location=None):
    """Normalize a rule-check wrapper while a statement subparser supplies the body."""
    location = location or {}
    return ast.RuleCheckBlock(
        name=rule_check_name_from_clause_cst(clause_cst),
        comments=comments,
        body=body,
        **location,
    )


def normalize_property_block_clause_shell(clause_cst: StatementClauseCst, *, body, location=None):
    """Normalize a property-block wrapper while a statement subparser supplies the body."""
    location = location or {}
    return ast.PropertyBlock(
        properties=property_names_from_clause_cst(clause_cst),
        body=body,
        **location,
    )


def rule_check_name_from_clause_cst(clause_cst: StatementClauseCst):
    for clause in clause_cst.header_clauses:
        if isinstance(clause, OperandClause) and clause.values:
            return str(clause.values[0])
    return ""


def property_names_from_clause_cst(clause_cst: StatementClauseCst):
    properties = []
    for clause in clause_cst.header_clauses[1:]:
        values = getattr(clause, "values", ())
        if values:
            properties.append(str(values[0]))
    return properties


def _header_words(clause_cst):
    for clause in clause_cst.header_clauses:
        if isinstance(clause, KeywordRunClause):
            return clause.words
    return ()


def _normalize_directive(clause_cst):
    arguments = []
    for clause in clause_cst.body_clauses:
        arguments.extend(_normalize_directive_clause_values(clause))
    return ast.Directive(
        keywords=list(_header_words(clause_cst)),
        arguments=arguments,
        property_block=None,
    )


def _normalize_group(clause_cst):
    clause = clause_cst.body_clauses[0] if clause_cst.body_clauses else None
    values = list(getattr(clause, "values", ()))
    if not values:
        return ast.Group(name="", members=[])
    return ast.Group(name=str(values[0]), members=[str(value) for value in values[1:]])


def _normalize_connect(clause_cst):
    soft = clause_cst.parse_kind == "sconnect"
    layers = []
    via_layer = None
    link_name = None
    abut_also = False
    for clause in clause_cst.body_clauses:
        values = tuple(getattr(clause, "values", ()))
        if isinstance(clause, OperandClause):
            layers.extend(str(value) for value in values)
        elif isinstance(clause, ModifierClause):
            if values[:1] == ("BY",) and len(values) > 1:
                via_layer = str(values[1])
            elif values[:1] == ("LINK",) and len(values) > 1:
                link_name = str(values[1])
            elif values[:2] == ("ABUT", "ALSO"):
                abut_also = True
    return ast.Connect(
        soft=soft,
        layers=layers,
        via_layer=via_layer,
        link_name=link_name,
        abut_also=abut_also,
    )


def _normalize_include(clause_cst):
    path = ""
    for clause in clause_cst.body_clauses:
        values = tuple(getattr(clause, "values", ()))
        if values:
            path = str(values[0])
            break
    return ast.Include(path=path, embedded=False, preprocessor=False)


def _normalize_attach(clause_cst):
    values = []
    for clause in clause_cst.body_clauses:
        values.extend(getattr(clause, "values", ()))
    layer = str(values[0]) if values else ""
    net = str(values[1]) if len(values) > 1 else ""
    return ast.Attach(layer=layer, net=net)


def _normalize_device(clause_cst):
    operands = []
    modifiers = []
    for clause in clause_cst.body_clauses:
        values = tuple(getattr(clause, "values", ()))
        if isinstance(clause, OperandClause):
            operands.extend(values)
        elif isinstance(clause, ModifierClause):
            modifiers.append(values)

    device_name = str(operands[0]) if operands else None
    seed_layer = str(operands[1]) if len(operands) > 1 else ""
    pins = [(str(value), None) for value in operands[2:]]
    aux_layers = []
    cmacro = None
    cmacro_args = []
    for modifier in modifiers:
        if modifier[:1] == ("CMACRO",) and len(modifier) > 1 and cmacro is None:
            cmacro = str(modifier[1])
            continue
        cmacro_args.extend(str(value) for value in modifier)
    return ast.Device(
        device_type=None,
        device_name=device_name,
        seed_layer=seed_layer,
        pins=pins,
        aux_layers=aux_layers,
        cmacro=cmacro,
        cmacro_args=cmacro_args,
    )


def _normalize_macro_call(clause_cst):
    kind = _header_words(clause_cst)[0] if _header_words(clause_cst) else "CMACRO"
    values = []
    for clause in clause_cst.body_clauses:
        values.extend(getattr(clause, "values", ()))
    name = str(values[0]) if values else ""
    arguments = [_value_to_ast(value) for value in values[1:]]
    return ast.MacroCall(kind=kind, name=name, arguments=arguments)


def _normalize_property_block(clause_cst):
    body = []
    for clause in clause_cst.body_clauses:
        if isinstance(clause, DelimitedGroupClause):
            body.extend(_normalize_simple_body_group(clause))
    return ast.PropertyBlock(properties=property_names_from_clause_cst(clause_cst), body=body)


def _normalize_rule_check(clause_cst):
    comments = []
    body = []
    for clause in clause_cst.body_clauses:
        if not isinstance(clause, DelimitedGroupClause):
            continue
        inner = list(clause.clauses)
        if inner and isinstance(inner[0], OpaqueEmbeddedLanguageChunk) and inner[0].reason == "comment":
            comments.append([str(value) for value in inner[0].values])
            inner = inner[1:]
        body.extend(_normalize_simple_rule_body(inner))
    return ast.RuleCheckBlock(
        name=rule_check_name_from_clause_cst(clause_cst),
        comments=comments or None,
        body=body,
    )


def _normalize_simple_body_group(group_clause):
    clauses = list(group_clause.clauses)
    if len(clauses) == 2 and isinstance(clauses[0], OperandClause) and isinstance(clauses[1], ScalarClause):
        values = clauses[0].values
        if len(values) >= 2 and values[1] == "=":
            return [
                ast.LayerAssignment(
                    name=str(values[0]),
                    expression=_scalar_clause_to_expr(clauses[1]),
                )
            ]
    return []


def _normalize_simple_rule_body(clauses):
    if len(clauses) == 2 and isinstance(clauses[0], OperandClause) and isinstance(clauses[1], ScalarClause):
        values = clauses[0].values
        if len(values) >= 3 and values[2] in {"<", "<=", ">", ">=", "==", "!="}:
            return [
                ast.DRCOp(
                    op=str(values[0]),
                    operands=[ast.LayerRef(name=str(values[1]))],
                    constraints=[
                        ast.Constraint(
                            op=str(values[2]),
                            value=_scalar_clause_to_expr(clauses[1]),
                        )
                    ],
                    modifiers=[],
                )
            ]
    return []


def _normalize_clause_values(clause):
    if isinstance(clause, ScalarClause):
        return [_value_to_ast(value) for value in clause.values]
    if isinstance(clause, (OperandClause, ModifierClause, OpaqueEmbeddedLanguageChunk)):
        return [str(value) for value in clause.values]
    if isinstance(clause, DelimitedGroupClause):
        return [str(clause.open_symbol), str(clause.close_symbol or "")]
    return []


def _normalize_directive_clause_values(clause):
    if isinstance(clause, ScalarClause):
        return list(clause.values)
    if isinstance(clause, DelimitedGroupClause):
        return [_render_delimited_group(clause)]
    if isinstance(clause, (OperandClause, ModifierClause, OpaqueEmbeddedLanguageChunk)):
        return [str(value) for value in clause.values]
    return []


def _render_delimited_group(clause):
    parts = []
    for child in clause.clauses:
        if isinstance(child, DelimitedGroupClause):
            parts.append(_render_delimited_group(child))
        elif isinstance(child, ScalarClause):
            parts.extend(str(value) for value in child.values)
        else:
            parts.extend(str(value) for value in getattr(child, "values", ()))
    close = clause.close_symbol or ""
    if not parts:
        return f"{clause.open_symbol}{close}"
    return f"{clause.open_symbol} {' '.join(parts)} {close}".rstrip()


def _scalar_clause_to_expr(clause):
    values = list(clause.values)
    if len(values) == 1:
        return _value_to_ast(values[0])
    return ast.StringLiteral(value=" ".join(str(value) for value in values))


def _value_to_ast(value):
    if isinstance(value, (int, float)):
        return ast.NumberLiteral(value=value)
    return ast.StringLiteral(value=str(value)) if _should_be_string_literal(value) else ast.LayerRef(name=str(value))


def _should_be_string_literal(value):
    return not isinstance(value, str) or any(ch in str(value) for ch in (" ", "/", "\\", "."))
