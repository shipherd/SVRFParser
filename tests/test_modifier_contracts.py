"""Typed modifier compatibility and shared operation contract regressions."""

import unittest

from svrf_parser import ast, parse, validate_svrf
from svrf_parser.expression_contexts import LITERAL_STRING, SCALAR_EXPRESSION, annotate_expression_contexts
from svrf_parser.modifiers import NamedModifier, RawModifier, as_modifier
from svrf_parser.operation_cst import OperationCst
from svrf_parser.operation_normalizer import normalize_operation_cst
from svrf_parser.operation_schema import OPERATION_SCHEMA_REGISTRY
from svrf_parser.printer import SvrfPrinter
from svrf_parser.semantic import validate_semantics
from svrf_parser.semantic_drc_rules import DRCOP_MIN_CONSTRAINTS, DRCOP_MIN_MODIFIERS, DRCOP_MIN_OPERANDS
from svrf_parser.svrf_spec import OPERATION_SCHEMA_SPEC


class TypedModifierTests(unittest.TestCase):
    def test_parser_exposes_legacy_by_tuple_and_typed_view(self):
        node = parse("TMP = SIZE M1 BY 0.1\n").statements[0].expression
        self.assertIsInstance(node.modifiers[0], tuple)
        self.assertIsInstance(node.modifier_nodes[0], NamedModifier)
        self.assertEqual("BY", node.modifier_nodes[0].name)
        self.assertIs(node.modifiers[0][1], node.modifier_nodes[0].value)

    def test_expression_modifier_path_also_preserves_legacy_tuples(self):
        node = parse("TMP = M1 INTERACT M2 > 1 BY NET\n").statements[0].expression
        self.assertIsInstance(node.modifiers[0], tuple)
        self.assertEqual("literal", node.modifier_nodes[0].context())

    def test_constructor_adapts_typed_modifiers(self):
        value = ast.NumberLiteral(value=1)
        for constructor in (ast.DRCOp, ast.ConstrainedExpr):
            with self.subTest(constructor=constructor.__name__):
                node = constructor(modifiers=[NamedModifier("BY", value), RawModifier("ABUT")])
                self.assertEqual([("BY", value), "ABUT"], node.modifiers)

    def test_operation_cst_accepts_typed_modifiers(self):
        value = ast.NumberLiteral(value=1)
        node = normalize_operation_cst(OperationCst("SIZE", modifiers=(NamedModifier("BY", value),)), location={})
        self.assertEqual([("BY", value)], node.modifiers)

    def test_view_reflects_mutations_of_legacy_list(self):
        node = ast.DRCOp(modifiers=["ABUT"])
        node.modifiers.append(("BY", ast.NumberLiteral(value=2)))
        self.assertEqual(2, len(node.modifier_nodes))
        self.assertIsInstance(node.modifier_nodes[1], NamedModifier)

    def test_view_handles_empty_optional_list(self):
        node = ast.DRCOp()
        node.modifiers = None
        self.assertEqual((), node.modifier_nodes)

    def test_typed_view_does_not_change_serialized_ast_fields(self):
        node = ast.DRCOp(modifiers=[NamedModifier("BY", ast.NumberLiteral(value=1))])
        payload = node.to_dict(include_position=False)
        self.assertNotIn("modifier_nodes", payload)
        self.assertEqual("BY", payload["modifiers"][0][0])
        self.assertEqual("NumberLiteral", payload["modifiers"][0][1]["type"])

    def test_walk_visits_modifier_expressions_once(self):
        value = ast.NumberLiteral(value=1)
        node = ast.DRCOp(modifiers=[NamedModifier("BY", value)])
        self.assertEqual([node, value], list(node.walk()))

    def test_scalar_modifier_context_is_shared_with_validation(self):
        for name in ("BY", "STEP", "WINDOW", "SCALE", "LENGTH", "WIDTH", "SIZE BY"):
            with self.subTest(name=name):
                value = ast.LayerRef(name="MISSING_LIMIT")
                node = ast.DRCOp(op="SIZE", modifiers=[(name, value)])
                program = ast.Program(statements=[node])
                annotations = annotate_expression_contexts(program)
                self.assertIn(SCALAR_EXPRESSION, annotations.get(value))
                self.assertEqual(["semantic.reference.scalar_undefined"],
                                 [d.code for d in validate_semantics(program)])

    def test_by_net_is_annotated_as_literal_mode(self):
        program = parse("TMP = M1 INTERACT M2 > 1 BY NET\n")
        value = program.statements[0].expression.modifiers[0][1]
        annotations = annotate_expression_contexts(program)
        self.assertIn(LITERAL_STRING, annotations.get(value))
        self.assertNotIn(SCALAR_EXPRESSION, annotations.get(value))

    def test_quoted_net_remains_a_symbol_not_a_mode(self):
        value = ast.StringLiteral(value="NET")
        modifier = NamedModifier("BY", value)
        self.assertEqual("scalar", modifier.context())

    def test_adapter_keeps_raw_modifiers_unchanged(self):
        for value in ("REGION EXTENTS", 3, ast.Constraint(op="<", value=ast.NumberLiteral(value=1))):
            with self.subTest(value=value):
                self.assertIs(value, as_modifier(value).to_legacy())

    def test_printer_renders_named_modifiers_without_python_tuple_repr(self):
        node = ast.DRCOp(op="SIZE", modifiers=[("WINDOW", ast.NumberLiteral(value=2))])
        self.assertEqual("SIZE WINDOW 2", SvrfPrinter().emit(node))

    def test_arithmetic_by_roundtrip_is_structurally_equal(self):
        program = parse("TMP = SIZE M1 BY 1 + 2 * 3\n", strict=True)
        printed = SvrfPrinter().emit(program)
        reparsed = parse(printed, strict=True)
        self.assertTrue(program.structurally_equal(reparsed), printed)

    def test_raw_expression_modifier_keeps_existing_rendering(self):
        expression = ast.BinaryOp(op="=", left=ast.LayerRef(name="P"), right=ast.NumberLiteral(value=1))
        node = ast.DRCOp(op="DFM PROPERTY", modifiers=[expression])
        self.assertEqual("DFM PROPERTY P = 1", SvrfPrinter().emit(node))


class SharedOperationContractTests(unittest.TestCase):
    def test_registry_uses_packaged_contracts(self):
        self.assertEqual({entry.name: entry for entry in OPERATION_SCHEMA_SPEC.contracts},
                         OPERATION_SCHEMA_REGISTRY.contracts)

    def test_semantic_requirements_are_derived_from_the_registry(self):
        for name, contract in OPERATION_SCHEMA_REGISTRY.contracts.items():
            with self.subTest(name=name):
                self.assertEqual(contract.min_operands, DRCOP_MIN_OPERANDS.get(name))
                self.assertEqual(contract.min_constraints, DRCOP_MIN_CONSTRAINTS.get(name))
                self.assertEqual(contract.min_modifiers, DRCOP_MIN_MODIFIERS.get(name))

    def test_operand_roles_distinguish_cell_names_from_layers(self):
        for name in ("INSIDE CELL", "OUTSIDE CELL", "OUT CELL", "NOT INSIDE CELL", "NOT OUTSIDE CELL", "NOT OUT CELL"):
            with self.subTest(name=name):
                self.assertEqual("layer", OPERATION_SCHEMA_REGISTRY.operand_role(name, 0, 2))
                self.assertEqual("literal", OPERATION_SCHEMA_REGISTRY.operand_role(name, 1, 2))

    def test_with_text_single_filter_role_is_literal(self):
        self.assertEqual("literal", OPERATION_SCHEMA_REGISTRY.operand_role("WITH TEXT", 0, 1))
        self.assertEqual("layer", OPERATION_SCHEMA_REGISTRY.operand_role("WITH TEXT", 0, 2))
        self.assertEqual("literal", OPERATION_SCHEMA_REGISTRY.operand_role("WITH TEXT", 1, 2))

    def test_literal_filter_does_not_emit_symbol_diagnostics(self):
        program = parse('LAYER M1 1\nTMP = INSIDE CELL M1 "cell-name"\n', strict=True)
        self.assertEqual("INSIDE CELL", program.statements[1].expression.op)
        self.assertEqual([], validate_semantics(program, strict=True))

    def test_unquoted_literal_filter_is_not_resolved_as_a_layer(self):
        program = parse("LAYER M1 1\nTMP = INSIDE CELL M1 CELL_NAME\n", strict=True)
        self.assertEqual("INSIDE CELL", program.statements[1].expression.op)
        self.assertEqual([], validate_semantics(program, strict=True))

    def test_negated_cell_filter_uses_the_same_literal_roles(self):
        program = parse("LAYER M1 1\nTMP = NOT INSIDE CELL M1 CELL_NAME\n", strict=True)
        self.assertEqual("NOT INSIDE CELL", program.statements[1].expression.op)
        self.assertEqual([], validate_semantics(program, strict=True))

    def test_declared_keyword_shaped_variable_is_not_skipped(self):
        program = ast.Program(statements=[
            ast.VariableDef(name="OTHER", values=[ast.LayerRef(name="WIDTH")]),
            ast.VariableDef(name="WIDTH", values=[ast.NumberLiteral(value=1)]),
        ])
        self.assertEqual(["semantic.variable.before_definition"],
                         [d.code for d in validate_semantics(program)])

    def test_unknown_contract_keeps_conservative_fallback(self):
        self.assertIsNone(OPERATION_SCHEMA_REGISTRY.contract_for("FUTURE OP"))
        self.assertIsNone(OPERATION_SCHEMA_REGISTRY.operand_role("FUTURE OP", 0, 1))

    def test_keyword_shaped_macro_name_is_not_part_of_statement_head(self):
        tree = parse("DMACRO CHECK A { COPY A }\nCMACRO CHECK M1\n", strict=True)
        self.assertEqual("CHECK", tree.statements[1].name)
        self.assertEqual("M1", tree.statements[1].arguments[0].name)
        result = validate_svrf("DMACRO CHECK A { COPY A }\nCMACRO CHECK M1\n", strict=True)
        self.assertTrue(result.valid, result.diagnostics)

    def test_keyword_shaped_group_name_is_not_part_of_statement_head(self):
        node = parse("GROUP CHECK M1\n", strict=True).statements[0]
        self.assertEqual("CHECK", node.name)
        self.assertEqual(["M1"], node.members)

    def test_keyword_shaped_connect_operand_is_not_part_of_statement_head(self):
        node = parse("CONNECT CHECK M1\n", strict=True).statements[0]
        self.assertEqual(["CHECK", "M1"], node.layers)


if __name__ == "__main__":
    unittest.main()
