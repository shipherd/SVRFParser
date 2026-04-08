"""Symbol-table and reference helper utilities for semantic validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import ast
from .diagnostics import Diagnostic, SEVERITY_ERROR
from .keywords import _DIRECTIVE_HEADS, _DRC_MODIFIERS, _SVRF_KEYWORDS
from .symbol_convention import SYMBOL_CONVENTION_REGISTRY

_SCALAR_TUPLE_HEADS = SYMBOL_CONVENTION_REGISTRY.scalar_tuple_heads
_SEMANTIC_REFERENCE_SKIP_NAMES = frozenset(
    {
        "ALL",
        "ANCHOR",
        "ANGLED",
        "BAD",
        "BOTTOM",
        "CENTERLINE",
        "CHECKNAME",
        "CELLS",
        "CLUSTER",
        "COMMENT",
        "DIRECTIONAL",
        "DV",
        "DVPARAMS",
        "ENDPOINT",
        "EVEN",
        "FACTOR",
        "FACE",
        "FILE",
        "GLOBALXY",
        "GOOD",
        "HORIZONTAL",
        "IN",
        "INVALID",
        "LABELED",
        "LEFT",
        "LOOP",
        "MAP",
        "MAXIMUM",
        "MEDIUM",
        "MASK0",
        "MASK1",
        "MULTI",
        "NEG",
        "NOFACE",
        "NODAL",
        "NOEMPTY",
        "NOPSEUDO",
        "NUMBER",
        "ODD",
        "OVER",
        "OVERLAP",
        "OUT",
        "POS",
        "RIGHT",
        "SKEW",
        "SQUARES",
        "SPACE",
        "SYNC",
        "SYNCID",
        "TIE",
        "TOP",
        "UNFILTERED",
        "GROUND",
        "POWER",
        "VERTICAL",
        "WELL",
    }
)
_SEMANTIC_PARAMETER_NAME_RE = re.compile(r"^(ANGLE|LENGTH|OPPOSITE)\d+$")
_PROPERTY_BLOCK_IMPLICIT_TERMINALS = frozenset({"B", "D", "G", "NEG", "POS", "S"})


def _node_diagnostic(severity, code, message, node, filename, metadata=None):
    return Diagnostic(
        severity=severity,
        code=code,
        message=message,
        filename=filename,
        line=getattr(node, "line", 0),
        col=getattr(node, "col", 0),
        end_line=getattr(node, "end_line", 0),
        end_col=getattr(node, "end_col", 0),
        start_offset=getattr(node, "start_offset", 0),
        end_offset=getattr(node, "end_offset", 0),
        snippet=getattr(node, "source_text", None),
        metadata=metadata,
    )


def _coerce_argument_text(argument):
    if isinstance(argument, ast.StringLiteral):
        return argument.value
    if isinstance(argument, ast.NumberLiteral):
        return str(argument.value)
    if isinstance(argument, (int, float)):
        return str(argument)
    if isinstance(argument, ast.LayerRef):
        return argument.name
    if isinstance(argument, str):
        return argument
    return None


def _coerce_argument_number(argument):
    if isinstance(argument, ast.NumberLiteral):
        return argument.value
    if isinstance(argument, (int, float)):
        return argument
    text = _coerce_argument_text(argument)
    if text is None:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _normalized_directive_tail(node, prefix_len):
    normalized = [str(part).upper() for part in node.keywords[prefix_len:]]
    for argument in node.arguments:
        text = _coerce_argument_text(argument)
        if text is None:
            return None
        normalized.append(str(text).upper())
    return normalized


@dataclass
class SymbolTable:
    layers: dict = field(default_factory=dict)
    variables: dict = field(default_factory=dict)
    macros: dict = field(default_factory=dict)
    groups: dict = field(default_factory=dict)
    rules: dict = field(default_factory=dict)
    preprocessor: dict = field(default_factory=dict)
    conditional_layers: set = field(default_factory=set)
    conditional_variables: set = field(default_factory=set)
    conditional_macros: set = field(default_factory=set)
    conditional_groups: set = field(default_factory=set)
    conditional_rules: set = field(default_factory=set)
    conditional_preprocessor: set = field(default_factory=set)
    local_only_references: set = field(default_factory=set)

    @property
    def layer_like_names(self):
        return (
            set(self.layers)
            | set(self.groups)
            | set(self.conditional_layers)
            | set(self.conditional_groups)
        )

    def knows_layer_like(self, name):
        return (
            name in self.layers
            or name in self.groups
            or name in self.conditional_layers
            or name in self.conditional_groups
        )

    def knows_macro(self, name):
        return name in self.macros or name in self.conditional_macros

    def knows_variable(self, name):
        return name in self.variables or name in self.conditional_variables

    def knows_preprocessor(self, name):
        return name in self.preprocessor or name in self.conditional_preprocessor

    def knows_reference(self, name):
        return self.knows_layer_like(name) or self.knows_variable(name)


@dataclass
class ValidationScope:
    parent: "ValidationScope | None" = None
    layers: set = field(default_factory=set)
    variables: set = field(default_factory=set)
    macros: set = field(default_factory=set)
    groups: set = field(default_factory=set)
    rules: set = field(default_factory=set)
    preprocessor: set = field(default_factory=set)

    @classmethod
    def from_symbol_table(cls, symbol_table):
        return cls(
            layers=set(symbol_table.layers) | set(symbol_table.conditional_layers),
            variables=set(symbol_table.variables)
            | set(symbol_table.conditional_variables),
            macros=set(symbol_table.macros) | set(symbol_table.conditional_macros),
            groups=set(symbol_table.groups) | set(symbol_table.conditional_groups),
            rules=set(symbol_table.rules) | set(symbol_table.conditional_rules),
            preprocessor=set(symbol_table.preprocessor)
            | set(symbol_table.conditional_preprocessor),
        )

    def child(self):
        return ValidationScope(parent=self)

    def merge_from(self, other):
        self.layers.update(other.layers)
        self.variables.update(other.variables)
        self.macros.update(other.macros)
        self.groups.update(other.groups)
        self.rules.update(other.rules)
        self.preprocessor.update(other.preprocessor)

    def define_layer(self, name):
        if name:
            self.layers.add(name)

    def define_variable(self, name):
        if name:
            self.variables.add(name)

    def define_macro(self, name):
        if name:
            self.macros.add(name)

    def define_group(self, name):
        if name:
            self.groups.add(name)

    def define_rule(self, name):
        if name:
            self.rules.add(name)

    def define_preprocessor(self, name):
        if name:
            self.preprocessor.add(name)

    def define_placeholder(self, name):
        if not name:
            return
        self.layers.add(name)
        self.variables.add(name)

    def knows_layer_like(self, name):
        scope = self
        while scope is not None:
            if name in scope.layers or name in scope.groups:
                return True
            scope = scope.parent
        return False

    def knows_macro(self, name):
        scope = self
        while scope is not None:
            if name in scope.macros:
                return True
            scope = scope.parent
        return False

    def knows_variable(self, name):
        scope = self
        while scope is not None:
            if name in scope.variables:
                return True
            scope = scope.parent
        return False

    def knows_preprocessor(self, name):
        scope = self
        while scope is not None:
            if name in scope.preprocessor:
                return True
            scope = scope.parent
        return False

    def knows_reference(self, name):
        return self.knows_layer_like(name) or self.knows_variable(name)


def _should_skip_symbol_name(name):
    if not name:
        return True
    if name.startswith("$"):
        return True
    if any(ch in name for ch in "*?[]\\/"):
        return True
    if ":" in name:
        return True
    return False


def _should_skip_expression_reference(name):
    if not name:
        return True
    if name.startswith("$"):
        return True
    upper_name = str(name).upper()
    if _SEMANTIC_PARAMETER_NAME_RE.match(upper_name):
        return True
    if upper_name in _SVRF_KEYWORDS or upper_name in _DIRECTIVE_HEADS or upper_name in _DRC_MODIFIERS:
        return True
    if upper_name in _SEMANTIC_REFERENCE_SKIP_NAMES:
        return True
    return _should_skip_symbol_name(name)


def _normalized_scope_name(name):
    if name is None:
        return None
    return str(name).upper()


def _collect_statement_placeholders(statements):
    names = set()
    pending = list(reversed(statements or []))
    while pending:
        current = pending.pop()
        if isinstance(current, ast.LayerAssignment):
            if current.name:
                names.add(current.name)
            continue
        if isinstance(current, ast.PropertyBlock):
            names.update(name for name in current.properties if name)
            pending.extend(reversed(current.body))
            continue
        if isinstance(current, ast.IfDef):
            pending.extend(reversed(current.else_body))
            pending.extend(reversed(current.then_body))
            continue
        if isinstance(current, ast.EncryptedBlock):
            pending.extend(reversed(current.body))
            continue
        if isinstance(current, ast.IfExpr):
            pending.extend(reversed(current.else_body))
            for branch in reversed(current.elseifs):
                if isinstance(branch, tuple) and len(branch) == 2:
                    _, body = branch
                    pending.extend(reversed(body))
            pending.extend(reversed(current.then_body))
    return names


def _collect_local_scope_reference_candidates(statements):
    names = set()
    pending = list(reversed(statements or []))
    while pending:
        current = pending.pop()
        if isinstance(current, tuple) and len(current) == 2 and isinstance(current[0], ast.AstNode):
            current = current[0]
        if isinstance(current, ast.RuleCheckBlock):
            names.update(_collect_statement_placeholders(current.body))
            pending.extend(reversed(current.body))
            continue
        if isinstance(current, ast.DMacro):
            names.update(name for name in current.params if name)
            names.update(_collect_statement_placeholders(current.body))
            pending.extend(reversed(current.body))
            continue
        if isinstance(current, ast.PropertyBlock):
            names.update(name for name in current.properties if name)
            names.update(_PROPERTY_BLOCK_IMPLICIT_TERMINALS)
            names.update(_collect_statement_placeholders(current.body))
            pending.extend(reversed(current.body))
            continue
        if isinstance(current, ast.IfDef):
            pending.extend(reversed(current.else_body))
            pending.extend(reversed(current.then_body))
            continue
        if isinstance(current, ast.EncryptedBlock):
            pending.extend(reversed(current.body))
            continue
        if isinstance(current, ast.IfExpr):
            pending.extend(reversed(current.else_body))
            for branch in reversed(current.elseifs):
                if isinstance(branch, tuple) and len(branch) == 2:
                    _, body = branch
                    pending.extend(reversed(body))
            pending.extend(reversed(current.then_body))
    return names


def _tuple_value_context(head, default):
    upper_head = str(head).upper()
    if upper_head == "BY" or upper_head.endswith(" BY") or upper_head in _SCALAR_TUPLE_HEADS:
        return "scalar"
    return default


def _collect_property_modifier_placeholders(modifiers):
    names = set()
    pending = list(reversed(modifiers or []))
    while pending:
        current = pending.pop()
        if isinstance(current, ast.ConstrainedExpr):
            pending.append(current.expr)
            pending.extend(reversed(current.constraints))
            pending.extend(reversed(current.modifiers))
            continue
        if isinstance(current, ast.BinaryOp):
            if current.op == "=" and isinstance(current.left, ast.LayerRef) and current.left.name:
                names.add(current.left.name)
            pending.append(current.right)
            pending.append(current.left)
            continue
        if isinstance(current, ast.UnaryOp):
            pending.append(current.operand)
            continue
        if isinstance(current, ast.FuncCall):
            pending.extend(reversed(current.args))
            continue
        if isinstance(current, (list, tuple)):
            pending.extend(reversed(current))
    return names


def _property_function_skipped_arg_indexes(node):
    name = (getattr(node, "name", "") or "").upper()
    if "PROPERTY" not in name:
        return ()
    if "PROPERTY_REF" in name or (name.startswith("SET_") and "PROPERTY" in name):
        return tuple(range(len(node.args)))
    return tuple(range(1, len(node.args)))


def _collect_property_function_source_placeholders(values):
    names = set()
    pending = [values]
    while pending:
        current = pending.pop()
        if isinstance(current, ast.FuncCall):
            name = (current.name or "").upper()
            if "PROPERTY" in name and "PROPERTY_REF" not in name and current.args:
                source = current.args[0]
                if isinstance(source, ast.LayerRef) and source.name:
                    names.add(source.name)
            pending.extend(reversed(current.args))
            continue
        if isinstance(current, ast.ConstrainedExpr):
            pending.append(current.expr)
            pending.extend(reversed(current.constraints))
            pending.extend(reversed(current.modifiers))
            continue
        if isinstance(current, ast.BinaryOp):
            pending.append(current.right)
            pending.append(current.left)
            continue
        if isinstance(current, ast.UnaryOp):
            pending.append(current.operand)
            continue
        if isinstance(current, (list, tuple)):
            pending.extend(reversed(current))
    return names


def _collect_dfm_text_placeholders(operands):
    names = set()
    for index, operand in enumerate(operands[:-1]):
        if not isinstance(operand, ast.LayerRef) or operand.name != "NUMBER":
            continue
        candidate = operands[index + 1]
        if isinstance(candidate, ast.LayerRef) and candidate.name:
            names.add(candidate.name)
    return names


def _directive_argument_skip_indexes(node):
    keywords = tuple(node.keywords)
    if keywords in {("LVS", "FILTER"), ("LVS", "REDUCE")}:
        return {1}
    return set()


def build_symbol_table(statements, filename="<input>", strict=False):
    """Build a top-level symbol table from an ordered statement stream."""

    table = SymbolTable()
    diagnostics = []

    def add_symbol(kind, name, stmt, stmt_filename, conditional=False):
        if not name:
            return
        if kind == "layer":
            bucket = table.layers
            conditional_bucket = table.conditional_layers
        elif kind == "variable":
            bucket = table.variables
            conditional_bucket = table.conditional_variables
        elif kind == "macro":
            bucket = table.macros
            conditional_bucket = table.conditional_macros
        elif kind == "group":
            bucket = table.groups
            conditional_bucket = table.conditional_groups
        elif kind == "rule":
            bucket = table.rules
            conditional_bucket = table.conditional_rules
        else:
            bucket = table.preprocessor
            conditional_bucket = table.conditional_preprocessor

        if conditional:
            if name not in bucket:
                conditional_bucket.add(name)
            return

        previous = bucket.get(name)
        if previous is not None:
            diagnostics.append(
                _node_diagnostic(
                    SEVERITY_ERROR,
                    f"semantic.duplicate_{kind}",
                    f"Duplicate {kind} definition for {name}",
                    stmt,
                    stmt_filename,
                )
            )
            return
        bucket[name] = stmt

    def visit_statements(stream, default_filename, conditional=False):
        pending = []

        def push_stream(items, item_filename, item_conditional):
            for entry in reversed(list(items)):
                pending.append((entry, item_filename, item_conditional))

        push_stream(stream, default_filename, conditional)
        while pending:
            item, item_default_filename, item_conditional = pending.pop()
            if isinstance(item, tuple):
                stmt, stmt_filename = item
            else:
                stmt, stmt_filename = item, item_default_filename

            if isinstance(stmt, (ast.LayerDef, ast.LayerAssignment)):
                add_symbol("layer", stmt.name, stmt, stmt_filename, conditional=item_conditional)
            elif isinstance(stmt, ast.VariableDef):
                add_symbol("variable", stmt.name, stmt, stmt_filename, conditional=item_conditional)
            elif isinstance(stmt, ast.DMacro):
                add_symbol("macro", stmt.name, stmt, stmt_filename, conditional=item_conditional)
            elif isinstance(stmt, ast.Group):
                add_symbol("group", stmt.name, stmt, stmt_filename, conditional=item_conditional)
            elif isinstance(stmt, ast.RuleCheckBlock):
                add_symbol("rule", stmt.name, stmt, stmt_filename, conditional=item_conditional)
            elif isinstance(stmt, ast.Define) and stmt.name:
                add_symbol(
                    "preprocessor",
                    stmt.name,
                    stmt,
                    stmt_filename,
                    conditional=item_conditional,
                )

            if isinstance(stmt, ast.IfDef):
                push_stream(stmt.else_body, stmt_filename, True)
                push_stream(stmt.then_body, stmt_filename, True)
            elif isinstance(stmt, ast.EncryptedBlock) and stmt.body:
                push_stream(stmt.body, stmt_filename, item_conditional)

    visit_statements(statements, filename)
    table.local_only_references.update(_collect_local_scope_reference_candidates(statements))
    table.local_only_references.difference_update(table.layer_like_names)
    table.local_only_references.difference_update(table.variables)
    table.local_only_references.difference_update(table.conditional_variables)
    return table, diagnostics
