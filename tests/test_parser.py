"""Manual-backed unittest coverage for the reconstructed SVRF parser."""

import unittest

from svrf_parser import parse, parse_with_diagnostics
from svrf_parser import ast


class TestManualExamples(unittest.TestCase):
    def test_layer_statement(self):
        tree = parse("LAYER DIFF 2 4")
        self.assertEqual(len(tree.statements), 1)
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerDef)
        self.assertEqual(node.name, "DIFF")
        self.assertEqual(node.numbers, [2, 4])

    def test_connect_by_statement(self):
        tree = parse("CONNECT METAL1 POLY BY CONTACT")
        node = tree.statements[0]
        self.assertIsInstance(node, ast.Connect)
        self.assertFalse(node.soft)
        self.assertEqual(node.layers, ["METAL1", "POLY"])
        self.assertEqual(node.via_layer, "CONTACT")

    def test_connect_without_trailing_newline_has_no_empty_layer(self):
        tree = parse("CONNECT METAL1 POLY")
        node = tree.statements[0]
        self.assertIsInstance(node, ast.Connect)
        self.assertEqual(node.layers, ["METAL1", "POLY"])

    def test_sconnect_statement(self):
        tree = parse("SCONNECT upper lower BY via LINK VDD ABUT ALSO")
        node = tree.statements[0]
        self.assertIsInstance(node, ast.Connect)
        self.assertTrue(node.soft)
        self.assertEqual(node.layers, ["UPPER", "LOWER"])
        self.assertEqual(node.via_layer, "VIA")
        self.assertEqual(node.link_name, "VDD")
        self.assertTrue(node.abut_also)

    def test_variable_statement(self):
        text = 'VARIABLE metal_text "a?" "b?" "c?"'
        tree = parse(text)
        node = tree.statements[0]
        self.assertIsInstance(node, ast.VariableDef)
        self.assertEqual(node.name, "METAL_TEXT")
        self.assertEqual([value.value for value in node.values], ["a?", "b?", "c?"])

    def test_include_statement(self):
        tree = parse('INCLUDE "$dir/rules.antenna"')
        node = tree.statements[0]
        self.assertIsInstance(node, ast.Include)
        self.assertEqual(node.path, "$dir/rules.antenna")
        self.assertFalse(node.preprocessor)

    def test_unquoted_include_path_preserves_case(self):
        tree = parse("INCLUDE MiXeD/FiLe.svrf\n")
        node = tree.statements[0]
        self.assertIsInstance(node, ast.Include)
        self.assertEqual(node.path, "MiXeD/FiLe.svrf")

    def test_quoted_environment_variable_name_preserves_case(self):
        tree = parse('VARIABLE "MiXeD_ENV" ENVIRONMENT\n')
        node = tree.statements[0]
        self.assertIsInstance(node, ast.VariableDef)
        self.assertEqual(node.name, "MiXeD_ENV")
        self.assertTrue(node.environment)

    def test_preprocessor_include_statement(self):
        tree = parse('#INCLUDE "common.svrf"')
        node = tree.statements[0]
        self.assertIsInstance(node, ast.Include)
        self.assertEqual(node.path, "common.svrf")
        self.assertTrue(node.preprocessor)

    def test_unknown_preprocessor_falls_back_to_generic_directive(self):
        tree = parse("#CUSTOM FLAG 1\n")
        node = tree.statements[0]
        self.assertIsInstance(node, ast.Directive)
        self.assertEqual(node.keywords, ["#CUSTOM"])
        self.assertEqual(node.arguments, ["FLAG", 1])

    def test_rule_check_with_comment(self):
        text = "rule1 {\n  @ spacing is within ^MY_VAR\n  INT METAL < 0.5\n}\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertEqual(node.name, "RULE1")
        self.assertEqual(len(node.comments), 1)
        self.assertTrue(any(isinstance(seg, ast.VarRef) for seg in node.comments[0]))
        self.assertEqual(len(node.body), 1)
        self.assertIsInstance(node.body[0], ast.DRCOp)
        self.assertEqual(node.body[0].op, "INT")

    def test_rule_check_preserves_unquoted_compact_voltage_labels(self):
        labels = (
            "CHECK.2.1:0.2V__1.250V",
            "CHECK.4.1:0.2V__1.250V",
            "CHECK.4.8:0.2V__1.250V",
            "CHECK.6.8:0.2V__1.250V",
        )
        for label in labels:
            with self.subTest(label=label):
                tree, warnings = parse_with_diagnostics(f"{label} {{ @ cmt\n  INT M1 < 1\n}}\n")
                self.assertEqual(warnings, [])
                self.assertEqual(len(tree.statements), 1)
                node = tree.statements[0]
                self.assertIsInstance(node, ast.RuleCheckBlock)
                self.assertEqual(node.name, label)

    def test_define_and_ifdef(self):
        text = "#DEFINE process 7lm\n#IFDEF process\nLAYER poly 5\n#ENDIF\n"
        tree = parse(text)
        self.assertEqual(len(tree.statements), 2)
        self.assertIsInstance(tree.statements[0], ast.Define)
        self.assertIsInstance(tree.statements[1], ast.IfDef)
        self.assertEqual(tree.statements[1].name, "PROCESS")
        self.assertEqual(len(tree.statements[1].then_body), 1)
        self.assertIsInstance(tree.statements[1].then_body[0], ast.LayerDef)

    def test_dmacro_and_call(self):
        text = "DMACRO WIDTH_CHECK lay val { result = INT lay < val }\nCMACRO WIDTH_CHECK poly 0.5"
        tree = parse(text)
        self.assertEqual(len(tree.statements), 2)
        macro_def = tree.statements[0]
        macro_call = tree.statements[1]
        self.assertIsInstance(macro_def, ast.DMacro)
        self.assertEqual(macro_def.name, "WIDTH_CHECK")
        self.assertEqual(macro_def.params, ["LAY", "VAL"])
        self.assertEqual(len(macro_def.body), 1)
        self.assertIsInstance(macro_call, ast.MacroCall)
        self.assertEqual(macro_call.kind, "CMACRO")
        self.assertEqual(macro_call.name, "WIDTH_CHECK")
        self.assertEqual(len(macro_call.arguments), 2)
        self.assertIsInstance(macro_call.arguments[0], ast.LayerRef)
        self.assertEqual(macro_call.arguments[0].name, "POLY")
        self.assertIsInstance(macro_call.arguments[1], ast.NumberLiteral)
        self.assertEqual(macro_call.arguments[1].value, 0.5)

    def test_cmacro_without_trailing_newline_has_no_empty_argument(self):
        tree = parse("CMACRO extract_params")
        node = tree.statements[0]
        self.assertIsInstance(node, ast.MacroCall)
        self.assertEqual(node.kind, "CMACRO")
        self.assertEqual(node.name, "EXTRACT_PARAMS")
        self.assertEqual(node.arguments, [])

    def test_cmacro_inside_rule_block_parses_as_macro_call(self):
        text = (
            "DMACRO CHECK_SHAPE Mx Mx_n { }\n"
            "RULE1 {\n"
            "  CMACRO CHECK_SHAPE Layer_A Layer_B\n"
            "}\n"
        )
        tree = parse(text)
        rule = tree.statements[1]
        self.assertIsInstance(rule, ast.RuleCheckBlock)
        self.assertEqual(len(rule.body), 1)
        call = rule.body[0]
        self.assertIsInstance(call, ast.MacroCall)
        self.assertEqual(call.kind, "CMACRO")
        self.assertEqual(call.name, "CHECK_SHAPE")
        self.assertEqual(
            [arg.name for arg in call.arguments],
            ["LAYER_A", "LAYER_B"],
        )

    def test_fmacro_inside_rule_block_parses_as_macro_call(self):
        text = (
            "RULE1 {\n"
            "  FMACRO F1(A, B)\n"
            "}\n"
        )
        tree = parse(text)
        rule = tree.statements[0]
        self.assertIsInstance(rule, ast.RuleCheckBlock)
        self.assertEqual(len(rule.body), 1)
        call = rule.body[0]
        self.assertIsInstance(call, ast.MacroCall)
        self.assertEqual(call.kind, "FMACRO")
        self.assertEqual(call.name, "F1")
        self.assertEqual(len(call.arguments), 2)

    def test_scientific_notation_variable_values(self):
        tree = parse("VARIABLE X 1E7\nVARIABLE Y 5E-06\n", strict=True)
        self.assertEqual(len(tree.statements), 2)
        self.assertEqual(tree.statements[0].values[0].value, 1e7)
        self.assertEqual(tree.statements[1].values[0].value, 5e-06)

    def test_digit_prefixed_assignment(self):
        tree = parse("15V_GATE = M1 AND M2")
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertEqual(node.name, "15V_GATE")
        self.assertIsInstance(node.expression, ast.BinaryOp)

    def test_property_block(self):
        tree = parse("[PROPERTY p1, p2\n  x = 1\n]")
        node = tree.statements[0]
        self.assertIsInstance(node, ast.PropertyBlock)
        self.assertEqual(node.properties, ["P1", "P2"])
        self.assertEqual(len(node.body), 1)
        self.assertIsInstance(node.body[0], ast.LayerAssignment)

    def test_encrypted_block(self):
        tree = parse("#ENCRYPT\npayload\n#ENDCRYPT")
        node = tree.statements[0]
        self.assertIsInstance(node, ast.EncryptedBlock)
        self.assertEqual(node.content, "payload")
        self.assertEqual(node.body, [])
        self.assertEqual(node.parse_status, "opaque")

    def test_encrypted_plaintext_payload_is_parsed_as_body(self):
        tree = parse("#ENCRYPT\nLAYER M1 1\nM2 = M1\n#ENDCRYPT")
        node = tree.statements[0]
        self.assertIsInstance(node, ast.EncryptedBlock)
        self.assertEqual(node.parse_status, "plaintext")
        self.assertEqual(len(node.body), 2)
        self.assertIsInstance(node.body[0], ast.LayerDef)
        self.assertEqual(node.body[0].name, "M1")
        self.assertIsInstance(node.body[1], ast.LayerAssignment)
        self.assertEqual(node.body[1].name, "M2")
        self.assertEqual(node.body[0].line, 2)

    def test_decrypt_inline_payload_block(self):
        tree = parse("#DECRYPT abc123\n#ENDCRYPT")
        node = tree.statements[0]
        self.assertIsInstance(node, ast.EncryptedBlock)
        self.assertEqual(node.content.strip(), "abc123")
        self.assertEqual(node.body, [])
        self.assertEqual(node.parse_status, "opaque")

    def test_prefix_edge_binary(self):
        tree = parse("_T = IN EDGE M1 M2")
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertEqual(node.expression.op, "IN EDGE")

    def test_not_compound_binary(self):
        tree = parse("_T = M1 NOT INSIDE EDGE M2")
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertEqual(node.expression.op, "NOT INSIDE EDGE")

    def test_not_enclose_rectangle(self):
        tree = parse("_T = (A INTERACT B) NOT ENCLOSE RECTANGLE 0.001 30")
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.DRCOp)
        self.assertEqual(node.expression.op, "NOT ENCLOSE RECTANGLE")

    def test_expand_edge_arithmetic_modifiers(self):
        tree = parse("_T = EXPAND EDGE M1 INSIDE BY 0.05+TOL OUTSIDE BY 0.02+TOL")
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.DRCOp)
        self.assertEqual(node.expression.op, "EXPAND EDGE")
        self.assertIn("INSIDE", node.expression.modifiers)
        self.assertIn("OUTSIDE", node.expression.modifiers)

    def test_with_width_direct_constraint(self):
        tree, warnings = parse_with_diagnostics("_T = M1 WITH WIDTH <= MIN_W")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.ConstrainedExpr)
        self.assertEqual(node.expression.expr.op, "WITH WIDTH")
        self.assertIsNone(node.expression.expr.right)
        self.assertEqual(node.expression.constraints[0].op, "<=")

    def test_property_block_ternary_assignment(self):
        text = (
            "[PROPERTY P1\n"
            "  pitchX = (EWYP(M1_MIN_C2C_P) > 0) ? (M1_G_1_CL + EWXP(M1_MIN_C2C_P)) : 0\n"
            "]"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        block = tree.statements[0]
        self.assertIsInstance(block, ast.PropertyBlock)
        node = block.body[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertEqual(node.expression.op, "?:")

    def test_coin_inside_edge_binary(self):
        tree, warnings = parse_with_diagnostics("_T = SQR_VIA0ii COIN INSIDE EDGE B1VIA0i_GOOD")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertEqual(node.expression.op, "COIN INSIDE EDGE")

    def test_enclose_rectangle_arithmetic_operand(self):
        tree, warnings = parse_with_diagnostics(
            "_T = ENCLOSE RECTANGLE M1 GRID M1_G_1_CPL2+GRID ORTHOGONAL ONLY"
        )
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.DRCOp)
        self.assertEqual(node.expression.op, "ENCLOSE RECTANGLE")

    def test_bracket_assignment_expression(self):
        text = "A = DFM PROPERTY MERGE OD_HV0 [ OD_MHV = MAX(PROPERTY(OD_HV0, OD_HV)) ]"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.DRCOp)

    def test_multiline_net_area_ratio_continuation(self):
        text = (
            "RULE1 {\n"
            "  NET AREA RATIO POLYC M0PO_M0OD_PO_DIO M0PO_M0OD_PO GATE ACT_GATE SF_GATE DF_GATE > 100\n"
            "      [ !!AREA(ACT_GATE) * !!AREA(GATE) ] RDB ONLY A.R.3.REP M0PO_M0OD_PO BY LAYER\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertEqual(len(node.body), 1)
        self.assertIsInstance(node.body[0], ast.DRCOp)
        self.assertEqual(node.body[0].op, "NET AREA RATIO")

    def test_multiline_dfm_property_continuation(self):
        text = (
            "RULE1 {\n"
            "  SHAPE_SET_VERTICAL = DFM PROPERTY SHAPE_SET SHAPE_SET_X SHAPE_SET_Y OVERLAP ABUT ALSO MULTI\n"
            "    [LY = LENGTH(SHAPE_SET_Y)] > 0\n"
            "    [LX = LENGTH(SHAPE_SET_X)] > 0\n"
            "    [-= PROPERTY_REF(LY) - PROPERTY_REF(LX)] >= 0\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        assignment = node.body[0]
        self.assertIsInstance(assignment, ast.LayerAssignment)
        self.assertIsInstance(assignment.expression, ast.DRCOp)
        self.assertEqual(assignment.expression.op, "DFM PROPERTY")
        self.assertEqual(
            ["SHAPE_SET", "SHAPE_SET_X", "SHAPE_SET_Y"],
            [operand.name for operand in assignment.expression.operands],
        )
        self.assertEqual("OVERLAP", assignment.expression.modifiers[0])
        self.assertIn("ABUT ALSO", assignment.expression.modifiers)
        self.assertIn("MULTI", assignment.expression.modifiers)
        self.assertTrue(
            any(isinstance(modifier, ast.ConstrainedExpr) for modifier in assignment.expression.modifiers)
        )

    def test_dfm_property_bracket_body_on_same_line_is_modifier(self):
        tree, warnings = parse_with_diagnostics("X = DFM PROPERTY MDV_sync [sid = GLOBALNETID(MDV_sync)]\n", strict=True)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.DRCOp)
        self.assertEqual(node.expression.op, "DFM PROPERTY")
        self.assertEqual(["MDV_SYNC"], [operand.name for operand in node.expression.operands])
        self.assertEqual(1, len(node.expression.modifiers))
        self.assertIsInstance(node.expression.modifiers[0], ast.BinaryOp)

    def test_dfm_property_newline_stops_before_following_expression_statement(self):
        text = "X = DFM PROPERTY M1_LC\nALL_CPO_S1\n"
        tree, warnings = parse_with_diagnostics(text, strict=True)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 2)
        self.assertIsInstance(tree.statements[0], ast.LayerAssignment)
        self.assertIsInstance(tree.statements[0].expression, ast.DRCOp)
        self.assertEqual(tree.statements[0].expression.op, "DFM PROPERTY")
        self.assertEqual(["M1_LC"], [operand.name for operand in tree.statements[0].expression.operands])
        self.assertIsInstance(tree.statements[1], ast.LayerRef)
        self.assertEqual(tree.statements[1].name, "ALL_CPO_S1")

    def test_bracket_assignment_keyword_name(self):
        tree, warnings = parse_with_diagnostics("_T = [ ENC = 1 ]")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertEqual(node.expression.op, "=")

    def test_rectangle_by_constraint_modifier(self):
        text = "_T = RECTANGLE BM0_OD1I == BM0_OD_W_1 BY == BM0_OD_L_1 ORTHOGONAL ONLY"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.DRCOp)
        self.assertEqual(node.expression.op, "RECTANGLE")

    def test_colon_qualified_rule_name(self):
        text = "OPTION.SEALRING:ERROR1 {\n  MERGE CHIP\n}\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertEqual(node.name, "OPTION.SEALRING:ERROR1")
        self.assertEqual(len(node.body), 1)
        self.assertIsInstance(node.body[0], ast.UnaryOp)
        self.assertEqual(node.body[0].op, "MERGE")

    def test_with_text_filter(self):
        text = "_T = M1I WITH TEXT VDD_TEXT M1_PIN_TEXT PRIMARY ONLY"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.DRCOp)
        self.assertEqual(node.expression.op, "WITH TEXT")
        self.assertIn("PRIMARY", node.expression.modifiers)
        self.assertIn("ONLY", node.expression.modifiers)

    def test_dollar_reference_expression(self):
        text = "_T = OFFGRID LAYER_A 0.001 * $PRECISION REGION 0.005"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.DRCOp)

    def test_tilde_unary_expression(self):
        text = "_T = ~(AREA(A) - 1)"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.UnaryOp)
        self.assertEqual(node.expression.op, "~")

    def test_postfix_rectangle_filter(self):
        text = "_T = V0 RECTANGLE ORTHOGONAL ONLY ASPECT == 1"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.DRCOp)
        self.assertEqual(node.expression.op, "RECTANGLE")

    def test_disconnect_directive(self):
        tree, warnings = parse_with_diagnostics("DISCONNECT\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.Directive)
        self.assertEqual(node.keywords, ["DISCONNECT"])

    def test_not_coin_inside_edge(self):
        tree, warnings = parse_with_diagnostics("_T = A NOT COIN INSIDE EDGE B")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertEqual(node.expression.op, "NOT COIN INSIDE EDGE")

    def test_not_touch_outside_edge(self):
        tree, warnings = parse_with_diagnostics("_T = EXPAND EDGE (A NOT TOUCH OUTSIDE EDGE B) OUTSIDE BY GRID")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.DRCOp)
        self.assertEqual(node.expression.op, "EXPAND EDGE")

    def test_holes_inner_modifier(self):
        tree, warnings = parse_with_diagnostics("_T = (HOLES A INNER) NOT A")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertEqual(node.expression.op, "NOT")

    def test_inside_cell_prefix(self):
        tree, warnings = parse_with_diagnostics("_T = INSIDE CELL VARI CellsForRRuleAnalog")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.DRCOp)
        self.assertEqual(node.expression.op, "INSIDE CELL")

    def test_not_inside_cell_prefix(self):
        tree, warnings = parse_with_diagnostics("_T = NOT INSIDE CELL VARI ExclCellsForRRuleAnalog")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.DRCOp)
        self.assertEqual(node.expression.op, "NOT INSIDE CELL")

    def test_dvparams_directive_in_rule(self):
        text = (
            "RULE1 {\n"
            "  DVPARAMS NET_PROP_LAYER \"Volt_Low\" 0.0 \"Volt_High\" 0.0 \"LUP_NO_SYNC\" > 0.0 <= 1.155 UNIDIRECTIONAL ANNOTATE\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertEqual(len(node.body), 1)
        self.assertIsInstance(node.body[0], ast.Directive)
        self.assertEqual(node.body[0].keywords, ["DVPARAMS"])

    def test_trace_property_same_line_statement_boundary(self):
        text = "TRACE PROPERTY DEV1 P1 GROUP G1 A\n"
        tree, warnings = parse_with_diagnostics(text, strict=True)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 2)
        self.assertIsInstance(tree.statements[0], ast.TraceProperty)
        self.assertEqual(tree.statements[0].device, "DEV1")
        self.assertEqual(tree.statements[0].args, ["P1"])
        self.assertIsInstance(tree.statements[1], ast.Group)
        self.assertEqual(tree.statements[1].name, "G1")
        self.assertEqual(tree.statements[1].members, ["A"])

    def test_numeric_arithmetic_constraint(self):
        text = "_T = INT X2 > 0.100+5*GRID < 0.100*2 ABUT < 90"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.DRCOp)

    def test_empty_area_call(self):
        tree, warnings = parse_with_diagnostics("_T = AREA()")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "AREA")

    def test_ret_prefix_operation(self):
        text = "_T = (RET NMDPC P48_M2_EP M2_LOP FILE P48_M2DPFILE MAP LOOP) NOT OUTSIDE M2_P48"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.BinaryOp)

    def test_extents_prefix_operation(self):
        tree, warnings = parse_with_diagnostics("_T = (EXTENTS A) NOT B")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.BinaryOp)

    def test_multiline_ternary_continuation(self):
        text = (
            "[PROPERTY P1\n"
            "  V = (COUNT(A)==0) ?\n"
            "      0 :\n"
            "      (COUNT(B)>0) ? MIN(PROPERTY(B, X)) :\n"
            "      1\n"
            "]"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.PropertyBlock)

    def test_deep_ternary_chain_parses_iteratively(self):
        expr = "0"
        for idx in range(1400, 0, -1):
            expr = f"C{idx} ? {idx} : {expr}"
        tree, warnings = parse_with_diagnostics(f"X = {expr}\n")
        self.assertEqual(warnings, [])
        self.assertIsInstance(tree.statements[0], ast.LayerAssignment)
        self.assertIsInstance(tree.statements[0].expression, ast.BinaryOp)
        self.assertEqual(tree.statements[0].expression.op, "?:")

    def test_group_wildcard_pattern(self):
        tree = parse("GROUP CHK_DENSITY_ONLY ?.DN.?")
        node = tree.statements[0]
        self.assertIsInstance(node, ast.Group)
        self.assertEqual(node.name, "CHK_DENSITY_ONLY")
        self.assertIn("DN.?", [str(member) for member in node.members])

    def test_group_same_line_statement_boundary(self):
        tree, warnings = parse_with_diagnostics("GROUP G1 A B GROUP G2 C\n", strict=True)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 2)
        self.assertIsInstance(tree.statements[0], ast.Group)
        self.assertEqual(tree.statements[0].name, "G1")
        self.assertEqual(tree.statements[0].members, ["A", "B"])
        self.assertIsInstance(tree.statements[1], ast.Group)
        self.assertEqual(tree.statements[1].name, "G2")
        self.assertEqual(tree.statements[1].members, ["C"])

    def test_device_same_line_statement_boundary(self):
        text = "DEVICE D1 M1 P1 DEVICE D2 M2 P2\n"
        tree, warnings = parse_with_diagnostics(text, strict=True)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 2)
        self.assertIsInstance(tree.statements[0], ast.Device)
        self.assertEqual(tree.statements[0].device_name, "D1")
        self.assertEqual(tree.statements[0].seed_layer, "M1")
        self.assertEqual(tree.statements[0].pins, [("P1", None)])
        self.assertIsInstance(tree.statements[1], ast.Device)
        self.assertEqual(tree.statements[1].device_name, "D2")
        self.assertEqual(tree.statements[1].seed_layer, "M2")
        self.assertEqual(tree.statements[1].pins, [("P2", None)])

    def test_device_cmacro_args_extend_to_statement_end(self):
        text = (
            "DEVICE R(rnwsti_2t_ckt) RES_RNWSTI_2T nwell(POS) nwell(NEG) "
            "CMACRO MEASURE_RESISTOR RES_RNWSTI_2T nwell rsh_rnwst dw_rnwst dl_rnwst NETLIST ELEMENT X\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 1)
        node = tree.statements[0]
        self.assertIsInstance(node, ast.Device)
        self.assertEqual(node.cmacro, "MEASURE_RESISTOR")
        self.assertEqual(
            node.cmacro_args,
            [
                "RES_RNWSTI_2T",
                "NWELL",
                "RSH_RNWST",
                "DW_RNWST",
                "DL_RNWST",
                "NETLIST",
                "ELEMENT",
                "X",
            ],
        )

    def test_directive_same_line_statement_boundary(self):
        text = "LVS IGNORE PORTS YES DRC INCREMENTAL CONNECT NO\n"
        tree, warnings = parse_with_diagnostics(text, strict=True)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 2)
        self.assertIsInstance(tree.statements[0], ast.Directive)
        self.assertEqual(tree.statements[0].keywords, ["LVS", "IGNORE", "PORTS", "YES"])
        self.assertEqual(tree.statements[0].arguments, [])
        self.assertIsInstance(tree.statements[1], ast.Directive)
        self.assertEqual(tree.statements[1].keywords, ["DRC", "INCREMENTAL", "CONNECT", "NO"])
        self.assertEqual(tree.statements[1].arguments, [])

    def test_same_line_parse_error_recovery_preserves_following_statement(self):
        text = "GROUP ) GROUP G2 C\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(len(warnings), 1)
        self.assertIsInstance(tree.statements[0], ast.ErrorNode)
        self.assertEqual(tree.statements[0].skipped_text, "GROUP")
        self.assertIn("statement_head:GROUP -> closing_delimiter:)", warnings[0].message)
        self.assertIsInstance(tree.statements[1], ast.Group)
        self.assertEqual(tree.statements[1].name, "G2")
        self.assertEqual(tree.statements[1].members, ["C"])

    def test_same_line_unknown_content_preserves_following_statement(self):
        text = "; GROUP G1 A\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(len(warnings), 1)
        self.assertIsInstance(tree.statements[0], ast.ErrorNode)
        self.assertEqual(tree.statements[0].skipped_text, ";")
        self.assertIsInstance(tree.statements[1], ast.Group)
        self.assertEqual(tree.statements[1].name, "G1")
        self.assertEqual(tree.statements[1].members, ["A"])

    def test_double_bang_measurement(self):
        tree = parse("_T = !!AREA(ACT_GATE)")
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.UnaryOp)
        self.assertEqual(node.expression.op, "NOT")
        self.assertIsInstance(node.expression.operand, ast.UnaryOp)
        self.assertEqual(node.expression.operand.op, "NOT")

    def test_ifdef_shared_rule_body(self):
        text = (
            "#IFDEF ALT\n"
            "RULE1:ALT { @ alternate header\n"
            "#ELSE\n"
            "RULE1 { @ default header\n"
            "#ENDIF\n"
            "  BAD = M1 NOT M2\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.IfDef)
        self.assertEqual(len(node.then_body), 1)
        self.assertEqual(len(node.else_body), 1)
        self.assertIsInstance(node.then_body[0], ast.RuleCheckBlock)
        self.assertIsInstance(node.else_body[0], ast.RuleCheckBlock)
        self.assertEqual(node.then_body[0].name, "RULE1:ALT")
        self.assertEqual(node.else_body[0].name, "RULE1")
        self.assertEqual(len(node.then_body[0].body), 1)
        self.assertEqual(len(node.else_body[0].body), 1)

    def test_colon_qualified_assignment_name(self):
        tree, warnings = parse_with_diagnostics("DRC:1 = EXTENT DRAWN ORIGINAL\nBULK = SIZE DRC:1 BY 1.0\n")
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 2)
        self.assertIsInstance(tree.statements[0], ast.LayerAssignment)
        self.assertEqual(tree.statements[0].name, "DRC:1")
        self.assertIsInstance(tree.statements[1], ast.LayerAssignment)

    def test_colon_qualified_property_name(self):
        tree, warnings = parse_with_diagnostics("[PROPERTY P1\n  GATE_ACTIVE:NUM = COUNT(GATE_ACTIVE)\n]")
        self.assertEqual(warnings, [])
        block = tree.statements[0]
        self.assertIsInstance(block, ast.PropertyBlock)
        self.assertEqual(block.body[0].name, "GATE_ACTIVE:NUM")

    def test_double_colon_qualified_name(self):
        tree, warnings = parse_with_diagnostics("SA = W / SUM(S::W / (S::A + 0.5 * L)) - 0.5 * L")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)

    def test_postfix_length_constraint(self):
        tree, warnings = parse_with_diagnostics("_T = (LAYER_A LENGTH != LIMIT_A) LENGTH != LIMIT_B")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)

    def test_postfix_size_by(self):
        tree, warnings = parse_with_diagnostics("_T = ((SRM OR SRAMDMY) SIZE BY M0_R_19_S) NOT (SRM OR SRAMDMY)")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.BinaryOp)

    def test_dfm_rdb_parenthesized_modifier(self):
        text = "RULE1 {\n  DFM RDB (FLATTEN POST_DRIVER_ACT) LUP_2_INJ.RDB NOEMPTY NOPSEUDO MAXIMUM ALL\n}\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertEqual(len(node.body), 1)
        self.assertIsInstance(node.body[0], ast.DRCOp)
        self.assertEqual(node.body[0].op, "DFM RDB")
        self.assertEqual(
            ["(FLATTEN POST_DRIVER_ACT)", "LUP_2_INJ.RDB", "NOEMPTY", "NOPSEUDO", "MAXIMUM", "ALL"],
            node.body[0].modifiers,
        )

    def test_dfm_rdb_nested_parenthesized_modifier_in_strict_mode(self):
        text = (
            "RULE1 {\n"
            "  DFM RDB (FLATTEN (SIZE TRIGGER_SOURCE BY 45)) LUP_13_0_1_WIN.RDB NOEMPTY NOPSEUDO MAXIMUM ALL\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text, strict=True)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertEqual(len(node.body), 1)
        self.assertIsInstance(node.body[0], ast.DRCOp)
        self.assertEqual(
            node.body[0].modifiers,
            ["(FLATTEN (SIZE TRIGGER_SOURCE BY 45))", "LUP_13_0_1_WIN.RDB", "NOEMPTY", "NOPSEUDO", "MAXIMUM", "ALL"],
        )

    def test_dfm_rdb_names_are_not_layer_operands(self):
        tree, warnings = parse_with_diagnostics("DFM RDB BAD_CHIP DTCD.R.9.1.TCDDMY_ALL NOEMPTY\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.DRCOp)
        self.assertEqual("DFM RDB", node.op)
        self.assertEqual([], node.operands)
        self.assertEqual(["BAD_CHIP", "DTCD.R.9.1.TCDDMY_ALL", "NOEMPTY"], node.modifiers)

    def test_dfm_dv_treats_dvparams_clause_as_modifiers(self):
        text = (
            "RULE1 {\n"
            '  ERR1 = DFM DV PSD PW_0 < AA_EN_3A_VAL DVPARAMS net_vol_assign "min_vol" 0 "max_vol" 0 "syncID" > 3.63 ANNOTATE NOT CONNECTED SINGULAR MEASURE ALL\n'
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text, strict=True)
        self.assertEqual(warnings, [])
        rule = tree.statements[0]
        self.assertIsInstance(rule, ast.RuleCheckBlock)
        node = rule.body[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.DRCOp)
        self.assertEqual(node.expression.op, "DFM DV")
        self.assertEqual([operand.name for operand in node.expression.operands[:2]], ["PSD", "PW_0"])
        self.assertIn("DVPARAMS", node.expression.modifiers)

    def test_bracket_plus_equals_expression(self):
        tree, warnings = parse_with_diagnostics("_T = [+= COUNT(A)] > 0")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.ConstrainedExpr)

    def test_standalone_bracket_expression_in_rule(self):
        text = "RULE1 {\n  [M1_AREA = AREA(M1)] > 0\n}\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertEqual(len(node.body), 1)
        self.assertIsInstance(node.body[0], ast.ConstrainedExpr)

    def test_multiline_assignment_after_equals(self):
        text = (
            "ANT_FILTER =\n"
            "NET AREA RATIO V0 INPUT_A INPUT_B GATE >= 0 ACCUMULATE\n"
            "[!AREA(V0) / !!AREA(GATE)]\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsNotNone(node.expression)

    def test_multiline_assignment_stops_before_following_top_level_statement(self):
        text = (
            "ANT_FILTER =\n"
            "NET AREA RATIO V0 INPUT_A INPUT_B GATE >= 0 ACCUMULATE\n"
            "[!AREA(V0) / !!AREA(GATE)]\n"
            "GROUP G1 M1\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 2)
        self.assertIsInstance(tree.statements[0], ast.LayerAssignment)
        self.assertIsInstance(tree.statements[1], ast.Group)
        self.assertEqual(tree.statements[1].name, "G1")

    def test_multiline_infix_rhs_continuation(self):
        text = (
            "RULE1 {\n"
            "  X = (A AND B) OR\n"
            "      (C AND D)\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertEqual(len(node.body), 1)

    def test_good_modifier_continuation(self):
        text = (
            "RULE1 {\n"
            "  BAD = RECTANGLE ENCLOSURE VIA1 M1 ABUT<90 SINGULAR\n"
            "  GOOD 0.02 0.02 0.02 0.02 OPPOSITE\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertIsInstance(node.body[0], ast.LayerAssignment)

    def test_rule_modifier_continuation_stops_before_closing_brace_and_following_statement(self):
        text = (
            "RULE1 {\n"
            "  BAD = RECTANGLE ENCLOSURE VIA1 M1 ABUT<90 SINGULAR\n"
            "  GOOD 0.02 0.02 0.02 0.02 OPPOSITE\n"
            "}\n"
            "GROUP G1 M1\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 2)
        self.assertIsInstance(tree.statements[0], ast.RuleCheckBlock)
        self.assertEqual(len(tree.statements[0].body), 1)
        self.assertIsInstance(tree.statements[1], ast.Group)
        self.assertEqual(tree.statements[1].name, "G1")

    def test_resolve_semicolon_directive(self):
        text = "RULE1 {\n  RESOLVE ;\n  OUTPUT ALL CONFLICTS ;\n}\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertEqual(len(node.body), 2)
        self.assertIsInstance(node.body[0], ast.Directive)

    def test_prefix_or_edge_with_parenthesized_rhs(self):
        text = "_T = OR EDGE LTU_GOOD_EDGES_108 (LTU_GOOD_EDGES_001 OR EDGE LTU_GOOD_EDGES_002)"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertEqual(node.expression.op, "OR EDGE")

    def test_interact_with_modifiers_inside_parentheses(self):
        text = "_T = ENC (VIA_INPUT INTERACT MIN_WID_MET_ALL SINGULAR ALSO) M1 < 0.0005 SINGULAR REGION"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.DRCOp)

    def test_region_extents_modifier_inside_parenthesized_operation(self):
        text = (
            "RULE1 {\n"
            "  ERR1 = (INT ALL_AA_IO < 0.144 ABUT<90 SINGULAR REGION EXTENTS) AND DG\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertIsInstance(node.body[0], ast.LayerAssignment)
        self.assertIsInstance(node.body[0].expression, ast.BinaryOp)

    def test_region_extents_modifier_before_with_edge(self):
        text = (
            "RULE1 {\n"
            "  LONG_EDGES = LENGTH M4 > 0.08\n"
            "  ERR1 = (EXT M4 <= GRID ABUT == 90 INTERSECTING ONLY REGION EXTENTS) WITH EDGE LONG_EDGES == 2\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertIsInstance(node.body[1], ast.LayerAssignment)

    def test_with_neighbor_space_modifier(self):
        text = "_T = VIA_INPUT INTERACT ((VIA_REGION INTERACT COLOR_A) WITH NEIGHBOR == 1 SPACE <= 0.5)"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)

    def test_path_length_prefix_operation(self):
        text = "_T = EDGE_SET_A COIN EDGE (PATH LENGTH (EDGE_SET_B OR EDGE EDGE_SET_A) > 0.27)"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)

    def test_constraint_modifiers_even_odd(self):
        text = "_T = PATH_A INTERACT LOP < 100000 ODD SINGULAR ALSO"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.ConstrainedExpr)
        self.assertIn("ODD", node.expression.modifiers)

    def test_postfix_holes_inner_expression(self):
        text = "_T = (NW HOLES INNER) ENCLOSE ACTIVE"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertEqual(node.expression.op, "ENCLOSE")

    def test_multiline_prefix_boolean_inside_parens(self):
        text = (
            "RULE1 {\n"
            "  SELECTED_VIA = VIA_INPUT NOT (OR \n"
            "      VIA_A \n"
            "      VIA_B \n"
            "  )\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertEqual(len(node.body), 1)
        self.assertIsInstance(node.body[0], ast.LayerAssignment)

    def test_property_header_ifdef_comma_fragment(self):
        text = (
            "[PROPERTY l,w,mode_a\n"
            "  #IFDEF ENABLE_OPTION FALSE\n"
            "      ,mode_b\n"
            "  #ENDIF\n"
            "  nfin = COUNT(layer1)\n"
            "]"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        block = tree.statements[0]
        self.assertIsInstance(block, ast.PropertyBlock)
        self.assertEqual(block.properties, ["L", "W", "MODE_A", "MODE_B"])
        self.assertEqual(block.body[0].name, "NFIN")

    def test_top_level_ternary_expression_statement(self):
        text = "#IFDEF FLAG\n(COUNT(A) > 0) ? 1 : 0\n#ENDIF\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.IfDef)
        self.assertEqual(len(node.then_body), 1)
        self.assertIsInstance(node.then_body[0], ast.BinaryOp)

    def test_top_level_not_expression_statement(self):
        tree, warnings = parse_with_diagnostics("CHECK_REGION_PRE1 NOT CHECK_REGION_PRE2\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.BinaryOp)
        self.assertEqual(node.op, "NOT")

    def test_pathchk_boolean_expression(self):
        text = "RULE1 {\n  X = PATHCHK !POWER && !GROUND NOFLOAT\n}\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertEqual(len(node.body), 1)
        self.assertIsInstance(node.body[0], ast.LayerAssignment)
        self.assertIsInstance(node.body[0].expression, ast.DRCOp)
        self.assertEqual(node.body[0].expression.op, "PATHCHK")

    def test_multiline_bracketed_directive_option_block(self):
        text = (
            "LVS REDUCE PARALLEL MOS YES\n"
            "    [   TOLERANCE l 0\n"
            "        effective l,nfin\n"
            "        l  = sum(l)/count()\n"
            "        nfin = sum(nfin)\n"
            "   ]\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 1)
        node = tree.statements[0]
        self.assertIsInstance(node, ast.Directive)
        self.assertEqual(node.keywords[:1], ["LVS"])
        self.assertTrue(any(isinstance(arg, str) and arg.startswith("[") for arg in node.arguments))

    def test_ifdef_shared_property_header_in_dmacro(self):
        text = (
            "DMACRO MEASURE_DEVICE seed_layer proclayer1 proclayer2 {\n"
            "  #IFDEF OUTPUT_MODE 1\n"
            "    [ PROPERTY l,w,nfin,mr,row,col,array\n"
            "  #ELSE\n"
            "    [ PROPERTY l,w,nfin,mr\n"
            "  #ENDIF\n"
            "      nfin = COUNT(proclayer1)\n"
            "      mr = COUNT(seed_layer)\n"
            "      row = 1\n"
            "  ]\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        macro = tree.statements[0]
        self.assertIsInstance(macro, ast.DMacro)
        self.assertEqual(len(macro.body), 1)
        cond = macro.body[0]
        self.assertIsInstance(cond, ast.IfDef)
        self.assertEqual(len(cond.then_body), 1)
        self.assertEqual(len(cond.else_body), 1)
        self.assertIsInstance(cond.then_body[0], ast.PropertyBlock)
        self.assertEqual(cond.then_body[0].properties, ["L", "W", "NFIN", "MR", "ROW", "COL", "ARRAY"])
        self.assertEqual(cond.else_body[0].properties, ["L", "W", "NFIN", "MR"])

    def test_directive_statement_inside_dmacro_in_strict_mode(self):
        text = (
            "DMACRO REDUCE_DEVICE device_name {\n"
            "  LVS REDUCE device_name PARALLEL yes\n"
            "  [ effective LR,WR,NF\n"
            "    LR = sum(LR*NF)/sum(NF)\n"
            "    WR = sum(WR*NF)/sum(NF)\n"
            "    NF = sum(NF)\n"
            "  ]\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text, strict=True)
        self.assertEqual(warnings, [])
        macro = tree.statements[0]
        self.assertIsInstance(macro, ast.DMacro)
        self.assertEqual(len(macro.body), 1)
        self.assertIsInstance(macro.body[0], ast.Directive)
        self.assertEqual(macro.body[0].keywords, ["LVS", "REDUCE"])

    def test_sequential_ifdef_property_headers_in_dmacro(self):
        text = (
            "DMACRO MEASURE_RESISTOR res_seed res_ter rsh_value dw_value dl_value {\n"
            "  #IFDEF OUTPUT_MODE 1\n"
            "   [PROPERTY wr,lr,mr,FR\n"
            "  #ENDIF\n"
            "  #IFDEF OUTPUT_MODE 2\n"
            "   [PROPERTY wr,lr,mr\n"
            "  #ENDIF\n"
            "    wr = PERIM_CO(res_seed,res_ter)/2\n"
            "    lr = AREA(res_seed)/wr\n"
            "    FR = 1\n"
            "   ]\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        macro = tree.statements[0]
        self.assertIsInstance(macro, ast.DMacro)
        self.assertGreaterEqual(len(macro.body), 2)
        self.assertTrue(any(isinstance(stmt, ast.IfDef) for stmt in macro.body))

    def test_strict_chained_ifdef_property_headers_share_body(self):
        text = (
            "DMACRO CHECK_RESISTOR res_seed res_ter rsh_value dw_value dl_value {\n"
            "  #IFDEF OUTPUT_MODE 1\n"
            "    [PROPERTY W,L,MR,FR,flag_cc,resistor_flag\n"
            "  #ENDIF\n"
            "  #IFDEF OUTPUT_MODE 2\n"
            "    [PROPERTY W,L,MR,flag_cc,resistor_flag\n"
            "  #ENDIF\n"
            "  #IFDEF RESISTOR_MODE 1\n"
            "    resistor_flag = 1\n"
            "  #ENDIF\n"
            "  W = 1\n"
            "  ]\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text, strict=True)
        self.assertEqual(warnings, [])
        macro = tree.statements[0]
        self.assertIsInstance(macro, ast.DMacro)
        self.assertEqual(len(macro.body), 2)
        for stmt in macro.body:
            self.assertIsInstance(stmt, ast.IfDef)
            self.assertEqual(len(stmt.then_body), 1)
            block = stmt.then_body[0]
            self.assertIsInstance(block, ast.PropertyBlock)
            self.assertEqual(len(block.body), 2)
            self.assertIsInstance(block.body[0], ast.IfDef)
            self.assertIsInstance(block.body[1], ast.LayerAssignment)
            self.assertEqual(block.body[1].name, "W")

    def test_prefix_or_assignment_stops_before_rulecheck(self):
        text = (
            "A = OR LAYER_A LAYER_B\n"
            "\n"
            "WIDTH_CHECK {\n"
            "  @ width check\n"
            "  err1 = INT LAYER_C < 0.001\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 2)
        self.assertIsInstance(tree.statements[0], ast.LayerAssignment)
        self.assertIsInstance(tree.statements[1], ast.RuleCheckBlock)

    def test_prefix_or_assignment_stops_before_layer_statement_in_strict_mode(self):
        text = (
            "LAYER_SET = OR LAYER_A LAYER_B LAYER_C\n"
            "\n"
            "LAYER SRM 5000\n"
        )
        tree, warnings = parse_with_diagnostics(text, strict=True)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 2)
        self.assertIsInstance(tree.statements[0], ast.LayerAssignment)
        self.assertIsInstance(tree.statements[1], ast.LayerDef)
        self.assertEqual(tree.statements[1].name, "SRM")

    def test_bracket_expression_with_preprocessor_fallback(self):
        text = (
            "RULE1 {\n"
            "  X = [ Volt_High = (COUNT(A) == 0) ? 0 :\n"
            "#IFDEF USE_ALT\n"
            "      (COUNT(B) > 0) ? 1 :\n"
            "#ELSE\n"
            "      (COUNT(C) > 0) ? 2 :\n"
            "#ENDIF\n"
            "      : 3 ]\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.RuleCheckBlock)
        self.assertEqual(len(node.body), 1)
        self.assertIsInstance(node.body[0], ast.LayerAssignment)
        self.assertIsInstance(node.body[0].expression, ast.StringLiteral)

    def test_measurement_constraint_before_operand(self):
        text = (
            "RULE1 {\n"
            "  X = LENGTH < MIN_LENGTH (EDGE_SET_A COIN EDGE EDGE_SET_B)\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        rule = tree.statements[0]
        self.assertIsInstance(rule, ast.RuleCheckBlock)
        node = rule.body[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.ConstrainedExpr)
        self.assertEqual(node.expression.expr.op, "LENGTH")
        self.assertEqual(node.expression.constraints[0].op, "<")

    def test_rule_expression_newline_does_not_swallow_next_parenthesized_statement(self):
        text = (
            "RULE1 {\n"
            "  A = LENGTH ((CONVEX EDGE X ANGLE1 == 90 ANGLE2 == 90 WITH LENGTH == L1) COIN EDGE Y) == V\n"
            "  X NOT WITH EDGE A == 2\n"
            "\n"
            "  (CONVEX EDGE X2 ANGLE1 == 90 ANGLE2 == 90 WITH LENGTH == W) NOT COIN EDGE Y\n"
            "  B = LENGTH ((CONVEX EDGE X2 ANGLE1 == 90 ANGLE2 == 90 WITH LENGTH == L2) COIN EDGE Y) == V2\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        rule = tree.statements[0]
        self.assertIsInstance(rule, ast.RuleCheckBlock)
        self.assertEqual(len(rule.body), 4)
        self.assertIsInstance(rule.body[0], ast.LayerAssignment)
        self.assertIsInstance(rule.body[3], ast.LayerAssignment)
        self.assertEqual(rule.body[3].name, "B")

    def test_rule_same_line_drc_operations_split_after_constraint(self):
        text = "RULE1 { INT M1 < 0.1 INT M2 < 0.2 }\n"
        tree, warnings = parse_with_diagnostics(text, strict=True)
        self.assertEqual(warnings, [])
        rule = tree.statements[0]
        self.assertIsInstance(rule, ast.RuleCheckBlock)
        self.assertEqual(len(rule.body), 2)
        self.assertIsInstance(rule.body[0], ast.DRCOp)
        self.assertEqual(rule.body[0].op, "INT")
        self.assertEqual(rule.body[0].operands[0].name, "M1")
        self.assertIsInstance(rule.body[1], ast.DRCOp)
        self.assertEqual(rule.body[1].op, "INT")
        self.assertEqual(rule.body[1].operands[0].name, "M2")

    def test_density_bracket_modifier_stops_before_next_dfm_statement(self):
        text = (
            "RULE1 {\n"
            "  DENSITY A B C D < E WINDOW F STEP G BACKUP INSIDE OF LAYER H PRINT I RDB J\n"
            "           [~(AREA(D)-F*F/2)]\n"
            "  DFM RDB (FLATTEN X) Y NOEMPTY NOPSEUDO MAXIMUM ALL\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        rule = tree.statements[0]
        self.assertIsInstance(rule, ast.RuleCheckBlock)
        self.assertEqual(len(rule.body), 2)
        self.assertIsInstance(rule.body[0], ast.DRCOp)
        self.assertEqual(rule.body[0].op, "DENSITY")
        self.assertIsInstance(rule.body[1], ast.DRCOp)
        self.assertEqual(rule.body[1].op, "DFM RDB")

    def test_ifdef_rule_variants_with_shared_tail(self):
        text = (
            "#IFDEF WLCSP\n"
            "RULE1 { @ branch a\n"
            "  A = COPY XA\n"
            "#ELSE\n"
            "RULE1 { @ branch b\n"
            "  A = COPY XB\n"
            "#ENDIF\n"
            "  B = COPY A\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.IfDef)
        self.assertEqual(len(node.then_body), 1)
        self.assertEqual(len(node.else_body), 1)
        then_rule = node.then_body[0]
        else_rule = node.else_body[0]
        self.assertIsInstance(then_rule, ast.RuleCheckBlock)
        self.assertIsInstance(else_rule, ast.RuleCheckBlock)
        self.assertEqual(len(then_rule.body), 2)
        self.assertEqual(len(else_rule.body), 2)
        self.assertEqual(then_rule.body[0].name, "A")
        self.assertEqual(else_rule.body[0].name, "A")
        self.assertEqual(then_rule.body[1].name, "B")
        self.assertEqual(else_rule.body[1].name, "B")

    def test_parenthesized_binary_with_trailing_modifiers(self):
        text = (
            "RULE1 {\n"
            "  (SR_POLY TOUCH EDGE (EXT_PO_CHK TOUCH EDGE PO_EXT_BAD_EDGE) ENDPOINT ONLY) NOT OUTSIDE EDGE PO_P76\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        rule = tree.statements[0]
        self.assertIsInstance(rule, ast.RuleCheckBlock)
        self.assertEqual(len(rule.body), 1)
        self.assertIsInstance(rule.body[0], ast.BinaryOp)
        self.assertEqual(rule.body[0].op, "NOT OUTSIDE EDGE")

    def test_dfm_dp_parenthesized_scalar_option(self):
        text = (
            "RULE1 {\n"
            "  X = (DFM DP RING M2_LOP P48_M2_EP (OPPOSITE 0)) NOT OUTSIDE M2_P48\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        rule = tree.statements[0]
        self.assertIsInstance(rule, ast.RuleCheckBlock)
        node = rule.body[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertEqual(node.expression.op, "NOT OUTSIDE")

    def test_top_level_bare_name_statement(self):
        tree, warnings = parse_with_diagnostics("ALL_CPO_S1\n")
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 1)
        self.assertIsInstance(tree.statements[0], ast.LayerRef)
        self.assertEqual(tree.statements[0].name, "ALL_CPO_S1")

    def test_drawn_skew_parses_as_modifier_in_strict_mode(self):
        text = "RULE1 {\n  DRAWN SKEW\n}\n"
        tree, warnings = parse_with_diagnostics(text, strict=True)
        self.assertEqual(warnings, [])
        rule = tree.statements[0]
        self.assertIsInstance(rule, ast.RuleCheckBlock)
        self.assertEqual(len(rule.body), 1)
        self.assertIsInstance(rule.body[0], ast.DRCOp)
        self.assertEqual(rule.body[0].op, "DRAWN")
        self.assertEqual(rule.body[0].modifiers, ["SKEW"])

    def test_multiline_dfm_property_operand_list(self):
        text = (
            "X = DFM PROPERTY M1_LC\n"
            "A B C D\n"
            "[COUNT = (COUNT(A) > 0 || COUNT(B) > 0)]\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.DRCOp)
        self.assertEqual(node.expression.op, "DFM PROPERTY")
        self.assertGreaterEqual(len(node.expression.operands), 5)

    def test_multiline_dfm_property_stops_before_dmacro(self):
        text = (
            "X = DFM PROPERTY A B NODAL MULTI\n"
            "[ Volt = FMIN(((COUNT(M13_LV_ID)>0) ? MIN(PROPERTY(M13_LV_ID , M13_MLV )) : 10),\n"
            "(COUNT(AP_LV_ID)>0) ? MIN(PROPERTY(AP_LV_ID , AP_MLV )) : 10 ) ]\n"
            "DMACRO VOLTAGE_ANNOTATE_2 MX_IN MXV_IN MX_OUT {\n"
            "  MX_OUT = DFM PROPERTY MX_IN MXV_IN NODAL MULTI\n"
            "  [ VOLT_HIGH = PROPERTY(MXV_IN,\"Volt_High\")]\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 2)
        self.assertIsInstance(tree.statements[0], ast.LayerAssignment)
        self.assertIsInstance(tree.statements[1], ast.DMacro)

    def test_ret_subtype_and_file_map_are_not_operands(self):
        tree, warnings = parse_with_diagnostics(
            "X = RET NMDPC M1_EP M1 FILE M1anchordpfile MAP loop\n",
            strict=True,
        )
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.DRCOp)
        self.assertEqual("RET NMDPC", node.expression.op)
        self.assertEqual(["M1_EP", "M1"], [operand.name for operand in node.expression.operands])
        self.assertEqual(["FILE", "M1ANCHORDPFILE", "MAP", "LOOP"], node.expression.modifiers)

    def test_dfm_ret_emulation_options_are_not_operands(self):
        tree, warnings = parse_with_diagnostics(
            "DFM RET NMDPC EMULATION YES\n",
            strict=True,
        )
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.DRCOp)
        self.assertEqual("DFM RET NMDPC", node.op)
        self.assertEqual([], node.operands)
        self.assertEqual(["EMULATION", "YES"], node.modifiers)

    def test_push_medium_parenthesized_operand_is_single_operation(self):
        tree, warnings = parse_with_diagnostics("COD_H = PUSH MEDIUM (COD_H_1 OR COD_H_2)\n", strict=True)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node.expression, ast.DRCOp)
        self.assertEqual("PUSH", node.expression.op)
        self.assertEqual(["MEDIUM"], node.expression.modifiers)
        self.assertEqual(1, len(node.expression.operands))
        self.assertIsInstance(node.expression.operands[0], ast.BinaryOp)

    def test_if_expr_with_spaced_function_call(self):
        text = (
            "DMACRO T X {\n"
            "  IF ( IS_MISSING ( X ) == 1 ) {\n"
            "    X = 1\n"
            "  }\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        macro = tree.statements[0]
        self.assertIsInstance(macro, ast.DMacro)
        self.assertIsInstance(macro.body[0], ast.IfExpr)

    def test_tvf_function_directive(self):
        text = "TVF FUNCTION Perc_ADP_properties [/* body */]\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 1)
        self.assertIsInstance(tree.statements[0], ast.Directive)
        self.assertEqual(tree.statements[0].keywords, ["TVF", "FUNCTION"])

    def test_device_bracket_parameter_tuple(self):
        text = "DEVICE C(CPM) PMCAP METAL1 PMCAP [6.760E-2 0]\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 1)
        self.assertIsInstance(tree.statements[0], ast.Device)

    def test_documented_device_abbreviation(self):
        text = "DEV C(CPM) PMCAP METAL1 PMCAP [6.760E-2 0]\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 1)
        self.assertIsInstance(tree.statements[0], ast.Device)

    def test_undocumented_device_abbreviation_is_not_accepted(self):
        text = "DEVI C(CPM) PMCAP METAL1 PMCAP [6.760E-2 0]\n"
        tree, warnings = parse_with_diagnostics(text, strict=False)
        self.assertEqual(len(tree.statements), 1)
        self.assertIsInstance(tree.statements[0], ast.ErrorNode)
        self.assertIn("parser.unrecognized_statement", {warning.code for warning in warnings})

    def test_abs_function_not_rewritten_as_abbreviation(self):
        tree, warnings = parse_with_diagnostics("_T = ABS(1)\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "ABS")

    def test_documented_property_abbreviation(self):
        text = "[PROP P1, P2\n  X = 1\n]"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        self.assertEqual(len(tree.statements), 1)
        self.assertIsInstance(tree.statements[0], ast.PropertyBlock)
        self.assertEqual(tree.statements[0].properties, ["P1", "P2"])

    def test_documented_perimeter_abbreviation(self):
        text = "_T = PERIM M1 == 1"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.ConstrainedExpr)
        self.assertEqual(node.expression.expr.op, "PERIMETER")

    def test_documented_parallel_and_perpendicular_abbreviations(self):
        text = (
            "RULE1 {\n"
            "  INT M1 < 0.1 PARA ONLY\n"
            "  INT M2 < 0.1 PERP ALSO\n"
            "}\n"
        )
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        rule = tree.statements[0]
        self.assertIsInstance(rule, ast.RuleCheckBlock)
        self.assertEqual(len(rule.body), 2)
        self.assertIsInstance(rule.body[0], ast.DRCOp)
        self.assertIn("PARALLEL", rule.body[0].modifiers)
        self.assertIn("ONLY", rule.body[0].modifiers)
        self.assertIsInstance(rule.body[1], ast.DRCOp)
        self.assertIn("PERPENDICULAR", rule.body[1].modifiers)
        self.assertIn("ALSO", rule.body[1].modifiers)

    def test_documented_projecting_abbreviation(self):
        text = "RULE1 {\n  EXT M1 < 0.1 OPPOSITE PROJ > 0 PARA ONLY\n}\n"
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        rule = tree.statements[0]
        self.assertIsInstance(rule, ast.RuleCheckBlock)
        self.assertEqual(len(rule.body), 1)
        self.assertIsInstance(rule.body[0], ast.DRCOp)
        self.assertIn("PROJECTING", rule.body[0].modifiers)
        self.assertIn("PARALLEL", rule.body[0].modifiers)

    def test_trunc_spaced_function_not_rewritten_as_truncate(self):
        tree, warnings = parse_with_diagnostics("_T = TRUNC (1.8)\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "TRUNC")

    def test_doc_math_functions_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics("_T = CEIL (1.2) + FLOOR (2.8)\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertIsInstance(node.expression.left, ast.FuncCall)
        self.assertEqual(node.expression.left.name, "CEIL")
        self.assertIsInstance(node.expression.right, ast.FuncCall)
        self.assertEqual(node.expression.right.name, "FLOOR")

    def test_doc_math_functions_with_long_name_and_zero_args(self):
        tree, warnings = parse_with_diagnostics("_T = ABSOLUTE (1) + PI ()\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertIsInstance(node.expression.left, ast.FuncCall)
        self.assertEqual(node.expression.left.name, "ABSOLUTE")
        self.assertIsInstance(node.expression.right, ast.FuncCall)
        self.assertEqual(node.expression.right.name, "PI")

    def test_doc_dfm_math_function_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics("_T = ROUND (1.25, 2) + FMIN (3, 1, 2)\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertIsInstance(node.expression.left, ast.FuncCall)
        self.assertEqual(node.expression.left.name, "ROUND")
        self.assertIsInstance(node.expression.right, ast.FuncCall)
        self.assertEqual(node.expression.right.name, "FMIN")

    def test_doc_dfm_coordinate_and_property_ref_functions_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics("_T = ECMAX (G2S) - PROPERTY_REF (LX)\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertIsInstance(node.expression.left, ast.FuncCall)
        self.assertEqual(node.expression.left.name, "ECMAX")
        self.assertIsInstance(node.expression.right, ast.FuncCall)
        self.assertEqual(node.expression.right.name, "PROPERTY_REF")

    def test_doc_dfm_vector_functions_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics("_T = VMIN (VECTOR (1, 2, 3), 0)\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "VMIN")
        self.assertIsInstance(node.expression.args[0], ast.FuncCall)
        self.assertEqual(node.expression.args[0].name, "VECTOR")

    def test_doc_dfm_string_vector_functions_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics('_T = CONCAT (VSTRING ("A"), VSTRING ("B"))\n')
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "CONCAT")
        self.assertTrue(all(isinstance(arg, ast.FuncCall) for arg in node.expression.args))
        self.assertEqual([arg.name for arg in node.expression.args], ["VSTRING", "VSTRING"])

    def test_doc_dfm_ec_function_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics("_T = EC (G2S)\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "EC")

    def test_doc_dfm_extended_vector_summary_functions_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics("_T = UNIQUE_COUNT (NORMALIZE_XY (VECTOR (1, 2, 2)))\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "UNIQUE_COUNT")
        self.assertIsInstance(node.expression.args[0], ast.FuncCall)
        self.assertEqual(node.expression.args[0].name, "NORMALIZE_XY")

    def test_doc_text_numeric_function_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics("_T = TEXT_NUMERIC (TPL1, 0.0)\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "TEXT_NUMERIC")

    def test_doc_text_string_function_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics('_T = TEXT_STRING (TPL2, "default")\n')
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "TEXT_STRING")

    def test_doc_string_compare_function_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics('_T = STRING_COMPARE ("A", "B")\n')
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "STRING_COMPARE")

    def test_doc_string_summary_functions_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics('_T = MATCH (NETNAME (PSNETID (M1)), "VDD*")\n')
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "MATCH")
        self.assertIsInstance(node.expression.args[0], ast.FuncCall)
        self.assertEqual(node.expression.args[0].name, "NETNAME")
        self.assertIsInstance(node.expression.args[0].args[0], ast.FuncCall)
        self.assertEqual(node.expression.args[0].args[0].name, "PSNETID")

    def test_doc_emptystring_function_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics("_T = EMPTYSTRING ()\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "EMPTYSTRING")

    def test_doc_dfm_comparison_and_measurement_functions_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics("_T = DRC_GE (EWX (ERR), 0.1)\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "DRC_GE")
        self.assertIsInstance(node.expression.args[0], ast.FuncCall)
        self.assertEqual(node.expression.args[0].name, "EWX")

    def test_doc_device_property_functions_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics("_T = AREA_COMMON (G, S) + BENDS (G)\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertIsInstance(node.expression.left, ast.FuncCall)
        self.assertEqual(node.expression.left.name, "AREA_COMMON")
        self.assertIsInstance(node.expression.right, ast.FuncCall)
        self.assertEqual(node.expression.right.name, "BENDS")

    def test_doc_trace_property_functions_with_spaced_parentheses(self):
        text = '_T = STRING_COMPARE (LAYOUT_STRING_VALUE ("R"), SOURCE_STRING_VALUE ("R"))\n'
        tree, warnings = parse_with_diagnostics(text)
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "STRING_COMPARE")
        self.assertTrue(all(isinstance(arg, ast.FuncCall) for arg in node.expression.args))
        self.assertEqual([arg.name for arg in node.expression.args], ["LAYOUT_STRING_VALUE", "SOURCE_STRING_VALUE"])

    def test_doc_effective_property_functions_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics("_T = EQUAL (GROUP1) + PROD (GROUP1)\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.BinaryOp)
        self.assertIsInstance(node.expression.left, ast.FuncCall)
        self.assertEqual(node.expression.left.name, "EQUAL")
        self.assertIsInstance(node.expression.right, ast.FuncCall)
        self.assertEqual(node.expression.right.name, "PROD")

    def test_doc_lvs_property_initialize_function_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics("_T = INPUT_NUMERIC_VALUE (PROP)\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "INPUT_NUMERIC_VALUE")

    def test_doc_namespaced_device_function_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics("_T = DEVICE::DEBUG ()\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "DEVICE::DEBUG")

    def test_doc_historical_enclosure_function_with_spaced_parentheses(self):
        tree, warnings = parse_with_diagnostics("_T = ENCLOSURE_PARALLEL_MULTIFINGER (NWELL, GATE)\n")
        self.assertEqual(warnings, [])
        node = tree.statements[0]
        self.assertIsInstance(node, ast.LayerAssignment)
        self.assertIsInstance(node.expression, ast.FuncCall)
        self.assertEqual(node.expression.name, "ENCLOSURE_PARALLEL_MULTIFINGER")


if __name__ == "__main__":
    unittest.main()
