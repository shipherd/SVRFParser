"""Load packaged SVRF spec artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files


_DATA_PACKAGE = "svrf_parser.svrf_spec.data"


@dataclass(frozen=True, slots=True)
class KeywordSpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    keyword_registry: dict[str, frozenset[str]]
    keyword_aliases: dict[str, str]
    layer_bp: dict[str, int]


@dataclass(frozen=True, slots=True)
class ParserSpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    tables: dict[str, object]
    function_families: dict[str, frozenset[str]]

    def table(self, name):
        return self.tables[name]

    def family(self, name):
        return self.function_families[name]


@dataclass(frozen=True, slots=True)
class StatementSchemaEntrySpec:
    name: str
    modes: frozenset[str]
    head_prefix: tuple[str, ...]
    parser_method: str
    parse_kinds: frozenset[str]


@dataclass(frozen=True, slots=True)
class StatementSchemaSpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    entries: tuple[StatementSchemaEntrySpec, ...]


@dataclass(frozen=True, slots=True)
class OperationSchemaEntrySpec:
    name: str
    head_prefix: tuple[str, ...]
    family: str
    parse_strategy: str
    modifier_family: str
    allow_nonstatement_expression_newline: bool
    bracket_modifier_mode: str
    parenthesized_scalar_modifiers: bool


@dataclass(frozen=True, slots=True)
class OperationContractEntrySpec:
    name: str
    min_operands: int | None = None
    min_constraints: int | None = None
    min_modifiers: int | None = None
    requires_content: bool = False
    operand_roles: tuple[str, ...] = ()
    variadic_operand_role: str | None = None
    single_operand_role: str | None = None


@dataclass(frozen=True, slots=True)
class OperationSchemaSpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    entries: tuple[OperationSchemaEntrySpec, ...]
    contracts: tuple[OperationContractEntrySpec, ...] = ()


@dataclass(frozen=True, slots=True)
class PreprocessorSchemaEntrySpec:
    name: str
    tags: frozenset[str]
    parser_method: str


@dataclass(frozen=True, slots=True)
class PreprocessorSchemaSpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    entries: tuple[PreprocessorSchemaEntrySpec, ...]


@dataclass(frozen=True, slots=True)
class PrefixExpressionSchemaEntrySpec:
    name: str
    priority: int
    tags: frozenset[str]
    parser_method: str


@dataclass(frozen=True, slots=True)
class PrefixExpressionSchemaSpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    entries: tuple[PrefixExpressionSchemaEntrySpec, ...]


@dataclass(frozen=True, slots=True)
class LedExpressionSchemaEntrySpec:
    name: str
    priority: int
    tags: frozenset[str]
    parser_method: str
    binding_power: int | None
    binding_power_source: str


@dataclass(frozen=True, slots=True)
class LedExpressionSchemaSpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    entries: tuple[LedExpressionSchemaEntrySpec, ...]


@dataclass(frozen=True, slots=True)
class StatementShapeEntrySpec:
    name: str
    family: str


@dataclass(frozen=True, slots=True)
class StatementShapeSpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    entries: tuple[StatementShapeEntrySpec, ...]


@dataclass(frozen=True, slots=True)
class DirectiveContractEntrySpec:
    name: str
    keywords: tuple[str, ...]
    dialect: str
    family: str
    value_sets: dict[str, frozenset[str]]
    ordered_values: dict[str, tuple[str, ...]]
    clause_sequences: dict[str, tuple[tuple[str, ...], ...]]


@dataclass(frozen=True, slots=True)
class DirectiveContractSpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    entries: tuple[DirectiveContractEntrySpec, ...]


@dataclass(frozen=True, slots=True)
class AstDialectProfileEntrySpec:
    name: str
    node_type: str
    dialects: frozenset[str]
    family: str
    support_level: str
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class DirectiveDialectProfileEntrySpec:
    name: str
    keywords: tuple[str, ...]
    dialects: frozenset[str]
    family: str
    support_level: str
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class OperationDialectProfileEntrySpec:
    name: str
    head_prefix: tuple[str, ...]
    dialects: frozenset[str]
    family: str
    support_level: str
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class DialectProfileSpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    ast_entries: tuple[AstDialectProfileEntrySpec, ...]
    directive_entries: tuple[DirectiveDialectProfileEntrySpec, ...]
    operation_entries: tuple[OperationDialectProfileEntrySpec, ...]


@dataclass(frozen=True, slots=True)
class SupportNoticeEntrySpec:
    name: str
    feature_name: str
    warning_code: str
    message: str
    category: str
    emit_warning: bool
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class SupportNoticeSpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    entries: tuple[SupportNoticeEntrySpec, ...]


@dataclass(frozen=True, slots=True)
class ManualExceptionEntrySpec:
    name: str
    category: str
    applies_to: tuple[str, ...]
    effect: str
    note: str
    manual_refs: tuple[str, ...]
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class ManualExceptionSpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    entries: tuple[ManualExceptionEntrySpec, ...]


@dataclass(frozen=True, slots=True)
class CaseSensitivityRuleEntrySpec:
    name: str
    category: str
    case_mode: str
    scope: str
    note: str
    manual_refs: tuple[str, ...]
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class CaseSensitivitySpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    entries: tuple[CaseSensitivityRuleEntrySpec, ...]


@dataclass(frozen=True, slots=True)
class SupportMatrixEntrySpec:
    name: str
    dialects: frozenset[str]
    feature_family: str
    support_level: str
    parser_support: str
    semantic_support: str
    note: str
    manual_refs: tuple[str, ...]
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class SupportMatrixSpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    entries: tuple[SupportMatrixEntrySpec, ...]


@dataclass(frozen=True, slots=True)
class SymbolConventionEntrySpec:
    name: str
    category: str
    values: tuple[str, ...]
    note: str
    manual_refs: tuple[str, ...]
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class SymbolConventionSpec:
    schema_version: int
    manual_root: str
    generated_from: tuple[str, ...]
    entries: tuple[SymbolConventionEntrySpec, ...]


def _read_json(filename):
    with files(_DATA_PACKAGE).joinpath(filename).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _freeze_table_values(values):
    frozen = {}
    for name, value in values.items():
        if isinstance(value, dict):
            frozen[name] = dict(value)
        else:
            frozen[name] = frozenset(value)
    return frozen


def _freeze_string_sets(values):
    return {
        name: frozenset(entry_values)
        for name, entry_values in values.items()
    }


def _freeze_string_sequences(values):
    return {
        name: tuple(entry_values)
        for name, entry_values in values.items()
    }


def _freeze_clause_sequences(values):
    return {
        name: tuple(tuple(words) for words in entry_values)
        for name, entry_values in values.items()
    }


@lru_cache(maxsize=1)
def load_keyword_spec():
    payload = _read_json("keywords.json")
    registry = {
        name: frozenset(roles)
        for name, roles in payload["keyword_registry"].items()
    }
    return KeywordSpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        keyword_registry=registry,
        keyword_aliases=dict(payload["keyword_aliases"]),
        layer_bp={name: int(value) for name, value in payload["layer_bp"].items()},
    )


@lru_cache(maxsize=1)
def load_parser_spec():
    payload = _read_json("parser_tables.json")
    return ParserSpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        tables=_freeze_table_values(payload["tables"]),
        function_families={
            name: frozenset(values)
            for name, values in payload["function_families"].items()
        },
    )


@lru_cache(maxsize=1)
def load_statement_schema_spec():
    payload = _read_json("statement_schemas.json")
    return StatementSchemaSpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        entries=tuple(
            StatementSchemaEntrySpec(
                name=entry["name"],
                modes=frozenset(entry["modes"]),
                head_prefix=tuple(entry["head_prefix"]),
                parser_method=entry["parser_method"],
                parse_kinds=frozenset(entry.get("parse_kinds", ())),
            )
            for entry in payload["entries"]
        ),
    )


@lru_cache(maxsize=1)
def load_operation_schema_spec():
    payload = _read_json("operation_schemas.json")
    return OperationSchemaSpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        entries=tuple(
            OperationSchemaEntrySpec(
                name=entry["name"],
                head_prefix=tuple(entry["head_prefix"]),
                family=entry.get("family", "fixed"),
                parse_strategy=entry.get("parse_strategy", "default"),
                modifier_family=entry.get("modifier_family", "default"),
                allow_nonstatement_expression_newline=bool(
                    entry.get("allow_nonstatement_expression_newline", False)
                ),
                bracket_modifier_mode=entry.get("bracket_modifier_mode", "none"),
                parenthesized_scalar_modifiers=bool(
                    entry.get("parenthesized_scalar_modifiers", False)
                ),
            )
            for entry in payload["entries"]
        ),
        contracts=tuple(
            OperationContractEntrySpec(
                name=name,
                min_operands=entry.get("min_operands"),
                min_constraints=entry.get("min_constraints"),
                min_modifiers=entry.get("min_modifiers"),
                requires_content=entry.get("requires_content", False),
                operand_roles=tuple(entry.get("operand_roles", ())),
                variadic_operand_role=entry.get("variadic_operand_role"),
                single_operand_role=entry.get("single_operand_role"),
            )
            for name, entry in payload.get("contracts", {}).items()
        ),
    )


@lru_cache(maxsize=1)
def load_preprocessor_schema_spec():
    payload = _read_json("preprocessor_schemas.json")
    return PreprocessorSchemaSpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        entries=tuple(
            PreprocessorSchemaEntrySpec(
                name=entry["name"],
                tags=frozenset(entry["tags"]),
                parser_method=entry["parser_method"],
            )
            for entry in payload["entries"]
        ),
    )


@lru_cache(maxsize=1)
def load_prefix_expression_schema_spec():
    payload = _read_json("prefix_expression_schemas.json")
    return PrefixExpressionSchemaSpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        entries=tuple(
            PrefixExpressionSchemaEntrySpec(
                name=entry["name"],
                priority=int(entry.get("priority", 0)),
                tags=frozenset(entry["tags"]),
                parser_method=entry["parser_method"],
            )
            for entry in payload["entries"]
        ),
    )


@lru_cache(maxsize=1)
def load_led_expression_schema_spec():
    payload = _read_json("led_expression_schemas.json")
    return LedExpressionSchemaSpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        entries=tuple(
            LedExpressionSchemaEntrySpec(
                name=entry["name"],
                priority=int(entry.get("priority", 0)),
                tags=frozenset(entry["tags"]),
                parser_method=entry["parser_method"],
                binding_power=(
                    None
                    if entry.get("binding_power") is None
                    else int(entry["binding_power"])
                ),
                binding_power_source=entry.get("binding_power_source", "static"),
            )
            for entry in payload["entries"]
        ),
    )


@lru_cache(maxsize=1)
def load_statement_shape_spec():
    payload = _read_json("statement_shapes.json")
    return StatementShapeSpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        entries=tuple(
            StatementShapeEntrySpec(
                name=entry["name"],
                family=entry["family"],
            )
            for entry in payload["entries"]
        ),
    )


@lru_cache(maxsize=1)
def load_directive_contract_spec():
    payload = _read_json("directive_contracts.json")
    return DirectiveContractSpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        entries=tuple(
            DirectiveContractEntrySpec(
                name=entry["name"],
                keywords=tuple(entry["keywords"]),
                dialect=entry["dialect"],
                family=entry["family"],
                value_sets=_freeze_string_sets(entry.get("value_sets", {})),
                ordered_values=_freeze_string_sequences(entry.get("ordered_values", {})),
                clause_sequences=_freeze_clause_sequences(entry.get("clause_sequences", {})),
            )
            for entry in payload["entries"]
        ),
    )


@lru_cache(maxsize=1)
def load_dialect_profile_spec():
    payload = _read_json("dialect_profiles.json")
    return DialectProfileSpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        ast_entries=tuple(
            AstDialectProfileEntrySpec(
                name=entry["name"],
                node_type=entry["node_type"],
                dialects=frozenset(entry["dialects"]),
                family=entry["family"],
                support_level=entry.get("support_level", "full"),
                tags=frozenset(entry.get("tags", ())),
            )
            for entry in payload.get("ast_entries", ())
        ),
        directive_entries=tuple(
            DirectiveDialectProfileEntrySpec(
                name=entry["name"],
                keywords=tuple(entry["keywords"]),
                dialects=frozenset(entry["dialects"]),
                family=entry["family"],
                support_level=entry.get("support_level", "full"),
                tags=frozenset(entry.get("tags", ())),
            )
            for entry in payload.get("directive_entries", ())
        ),
        operation_entries=tuple(
            OperationDialectProfileEntrySpec(
                name=entry["name"],
                head_prefix=tuple(entry["head_prefix"]),
                dialects=frozenset(entry["dialects"]),
                family=entry["family"],
                support_level=entry.get("support_level", "full"),
                tags=frozenset(entry.get("tags", ())),
            )
            for entry in payload.get("operation_entries", ())
        ),
    )


@lru_cache(maxsize=1)
def load_support_notice_spec():
    payload = _read_json("support_notices.json")
    return SupportNoticeSpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        entries=tuple(
            SupportNoticeEntrySpec(
                name=entry["name"],
                feature_name=entry["feature_name"],
                warning_code=entry["warning_code"],
                message=entry["message"],
                category=entry["category"],
                emit_warning=bool(entry.get("emit_warning", True)),
                tags=frozenset(entry.get("tags", ())),
            )
            for entry in payload.get("entries", ())
        ),
    )


@lru_cache(maxsize=1)
def load_manual_exception_spec():
    payload = _read_json("manual_exceptions.json")
    return ManualExceptionSpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        entries=tuple(
            ManualExceptionEntrySpec(
                name=entry["name"],
                category=entry["category"],
                applies_to=tuple(entry.get("applies_to", ())),
                effect=entry["effect"],
                note=entry["note"],
                manual_refs=tuple(entry.get("manual_refs", ())),
                tags=frozenset(entry.get("tags", ())),
            )
            for entry in payload.get("entries", ())
        ),
    )


@lru_cache(maxsize=1)
def load_case_sensitivity_spec():
    payload = _read_json("case_sensitivity.json")
    return CaseSensitivitySpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        entries=tuple(
            CaseSensitivityRuleEntrySpec(
                name=entry["name"],
                category=entry["category"],
                case_mode=entry["case_mode"],
                scope=entry["scope"],
                note=entry["note"],
                manual_refs=tuple(entry.get("manual_refs", ())),
                tags=frozenset(entry.get("tags", ())),
            )
            for entry in payload.get("entries", ())
        ),
    )


@lru_cache(maxsize=1)
def load_support_matrix_spec():
    payload = _read_json("support_matrix.json")
    return SupportMatrixSpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        entries=tuple(
            SupportMatrixEntrySpec(
                name=entry["name"],
                dialects=frozenset(entry.get("dialects", ())),
                feature_family=entry["feature_family"],
                support_level=entry["support_level"],
                parser_support=entry["parser_support"],
                semantic_support=entry["semantic_support"],
                note=entry["note"],
                manual_refs=tuple(entry.get("manual_refs", ())),
                tags=frozenset(entry.get("tags", ())),
            )
            for entry in payload.get("entries", ())
        ),
    )


@lru_cache(maxsize=1)
def load_symbol_convention_spec():
    payload = _read_json("symbol_conventions.json")
    return SymbolConventionSpec(
        schema_version=int(payload["schema_version"]),
        manual_root=payload["manual_root"],
        generated_from=tuple(payload.get("generated_from", ())),
        entries=tuple(
            SymbolConventionEntrySpec(
                name=entry["name"],
                category=entry["category"],
                values=tuple(entry.get("values", ())),
                note=entry["note"],
                manual_refs=tuple(entry.get("manual_refs", ())),
                tags=frozenset(entry.get("tags", ())),
            )
            for entry in payload.get("entries", ())
        ),
    )
