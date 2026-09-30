"""Branch isolation and conservative symbol availability regressions."""

import unittest

from svrf_parser import ast, parse, validate_svrf
from svrf_parser.semantic import validate_semantics
from svrf_parser.semantic_symbols import SymbolTable, ValidationScope, build_symbol_table
from svrf_parser.diagnostic_postprocess import summarize_conditional_references
from svrf_parser.diagnostics import Diagnostic
from svrf_parser.symbol_availability import Availability, guarded_availability
from audit_sample_corpus import classify_diagnostic


class GuardedAvailabilityTests(unittest.TestCase):
    def test_empty_and_unconditional_definitions(self):
        self.assertEqual(Availability.ABSENT, guarded_availability([], ()))
        self.assertEqual(Availability.DEFINITE, guarded_availability([()], ()))

    def test_exclusive_guard_is_unavailable(self):
        self.assertEqual(Availability.UNAVAILABLE, guarded_availability([((1, True),)], ((1, False),)))

    def test_selected_guard_is_definite(self):
        self.assertEqual(Availability.DEFINITE, guarded_availability([((1, True),)], ((1, True),)))

    def test_unselected_guard_is_conditional(self):
        self.assertEqual(Availability.CONDITIONAL, guarded_availability([((1, True),)], ()))

    def test_both_arms_cover_parent(self):
        paths = [((1, True),), ((1, False),)]
        self.assertEqual(Availability.DEFINITE, guarded_availability(paths, ()))

    def test_nested_alternatives_cover_parent(self):
        paths = [((1, True), (2, True)), ((1, True), (2, False)), ((1, False),)]
        self.assertEqual(Availability.DEFINITE, guarded_availability(paths, ()))

    def test_incomplete_nested_alternatives_are_conditional(self):
        paths = [((1, True), (2, True)), ((1, False),)]
        self.assertEqual(Availability.CONDITIONAL, guarded_availability(paths, ()))

    def test_explicit_unconditional_symbol_tables_remain_supported(self):
        table = SymbolTable(variables={"LIMIT": ast.VariableDef(name="LIMIT")})
        self.assertEqual(Availability.DEFINITE, table.availability(("variables",), "limit"))

    def test_explicit_conditional_symbol_tables_remain_conservative(self):
        table = SymbolTable(conditional_layers={"M1"})
        self.assertEqual(Availability.CONDITIONAL, table.availability(("layers",), "m1"))

    def test_summarizing_preserves_distinct_include_stacks_and_contexts(self):
        notices = [Diagnostic("warning", "semantic.reference.conditional", "Conditional M1",
                              filename="shared.svrf", include_stack=stack,
                              metadata={"symbol": "M1", "reference_context": context})
                   for stack, context in (((), "scalar"), (("root.svrf",), "scalar"), ((), "layer"))]
        self.assertEqual(notices, summarize_conditional_references(notices))


class ConditionalSymbolTests(unittest.TestCase):
    def diagnostics(self, text, **kwargs):
        return validate_semantics(parse(text), **kwargs)

    def codes(self, text, **kwargs):
        return {diag.code for diag in self.diagnostics(text, **kwargs)}

    def test_variable_does_not_leak_from_then_to_else(self):
        text = "#IFDEF FEATURE\nVARIABLE LIMIT 1\n#ELSE\nVARIABLE OTHER LIMIT\n#ENDIF\n"
        diags = self.diagnostics(text)
        self.assertEqual(["semantic.reference.unavailable_branch"], [diag.code for diag in diags])
        self.assertEqual(4, diags[0].line)
        self.assertEqual("LIMIT", diags[0].metadata["symbol"])

    def test_variable_does_not_leak_from_else_to_then(self):
        text = "#IFDEF FEATURE\nVARIABLE OTHER LIMIT\n#ELSE\nVARIABLE LIMIT 1\n#ENDIF\n"
        self.assertEqual({"semantic.reference.unavailable_branch"}, self.codes(text))

    def test_ifndef_has_same_isolation(self):
        text = "#IFNDEF FEATURE\nVARIABLE LIMIT 1\n#ELSE\nVARIABLE OTHER LIMIT\n#ENDIF\n"
        self.assertEqual({"semantic.reference.unavailable_branch"}, self.codes(text))

    def test_conditional_variable_after_join_is_not_definite(self):
        text = "#IFDEF FEATURE\nVARIABLE LIMIT 1\n#ENDIF\nVARIABLE OTHER LIMIT\n"
        self.assertEqual({"semantic.reference.conditional"}, self.codes(text))

    def test_variable_defined_in_all_branches_is_definite_after_join(self):
        text = "#IFDEF FEATURE\nVARIABLE LIMIT 1\n#ELSE\nVARIABLE LIMIT 2\n#ENDIF\nVARIABLE OTHER LIMIT\n"
        self.assertEqual(set(), self.codes(text, strict=True))

    def test_outer_variable_remains_definite_after_partial_redefinition(self):
        text = "VARIABLE LIMIT 1\n#IFDEF FEATURE\nVARIABLE LIMIT 2\n#ENDIF\nVARIABLE OTHER LIMIT\n"
        self.assertEqual(set(), self.codes(text, strict=True))

    def test_order_is_checked_inside_compatible_branch(self):
        text = "#IFDEF FEATURE\nVARIABLE OTHER LIMIT\nVARIABLE LIMIT 1\n#ENDIF\n"
        self.assertEqual({"semantic.variable.before_definition"}, self.codes(text))

    def test_variables_still_enter_in_source_order_after_join(self):
        text = "VARIABLE OTHER LIMIT\n#IFDEF FEATURE\nVARIABLE LIMIT 1\n#ELSE\nVARIABLE LIMIT 2\n#ENDIF\n"
        self.assertEqual({"semantic.variable.before_definition"}, self.codes(text))

    def test_forward_layer_is_visible_in_its_own_branch(self):
        text = "#IFDEF FEATURE\nCOPY M1\nLAYER M1 1\n#ENDIF\n"
        self.assertEqual(set(), self.codes(text, strict=True))

    def test_forward_layer_is_not_visible_in_exclusive_branch(self):
        text = "#IFDEF FEATURE\nCOPY M1\n#ELSE\nLAYER M1 1\n#ENDIF\n"
        self.assertEqual({"semantic.reference.unavailable_branch"}, self.codes(text))

    def test_layer_defined_in_all_branches_allows_forward_reference(self):
        text = "COPY M1\n#IFDEF FEATURE\nLAYER M1 1\n#ELSE\nLAYER M1 2\n#ENDIF\n"
        self.assertEqual(set(), self.codes(text, strict=True))

    def test_nested_partial_definition_is_conditional_after_outer_join(self):
        text = "#IFDEF A\n#IFDEF B\nVARIABLE LIMIT 1\n#ENDIF\n#ELSE\nVARIABLE LIMIT 2\n#ENDIF\nVARIABLE OTHER LIMIT\n"
        self.assertEqual({"semantic.reference.conditional"}, self.codes(text))

    def test_conditional_macro_is_reported_outside_its_branch(self):
        text = "#IFDEF FEATURE\nDMACRO CHECK A {}\n#ENDIF\nCMACRO CHECK M1\n"
        self.assertEqual({"semantic.reference.conditional"}, self.codes(text))

    def test_macro_forward_reference_inside_its_branch_remains_valid(self):
        text = "#IFDEF FEATURE\nCMACRO CHECK M1\nDMACRO CHECK A { COPY A }\n#ENDIF\n"
        self.assertEqual(set(), self.codes(text, strict=True))

    def test_rule_placeholders_do_not_predeclare_conditional_assignments(self):
        text = "LAYER M1 1\nR {\n#IFDEF FEATURE\nTMP = COPY M1\n#ELSE\nCOPY TMP\n#ENDIF\n}\n"
        self.assertIn("semantic.reference.local_scope_only", self.codes(text))

    def test_runtime_if_scopes_are_joined_only_after_all_arms(self):
        conditional = ast.IfExpr(
            condition=ast.NumberLiteral(value=1),
            then_body=[ast.VariableDef(name="LIMIT", values=[ast.NumberLiteral(value=1)])],
            else_body=[ast.VariableDef(name="OTHER", values=[ast.LayerRef(name="LIMIT")])],
        )
        diags = validate_semantics(ast.Program(statements=[conditional]))
        self.assertEqual(["semantic.reference.scalar_undefined"], [diag.code for diag in diags])

    def test_runtime_if_without_else_has_an_empty_alternative(self):
        program = ast.Program(statements=[
            ast.IfExpr(condition=ast.NumberLiteral(value=1), then_body=[
                ast.VariableDef(name="LIMIT", values=[ast.NumberLiteral(value=1)])]),
            ast.VariableDef(name="OTHER", values=[ast.LayerRef(name="LIMIT")]),
        ])
        self.assertEqual(["semantic.reference.conditional"], [d.code for d in validate_semantics(program)])

    def test_strict_promotes_conditional_finding(self):
        text = "#IFDEF FEATURE\nVARIABLE LIMIT 1\n#ENDIF\nVARIABLE OTHER LIMIT\n"
        result = validate_svrf(text, strict=True, unresolved_policy="practical",
                               symbol_manifest={"scalar_parameters": ["LIMIT"]})
        self.assertFalse(result.valid)
        self.assertEqual(["semantic.reference.conditional"], [d.code for d in result.errors])

    def test_conditional_symbols_are_not_preloaded_as_definite(self):
        table, _ = build_symbol_table(parse("#IFDEF FEATURE\nLAYER M1 1\n#ENDIF\n").statements)
        scope = ValidationScope.from_symbol_table(table)
        self.assertFalse(scope.knows_layer_like("M1"))
        self.assertEqual(Availability.CONDITIONAL, scope.availability(("layers",), "m1"))

    def test_practical_mode_groups_notices_without_manifest_suppression(self):
        text = "#IFDEF FEATURE\nLAYER M1 1\n#ENDIF\nA = COPY M1\nB = COPY M1\n"
        result = validate_svrf(text, unresolved_policy="practical", symbol_manifest={"layer_like_symbols": ["M1"]})
        notices = [d for d in result.warnings if d.code == "semantic.reference.conditional"]
        self.assertEqual(1, len(notices))
        self.assertEqual(2, notices[0].metadata["occurrence_count"])
        self.assertEqual(4, notices[0].line)
        self.assertEqual("semantic_conditional_symbol", classify_diagnostic(notices[0]))
        self.assertEqual(0, result.policy_summary.manifest_resolved_count)

    def test_strict_mode_keeps_all_conditional_findings(self):
        text = "#IFDEF FEATURE\nLAYER M1 1\n#ENDIF\nA = COPY M1\nB = COPY M1\n"
        result = validate_svrf(text, strict=True, unresolved_policy="practical")
        notices = [d for d in result.errors if d.code == "semantic.reference.conditional"]
        self.assertEqual(2, len(notices))

    def test_strict_policy_keeps_all_notices_without_promoting_severity(self):
        text = "#IFDEF FEATURE\nLAYER M1 1\n#ENDIF\nA = COPY M1\nB = COPY M1\n"
        result = validate_svrf(text, unresolved_policy="strict")
        self.assertEqual(2, len(result.warnings))
        self.assertEqual([], result.errors)


if __name__ == "__main__":
    unittest.main()
