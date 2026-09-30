"""Reviewed manual-derived overrides for packaged SVRF spec artifacts."""

from __future__ import annotations


APPROVED_KEYWORD_ALIASES = {
    "DEV": "DEVICE",
    "PARA": "PARALLEL",
    "PERIM": "PERIMETER",
    "PERP": "PERPENDICULAR",
    "PROJ": "PROJECTING",
    "PROP": "PROPERTY",
}


DOC_ALL_EXTRA_FUNCTION_NAMES = frozenset(
    {
        "ENCLOSURE_PARALLEL_MULTIFINGER",
        "ENCLOSURE_PERPENDICULAR_MULTIFINGER",
    }
)


DOC_DFM_EXTRA_FUNCTION_NAMES = frozenset(
    {
        "ANGLE",
        "AREA",
        "COUNT",
        "DRC_EQ",
        "DRC_GE",
        "DRC_GT",
        "DRC_LE",
        "DRC_LT",
        "DRC_NE",
        "ECX",
        "ECXP",
        "ECY",
        "ECYP",
        "EMPTYSTRING",
        "EW",
        "EWP",
        "EWX",
        "EWXP",
        "EWY",
        "EWYP",
        "GLOBALNETID",
        "LENGTH",
        "LENGTHX",
        "LENGTHXP",
        "LENGTHY",
        "LENGTHYP",
        "MATCH",
        "MAX_NUMBER",
        "NETID",
        "NETNAME",
        "NONETID",
        "PERIMETER",
        "PERIMETERX",
        "PERIMETERXP",
        "PERIMETERY",
        "PERIMETERYP",
        "PRECISION",
        "PSNETID",
        "RANDOM",
        "STRING_COMPARE",
        "TEXT_NUMERIC",
        "TEXT_STRING",
    }
)


FUNCTION_LIKE_EXTRA_NAMES = frozenset(
    {
        "DFM",
        "ENC",
        "EXT",
        "INT",
        "NET",
        "RECTANGLE",
        "VERTEX",
    }
)


MANUAL_EXCEPTION_ENTRIES = (
    {
        "name": "top_level_order_default",
        "category": "ordering",
        "applies_to": ("TOP_LEVEL_RULE_FILE",),
        "effect": "order_independent",
        "note": "Top-level SVRF rule-file statements are generally order-independent.",
        "manual_refs": (
            r"luj1752242843309\id39084ca3-0d46-48c6-81df-86585450e37a.html",
        ),
        "tags": ("manual_default",),
    },
    {
        "name": "variable_definition_order_exception",
        "category": "ordering",
        "applies_to": ("VARIABLE", "#DEFINE"),
        "effect": "must_precede_use",
        "note": "Variable and preprocessor symbol definitions must precede use sites.",
        "manual_refs": (
            r"luj1752242843309\id39084ca3-0d46-48c6-81df-86585450e37a.html",
        ),
        "tags": ("manual_exception", "ordered_use"),
    },
    {
        "name": "incremental_connectivity_order_exception",
        "category": "ordering",
        "applies_to": ("DRC INCREMENTAL CONNECT",),
        "effect": "ordered_exception",
        "note": "Incremental connectivity definitions have ordering-sensitive semantics.",
        "manual_refs": (
            r"luj1752242843309\id39084ca3-0d46-48c6-81df-86585450e37a.html",
        ),
        "tags": ("manual_exception", "ordered_use"),
    },
    {
        "name": "operation_item_order_default",
        "category": "statement_syntax",
        "applies_to": ("OPERATIONS",),
        "effect": "order_free_by_default",
        "note": "Operation syntax elements generally appear in any order unless the manual says otherwise.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("manual_default",),
    },
    {
        "name": "specification_statement_order_exception",
        "category": "statement_syntax",
        "applies_to": ("SPECIFICATION_STATEMENTS",),
        "effect": "ordered_exception",
        "note": "Specification statements are not universally order-free.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("manual_exception", "ordered_options"),
    },
    {
        "name": "dfm_operation_order_exception",
        "category": "statement_syntax",
        "applies_to": ("DFM_OPERATIONS",),
        "effect": "ordered_exception",
        "note": "Many DFM operations are documented with statement-specific ordering constraints.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("manual_exception", "ordered_options"),
    },
    {
        "name": "multiword_keyword_atomic",
        "category": "tokenization",
        "applies_to": ("MULTIWORD_SYNTAX_ELEMENTS",),
        "effect": "atomic",
        "note": "Multi-word syntax elements are atomic and cannot be reordered or split.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("manual_exception", "atomic_keyword"),
    },
    {
        "name": "statement_boundary_primary_keywords",
        "category": "whitespace",
        "applies_to": ("STATEMENT_BOUNDARIES",),
        "effect": "primary_keyword_delimited",
        "note": "Whitespace is broadly insignificant; statement boundaries are inferred from primary keywords and structure.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("manual_default", "whitespace_agnostic"),
    },
    {
        "name": "builtin_language_subgrammar_boundary",
        "category": "embedded_language",
        "applies_to": ("TVF", "BUILTIN_LANGUAGES"),
        "effect": "separate_subgrammar",
        "note": "Built-in languages have their own syntax rules and should not be parsed as ordinary SVRF statements.",
        "manual_refs": (
            r"hri1752242863124\id56178a50-4711-4336-8418-0fc85e03fc23.html",
        ),
        "tags": ("manual_exception", "embedded_language"),
    },
)


CASE_SENSITIVITY_RULES = (
    {
        "name": "svrf_keywords_default",
        "category": "keywords",
        "case_mode": "case_insensitive",
        "scope": "SVRF_KEYWORDS_AND_IDENTIFIERS",
        "note": "SVRF keywords and identifiers are case-insensitive by default.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("manual_default",),
    },
    {
        "name": "filenames_case_sensitive",
        "category": "filenames",
        "case_mode": "case_sensitive",
        "scope": "INCLUDE_AND_EXTERNAL_PATHS",
        "note": "Filenames are case-sensitive because external filesystems may be case-sensitive.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
            r"luj1752242843309\idf931aa5d-e2bf-4101-be8d-801786c3e65b.html",
        ),
        "tags": ("manual_exception",),
    },
    {
        "name": "environment_variables_case_sensitive",
        "category": "environment",
        "case_mode": "case_sensitive",
        "scope": "PATH_ENVIRONMENT_VARIABLES",
        "note": "Environment variable names in path handling are treated as case-sensitive external inputs.",
        "manual_refs": (
            r"luj1752242843309\id227f5401-c3e0-428d-97cb-cc1872c793cc.html",
            r"luj1752242843309\idf931aa5d-e2bf-4101-be8d-801786c3e65b.html",
        ),
        "tags": ("manual_exception",),
    },
    {
        "name": "cell_names_case_sensitive",
        "category": "cell_names",
        "case_mode": "case_sensitive",
        "scope": "EXTERNAL_LAYOUT_AND_NETLIST_NAMES",
        "note": "Cell names are case-sensitive because they must match external layout/netlist systems.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("manual_exception",),
    },
    {
        "name": "dfm_property_names_case_sensitive",
        "category": "property_names",
        "case_mode": "case_sensitive",
        "scope": "DFM_PROPERTY_NAMES",
        "note": "DFM property names are documented as case-sensitive data values.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("manual_exception",),
    },
    {
        "name": "quoted_strings_not_implicitly_sensitive",
        "category": "quoted_strings",
        "case_mode": "context_dependent",
        "scope": "QUOTED_STRINGS",
        "note": "Quoted strings are not automatically case-sensitive; case behavior depends on the referenced external object.",
        "manual_refs": (
            r"luj1752242843309\id74c833a8-79b2-4d25-976f-96a5a1e6ed2d.html",
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("manual_exception", "context_dependent"),
    },
)


SUPPORT_MATRIX_ENTRIES = (
    {
        "name": "core_rule_file",
        "dialects": ("CORE",),
        "feature_family": "rule_file_core",
        "support_level": "full",
        "parser_support": "full",
        "semantic_support": "full",
        "note": "Core SVRF rule-file constructs are fully parsed and semantically validated.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("stable",),
    },
    {
        "name": "preprocessor_control",
        "dialects": ("CORE",),
        "feature_family": "preprocessor_control",
        "support_level": "full",
        "parser_support": "full",
        "semantic_support": "full",
        "note": "Core preprocessor directives are parsed and scoped explicitly.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("stable",),
    },
    {
        "name": "polygon_directive",
        "dialects": ("DRC",),
        "feature_family": "region_definition",
        "support_level": "limited",
        "parser_support": "full",
        "semantic_support": "limited",
        "note": "POLYGON directives are recognized, but only generic semantic handling is implemented.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("manual_review", "generic_semantics"),
    },
    {
        "name": "rdb_directive",
        "dialects": ("DRC",),
        "feature_family": "results_database",
        "support_level": "limited",
        "parser_support": "full",
        "semantic_support": "limited",
        "note": "Top-level RDB directives are recognized, but only generic semantic handling is implemented.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("manual_review", "generic_semantics"),
    },
    {
        "name": "tvf_directive",
        "dialects": ("TVF",),
        "feature_family": "builtin_language",
        "support_level": "limited",
        "parser_support": "full",
        "semantic_support": "generic_only",
        "note": "TVF constructs are recognized, but TVF bodies are treated as opaque built-in language content.",
        "manual_refs": (
            r"hri1752242863124\id56178a50-4711-4336-8418-0fc85e03fc23.html",
        ),
        "tags": ("manual_review", "embedded_language"),
    },
    {
        "name": "encrypted_block",
        "dialects": ("CORE",),
        "feature_family": "opaque_content",
        "support_level": "opaque",
        "parser_support": "full",
        "semantic_support": "opaque",
        "note": "Encrypted SVRF blocks are preserved structurally but not semantically interpreted.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("manual_review", "opaque_content"),
    },
)


SYMBOL_CONVENTION_ENTRIES = (
    {
        "name": "scalar_tuple_heads",
        "category": "scalar_context",
        "values": ("BY", "STEP", "WINDOW", "SCALE", "LENGTH", "WIDTH"),
        "note": "These tuple heads introduce scalar/numeric argument contexts in the current parser and validator.",
        "manual_refs": (
            r"luj1752242843309\iddc028bbf-ba2d-4d09-b069-717e96433bbb.html",
        ),
        "tags": ("reviewed_runtime_policy",),
    },
    {
        "name": "companion_file_suffixes",
        "category": "external_context",
        "values": (),
        "note": "Compatibility entry only; current companion scanning considers all regular sibling files and uses no suffix whitelist.",
        "manual_refs": (),
        "tags": ("reviewed_runtime_policy",),
    },
    {
        "name": "local_scope_kinds",
        "category": "local_scope",
        "values": (
            "rule_check_assignment",
            "macro_parameter",
            "property_name",
            "implicit_device_terminal",
        ),
        "note": "These locally-scoped symbol classes are intentionally not promoted to global symbol-table definitions.",
        "manual_refs": (),
        "tags": ("reviewed_runtime_policy",),
    },
    {
        "name": "external_unresolved_contexts",
        "category": "external_context",
        "values": (
            "omitted_include",
            "companion_deck",
            "tool_runtime_global",
            "process_setup_parameter",
        ),
        "note": "These are the main external-context buckets used when unresolved names have no visible plaintext definition.",
        "manual_refs": (),
        "tags": ("reviewed_runtime_policy",),
    },
)
