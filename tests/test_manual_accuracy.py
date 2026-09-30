"""Regression tests for manual-defined grammar and validation contracts."""

import unittest

from svrf_parser import ast, parse_with_diagnostics, validate_svrf


class NumericGrammarTests(unittest.TestCase):
    def parse_expression(self, expression):
        tree, warnings = parse_with_diagnostics(f"VARIABLE X {expression}\n")
        self.assertEqual([], warnings)
        return tree.statements[0].values[0]

    def test_scalar_power_has_multiplicative_precedence(self):
        expr = self.parse_expression("2 * 3 ^ 2")
        self.assertIsInstance(expr, ast.BinaryOp)
        self.assertEqual("^", expr.op)
        self.assertEqual("*", expr.left.op)

    def test_multiplicative_operators_associate_left_to_right(self):
        for expression, outer, inner in [
            ("2 ^ 3 * 4", "*", "^"),
            ("2 ^ 3 ^ 4", "^", "^"),
            ("7 % 4 / 2", "/", "%"),
        ]:
            with self.subTest(expression=expression):
                expr = self.parse_expression(expression)
                self.assertEqual(outer, expr.op)
                self.assertEqual(inner, expr.left.op)

    def test_by_modifier_uses_scalar_precedence(self):
        tree, warnings = parse_with_diagnostics("TMP = SIZE M1 BY 1 + 2 * 3 % 4\n")
        self.assertEqual([], warnings)
        expr = tree.statements[0].expression.modifiers[0][1]
        self.assertEqual("+", expr.op)
        self.assertEqual("%", expr.right.op)
        self.assertEqual("*", expr.right.left.op)

    def test_dfm_power_keeps_higher_precedence_and_context_does_not_leak(self):
        tree, warnings = parse_with_diagnostics(
            "TMP = DFM PROPERTY M1 [P = 2 * 3 ^ 2]\n"
            "VARIABLE X 2 * 3 ^ 2\n"
        )
        self.assertEqual([], warnings)
        dfm_expr = tree.statements[0].expression.modifiers[0].right
        self.assertEqual("*", dfm_expr.op)
        self.assertEqual("^", dfm_expr.right.op)
        self.assertEqual("^", tree.statements[1].values[0].op)

    def test_power_and_modulus_references_are_scalar(self):
        for operator in ("^", "%"):
            with self.subTest(operator=operator):
                result = validate_svrf(f"VARIABLE X MISSING {operator} 2\n")
                self.assertIn("semantic.reference.scalar_undefined", {d.code for d in result.warnings})

    def test_by_net_is_a_mode_not_an_empty_net_operation(self):
        result = validate_svrf("LAYER M1 1\nLAYER M2 2\nTMP = M1 INTERACT M2 > 1 BY NET\n", strict=True)
        self.assertTrue(result.valid, result.diagnostics)
        value = result.program.statements[2].expression.modifiers[0][1]
        self.assertIsInstance(value, ast.LayerRef)
        self.assertEqual("NET", value.name)


class OperationBoundaryTests(unittest.TestCase):
    def test_standalone_measurement_is_not_swallowed_as_a_modifier(self):
        for operation in ("LENGTH", "ANGLE", "AREA"):
            with self.subTest(operation=operation):
                text = (
                    "LAYER M1 1\nLAYER M2 2\nVARIABLE GRID 0.001\nVARIABLE WIDTH 1\n"
                    "R {\n A = INT M1 [M2] < GRID ABUT == 90 INTERSECTING ONLY\n"
                    f" {operation} M1 > WIDTH\n}}\n"
                )
                tree, warnings = parse_with_diagnostics(text)
                self.assertEqual([], warnings)
                rule = tree.statements[-1]
                self.assertEqual(2, len(rule.body))
                self.assertIsInstance(rule.body[-1], ast.ConstrainedExpr)
                self.assertTrue(validate_svrf(text, strict=True).valid)

    def test_measurement_constraints_can_still_continue_modifiers(self):
        text = "R { A = CONVEX EDGE M1 ANGLE1 == 90\n WITH LENGTH < 0.2\n COPY A }\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual([], warnings)
        self.assertEqual(2, len(tree.statements[0].body))
        self.assertIn("LENGTH", tree.statements[0].body[0].expression.modifiers)

    def test_namespaced_keyword_is_a_layer_reference(self):
        text = "LAYER M1 1\nR { DRC:1 NOT INTERACT M1 }\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual([], warnings)
        operation = tree.statements[1].body[0]
        self.assertIsInstance(operation, ast.BinaryOp)
        self.assertEqual("DRC:1", operation.left.name)
        self.assertTrue(validate_svrf(text, strict=True).valid)

    def test_standalone_operations_after_assignments_remain_separate(self):
        for operation in (
            "RECTANGLE ENCLOSURE M1 M2 ABUT<90 SINGULAR OUTSIDE ALSO GOOD 0.1 0.2 OPPOSITE",
            "WITH NEIGHBOR M1 >= 1 SPACE < 0.1 CENTERS",
            "FLATTEN (M1 AND M2)",
        ):
            with self.subTest(operation=operation):
                text = "R {\n A = M1 INTERACT M2\n " + operation + "\n}\n"
                tree, warnings = parse_with_diagnostics(text)
                self.assertEqual([], warnings)
                self.assertEqual(2, len(tree.statements[0].body))

    def test_density_bracket_does_not_consume_following_flatten(self):
        text = (
            "R {\n EST = DENSITY M1 M2 < 0.2 WINDOW 1 STEP 1 PRINT density.rdb\n"
            " [AREA(M1)/AREA(M2)]\n FLATTEN (EST AND M1)\n}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual([], warnings)
        self.assertEqual(2, len(tree.statements[0].body))
        self.assertEqual("FLATTEN", tree.statements[0].body[1].op)

    def test_flatten_cell_specifications_are_not_layer_operations(self):
        for statement in ('FLATTEN CELL "cellName"', 'FLATTEN INSIDE CELL "cellName"'):
            with self.subTest(statement=statement):
                tree, warnings = parse_with_diagnostics(statement)
                self.assertEqual([], warnings)
                self.assertIsInstance(tree.statements[0], ast.Directive)


class SymbolContractTests(unittest.TestCase):
    def assertValid(self, text):
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid, result.diagnostics)

    def test_quoted_layer_definition_and_reference_are_case_insensitive(self):
        self.assertValid('LAYER "m1" 1\nR { INT M1 < 1 }\n')
        self.assertValid('LAYER M1 1\nR { INT "m1" < 1 }\n')

    def test_quoted_name_duplicate_is_detected(self):
        result = validate_svrf('LAYER "m1" 1\nLAYER M1 2\n', strict=True)
        self.assertIn("semantic.duplicate_layer", {d.code for d in result.errors})

    def test_undefined_quoted_layer_and_quoted_keyword_are_detected(self):
        for name in ("UNDEFINED_LAYER", "COPY", "a layer"):
            with self.subTest(name=name):
                result = validate_svrf(f'LAYER M1 1\nR {{ INT "{name}" < 1 }}\n', strict=True)
                self.assertIn("semantic.reference.undefined", {d.code for d in result.errors})

    def test_text_values_are_not_layer_references(self):
        self.assertValid(
            'LAYER M1 1\nVARIABLE NETS "MixedCase" "OtherCase"\n'
            'LAYOUT PATH "Design.GDS"\nR { M1 WITH TEXT "SomeLabel" }\n'
        )

    def test_quoted_numeric_variable_reference(self):
        self.assertValid('VARIABLE "width" 0.1\nVARIABLE HALF "WIDTH" * 0.5\n')
        self.assertValid('VARIABLE "width" 0.1\nLAYER M1 1\nR { INT M1 < "WIDTH" }\n')

    def test_variables_must_precede_use(self):
        for text in (
            "VARIABLE SECOND FIRST * 0.5\nVARIABLE FIRST 4\n",
            "LAYER M1 1\nR { INT M1 < WIDTH }\nVARIABLE WIDTH 0.1\n",
        ):
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertIn("semantic.variable.before_definition", {d.code for d in result.errors})

    def test_declared_variables_and_forward_layers_are_accepted(self):
        self.assertValid("VARIABLE FIRST 4\nVARIABLE SECOND FIRST * 0.5\n")
        self.assertValid("R { INT M1 < 1 }\nLAYER M1 1\n")

    def test_macro_definition_does_not_impose_call_time_variable_order(self):
        self.assertValid("DMACRO CHECK { INT M1 < WIDTH }\nVARIABLE WIDTH 0.1\nLAYER M1 1\nR { CMACRO CHECK }\n")

    def test_assignment_only_rule_has_no_output(self):
        result = validate_svrf("LAYER M1 1\nR { TMP = COPY M1 }\n", strict=True)
        self.assertIn("semantic.rule.missing_output", {d.code for d in result.errors})
        self.assertValid("LAYER M1 1\nR { TMP = COPY M1\nCOPY TMP }\n")

    def test_sconnect_requires_both_layers(self):
        result = validate_svrf("LAYER M1 1\nSCONNECT M1\n", strict=True)
        self.assertIn("semantic.connect.too_few_layers", {d.code for d in result.errors})

    def test_sconnect_syntax_variants(self):
        layers = "LAYER M1 1\nLAYER M2 2\nLAYER VIA 3\n"
        for statement in ("SCONNECT M1 M2 LINK VDD ABUT ALSO", "SCONNECT M1 M2 BY VIA LINK VDD"):
            self.assertValid(layers + statement + "\n")
        result = validate_svrf(layers + "SCONNECT M1 M2 BY VIA ABUT ALSO\n", strict=True)
        self.assertIn("semantic.connect.invalid_abut", {d.code for d in result.errors})
        result = validate_svrf(layers + "SCONNECT M1 M2 VIA\n", strict=True)
        self.assertIn("semantic.connect.invalid_layer_count", {d.code for d in result.errors})

    def test_sconnect_lower_layer_limit(self):
        layers = "LAYER U 1\nLAYER VIA 2\n" + "".join(f"LAYER L{i} {i + 3}\n" for i in range(33))
        for count in (32, 33):
            with self.subTest(count=count):
                result = validate_svrf(layers + "SCONNECT U " + " ".join(f"L{i}" for i in range(count)) + " BY VIA\n", strict=True)
                self.assertEqual(count == 32, result.valid, result.diagnostics)


if __name__ == "__main__":
    unittest.main()
