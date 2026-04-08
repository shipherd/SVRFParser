"""Semantic validation for reconstructed SVRF ASTs."""

from __future__ import annotations

from . import ast
from .diagnostics import SEVERITY_ERROR, SEVERITY_WARNING
from .expression_contexts import annotate_expression_contexts
from .semantic_directives import DirectiveValidationMixin
from .semantic_node_dispatch import validate_semantic_node
from .semantic_symbols import (
    SymbolTable,
    ValidationScope,
    _node_diagnostic,
    _should_skip_expression_reference,
    _should_skip_symbol_name,
    build_symbol_table,
)
from .semantic_value_validation import ValueValidationMixin


class SemanticValidator(DirectiveValidationMixin, ValueValidationMixin):
    """Conservative semantic checks over the parsed AST."""

    def __init__(self, filename="<input>", strict=False, symbol_table=None, expression_contexts=None):
        self.filename = filename
        self.strict = strict
        self.symbol_table = symbol_table or SymbolTable()
        self.expression_contexts = expression_contexts
        self.diagnostics = []

    def error(self, code, message, node, metadata=None):
        self.diagnostics.append(
            _node_diagnostic(SEVERITY_ERROR, code, message, node, self.filename, metadata=metadata)
        )

    def warning(self, code, message, node, metadata=None):
        severity = SEVERITY_ERROR if self.strict else SEVERITY_WARNING
        self.diagnostics.append(
            _node_diagnostic(severity, code, message, node, self.filename, metadata=metadata)
        )

    def validate(self, program):
        scope = ValidationScope.from_symbol_table(self.symbol_table)
        self._validate_statement_list(program.statements, scope)
        return self.diagnostics

    def _warn_unknown_layer(self, code, name, node, scope):
        if _should_skip_symbol_name(name):
            return
        if scope.knows_layer_like(name):
            return
        self.warning(code, f"Unknown layer or group reference {name}", node, metadata={"symbol": name})

    def _warn_unknown_reference(self, code, name, node, scope, context="generic"):
        if _should_skip_expression_reference(name):
            return
        if scope.knows_reference(name):
            return
        if name in self.symbol_table.local_only_references:
            self.warning(
                "semantic.reference.local_scope_only",
                f"Reference {name} is only defined in local rule, macro, or property scopes elsewhere in this file",
                node,
                metadata={"symbol": name, "reference_context": context},
            )
            return
        if context == "scalar":
            self.warning(
                "semantic.reference.scalar_undefined",
                f"Unresolved scalar parameter-like identifier {name}",
                node,
                metadata={"symbol": name, "reference_context": context},
            )
            return
        self.warning(
            code,
            f"Unknown layer or variable reference {name}",
            node,
            metadata={"symbol": name, "reference_context": context},
        )

    def _validate_node(self, node, scope, pending):
        validate_semantic_node(self, node, scope, pending)

    def expression_context_for(self, node, fallback="generic"):
        if self.expression_contexts is None:
            return fallback
        return self.expression_contexts.semantic_context_for(node, fallback)


def validate_semantics(program, filename="<input>", strict=False, symbol_table=None):
    """Return semantic diagnostics for *program*."""

    symbol_diags = []
    if symbol_table is None:
        symbol_table, symbol_diags = build_symbol_table(
            program.statements,
            filename=filename,
            strict=strict,
        )
    expression_contexts = annotate_expression_contexts(program)
    validator = SemanticValidator(
        filename=filename,
        strict=strict,
        symbol_table=symbol_table,
        expression_contexts=expression_contexts,
    )
    return [*symbol_diags, *validator.validate(program)]
