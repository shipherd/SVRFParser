import unittest

from svrf_parser import ast, parse, parse_with_diagnostics
from svrf_parser.printer import SvrfPrinter


class OperationContinuationTests(unittest.TestCase):
    def checked(self, text):
        tree = parse(text, strict=True)
        printed = SvrfPrinter().emit(tree)
        self.assertEqual(tree.to_dict(False), parse(printed, strict=True).to_dict(False))
        return tree.statements

    def test_copy_list_has_no_indentation_requirement(self):
        for prefix in ("", "   "):
            with self.subTest(prefix=prefix):
                out, following = self.checked(f"X = DFM COPY A\n{prefix}B\nLAYER LAST 3")
                self.assertEqual([x.name for x in out.expression.operands], ["A", "B"])
                self.assertEqual(following.name, "LAST")

    def test_deep_literal_boolean_chain_preserves_association_and_spans(self):
        count = 200
        source = "X = " + "".join(f"(L{i} OR " for i in range(count)) + "BASE" + ")" * count
        expr = parse(source, strict=True).statements[0].expression
        for i in range(count):
            self.assertEqual((expr.op, expr.left.name, expr.left.source_text), ("OR", f"L{i}", f"L{i}"))
            self.assertEqual(source[expr.start_offset:expr.end_offset], expr.source_text)
            expr = expr.right
        self.assertEqual(expr.name, "BASE")

    def test_copy_stops_at_independent_infix_expression(self):
        rule, = self.checked("R {\n X = DFM COPY A\n B AND C\n}")
        self.assertEqual(len(rule.body[0].expression.operands), 1)
        self.assertEqual(rule.body[1].op, "AND")

    def test_copy_distinguishes_parenthesized_inputs_from_infix_checks(self):
        rule, = self.checked("R {\n X = DFM COPY A\n (B AND C)\n"
                             "(ANGLE D == 0) NOT TOUCH EDGE E\n}")
        assignment, check = rule.body
        self.assertEqual(len(assignment.expression.operands), 2)
        self.assertEqual(check.op, "NOT TOUCH EDGE")

    def test_copy_does_not_consume_a_following_dfm_rdb(self):
        rule, = self.checked('R {\nX = DFM COPY A\nDFM RDB X "out.rdb"\n}')
        assignment, rdb = rule.body
        self.assertEqual(len(assignment.expression.operands), 1)
        self.assertEqual(rdb.op, "DFM RDB")

    def test_dp_arguments_keep_their_order_without_interpreting_option_groups(self):
        assign, = self.checked('X = DFM DP MASK0 A B (OPPOSITE 0) C (ANCHOR "a b")')
        self.assertEqual([v.name if isinstance(v, ast.LayerRef) else v.text for v in assign.expression.operands],
                         ["A", "B", "(OPPOSITE 0)", "C", '(ANCHOR "a b")'])

    def test_pathchk_optional_layer_before_port_selection(self):
        assign, = self.checked("X = PATHCHK !GROUND MET\nPORTS ALSO")
        op = assign.expression
        self.assertEqual((op.operands[0].op, op.operands[1].name, op.modifiers), ("NOT", "MET", ["PORTS", "ALSO"]))

    def test_touch_edge_endpoint_option_and_stamp_group(self):
        for expr in ("A TOUCH INSIDE EDGE B", "TOUCH INSIDE EDGE A B"):
            assign, = self.checked("X = " + expr + " ENDPOINT ONLY")
            self.assertEqual(assign.expression.modifiers, ["ENDPOINT", "ONLY"])
        assign, = self.checked("X = STAMP (A INTERACT B) BY C")
        self.assertEqual((assign.expression.op, assign.expression.left.op, assign.expression.right.name), ("STAMP", "INTERACT", "C"))

    def test_ratio_owns_conditional_rdb_but_not_the_next_check(self):
        rule, = self.checked('R {\n X = NET AREA RATIO A B > 1\n'
                             '#IFDEF USE_DB\nRDB ONLY "a b.rdb"\n#ELSE\nRDB alt.rdb\n#ENDIF\nCOPY M\n}')
        assignment, following = rule.body
        op = assignment.expression
        branch, = op.modifiers
        self.assertIsInstance(branch, ast.IfDef)
        self.assertEqual(branch.then_body[0].text, 'RDB ONLY "a b.rdb"')
        self.assertEqual(branch.else_body[0].text, 'RDB alt.rdb')
        self.assertIn("#ENDIF", op.source_text)
        self.assertEqual(following.op, "COPY")

    def test_ratio_preserves_fragments_across_nested_conditionals(self):
        rule, = self.checked("R {\nNET AREA RATIO A B > 1 ACCUMULATE M\n"
                             "#IFDEF F\n#IFNDEF G\nOTHER\n#ENDIF\n#ENDIF\n"
                             "[ AREA(A) ] RDB out.rdb\n#IFDEF H\nLAY2\n#ENDIF\nLAST BY LAYER\n}")
        op, = rule.body
        self.assertEqual(op.modifiers[-4].then_body[0].then_body[0].text, "OTHER")
        self.assertEqual(op.modifiers[-3].text, "[ AREA(A) ] RDB out.rdb")
        self.assertEqual(op.modifiers[-1].text, "LAST BY LAYER")

    def test_ratio_does_not_consume_an_unrelated_conditional(self):
        rule, = self.checked("R {\nNET AREA RATIO A B > 1\n#IFDEF FLAG\nCOPY M\n#ENDIF\n}")
        self.assertIsInstance(rule.body[1], ast.IfDef)
        self.assertEqual(rule.body[0].modifiers, [])
        rule, = self.checked('R {\nNET AREA RATIO A B > 1 ACCUMULATE M\n#IFDEF FLAG\nNET A "VDD"\n#ENDIF\n}')
        self.assertIsInstance(rule.body[1], ast.IfDef)
        self.assertEqual(rule.body[1].then_body[0].op, "NET")

    def test_device_argument_macro_keeps_conditional_properties_and_payload(self):
        macro, = self.checked("DMACRO P X {\n<AUX> <OTHER> [PROPERTY A\n"
                              "#IFDEF EXTRA\n, B\n#ENDIF\nHIDDEN PROPERTY V, W\n"
                              "#DECRYPT\nLAYER DATA 7\n#ENDCRYPT\n]\n}")
        aux, block = macro.body
        self.assertEqual(aux.layers, ["AUX", "OTHER"])
        self.assertEqual(block.properties, ["A"])
        cond, hidden, wrapper = block.body
        self.assertEqual(cond.then_body[0].properties, ["B"])
        self.assertEqual(hidden.properties, ["V", "W"])
        self.assertEqual(wrapper.body[0].name, "DATA")

    def test_missing_property_closer_does_not_consume_macro_closer(self):
        tree, diagnostics = parse_with_diagnostics("DMACRO M {\n<A> [PROPERTY P\n#DECRYPT\nopaque\n#ENDCRYPT\n}\nLAYER NEXT 2")
        self.assertEqual([d.code for d in diagnostics], ["parser.property.unterminated"])
        macro, following = tree.statements
        self.assertEqual(macro.body[1].body[0].parse_status, "opaque")
        self.assertEqual(following.name, "NEXT")
