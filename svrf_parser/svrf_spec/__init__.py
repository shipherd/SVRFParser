"""Manual-backed spec artifacts for the SVRF parser.

This package is the bootstrap home for parser spec data that should not live as
scattered Python constants. The current JSON payloads are generated from the
repository's existing doc-backed tables and form the first step toward a more
explicit, reviewable language specification layer.
"""

from .loader import (
    AstDialectProfileEntrySpec,
    CaseSensitivityRuleEntrySpec,
    CaseSensitivitySpec,
    DialectProfileSpec,
    DirectiveContractEntrySpec,
    DirectiveContractSpec,
    DirectiveDialectProfileEntrySpec,
    KeywordSpec,
    ManualExceptionEntrySpec,
    ManualExceptionSpec,
    LedExpressionSchemaEntrySpec,
    LedExpressionSchemaSpec,
    OperationDialectProfileEntrySpec,
    OperationContractEntrySpec,
    OperationSchemaEntrySpec,
    OperationSchemaSpec,
    ParserSpec,
    PrefixExpressionSchemaEntrySpec,
    PrefixExpressionSchemaSpec,
    PreprocessorSchemaEntrySpec,
    PreprocessorSchemaSpec,
    SupportMatrixEntrySpec,
    SupportMatrixSpec,
    StatementSchemaEntrySpec,
    StatementSchemaSpec,
    StatementShapeEntrySpec,
    StatementShapeSpec,
    SymbolConventionEntrySpec,
    SymbolConventionSpec,
    SupportNoticeEntrySpec,
    SupportNoticeSpec,
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


KEYWORD_SPEC = load_keyword_spec()
PARSER_SPEC = load_parser_spec()
STATEMENT_SCHEMA_SPEC = load_statement_schema_spec()
OPERATION_SCHEMA_SPEC = load_operation_schema_spec()
PREPROCESSOR_SCHEMA_SPEC = load_preprocessor_schema_spec()
PREFIX_EXPRESSION_SCHEMA_SPEC = load_prefix_expression_schema_spec()
LED_EXPRESSION_SCHEMA_SPEC = load_led_expression_schema_spec()
STATEMENT_SHAPE_SPEC = load_statement_shape_spec()
DIRECTIVE_CONTRACT_SPEC = load_directive_contract_spec()
DIALECT_PROFILE_SPEC = load_dialect_profile_spec()
SUPPORT_NOTICE_SPEC = load_support_notice_spec()
MANUAL_EXCEPTION_SPEC = load_manual_exception_spec()
CASE_SENSITIVITY_SPEC = load_case_sensitivity_spec()
SUPPORT_MATRIX_SPEC = load_support_matrix_spec()
SYMBOL_CONVENTION_SPEC = load_symbol_convention_spec()

__all__ = [
    "CASE_SENSITIVITY_SPEC",
    "DIALECT_PROFILE_SPEC",
    "DIRECTIVE_CONTRACT_SPEC",
    "KEYWORD_SPEC",
    "LED_EXPRESSION_SCHEMA_SPEC",
    "MANUAL_EXCEPTION_SPEC",
    "OPERATION_SCHEMA_SPEC",
    "PARSER_SPEC",
    "PREFIX_EXPRESSION_SCHEMA_SPEC",
    "PREPROCESSOR_SCHEMA_SPEC",
    "STATEMENT_SCHEMA_SPEC",
    "STATEMENT_SHAPE_SPEC",
    "SUPPORT_MATRIX_SPEC",
    "SUPPORT_NOTICE_SPEC",
    "SYMBOL_CONVENTION_SPEC",
    "AstDialectProfileEntrySpec",
    "CaseSensitivityRuleEntrySpec",
    "CaseSensitivitySpec",
    "DialectProfileSpec",
    "DirectiveContractEntrySpec",
    "DirectiveContractSpec",
    "DirectiveDialectProfileEntrySpec",
    "KeywordSpec",
    "ManualExceptionEntrySpec",
    "ManualExceptionSpec",
    "LedExpressionSchemaEntrySpec",
    "LedExpressionSchemaSpec",
    "OperationSchemaEntrySpec",
    "OperationContractEntrySpec",
    "OperationSchemaSpec",
    "OperationDialectProfileEntrySpec",
    "ParserSpec",
    "PrefixExpressionSchemaEntrySpec",
    "PrefixExpressionSchemaSpec",
    "PreprocessorSchemaEntrySpec",
    "PreprocessorSchemaSpec",
    "StatementSchemaEntrySpec",
    "StatementSchemaSpec",
    "StatementShapeEntrySpec",
    "StatementShapeSpec",
    "SupportMatrixEntrySpec",
    "SupportMatrixSpec",
    "SymbolConventionEntrySpec",
    "SymbolConventionSpec",
    "SupportNoticeEntrySpec",
    "SupportNoticeSpec",
    "load_case_sensitivity_spec",
    "load_directive_contract_spec",
    "load_dialect_profile_spec",
    "load_keyword_spec",
    "load_led_expression_schema_spec",
    "load_manual_exception_spec",
    "load_operation_schema_spec",
    "load_parser_spec",
    "load_prefix_expression_schema_spec",
    "load_preprocessor_schema_spec",
    "load_statement_schema_spec",
    "load_statement_shape_spec",
    "load_support_matrix_spec",
    "load_support_notice_spec",
    "load_symbol_convention_spec",
]
