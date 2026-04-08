import unittest

from svrf_parser import ast, parse, validate_svrf
from svrf_parser.expression_contexts import (
    LAYER_EXPRESSION,
    PROPERTY_EXPRESSION,
    RULE_BODY_OPERATION,
    SCALAR_EXPRESSION,
    annotate_expression_contexts,
)


class ExpressionContextAnnotationTests(unittest.TestCase):
    def test_annotation_tags_layer_assignment_and_scalar_modifier_contexts(self):
        tree = parse("LAYER M1 1\nTMP = SIZE M1 BY WIDTH_CONST\n")
        assignment = tree.statements[1]
        operation = assignment.expression
        by_value = operation.modifiers[0][1]

        annotations = annotate_expression_contexts(tree)

        self.assertIn(LAYER_EXPRESSION, annotations.get(operation))
        self.assertIn(SCALAR_EXPRESSION, annotations.get(by_value))

    def test_annotation_tags_rule_body_and_property_contexts(self):
        tree = parse(
            "RULE1 {\n  INT M1 < WIDTH_CONST\n}\n"
            "[PROPERTY P1\n  VALUE = WIDTH_CONST + 1\n]\n"
        )
        rule_op = tree.statements[0].body[0]
        property_expr = tree.statements[1].body[0].expression

        annotations = annotate_expression_contexts(tree)

        self.assertIn(RULE_BODY_OPERATION, annotations.get(rule_op))
        self.assertIn(PROPERTY_EXPRESSION, annotations.get(property_expr))

    def test_validation_uses_annotation_for_scalar_vs_layer_reference(self):
        scalar_result = validate_svrf("LAYER M1 1\nTMP = SIZE M1 BY WIDTH_CONST\n", strict=False)
        layer_result = validate_svrf("LAYER M1 1\nTMP = M1 AND MISSING_LAYER\n", strict=False)

        scalar_codes = {diag.code for diag in scalar_result.warnings}
        layer_codes = {diag.code for diag in layer_result.warnings}

        self.assertIn("semantic.reference.scalar_undefined", scalar_codes)
        self.assertIn("semantic.reference.undefined", layer_codes)

    def test_variable_values_are_annotated_as_scalar_context(self):
        tree = parse("VARIABLE WIDTH WIDTH_CONST\n")
        value = tree.statements[0].values[0]

        annotations = annotate_expression_contexts(tree)

        self.assertIn(SCALAR_EXPRESSION, annotations.get(value))
        self.assertEqual("scalar", annotations.semantic_context_for(value))


if __name__ == "__main__":
    unittest.main()
