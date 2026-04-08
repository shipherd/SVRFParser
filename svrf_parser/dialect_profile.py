"""Dialect and support-profile analysis for parsed SVRF programs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from . import ast


@dataclass(frozen=True, slots=True)
class AstDialectProfile:
    name: str
    node_type: str
    dialects: frozenset[str]
    family: str
    support_level: str
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class DirectiveDialectProfile:
    name: str
    keywords: tuple[str, ...]
    dialects: frozenset[str]
    family: str
    support_level: str
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class OperationDialectProfile:
    name: str
    head_prefix: tuple[str, ...]
    dialects: frozenset[str]
    family: str
    support_level: str
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class ProgramDialectProfile:
    dialects: tuple[str, ...]
    families: tuple[str, ...]
    tags: tuple[str, ...]
    limited_support_features: tuple[str, ...]
    feature_counts: dict[str, int]
    dialect_counts: dict[str, int]

    def to_dict(self):
        return {
            "dialects": self.dialects,
            "families": self.families,
            "tags": self.tags,
            "limited_support_features": self.limited_support_features,
            "feature_counts": dict(self.feature_counts),
            "dialect_counts": dict(self.dialect_counts),
        }


class DialectProfileRegistry:
    def __init__(self, *, ast_profiles, directive_profiles, operation_profiles):
        self.ast_profiles = tuple(ast_profiles)
        self.directive_profiles = tuple(
            sorted(
                directive_profiles,
                key=lambda entry: (len(entry.keywords), entry.name),
                reverse=True,
            )
        )
        self.operation_profiles = tuple(
            sorted(
                operation_profiles,
                key=lambda entry: (len(entry.head_prefix), entry.name),
                reverse=True,
            )
        )
        self._ast_by_type = {entry.node_type: entry for entry in self.ast_profiles}
        self._directives_by_first_word = {}
        for entry in self.directive_profiles:
            if entry.keywords:
                self._directives_by_first_word.setdefault(entry.keywords[0], []).append(entry)
        self._operations_by_first_word = {}
        for entry in self.operation_profiles:
            if entry.head_prefix:
                self._operations_by_first_word.setdefault(entry.head_prefix[0], []).append(entry)

    def match_ast(self, node):
        return self._ast_by_type.get(type(node).__name__)

    def match_directive(self, keywords):
        keywords = tuple(str(keyword).upper() for keyword in keywords or ())
        if not keywords:
            return None
        for entry in self._directives_by_first_word.get(keywords[0], ()):
            if keywords[: len(entry.keywords)] == entry.keywords:
                return entry
        return None

    def match_operation(self, op_name):
        words = tuple(str(part).upper() for part in str(op_name or "").split())
        if not words:
            return None
        for entry in self._operations_by_first_word.get(words[0], ()):
            if words[: len(entry.head_prefix)] == entry.head_prefix:
                return entry
        return None


def _ast_entry(name, node_type, dialects, family, support_level="full", tags=()):
    return AstDialectProfile(
        name=name,
        node_type=node_type,
        dialects=frozenset(dialects),
        family=family,
        support_level=support_level,
        tags=frozenset(tags),
    )


def _directive_entry(name, keywords, dialects, family, support_level="full", tags=()):
    return DirectiveDialectProfile(
        name=name,
        keywords=tuple(keywords),
        dialects=frozenset(dialects),
        family=family,
        support_level=support_level,
        tags=frozenset(tags),
    )


def _operation_entry(name, head_prefix, dialects, family, support_level="full", tags=()):
    return OperationDialectProfile(
        name=name,
        head_prefix=tuple(head_prefix),
        dialects=frozenset(dialects),
        family=family,
        support_level=support_level,
        tags=frozenset(tags),
    )


AST_DIALECT_PROFILES = (
    _ast_entry("layer_definition", "LayerDef", ("CORE",), "layer_definition"),
    _ast_entry("layer_map", "LayerMap", ("CORE",), "layer_mapping"),
    _ast_entry("layer_assignment", "LayerAssignment", ("CORE",), "layer_expression"),
    _ast_entry("variable_definition", "VariableDef", ("CORE",), "variable_definition"),
    _ast_entry("include", "Include", ("CORE",), "include_control"),
    _ast_entry("define", "Define", ("CORE",), "preprocessor_control"),
    _ast_entry("ifdef", "IfDef", ("CORE",), "preprocessor_control"),
    _ast_entry(
        "encrypted_block",
        "EncryptedBlock",
        ("CORE",),
        "encrypted_content",
        support_level="limited",
        tags=("hidden_plaintext_definitions", "manual_exception"),
    ),
    _ast_entry("rule_check", "RuleCheckBlock", ("DRC",), "rule_check"),
    _ast_entry("connect", "Connect", ("CORE", "LVS"), "connectivity"),
    _ast_entry("device", "Device", ("LVS", "DFM"), "device_extraction"),
    _ast_entry("dmacro", "DMacro", ("CORE",), "macro_definition"),
    _ast_entry("macro_call", "MacroCall", ("CORE",), "macro_call"),
    _ast_entry("property_block", "PropertyBlock", ("DFM",), "property_block"),
    _ast_entry("group", "Group", ("CORE",), "group_definition"),
    _ast_entry("attach", "Attach", ("LVS",), "attach"),
    _ast_entry("trace_property", "TraceProperty", ("DFM",), "trace_property"),
)


DIRECTIVE_DIALECT_PROFILES = (
    _directive_entry("drc_root", ("DRC",), ("DRC",), "directive_root"),
    _directive_entry("erc_root", ("ERC",), ("ERC",), "directive_root"),
    _directive_entry("lvs_root", ("LVS",), ("LVS",), "directive_root"),
    _directive_entry("pex_root", ("PEX",), ("PEX",), "directive_root"),
    _directive_entry("dfm_root", ("DFM",), ("DFM",), "directive_root"),
    _directive_entry(
        "polygon_directive",
        ("POLYGON",),
        ("DRC",),
        "region_definition",
        support_level="limited",
        tags=("generic_semantics",),
    ),
    _directive_entry(
        "rdb_directive",
        ("RDB",),
        ("DRC",),
        "results_database",
        support_level="limited",
        tags=("generic_semantics",),
    ),
    _directive_entry(
        "tvf_directive",
        ("TVF",),
        ("TVF",),
        "builtin_language",
        support_level="limited",
        tags=("embedded_language", "parse_generic"),
    ),
    _directive_entry(
        "lvs_recognize_gates",
        ("LVS", "RECOGNIZE", "GATES"),
        ("LVS",),
        "gate_recognition",
        tags=("ordered_options", "manual_exception"),
    ),
    _directive_entry(
        "lvs_spice_strict",
        ("LVS", "SPICE", "STRICT"),
        ("LVS",),
        "spice_netlist_policy",
        tags=("ordered_options", "manual_exception"),
    ),
    _directive_entry(
        "pex_report_netsummary",
        ("PEX", "REPORT", "NETSUMMARY"),
        ("PEX",),
        "pex_reporting",
        tags=("ordered_options", "manual_exception"),
    ),
    _directive_entry(
        "pex_report_point2point",
        ("PEX", "REPORT", "POINT2POINT"),
        ("PEX",),
        "pex_reporting",
        tags=("ordered_options", "manual_exception"),
    ),
    _directive_entry(
        "drc_results_database",
        ("DRC", "RESULTS", "DATABASE"),
        ("DRC",),
        "results_database",
        tags=("ordered_options", "manual_exception"),
    ),
    _directive_entry(
        "erc_results_database",
        ("ERC", "RESULTS", "DATABASE"),
        ("ERC",),
        "results_database",
        tags=("ordered_options", "manual_exception"),
    ),
)


OPERATION_DIALECT_PROFILES = (
    _operation_entry("dfm_operation", ("DFM",), ("DFM",), "dfm_operation"),
    _operation_entry("dfm_rdb_operation", ("DFM", "RDB"), ("DFM",), "results_database", tags=("manual_exception",)),
    _operation_entry("ret_operation", ("RET",), ("DRC",), "ret_operation"),
    _operation_entry("pathchk_operation", ("PATHCHK",), ("DRC",), "path_check"),
    _operation_entry("with_text_operation", ("WITH", "TEXT"), ("DRC",), "text_filter"),
)


DIALECT_PROFILE_REGISTRY = DialectProfileRegistry(
    ast_profiles=AST_DIALECT_PROFILES,
    directive_profiles=DIRECTIVE_DIALECT_PROFILES,
    operation_profiles=OPERATION_DIALECT_PROFILES,
)


def _record_feature(entry, feature_counts, dialect_counts, families, tags, limited_support):
    feature_counts[entry.name] += 1
    families.add(entry.family)
    tags.update(entry.tags)
    for dialect in entry.dialects:
        dialect_counts[dialect] += 1
    if entry.support_level != "full":
        limited_support.add(entry.name)


def _coerce_argument_text(argument):
    if isinstance(argument, ast.StringLiteral):
        return argument.value
    if isinstance(argument, ast.LayerRef):
        return argument.name
    if isinstance(argument, str):
        return argument
    return None


def _directive_match_words(node):
    words = [str(keyword).upper() for keyword in getattr(node, "keywords", ()) or ()]
    for argument in getattr(node, "arguments", ()) or ():
        text = _coerce_argument_text(argument)
        if text is None:
            break
        words.append(str(text).upper())
    return tuple(words)


def iter_program_profile_matches(program):
    if program is None:
        return
    for node in program.walk():
        entry = DIALECT_PROFILE_REGISTRY.match_ast(node)
        if entry is not None:
            yield entry, node

        if isinstance(node, ast.Directive):
            entry = DIALECT_PROFILE_REGISTRY.match_directive(_directive_match_words(node))
            if entry is not None:
                yield entry, node

        if isinstance(node, ast.DRCOp):
            entry = DIALECT_PROFILE_REGISTRY.match_operation(node.op)
            if entry is not None:
                yield entry, node


def analyze_program_dialects(program):
    if program is None:
        return ProgramDialectProfile((), (), (), (), {}, {})

    feature_counts = Counter()
    dialect_counts = Counter()
    families = set()
    tags = set()
    limited_support = set()

    for entry, _node in iter_program_profile_matches(program):
        _record_feature(entry, feature_counts, dialect_counts, families, tags, limited_support)

    return ProgramDialectProfile(
        dialects=tuple(sorted(dialect_counts)),
        families=tuple(sorted(families)),
        tags=tuple(sorted(tags)),
        limited_support_features=tuple(sorted(limited_support)),
        feature_counts=dict(sorted(feature_counts.items())),
        dialect_counts=dict(sorted(dialect_counts.items())),
    )


def merge_program_dialect_profiles(profiles):
    feature_counts = Counter()
    dialect_counts = Counter()
    families = set()
    tags = set()
    limited_support = set()

    for profile in profiles:
        if profile is None:
            continue
        feature_counts.update(profile.feature_counts)
        dialect_counts.update(profile.dialect_counts)
        families.update(profile.families)
        tags.update(profile.tags)
        limited_support.update(profile.limited_support_features)

    return ProgramDialectProfile(
        dialects=tuple(sorted(dialect_counts)),
        families=tuple(sorted(families)),
        tags=tuple(sorted(tags)),
        limited_support_features=tuple(sorted(limited_support)),
        feature_counts=dict(sorted(feature_counts.items())),
        dialect_counts=dict(sorted(dialect_counts.items())),
    )
