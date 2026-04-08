import os
import unittest
from pathlib import Path

from svrf_parser.case_sensitivity import CASE_SENSITIVITY_REGISTRY
from svrf_parser import keywords, parser
from svrf_parser.dialect_profile import DIALECT_PROFILE_REGISTRY
from svrf_parser.directive_contract import DIRECTIVE_CONTRACT_REGISTRY
from svrf_parser.expression_schema import (
    LED_EXPRESSION_SCHEMA_REGISTRY,
    PREFIX_EXPRESSION_SCHEMA_REGISTRY,
)
from svrf_parser.lexer import Lexer
from svrf_parser.manual_exception import MANUAL_EXCEPTION_REGISTRY
from svrf_parser.operation_schema import OPERATION_SCHEMA_REGISTRY
from svrf_parser.preprocessor_schema import PREPROCESSOR_SCHEMA_REGISTRY
from svrf_parser.statement_schema import STATEMENT_SCHEMA_REGISTRY
from svrf_parser.statement_shape import STATEMENT_SHAPE_REGISTRY
from svrf_parser.support_matrix import SUPPORT_MATRIX_REGISTRY
from svrf_parser.support_notice import SUPPORT_NOTICE_REGISTRY
from svrf_parser.symbol_convention import SYMBOL_CONVENTION_REGISTRY
from svrf_parser.svrf_spec import (
    CASE_SENSITIVITY_SPEC,
    DIALECT_PROFILE_SPEC,
    DIRECTIVE_CONTRACT_SPEC,
    KEYWORD_SPEC,
    LED_EXPRESSION_SCHEMA_SPEC,
    MANUAL_EXCEPTION_SPEC,
    OPERATION_SCHEMA_SPEC,
    PARSER_SPEC,
    PREFIX_EXPRESSION_SCHEMA_SPEC,
    PREPROCESSOR_SCHEMA_SPEC,
    STATEMENT_SCHEMA_SPEC,
    STATEMENT_SHAPE_SPEC,
    SUPPORT_MATRIX_SPEC,
    SUPPORT_NOTICE_SPEC,
    SYMBOL_CONVENTION_SPEC,
    load_case_sensitivity_spec,
    load_dialect_profile_spec,
    load_directive_contract_spec,
    load_keyword_spec,
    load_led_expression_schema_spec,
    load_manual_exception_spec,
    load_operation_schema_spec,
    load_parser_spec,
    load_prefix_expression_schema_spec,
    load_preprocessor_schema_spec,
    load_statement_schema_spec,
    load_statement_shape_spec,
    load_support_matrix_spec,
    load_support_notice_spec,
    load_symbol_convention_spec,
)
from svrf_parser.svrf_spec.manual_sources import (
    build_doc_all_function_names,
    build_doc_dfm_function_names,
    build_doc_math_function_names,
    build_doc_string_function_names,
    build_function_like_names,
    build_keyword_aliases,
    build_known_keyword_inventory,
)


class SpecBootstrapTests(unittest.TestCase):
    def test_keyword_spec_matches_exported_keyword_tables(self):
        self.assertEqual(KEYWORD_SPEC, load_keyword_spec())
        self.assertEqual(dict(KEYWORD_SPEC.keyword_registry), keywords._KEYWORD_REGISTRY)
        self.assertEqual(dict(KEYWORD_SPEC.keyword_aliases), keywords._KEYWORD_ALIASES)
        self.assertEqual(dict(KEYWORD_SPEC.layer_bp), keywords._LAYER_BP)

    def test_parser_spec_matches_exported_parser_tables(self):
        self.assertEqual(PARSER_SPEC, load_parser_spec())
        table_attrs = {
            "measurement_ops": parser._MEASUREMENT_OPS,
            "unary_ops": parser._UNARY_OPS,
            "prefix_boolean_ops": parser._PREFIX_BOOLEAN_OPS,
            "generic_prefix_ops": parser._GENERIC_PREFIX_OPS,
            "comparison_symbols": parser._COMPARISON_SYMBOLS,
            "arithmetic_bp": parser._ARITHMETIC_BP,
            "infix_bp": parser._INFIX_BP,
            "with_secondary_ops": parser._WITH_SECONDARY_OPS,
            "directive_secondary_words": parser._DIRECTIVE_SECONDARY_WORDS,
            "simple_keyword_directives": parser._SIMPLE_KEYWORD_DIRECTIVES,
            "directive_same_line_heads": parser._DIRECTIVE_SAME_LINE_HEADS,
            "top_level_explicit_heads": parser._TOP_LEVEL_EXPLICIT_HEADS,
            "modifier_starters": parser._MODIFIER_STARTERS,
            "dfm_property_modifiers": parser._DFM_PROPERTY_MODIFIERS,
            "ret_option_starters": parser._RET_OPTION_STARTERS,
            "edge_binary_prefix_ops": parser._EDGE_BINARY_PREFIX_OPS,
            "rule_body_same_line_starters": parser._RULE_BODY_SAME_LINE_STARTERS,
            "not_compound_ops": parser._NOT_COMPOUND_OPS,
            "with_text_trailing_modifiers": parser._WITH_TEXT_TRAILING_MODIFIERS,
            "function_like_names": parser._FUNCTION_LIKE_NAMES,
        }
        for name, exported in table_attrs.items():
            with self.subTest(name=name):
                self.assertEqual(PARSER_SPEC.table(name), exported)

        family_attrs = {
            "doc_math_function_names": parser._DOC_MATH_FUNCTION_NAMES,
            "doc_dfm_coordinate_function_names": parser._DOC_DFM_COORDINATE_FUNCTION_NAMES,
            "doc_dfm_measurement_function_names": parser._DOC_DFM_MEASUREMENT_FUNCTION_NAMES,
            "doc_dfm_comparison_function_names": parser._DOC_DFM_COMPARISON_FUNCTION_NAMES,
            "doc_dfm_per_shape_function_names": parser._DOC_DFM_PER_SHAPE_FUNCTION_NAMES,
            "doc_dfm_property_function_names": parser._DOC_DFM_PROPERTY_FUNCTION_NAMES,
            "doc_dfm_net_function_names": parser._DOC_DFM_NET_FUNCTION_NAMES,
            "doc_dfm_vector_function_names": parser._DOC_DFM_VECTOR_FUNCTION_NAMES,
            "doc_dfm_misc_function_names": parser._DOC_DFM_MISC_FUNCTION_NAMES,
            "doc_string_function_names": parser._DOC_STRING_FUNCTION_NAMES,
            "doc_dfm_function_names": parser._DOC_DFM_FUNCTION_NAMES,
            "doc_device_property_function_names": parser._DOC_DEVICE_PROPERTY_FUNCTION_NAMES,
            "doc_trace_property_function_names": parser._DOC_TRACE_PROPERTY_FUNCTION_NAMES,
            "doc_effective_property_function_names": parser._DOC_EFFECTIVE_PROPERTY_FUNCTION_NAMES,
            "doc_lvs_property_initialize_function_names": parser._DOC_LVS_PROPERTY_INITIALIZE_FUNCTION_NAMES,
            "doc_device_annotation_function_names": parser._DOC_DEVICE_ANNOTATION_FUNCTION_NAMES,
            "doc_historical_enclosure_function_names": parser._DOC_HISTORICAL_ENCLOSURE_FUNCTION_NAMES,
            "doc_builtin_language_function_names": parser._DOC_BUILTIN_LANGUAGE_FUNCTION_NAMES,
            "doc_all_function_names": parser._DOC_ALL_FUNCTION_NAMES,
        }
        for name, exported in family_attrs.items():
            with self.subTest(name=name):
                self.assertEqual(PARSER_SPEC.family(name), exported)

    def test_packaged_specs_record_manual_root(self):
        expected = "$SVRF_MANUAL_ROOT"
        self.assertEqual(KEYWORD_SPEC.manual_root, expected)
        self.assertEqual(OPERATION_SCHEMA_SPEC.manual_root, expected)
        self.assertEqual(PARSER_SPEC.manual_root, expected)
        self.assertEqual(PREFIX_EXPRESSION_SCHEMA_SPEC.manual_root, expected)
        self.assertEqual(PREPROCESSOR_SCHEMA_SPEC.manual_root, expected)
        self.assertEqual(STATEMENT_SCHEMA_SPEC.manual_root, expected)
        self.assertEqual(LED_EXPRESSION_SCHEMA_SPEC.manual_root, expected)
        self.assertEqual(STATEMENT_SHAPE_SPEC.manual_root, expected)
        self.assertEqual(DIRECTIVE_CONTRACT_SPEC.manual_root, expected)
        self.assertEqual(DIALECT_PROFILE_SPEC.manual_root, expected)
        self.assertEqual(SUPPORT_NOTICE_SPEC.manual_root, expected)
        self.assertEqual(MANUAL_EXCEPTION_SPEC.manual_root, expected)
        self.assertEqual(CASE_SENSITIVITY_SPEC.manual_root, expected)
        self.assertEqual(SUPPORT_MATRIX_SPEC.manual_root, expected)
        self.assertEqual(SYMBOL_CONVENTION_SPEC.manual_root, expected)
        self.assertEqual(KEYWORD_SPEC.schema_version, 1)
        self.assertEqual(OPERATION_SCHEMA_SPEC.schema_version, 1)
        self.assertEqual(PARSER_SPEC.schema_version, 1)
        self.assertEqual(PREFIX_EXPRESSION_SCHEMA_SPEC.schema_version, 1)
        self.assertEqual(PREPROCESSOR_SCHEMA_SPEC.schema_version, 1)
        self.assertEqual(STATEMENT_SCHEMA_SPEC.schema_version, 1)
        self.assertEqual(LED_EXPRESSION_SCHEMA_SPEC.schema_version, 1)
        self.assertEqual(STATEMENT_SHAPE_SPEC.schema_version, 1)
        self.assertEqual(DIRECTIVE_CONTRACT_SPEC.schema_version, 1)
        self.assertEqual(DIALECT_PROFILE_SPEC.schema_version, 1)
        self.assertEqual(SUPPORT_NOTICE_SPEC.schema_version, 1)
        self.assertEqual(MANUAL_EXCEPTION_SPEC.schema_version, 1)
        self.assertEqual(CASE_SENSITIVITY_SPEC.schema_version, 1)
        self.assertEqual(SUPPORT_MATRIX_SPEC.schema_version, 1)
        self.assertEqual(SYMBOL_CONVENTION_SPEC.schema_version, 1)

    def test_statement_schema_registry_matches_prefixes_and_modes(self):
        self.assertEqual(STATEMENT_SCHEMA_SPEC, load_statement_schema_spec())

        expected = {
            (
                entry.name,
                tuple(sorted(entry.modes)),
                entry.head_prefix,
                entry.parser_method,
                tuple(sorted(entry.parse_kinds)),
            )
            for entry in STATEMENT_SCHEMA_SPEC.entries
        }
        actual = {
            (
                schema.name,
                tuple(sorted(schema.modes)),
                schema.head_prefix,
                schema.parser_method,
                tuple(sorted(schema.parse_kinds)),
            )
            for schema in STATEMENT_SCHEMA_REGISTRY.schemas
        }
        self.assertEqual(expected, actual)

        schema = STATEMENT_SCHEMA_REGISTRY.match("top", ("TRACE", "PROPERTY"), parse_kind="statement_head")
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_trace_property")

        schema = STATEMENT_SCHEMA_REGISTRY.match("top", ("LAYER", "MAP"), parse_kind="statement_head")
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_layer")

        schema = STATEMENT_SCHEMA_REGISTRY.match("macro", ("IF",), parse_kind="statement_head")
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_if_statement")

        schema = STATEMENT_SCHEMA_REGISTRY.match("rule", ("IF",), parse_kind="statement_head")
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_expression_statement_from_cst")

        schema = STATEMENT_SCHEMA_REGISTRY.match("top", ("POLYGON",), parse_kind="directive")
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_directive")
        self.assertEqual(schema.head_prefix, ("POLYGON",))

        schema = STATEMENT_SCHEMA_REGISTRY.match("rule", ("WHATEVER",), parse_kind="directive")
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_directive")
        self.assertEqual(schema.parse_kinds, frozenset({"directive"}))

        schema = STATEMENT_SCHEMA_REGISTRY.match("property", parse_kind="expression_statement")
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_expression_statement_from_cst")

        schema = STATEMENT_SCHEMA_REGISTRY.match("rule", ("INT",), parse_kind="statement_head")
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_expression_statement_from_cst")

    def test_operation_schema_registry_matches_packaged_spec(self):
        self.assertEqual(OPERATION_SCHEMA_SPEC, load_operation_schema_spec())

        expected = {
            (
                entry.name,
                entry.head_prefix,
                entry.family,
                entry.parse_strategy,
                entry.modifier_family,
                entry.allow_nonstatement_expression_newline,
                entry.bracket_modifier_mode,
                entry.parenthesized_scalar_modifiers,
            )
            for entry in OPERATION_SCHEMA_SPEC.entries
        }
        actual = {
            (
                schema.name,
                schema.head_prefix,
                schema.family,
                schema.parse_strategy,
                schema.modifier_family,
                schema.allow_nonstatement_expression_newline,
                schema.bracket_modifier_mode,
                schema.parenthesized_scalar_modifiers,
            )
            for schema in OPERATION_SCHEMA_REGISTRY.schemas
        }
        self.assertEqual(expected, actual)

        tokens = Lexer("DFM PROPERTY NET M1 [X=1]", filename="<test>").tokens()
        schema = OPERATION_SCHEMA_REGISTRY.resolve(
            tokens,
            0,
            lambda idx: next(
                (
                    probe
                    for probe in range(idx, len(tokens))
                    if tokens[probe].type.name != "NEWLINE"
                ),
                len(tokens),
            ),
        )
        self.assertEqual(schema.name, "DFM PROPERTY NET")
        self.assertEqual(schema.modifier_family, "dfm_property")
        self.assertEqual(schema.bracket_modifier_mode, "expression")

        tokens = Lexer("WITH TEXT VDD PRIMARY", filename="<test>").tokens()
        schema = OPERATION_SCHEMA_REGISTRY.resolve(
            tokens,
            0,
            lambda idx: next(
                (
                    probe
                    for probe in range(idx, len(tokens))
                    if tokens[probe].type.name != "NEWLINE"
                ),
                len(tokens),
            ),
        )
        self.assertEqual(schema.name, "WITH TEXT")

    def test_preprocessor_schema_registry_matches_packaged_spec(self):
        self.assertEqual(PREPROCESSOR_SCHEMA_SPEC, load_preprocessor_schema_spec())

        expected = {
            (entry.name, tuple(sorted(entry.tags)), entry.parser_method)
            for entry in PREPROCESSOR_SCHEMA_SPEC.entries
        }
        actual = {
            (schema.name, tuple(sorted(schema.tags)), schema.parser_method)
            for schema in PREPROCESSOR_SCHEMA_REGISTRY.schemas
        }
        self.assertEqual(expected, actual)

        schema = PREPROCESSOR_SCHEMA_REGISTRY.match("#DEFINE")
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_define")

        schema = PREPROCESSOR_SCHEMA_REGISTRY.match("#IFNDEF")
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_ifdef_from_preprocessor")

        schema = PREPROCESSOR_SCHEMA_REGISTRY.match("#SOMETHING_UNKNOWN")
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_preprocessor_directive")

    def test_prefix_expression_schema_registry_matches_packaged_spec(self):
        self.assertEqual(PREFIX_EXPRESSION_SCHEMA_SPEC, load_prefix_expression_schema_spec())

        expected = {
            (
                entry.name,
                entry.priority,
                tuple(sorted(entry.tags)),
                entry.parser_method,
            )
            for entry in PREFIX_EXPRESSION_SCHEMA_SPEC.entries
        }
        actual = {
            (
                schema.name,
                schema.priority,
                tuple(sorted(schema.tags)),
                schema.parser_method,
            )
            for schema in PREFIX_EXPRESSION_SCHEMA_REGISTRY.schemas
        }
        self.assertEqual(expected, actual)

        schema = PREFIX_EXPRESSION_SCHEMA_REGISTRY.match({"measurement", "layer_ref"})
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_ident_measurement_nud")

        schema = PREFIX_EXPRESSION_SCHEMA_REGISTRY.match({"callable_name", "layer_ref"})
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_function_call_nud")

        schema = PREFIX_EXPRESSION_SCHEMA_REGISTRY.match({"layer_ref"})
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_ident_layer_ref")

    def test_led_expression_schema_registry_matches_packaged_spec(self):
        self.assertEqual(LED_EXPRESSION_SCHEMA_SPEC, load_led_expression_schema_spec())

        expected = {
            (
                entry.name,
                entry.priority,
                tuple(sorted(entry.tags)),
                entry.parser_method,
                entry.binding_power,
                entry.binding_power_source,
            )
            for entry in LED_EXPRESSION_SCHEMA_SPEC.entries
        }
        actual = {
            (
                schema.name,
                schema.priority,
                tuple(sorted(schema.tags)),
                schema.parser_method,
                schema.binding_power,
                schema.binding_power_source,
            )
            for schema in LED_EXPRESSION_SCHEMA_REGISTRY.schemas
        }
        self.assertEqual(expected, actual)

        schema = LED_EXPRESSION_SCHEMA_REGISTRY.match({"comparison_symbol", "arithmetic_symbol"})
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_constraint_led_from_schema")

        schema = LED_EXPRESSION_SCHEMA_REGISTRY.match({"edge_binary", "generic_ident"})
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_edge_binary_led")

        schema = LED_EXPRESSION_SCHEMA_REGISTRY.match({"generic_ident"})
        self.assertIsNotNone(schema)
        self.assertEqual(schema.parser_method, "_parse_generic_infix_led_from_schema")

    def test_statement_shape_registry_matches_packaged_spec(self):
        self.assertEqual(STATEMENT_SHAPE_SPEC, load_statement_shape_spec())

        expected = {
            (entry.name, entry.family)
            for entry in STATEMENT_SHAPE_SPEC.entries
        }
        actual = {
            (shape.name, shape.family)
            for shape in STATEMENT_SHAPE_REGISTRY.shapes
        }
        self.assertEqual(expected, actual)

        shape = STATEMENT_SHAPE_REGISTRY.get("group")
        self.assertIsNotNone(shape)
        self.assertEqual(shape.family, "named_scalar_list")

        shape = STATEMENT_SHAPE_REGISTRY.get("connect")
        self.assertIsNotNone(shape)
        self.assertEqual(shape.family, "connect")

    def test_directive_contract_registry_matches_packaged_spec(self):
        self.assertEqual(DIRECTIVE_CONTRACT_SPEC, load_directive_contract_spec())

        expected = {
            (
                entry.name,
                entry.keywords,
                entry.dialect,
                entry.family,
                tuple(
                    sorted((name, tuple(sorted(values))) for name, values in entry.value_sets.items())
                ),
                tuple(
                    sorted((name, values) for name, values in entry.ordered_values.items())
                ),
                tuple(
                    sorted((name, values) for name, values in entry.clause_sequences.items())
                ),
            )
            for entry in DIRECTIVE_CONTRACT_SPEC.entries
        }
        actual = {
            (
                contract.name,
                contract.keywords,
                contract.dialect,
                contract.family,
                tuple(
                    sorted((name, tuple(sorted(values))) for name, values in contract.value_sets.items())
                ),
                tuple(
                    sorted((name, values) for name, values in contract.ordered_values.items())
                ),
                tuple(
                    sorted((name, values) for name, values in contract.clause_sequences.items())
                ),
            )
            for contract in DIRECTIVE_CONTRACT_REGISTRY.contracts
        }
        self.assertEqual(expected, actual)

        contract = DIRECTIVE_CONTRACT_REGISTRY.get(("LVS", "RECOGNIZE", "GATES"))
        self.assertIsNotNone(contract)
        self.assertEqual(contract.dialect, "LVS")
        self.assertIn("ALL", contract.value_sets["modes"])
        self.assertEqual(contract.clause_sequences["trailing_clause"], (("CELL", "LIST"),))

        contract = DIRECTIVE_CONTRACT_REGISTRY.get(("PEX", "REPORT", "NETSUMMARY"))
        self.assertIsNotNone(contract)
        self.assertEqual(contract.family, "report_netsummary")
        self.assertIn("ADVANCED", contract.value_sets["columns"])

        contract = DIRECTIVE_CONTRACT_REGISTRY.get(("PEX", "NETLIST", "UPPERCASE"))
        self.assertIsNotNone(contract)
        self.assertEqual(contract.ordered_values["fields"], ("KEYWORDS", "MODELNAMES", "PARAMETERS"))
        self.assertIn("YES", contract.value_sets["values"])

        contract = DIRECTIVE_CONTRACT_REGISTRY.get(("DRC", "SUMMARY", "REPORT"))
        self.assertIsNotNone(contract)
        self.assertEqual(contract.ordered_values["flags"], ("HIER", "EXECUTED"))

        contract = DIRECTIVE_CONTRACT_REGISTRY.get(("DRC", "RESULTS", "DATABASE"))
        self.assertIsNotNone(contract)
        self.assertIn("STRICT", contract.value_sets["strictness"])

    def test_dialect_profile_registry_matches_packaged_spec(self):
        self.assertEqual(DIALECT_PROFILE_SPEC, load_dialect_profile_spec())

        expected_ast = {
            (
                entry.name,
                entry.node_type,
                tuple(sorted(entry.dialects)),
                entry.family,
                entry.support_level,
                tuple(sorted(entry.tags)),
            )
            for entry in DIALECT_PROFILE_SPEC.ast_entries
        }
        actual_ast = {
            (
                entry.name,
                entry.node_type,
                tuple(sorted(entry.dialects)),
                entry.family,
                entry.support_level,
                tuple(sorted(entry.tags)),
            )
            for entry in DIALECT_PROFILE_REGISTRY.ast_profiles
        }
        self.assertEqual(expected_ast, actual_ast)

        expected_directives = {
            (
                entry.name,
                entry.keywords,
                tuple(sorted(entry.dialects)),
                entry.family,
                entry.support_level,
                tuple(sorted(entry.tags)),
            )
            for entry in DIALECT_PROFILE_SPEC.directive_entries
        }
        actual_directives = {
            (
                entry.name,
                entry.keywords,
                tuple(sorted(entry.dialects)),
                entry.family,
                entry.support_level,
                tuple(sorted(entry.tags)),
            )
            for entry in DIALECT_PROFILE_REGISTRY.directive_profiles
        }
        self.assertEqual(expected_directives, actual_directives)

        expected_operations = {
            (
                entry.name,
                entry.head_prefix,
                tuple(sorted(entry.dialects)),
                entry.family,
                entry.support_level,
                tuple(sorted(entry.tags)),
            )
            for entry in DIALECT_PROFILE_SPEC.operation_entries
        }
        actual_operations = {
            (
                entry.name,
                entry.head_prefix,
                tuple(sorted(entry.dialects)),
                entry.family,
                entry.support_level,
                tuple(sorted(entry.tags)),
            )
            for entry in DIALECT_PROFILE_REGISTRY.operation_profiles
        }
        self.assertEqual(expected_operations, actual_operations)

        entry = DIALECT_PROFILE_REGISTRY.match_directive(("TVF", "FUNCTION"))
        self.assertIsNotNone(entry)
        self.assertEqual(entry.support_level, "limited")
        self.assertIn("embedded_language", entry.tags)

        entry = DIALECT_PROFILE_REGISTRY.match_directive(("PEX", "REPORT", "NETSUMMARY"))
        self.assertIsNotNone(entry)
        self.assertEqual(entry.family, "pex_reporting")

        entry = DIALECT_PROFILE_REGISTRY.match_operation("DFM RDB")
        self.assertIsNotNone(entry)
        self.assertIn("DFM", entry.dialects)

    def test_support_notice_registry_matches_packaged_spec(self):
        self.assertEqual(SUPPORT_NOTICE_SPEC, load_support_notice_spec())
        expected = {
            (
                entry.name,
                entry.feature_name,
                entry.warning_code,
                entry.message,
                entry.category,
                entry.emit_warning,
                tuple(sorted(entry.tags)),
            )
            for entry in SUPPORT_NOTICE_SPEC.entries
        }
        actual = {
            (
                entry.name,
                entry.feature_name,
                entry.warning_code,
                entry.message,
                entry.category,
                entry.emit_warning,
                tuple(sorted(entry.tags)),
            )
            for entry in SUPPORT_NOTICE_REGISTRY.notices
        }
        self.assertEqual(expected, actual)

        entry = SUPPORT_NOTICE_REGISTRY.get("tvf_directive")
        self.assertIsNotNone(entry)
        self.assertTrue(entry.emit_warning)
        self.assertEqual(entry.warning_code, "validation.support.limited_feature")

        entry = SUPPORT_NOTICE_REGISTRY.get("encrypted_block")
        self.assertIsNotNone(entry)
        self.assertFalse(entry.emit_warning)

    def test_manual_exception_registry_matches_packaged_spec(self):
        self.assertEqual(MANUAL_EXCEPTION_SPEC, load_manual_exception_spec())
        expected = {
            (
                entry.name,
                entry.category,
                entry.applies_to,
                entry.effect,
                entry.note,
                entry.manual_refs,
                tuple(sorted(entry.tags)),
            )
            for entry in MANUAL_EXCEPTION_SPEC.entries
        }
        actual = {
            (
                entry.name,
                entry.category,
                entry.applies_to,
                entry.effect,
                entry.note,
                entry.manual_refs,
                tuple(sorted(entry.tags)),
            )
            for entry in MANUAL_EXCEPTION_REGISTRY.entries
        }
        self.assertEqual(expected, actual)
        entry = MANUAL_EXCEPTION_REGISTRY.get("multiword_keyword_atomic")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.effect, "atomic")

    def test_case_sensitivity_registry_matches_packaged_spec(self):
        self.assertEqual(CASE_SENSITIVITY_SPEC, load_case_sensitivity_spec())
        expected = {
            (
                entry.name,
                entry.category,
                entry.case_mode,
                entry.scope,
                entry.note,
                entry.manual_refs,
                tuple(sorted(entry.tags)),
            )
            for entry in CASE_SENSITIVITY_SPEC.entries
        }
        actual = {
            (
                rule.name,
                rule.category,
                rule.case_mode,
                rule.scope,
                rule.note,
                rule.manual_refs,
                tuple(sorted(rule.tags)),
            )
            for rule in CASE_SENSITIVITY_REGISTRY.rules
        }
        self.assertEqual(expected, actual)
        self.assertEqual(
            CASE_SENSITIVITY_REGISTRY.get("filenames_case_sensitive").case_mode,
            "case_sensitive",
        )

    def test_support_matrix_registry_matches_packaged_spec(self):
        self.assertEqual(SUPPORT_MATRIX_SPEC, load_support_matrix_spec())
        expected = {
            (
                entry.name,
                tuple(sorted(entry.dialects)),
                entry.feature_family,
                entry.support_level,
                entry.parser_support,
                entry.semantic_support,
                entry.note,
                entry.manual_refs,
                tuple(sorted(entry.tags)),
            )
            for entry in SUPPORT_MATRIX_SPEC.entries
        }
        actual = {
            (
                entry.name,
                tuple(sorted(entry.dialects)),
                entry.feature_family,
                entry.support_level,
                entry.parser_support,
                entry.semantic_support,
                entry.note,
                entry.manual_refs,
                tuple(sorted(entry.tags)),
            )
            for entry in SUPPORT_MATRIX_REGISTRY.entries
        }
        self.assertEqual(expected, actual)
        entry = SUPPORT_MATRIX_REGISTRY.get("encrypted_block")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.support_level, "opaque")

    def test_symbol_convention_registry_matches_packaged_spec(self):
        self.assertEqual(SYMBOL_CONVENTION_SPEC, load_symbol_convention_spec())
        expected = {
            (
                entry.name,
                entry.category,
                entry.values,
                entry.note,
                entry.manual_refs,
                tuple(sorted(entry.tags)),
            )
            for entry in SYMBOL_CONVENTION_SPEC.entries
        }
        actual = {
            (
                entry.name,
                entry.category,
                entry.values,
                entry.note,
                entry.manual_refs,
                tuple(sorted(entry.tags)),
            )
            for entry in SYMBOL_CONVENTION_REGISTRY.entries
        }
        self.assertEqual(expected, actual)
        self.assertIn("BY", SYMBOL_CONVENTION_REGISTRY.scalar_tuple_heads)
        self.assertEqual((), SYMBOL_CONVENTION_REGISTRY.companion_file_suffixes)

    def test_manual_source_overrides_drive_packaged_aliases_and_function_names(self):
        doc_root_env = os.environ.get("SVRF_MANUAL_ROOT")
        if not doc_root_env:
            self.skipTest("SVRF_MANUAL_ROOT is not set")
        doc_root = Path(doc_root_env)
        if not doc_root.exists():
            self.skipTest("SVRF_MANUAL_ROOT does not exist")
        known_keywords = build_known_keyword_inventory(
            KEYWORD_SPEC.keyword_registry,
            directive_secondary_words=PARSER_SPEC.table("directive_secondary_words"),
            modifier_starters=PARSER_SPEC.table("modifier_starters"),
            generic_prefix_ops=PARSER_SPEC.table("generic_prefix_ops"),
            measurement_ops=PARSER_SPEC.table("measurement_ops"),
            edge_binary_prefix_ops=PARSER_SPEC.table("edge_binary_prefix_ops"),
            not_compound_ops=PARSER_SPEC.table("not_compound_ops"),
            with_secondary_ops=PARSER_SPEC.table("with_secondary_ops"),
            function_like_names=build_function_like_names(doc_root),
        )
        aliases, _ = build_keyword_aliases(doc_root, known_keywords)
        self.assertEqual(dict(KEYWORD_SPEC.keyword_aliases), aliases)
        self.assertEqual(
            PARSER_SPEC.family("doc_math_function_names"),
            build_doc_math_function_names(doc_root),
        )
        self.assertEqual(
            PARSER_SPEC.family("doc_string_function_names"),
            build_doc_string_function_names(doc_root),
        )
        self.assertEqual(
            PARSER_SPEC.family("doc_dfm_function_names"),
            build_doc_dfm_function_names(doc_root),
        )
        self.assertEqual(
            PARSER_SPEC.family("doc_all_function_names"),
            build_doc_all_function_names(doc_root),
        )
        self.assertEqual(
            PARSER_SPEC.table("function_like_names"),
            build_function_like_names(doc_root),
        )


if __name__ == "__main__":
    unittest.main()
