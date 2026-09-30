"""Synthetic regressions for operation and specification forms in rule decks."""

import unittest

from svrf_parser import ast, parse_with_diagnostics, validate_svrf
from svrf_parser.printer import SvrfPrinter
from tests.helpers import ast_equal


class DeckSyntaxTestCase(unittest.TestCase):
    def parse_clean(self, source):
        program, diagnostics = parse_with_diagnostics(source, strict=True)
        self.assertEqual([], diagnostics)
        self.assertFalse(any(isinstance(node, ast.ErrorNode) for node in program.walk()))
        return program

    def assert_roundtrip(self, source):
        program = self.parse_clean(source)
        emitted = SvrfPrinter().emit(program)
        reparsed = self.parse_clean(emitted)
        self.assertTrue(ast_equal(program, reparsed), emitted)


class SelectionSyntaxTests(DeckSyntaxTestCase):
    def test_infix_cell_filter_remains_inside_parenthesized_assignment(self):
        program = self.parse_clean('R { A = (M1 INSIDE CELL "*" CIRCLE) INTERACT M2\nCOPY A }')
        rule = program.statements[0]
        self.assertEqual(2, len(rule.body))
        selection = rule.body[0].expression.left
        self.assertEqual("INSIDE CELL", selection.op)
        self.assertEqual("M1", selection.operands[0].name)
        self.assertEqual("*", selection.operands[1].value)
        self.assertEqual(["CIRCLE"], selection.modifiers)

    def test_prefix_and_infix_cell_filters_have_identical_structure(self):
        prefix = self.parse_clean('A = INSIDE CELL M1 "cell*" CIRCLE').statements[0].expression
        infix = self.parse_clean('A = M1 INSIDE CELL "cell*" CIRCLE').statements[0].expression
        self.assertTrue(ast_equal(prefix, infix))

    def test_negated_cell_filters_keep_shape_modifiers(self):
        for source in ('NOT INSIDE CELL M1 "cell*" CIRCLE', 'M1 NOT INSIDE CELL "cell*" CIRCLE'):
            with self.subTest(source=source):
                selection = self.parse_clean('A = ' + source).statements[0].expression
                self.assertEqual("NOT INSIDE CELL", selection.op)
                self.assertEqual(["CIRCLE"], selection.modifiers)

    def test_quoted_shape_keyword_is_a_cell_name(self):
        selection = self.parse_clean('A = INSIDE CELL M1 "CIRCLE" CIRCLE').statements[0].expression
        self.assertEqual("CIRCLE", selection.operands[1].value)
        self.assertEqual(["CIRCLE"], selection.modifiers)

    def test_cell_selector_roundtrip(self):
        self.assert_roundtrip('A = (M1 INSIDE CELL "*" CIRCLE) INTERACT M2')

    def test_unquoted_cell_names_preserve_case(self):
        for operation in ('INSIDE CELL', 'NOT INSIDE CELL'):
            with self.subTest(operation=operation):
                source = f'A = {operation} M1 CellCase OtherCell CIRCLE'
                selection = self.parse_clean(source).statements[0].expression
                self.assertEqual(["CellCase", "OtherCell"], [operand.name for operand in selection.operands[1:]])
                self.assert_roundtrip(source)

    def test_unquoted_case_sensitive_text_name_is_not_uppercased(self):
        source = 'A = M1 WITH TEXT TextCase CASE SENSITIVE'
        selection = self.parse_clean(source).statements[0].expression
        self.assertIsInstance(selection.operands[1], ast.LayerRef)
        self.assertEqual("TextCase", selection.operands[1].name)
        self.assertEqual(["CASE", "SENSITIVE"], selection.modifiers)
        self.assert_roundtrip(source)

    def test_text_variable_name_remains_unquoted(self):
        source = 'VARIABLE TextNames "abc" "def"\nA = M1 WITH TEXT TextNames'
        program = self.parse_clean(source)
        selection = program.statements[1].expression
        self.assertIsInstance(selection.operands[1], ast.LayerRef)
        self.assertEqual("TextNames", selection.operands[1].name)
        self.assertIn('WITH TEXT M1 TextNames', SvrfPrinter().emit(program))
        self.assert_roundtrip(source)

    def test_unique_is_a_modifier_not_a_text_layer(self):
        for operation in ('WITH TEXT', 'NOT WITH TEXT'):
            with self.subTest(operation=operation):
                source = f'A = M1 {operation} "abc" UNIQUE'
                selection = self.parse_clean(source).statements[0].expression
                self.assertEqual(2, len(selection.operands))
                self.assertEqual(["UNIQUE"], selection.modifiers)
                self.assert_roundtrip(source)
                result = validate_svrf('LAYER M1 1\n' + source)
                self.assertEqual([], [d for d in result.diagnostics if d.code == "semantic.reference.undefined"])

    def test_chained_not_with_text_retains_both_filters_and_text_layers(self):
        selection = self.parse_clean('R { (M1 NOT WITH TEXT ? LABELS) NOT WITH TEXT ? TOP_LABELS }').statements[0].body[0]
        self.assertEqual("NOT WITH TEXT", selection.op)
        self.assertEqual("NOT WITH TEXT", selection.operands[0].op)
        self.assertEqual("?", selection.operands[1].value)
        self.assertEqual("TOP_LABELS", selection.operands[2].name)
        self.assertEqual("LABELS", selection.operands[0].operands[2].name)

    def test_unquoted_question_mark_patterns_are_not_ternaries(self):
        for pattern in ('?', '??', 'V?DD', '?power?', '123?'):
            with self.subTest(pattern=pattern):
                expression = self.parse_clean('A = M1 WITH TEXT ' + pattern + ' LABELS').statements[0].expression
                self.assertEqual(pattern, expression.operands[1].value)
                self.assertEqual("LABELS", expression.operands[2].name)

    def test_prefix_text_selection_and_negation(self):
        for operation in ('WITH TEXT', 'NOT WITH TEXT'):
            with self.subTest(operation=operation):
                expression = self.parse_clean('A = ' + operation + ' M1 ? LABELS').statements[0].expression
                self.assertEqual(operation, expression.op)
                self.assertEqual(3, len(expression.operands))

    def test_text_filter_is_literal_but_text_layer_is_a_reference(self):
        result = validate_svrf('LAYER M1 1\nA = M1 NOT WITH TEXT ? MISSING\n')
        undefined = [d for d in result.warnings if d.code == "semantic.reference.undefined"]
        self.assertEqual(["MISSING"], [d.metadata["symbol"] for d in undefined])

    def test_text_selection_roundtrip(self):
        self.assert_roundtrip('A = (M1 NOT WITH TEXT ? LABELS) NOT WITH TEXT V?DD TOP_LABELS')


class ReorderedBooleanTests(DeckSyntaxTestCase):
    def test_primary_keyword_can_follow_multiple_operands(self):
        for operation in ('OR', 'AND', 'XOR'):
            with self.subTest(operation=operation):
                prefix = self.parse_clean(f'A = {operation} M1 M2 M3').statements[0].expression
                reordered = self.parse_clean(f'A = (M1 M2 {operation} M3)').statements[0].expression
                self.assertTrue(ast_equal(prefix, reordered))

    def test_postfix_boolean(self):
        expression = self.parse_clean('A = (M1 M2 OR)').statements[0].expression
        self.assertEqual("OR", expression.op)
        self.assertEqual("M1", expression.left.name)
        self.assertEqual("M2", expression.right.name)

    def test_one_layer_merge_does_not_discard_the_operation(self):
        for source in ('A = OR M1', 'A = (M1 OR)'):
            with self.subTest(source=source):
                operation = self.parse_clean(source).statements[0].expression
                self.assertIsInstance(operation, ast.UnaryOp)
                self.assertEqual("OR", operation.op)
                self.assertEqual("M1", operation.operand.name)
                self.assert_roundtrip(source)

    def test_boolean_with_nested_operands(self):
        self.assert_roundtrip('R { COPY ((SIZE M1 BY 0.1) M2 OR M3) }')

    def test_adjacent_operands_without_a_primary_keyword_are_not_accepted(self):
        _, diagnostics = parse_with_diagnostics('R { COPY (M1 M2) }')
        self.assertTrue(diagnostics)

    def test_boolean_does_not_consume_the_next_assignment(self):
        program = self.parse_clean('A = (M1 M2 OR M3)\nB = OR M4 M5\n')
        self.assertEqual(["A", "B"], [node.name for node in program.statements])


class PercSelectionTests(DeckSyntaxTestCase):
    def test_multiline_selections_and_conditional_names_are_not_layer_operations(self):
        source = 'PERC LOAD proc_lib INIT setup SELECT\nCheck_A\n#IFDEF EXTRA\nCheck_B\n#ENDIF\nSELECTTYPE INFO Check_A\nVARIABLE LIMIT 0.1'
        program = self.parse_clean(source)
        load = program.statements[0]
        self.assertIsInstance(load, ast.PercLoad)
        self.assertEqual("PROC_LIB", load.function)
        self.assertEqual("Check_A", load.body[2].value)
        self.assertEqual("Check_B", load.body[3].then_body[0].value)
        self.assertEqual(["SELECTTYPE", "INFO"], load.body[4].keywords)
        self.assertIsInstance(program.statements[1], ast.VariableDef)
        self.assert_roundtrip(source)

    def test_parallel_groups_preserve_group_boundaries(self):
        source = 'PERC LOAD lib SELECT PARALLEL Check_A (Check_B Check_C) Check_D (Check_E Check_F)'
        load = self.parse_clean(source).statements[0]
        groups = [item for item in load.body if isinstance(item, ast.PercGroup)]
        self.assertEqual([["Check_B", "Check_C"], ["Check_E", "Check_F"]], [[item.value for item in group.items] for group in groups])
        self.assert_roundtrip(source)

    def test_conditional_following_svrf_statements_remain_outside_the_load(self):
        program = self.parse_clean('PERC LOAD lib SELECT Check_A\n#IFDEF EXTRA\nVARIABLE LIMIT 0.1\n#ENDIF')
        self.assertEqual(2, len(program.statements))
        self.assertIsInstance(program.statements[1].then_body[0], ast.VariableDef)

    def test_conditional_namespace_qualified_procedures_remain_in_the_load(self):
        source = 'PERC LOAD lib SELECT Check_A\n#IFDEF EXTRA\nns::Check_B (ns::nested::Check_C ns::Check_D)\n#ENDIF'
        load = self.parse_clean(source).statements[0]
        self.assertEqual("ns::Check_B", load.body[2].then_body[0].value)
        self.assertEqual(["ns::nested::Check_C", "ns::Check_D"], [name.value for name in load.body[2].then_body[1].items])
        self.assert_roundtrip(source)


class DfmSpecificationTests(DeckSyntaxTestCase):
    def test_fill_shape_is_a_declaration_not_an_operation(self):
        program = self.parse_clean('DFM SPEC FILL SHAPE shape_a\nPOLYFILL 0 0 2 0 2 2\nA = COPY M1')
        specification = program.statements[0]
        self.assertIsInstance(specification, ast.DfmSpec)
        self.assertEqual(("FILL", "SHAPE", "SHAPE_A"), (specification.kind, specification.variant, specification.name))
        self.assertEqual(["POLYFILL"], specification.body[0].keywords)
        self.assertEqual(6, len(specification.body[0].arguments))
        self.assertIsInstance(program.statements[1], ast.LayerAssignment)

    def test_fill_clauses_preserve_order_and_arithmetic(self):
        program = self.parse_clean('DFM SPEC FILL spec_a\nINSIDE OF LAYER boundary\nINITIAL INSIDE OF LAYER\nSTRIPE width pitch-width HORIZONTAL ALLOW [GRID]\nA = DFM FILL spec_a')
        specification = program.statements[0]
        self.assertEqual(["INSIDE OF LAYER", "INITIAL INSIDE OF LAYER", "STRIPE", "HORIZONTAL", "ALLOW"], [' '.join(node.keywords) for node in specification.body])
        self.assertEqual("-", specification.body[2].arguments[1].op)
        self.assertIsInstance(specification.body[-1].arguments[0], ast.BracketExpr)
        self.assertEqual(2, len(program.statements))

    def test_polygon_region_flag_does_not_end_a_specification(self):
        program = self.parse_clean('DFM SPEC FILL spec_a INSIDE OF LAYER BY POLYGON boundary FILLSHAPE base OUTPUT result "shape" STEP pitch\nA = DFM FILL spec_a')
        specification = program.statements[0]
        self.assertEqual(["INSIDE", "OF", "LAYER", "BY", "POLYGON"], specification.body[0].keywords)
        self.assertEqual("STEP", specification.body[-1].keywords[0])

    def test_conditional_clauses_remain_in_the_specification(self):
        source = 'DFM SPEC FILL spec_a\n#IFDEF FULL\nINSIDE OF LAYER chip\n#ELSE\n#IFDEF SUB\nINSIDE OF LAYER subchip\n#ELSE\nINSIDE OF LAYER boundary\n#ENDIF\n#ENDIF\nSTRIPE 0.1 0.2\nA = DFM FILL spec_a'
        specification = self.parse_clean(source).statements[0]
        self.assertIsInstance(specification.body[0], ast.IfDef)
        self.assertIsInstance(specification.body[0].else_body[0], ast.IfDef)
        self.assert_roundtrip(source)

    def test_conditional_following_statement_is_not_swallowed(self):
        program = self.parse_clean('DFM SPEC FILL spec_a STRIPE 0.1 0.2\n#IFDEF FULL\nA = COPY M1\n#ENDIF')
        self.assertEqual(2, len(program.statements))
        self.assertIsInstance(program.statements[1], ast.IfDef)

    def test_clauses_shared_by_conditional_definitions_keep_their_source_level(self):
        source = '#IFDEF A\nDFM SPEC FILL SHAPE shape_a POLYFILL 0 0 1 0 1 1\n#ELSE\n#IFDEF B\nDFM SPEC FILL SHAPE shape_a RECTFILL 0 0 1 1\n#ELSE\nDFM SPEC FILL SHAPE shape_a RECTFILL 0 0 2 2\n#ENDIF\n#ENDIF\nSPACE INTERIOR gap M1\n#IFDEF FULL\nSPACE 0 M2\n#ENDIF\nA = COPY M1'
        program = self.parse_clean(source)
        self.assertEqual(4, len(program.statements))
        self.assertIsInstance(program.statements[1], ast.DfmClause)
        self.assertIsInstance(program.statements[2].then_body[0], ast.DfmClause)
        self.assertEqual(1, len(program.statements[0].then_body[0].body))
        self.assert_roundtrip(source)

    def test_fill_region_variant_retains_the_actual_name(self):
        specification = self.parse_clean('DFM SPEC FILL REGION region_spec SPACE "spacing"').statements[0]
        self.assertEqual("REGION", specification.variant)
        self.assertEqual("REGION_SPEC", specification.name)

    def test_region_and_wrap_operations_keep_their_complete_heads(self):
        for variant in ('REGION', 'WRAP'):
            with self.subTest(variant=variant):
                operation = self.parse_clean(f'A = DFM FILL {variant} spec_a').statements[0].expression
                self.assertEqual("DFM FILL " + variant, operation.op)
                self.assertEqual("SPEC_A", operation.operands[0].name)

    def test_conditional_pattern_arguments_keep_their_original_position(self):
        source = 'DFM SPEC FILL spec_a RECTFILL\n#IFDEF VERTICAL\n"vertical" OUTPUT result 0 0 width length\n#ELSE\n"horizontal" OUTPUT result 0 0 length width\n#ENDIF\nSTEP pitch\nA = DFM FILL spec_a'
        specification = self.parse_clean(source).statements[0]
        branch = specification.body[1]
        self.assertIsInstance(branch, ast.IfDef)
        self.assertEqual([], branch.then_body[0].keywords)
        self.assertEqual("vertical", branch.then_body[0].arguments[0].value)
        self.assert_roundtrip(source)

    def test_shared_clauses_do_not_require_a_default_definition_branch(self):
        program = self.parse_clean('#IFDEF FILL\nDFM SPEC FILL SHAPE shape_a RECTFILL 0 0 1 1\n#ENDIF\nSPACE gap M1')
        self.assertIsInstance(program.statements[1], ast.DfmClause)

    def test_legacy_wrap_specification_preserves_orientation_branches(self):
        source = 'DFM SPEC FILL WRAP "wrapping"\n#IFDEF VERTICAL\nVSHAPE vertical 0.1 0.2 0.3 0.4 STEP 0.1 0.2\n#ELSE\nHSHAPE horizontal 0.1 0.2 0.3 0.4 STEP 0.2 0.1\n#ENDIF\nEDGE ALIGN INSIDE BY 0.04 EXTEND BY 0.03 MAJOR "B" WRAPS 2 LONGSHAPE WIDESHAPE'
        specification = self.parse_clean(source).statements[0]
        self.assertEqual(("WRAP", "wrapping"), (specification.variant, specification.name))
        self.assertEqual(4, len(specification.body))
        self.assert_roundtrip(source)

    def test_legacy_optimize_specification_preserves_its_data_and_targets(self):
        source = 'DFM SPEC OPTIMIZE DATA "density"\n[AREA(M1) / AREA(CHIP)] < 0.5 TOMAX WINDOW 10 STEP 5\nDFM SPEC OPTIMIZE "optimization"\nGUARDED M1 M2 CHIP\nOPTIMIZABLE candidate\nOPTIMIZER "density"\nA = DFM OPTIMIZE "optimization"'
        program = self.parse_clean(source)
        self.assertEqual(("OPTIMIZE", "DATA", "density"), (program.statements[0].kind, program.statements[0].variant, program.statements[0].name))
        self.assertEqual(3, len(program.statements[1].body))
        self.assert_roundtrip(source)

    def test_legacy_space_specification_preserves_clauses(self):
        source = 'DFM SPEC SPACE "spacing" TYPE LOCAL CONSTRAINTS\nSPACEXY xspace yspace M1\nSPACE INTERIOR 0 M2\nA = COPY M1'
        specification = self.parse_clean(source).statements[0]
        self.assertEqual("SPACE", specification.kind)
        self.assertEqual("spacing", specification.name)
        self.assertEqual(2, len(specification.body))
        self.assert_roundtrip(source)

    def test_legacy_mat_operation_retains_continuations_and_intervals(self):
        source = 'A = DFM MAT region\nNARROWTRACKX width\nNARROWTRACKY length\nPITCHX [0 pitch] [pitch-width] EXTEND BY 0.1 M1\nB = COPY A'
        program = self.parse_clean(source)
        operation = program.statements[0].expression
        self.assertEqual("DFM MAT", operation.op)
        self.assertEqual(3, len(operation.modifiers))
        self.assertEqual(2, len(operation.modifiers[-1].arguments[0].items))
        self.assert_roundtrip(source)

    def test_fill_source_spans_cover_their_clauses(self):
        source = 'DFM SPEC FILL spec_a\nSTRIPE 0.1 0.2\nSTEP pitch\nA = COPY M1'
        specification = self.parse_clean(source).statements[0]
        self.assertIn('STEP pitch', specification.source_text)
        self.assertNotIn('A =', specification.source_text)
        self.assertEqual('STEP pitch', specification.body[-1].source_text.strip())

    def test_unclosed_bracket_reports_a_parse_error(self):
        _, diagnostics = parse_with_diagnostics('DFM SPEC FILL spec_a STRIPE 0.1 ALLOW [GRID')
        self.assertTrue(diagnostics)


class DeckSyntaxValidationTests(unittest.TestCase):
    def test_fill_specification_name_and_clauses_have_distinct_reference_roles(self):
        source = 'LAYER M1 1\nVARIABLE GRID 0.1\nDFM SPEC FILL spec_a INSIDE OF LAYER M1 STRIPE 0.1 0.2 STEP GRID\nA = DFM FILL spec_a'
        result = validate_svrf(source, strict=True)
        self.assertTrue(result.valid, result.diagnostics)
        self.assertEqual([], result.diagnostics)

    def test_fill_clause_layer_and_scalar_references_are_validated(self):
        result = validate_svrf('DFM SPEC FILL spec_a INSIDE OF LAYER MISSING\nSTEP LIMIT')
        self.assertEqual(
            [('semantic.reference.undefined', 'MISSING'), ('semantic.reference.scalar_undefined', 'LIMIT')],
            [(diagnostic.code, diagnostic.metadata.get('symbol')) for diagnostic in result.diagnostics],
        )

    def test_perc_procedure_names_are_not_layer_references(self):
        source = 'PERC LOAD lib INIT setup SELECT Check_A\n#IFDEF EXTRA\nns::Check_B\n#ENDIF'
        result = validate_svrf(source, strict=True)
        self.assertTrue(result.valid, result.diagnostics)
        self.assertEqual([], result.diagnostics)


if __name__ == '__main__':
    unittest.main()
