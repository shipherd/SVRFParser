"""Validation-semantic passes with narrow, testable boundaries."""

from __future__ import annotations

from dataclasses import dataclass

from .feature_spec import merge_program_profiles
from .semantic import validate_semantics
from .semantic_symbols import build_symbol_table

_DIRECTIVE_CODES = frozenset(
    {
        "semantic.directive.missing_argument",
        "semantic.directive.argument_shape",
        "semantic.directive.invalid_value",
        "semantic.directive.invalid_order",
    }
)

_DRC_OPERATION_CODES = frozenset(
    {
        "semantic.drc.with_empty",
        "semantic.drc.with_text.missing_filter",
        "semantic.drc.missing_operand",
        "semantic.drc.missing_constraint",
        "semantic.drc.missing_modifier",
        "semantic.device_layer.missing_modifier",
    }
)

_REFERENCE_PREFIXES = (
    "semantic.reference.",
    "semantic.varref.",
)

_SCOPE_PREFIXES = (
    "semantic.duplicate_",
    "semantic.define.",
    "semantic.ifdef.",
    "semantic.include.",
    "semantic.assignment.",
    "semantic.group.",
    "semantic.rule.",
    "semantic.connect.",
    "semantic.attach.",
    "semantic.trace_property.",
    "semantic.device.",
    "semantic.macro.",
)


@dataclass(frozen=True, slots=True)
class SymbolTablePassResult:
    symbol_table: object
    diagnostics: tuple


@dataclass(frozen=True, slots=True)
class SemanticDiagnosticBuckets:
    directive_contract: tuple = ()
    drc_operation: tuple = ()
    reference_classification: tuple = ()
    scope_resolution: tuple = ()
    other: tuple = ()


@dataclass(frozen=True, slots=True)
class SemanticValidationPassResult:
    diagnostics: tuple
    buckets: SemanticDiagnosticBuckets


def run_symbol_table_pass(statements, *, filename="<input>", strict=False):
    symbol_table, diagnostics = build_symbol_table(
        statements,
        filename=filename,
        strict=strict,
    )
    return SymbolTablePassResult(
        symbol_table=symbol_table,
        diagnostics=tuple(diagnostics),
    )


def classify_semantic_diagnostic(diagnostic):
    code = getattr(diagnostic, "code", "")
    if code in _DIRECTIVE_CODES or code.startswith("semantic.directive."):
        return "directive_contract"
    if code in _DRC_OPERATION_CODES or code.startswith("semantic.drc."):
        return "drc_operation"
    if code.startswith(_REFERENCE_PREFIXES):
        return "reference_classification"
    if code.startswith(_SCOPE_PREFIXES):
        return "scope_resolution"
    return "other"


def bucket_semantic_diagnostics(diagnostics):
    buckets = {
        "directive_contract": [],
        "drc_operation": [],
        "reference_classification": [],
        "scope_resolution": [],
        "other": [],
    }
    for diagnostic in diagnostics:
        buckets[classify_semantic_diagnostic(diagnostic)].append(diagnostic)
    return SemanticDiagnosticBuckets(
        directive_contract=tuple(buckets["directive_contract"]),
        drc_operation=tuple(buckets["drc_operation"]),
        reference_classification=tuple(buckets["reference_classification"]),
        scope_resolution=tuple(buckets["scope_resolution"]),
        other=tuple(buckets["other"]),
    )


def run_semantic_validation_pass(program, *, filename="<input>", strict=False, symbol_table=None):
    diagnostics = tuple(
        validate_semantics(
            program,
            filename=filename,
            strict=strict,
            symbol_table=symbol_table,
        )
    )
    return SemanticValidationPassResult(
        diagnostics=diagnostics,
        buckets=bucket_semantic_diagnostics(diagnostics),
    )


def build_validation_profile(documents):
    return merge_program_profiles(doc.program for doc in documents)
