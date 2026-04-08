import unittest

from svrf_parser import ast, parse
from svrf_parser.operation_cst import OperationCst
from svrf_parser.operation_normalizer import normalize_operation_cst, normalize_operation_parts


class OperationNormalizerTests(unittest.TestCase):
    def test_normalize_operation_cst_builds_drc_op(self):
        operand = ast.LayerRef(name="M1")
        constraint = ast.Constraint(op="<", value=ast.NumberLiteral(value=0.1))
        node = normalize_operation_cst(
            OperationCst(
                op="INT",
                operands=(operand,),
                constraints=(constraint,),
                modifiers=("ABUT",),
                strategy="default",
            ),
            location={"line": 1, "col": 1},
        )

        self.assertIsInstance(node, ast.DRCOp)
        self.assertEqual(node.op, "INT")
        self.assertEqual(node.operands, [operand])
        self.assertEqual(node.constraints, [constraint])
        self.assertEqual(node.modifiers, ["ABUT"])

    def test_normalize_operation_parts_builds_canonical_drc_op(self):
        operand = ast.LayerRef(name="M2")
        node = normalize_operation_parts(
            "WITH TEXT",
            operands=[operand],
            modifiers=["PRIMARY", "ONLY"],
            strategy="with_text",
            location={"line": 1, "col": 1},
        )

        self.assertIsInstance(node, ast.DRCOp)
        self.assertEqual(node.op, "WITH TEXT")
        self.assertEqual(node.operands, [operand])
        self.assertEqual(node.modifiers, ["PRIMARY", "ONLY"])

    def test_live_operation_parser_still_normalizes_rule_ops(self):
        tree = parse("RULE1 { INT M1 < 0.1 INT M2 < 0.2 }\n", strict=True)
        rule = tree.statements[0]

        self.assertEqual(len(rule.body), 2)
        self.assertIsInstance(rule.body[0], ast.DRCOp)
        self.assertEqual(rule.body[0].op, "INT")
        self.assertIsInstance(rule.body[1], ast.DRCOp)
        self.assertEqual(rule.body[1].op, "INT")


if __name__ == "__main__":
    unittest.main()
