"""Tests for diagnostics, AST spans/helpers, and semantic validation."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
import shutil

from svrf_parser import parse, parse_with_diagnostics, validate_svrf, validate_svrf_file
from svrf_parser.diagnostic_postprocess import undefined_symbol_name
from svrf_parser.ast_nodes import Attach, BinaryOp, IfDef, LayerAssignment, LayerDef, Program
from svrf_parser.diagnostics import Diagnostic
from svrf_parser.exceptions import ParseError
from svrf_parser.semantic import validate_semantics


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "includes"


class ValidationTests(unittest.TestCase):
    def test_parse_with_diagnostics_returns_structured_diagnostics(self):
        tree, warnings = parse_with_diagnostics("X =\n")
        self.assertIsInstance(tree, Program)
        self.assertEqual(len(warnings), 1)
        self.assertIsInstance(warnings[0], Diagnostic)
        self.assertEqual(warnings[0].code, "parser.assignment.empty")
        self.assertEqual(warnings[0].include_stack, ())
        self.assertIn("Empty assignment for X", str(warnings[0]))

    def test_ast_nodes_include_spans_and_source_text(self):
        tree = parse("_T = A AND B\n")
        stmt = tree.statements[0]
        self.assertIsInstance(stmt, LayerAssignment)
        self.assertEqual(stmt.source_text, "_T = A AND B")
        self.assertEqual(stmt.expression.source_text, "A AND B")
        self.assertGreater(stmt.end_col, stmt.col)
        self.assertEqual(stmt.span[0], (1, 1))

    def test_ast_helpers_walk_to_dict_and_structural_equality(self):
        left = parse("_T = A AND B\n")
        right = parse("_T = A AND B\n")
        self.assertTrue(left.structurally_equal(right))
        names = [type(node).__name__ for node in left.walk()]
        self.assertIn("Program", names)
        self.assertIn("LayerAssignment", names)
        self.assertIn("BinaryOp", names)
        stmt = left.statements[0]
        payload = stmt.to_dict()
        self.assertEqual(payload["type"], "LayerAssignment")
        self.assertEqual(payload["source_text"], "_T = A AND B")

    def test_ast_walk_handles_deep_trees_iteratively(self):
        expr = LayerDef(name="L0", numbers=[0])
        for idx in range(2500):
            expr = BinaryOp(op="AND", left=expr, right=LayerDef(name=f"L{idx+1}", numbers=[idx + 1]))
        tree = Program(statements=[LayerAssignment(name="TMP", expression=expr)])
        count = sum(1 for _ in tree.walk())
        self.assertGreater(count, 2500)

    def test_validate_svrf_reports_semantic_errors(self):
        result = validate_svrf("LAYER M1 10\nCMACRO NO_SUCH_MACRO ARG1\n")
        self.assertFalse(result.valid)
        codes = {diag.code for diag in result.errors}
        self.assertIn("semantic.macro.undefined", codes)

    def test_validate_svrf_keeps_parser_warnings_and_semantic_errors(self):
        result = validate_svrf("LAYER M1 10\nX =\n")
        self.assertFalse(result.valid)
        self.assertIn("semantic.assignment.empty_expression", {diag.code for diag in result.errors})
        self.assertIn("parser.assignment.empty", {diag.code for diag in result.warnings})
        self.assertTrue(any("Empty assignment for X" in msg for msg in result.warning_messages))

    def test_validate_warns_that_encrypted_blocks_may_define_unresolved_symbols(self):
        text = "#DECRYPT abc123\n#ENDCRYPT\nTMP = HIDDEN_LAYER\n"
        result = validate_svrf(text, strict=False)
        self.assertTrue(result.valid)
        codes = {diag.code for diag in result.warnings}
        self.assertIn("semantic.reference.undefined", codes)
        self.assertIn("validation.encrypted_blocks.possible_hidden_definitions", codes)
        message = next(
            diag.message
            for diag in result.warnings
            if diag.code == "validation.encrypted_blocks.possible_hidden_definitions"
        )
        self.assertIn("encrypted SVRF blocks", message)
        self.assertIn("HIDDEN_LAYER", message)

    def test_validate_uses_plaintext_encrypted_body_symbols(self):
        text = "#ENCRYPT\nLAYER HIDDEN_LAYER 99\n#ENDCRYPT\nTMP = HIDDEN_LAYER\n"
        result = validate_svrf(text, strict=False)
        warning_codes = {diag.code for diag in result.warnings}
        error_codes = {diag.code for diag in result.errors}

        self.assertTrue(result.valid)
        self.assertNotIn("semantic.reference.undefined", warning_codes)
        self.assertNotIn(
            "validation.encrypted_blocks.possible_hidden_definitions",
            warning_codes,
        )
        self.assertNotIn("semantic.reference.undefined", error_codes)
        encrypted = result.program.statements[0]
        self.assertEqual("plaintext", encrypted.parse_status)
        self.assertEqual("HIDDEN_LAYER", encrypted.body[0].name)

    def test_validate_exposes_profile_dialects_and_families(self):
        text = (
            "LAYER M1 10\n"
            "DRC RESULTS DATABASE out.gds GDSII\n"
            "LVS SPICE STRICT WL NO\n"
            "PEX REPORT NETSUMMARY net.summary\n"
        )
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        self.assertEqual(("CORE", "DRC", "LVS", "PEX"), result.dialects)
        self.assertIn("layer_definition", result.feature_families)
        self.assertIn("results_database", result.feature_families)
        self.assertIn("spice_netlist_policy", result.feature_families)
        self.assertIn("pex_reporting", result.feature_families)
        self.assertIn("manual_exception", result.profile_tags)

    def test_validate_exposes_limited_support_features(self):
        text = "#DECRYPT abc123\n#ENDCRYPT\nTVF FUNCTION Perc_ADP_properties [/* body */]\n"
        result = validate_svrf(text, strict=False)
        self.assertTrue(result.valid)
        self.assertIn("CORE", result.dialects)
        self.assertIn("TVF", result.dialects)
        self.assertIn("builtin_language", result.feature_families)
        self.assertIn("encrypted_content", result.feature_families)
        self.assertIn("tvf_directive", result.limited_support_features)
        self.assertIn("encrypted_block", result.limited_support_features)
        self.assertIn("embedded_language", result.profile_tags)

    def test_validate_warns_for_recognized_limited_support_features(self):
        text = "TVF FUNCTION Perc_ADP_properties [/* body */]\nPOLYGON 0 0 100 200 REGION1\n"
        result = validate_svrf(text, strict=False)
        self.assertTrue(result.valid)
        warnings = [diag for diag in result.warnings if diag.code == "validation.support.limited_feature"]
        self.assertEqual(2, len(warnings))
        messages = {diag.message for diag in warnings}
        self.assertTrue(any("TVF built-in language constructs" in message for message in messages))
        self.assertTrue(any("POLYGON directives" in message for message in messages))

    def test_validate_warns_for_all_limited_support_directive_families_once(self):
        text = (
            "TVF FUNCTION Perc_ADP_properties [/* body */]\n"
            "POLYGON 0 0 100 200 REGION1\n"
            "RDB \"./output/report.RDB\" M1 GATE\n"
            "POLYGON 1 1 10 20 REGION2\n"
            "RDB other.rdb M2\n"
        )
        result = validate_svrf(text, strict=False)
        self.assertTrue(result.valid)
        self.assertEqual(("polygon_directive", "rdb_directive", "tvf_directive"), result.limited_support_features)
        warnings = [diag for diag in result.warnings if diag.code == "validation.support.limited_feature"]
        self.assertEqual(3, len(warnings))
        messages = {diag.message for diag in warnings}
        self.assertTrue(any("TVF built-in language constructs" in message for message in messages))
        self.assertTrue(any("POLYGON directives" in message for message in messages))
        self.assertTrue(any("Top-level RDB directives" in message for message in messages))

    def test_validate_distinguishes_top_level_rdb_from_dfm_rdb_operation_support(self):
        text = "RULE1 {\n  DFM RDB BAD_CHIP DTCD.R.9.1.TCDDMY_ALL NOEMPTY\n}\n"
        result = validate_svrf(text, strict=False)
        self.assertTrue(result.valid)
        self.assertIn("results_database", result.feature_families)
        self.assertEqual((), result.limited_support_features)
        self.assertNotIn(
            "validation.support.limited_feature",
            {diag.code for diag in result.warnings},
        )

    def test_validate_svrf_handles_deep_expression_iteratively(self):
        text = "VARIABLE A 1\nTMP = " + " + ".join(["A"] * 2500) + "\n"
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)
        self.assertEqual([], result.warnings)
        self.assertEqual("strict", result.unresolved_policy)
        self.assertEqual(0, result.policy_summary.raw_unresolved_count)

    def test_validate_semantics_handles_deep_nested_ifdefs_iteratively(self):
        node = LayerDef(name="M1", numbers=[1])
        for idx in range(1200):
            node = IfDef(name=f"S{idx}", then_body=[node], else_body=[])
        diagnostics = validate_semantics(Program(statements=[node]), strict=True)
        self.assertEqual([], diagnostics)

    def test_parse_strict_raises_on_recovery_warning(self):
        with self.assertRaises(ParseError):
            parse("X =\n", strict=True)

    def test_validate_strict_promotes_unknown_layer_warning(self):
        result = validate_svrf("CONNECT M1 M2 BY VIA1\n", strict=True)
        self.assertFalse(result.valid)
        self.assertIn("semantic.connect.unknown_layer", {diag.code for diag in result.errors})

    def test_validate_ifdef_macro_and_dmacro_params_use_scoped_symbols(self):
        text = (
            "#IFDEF USE_CHECK\n"
            "DMACRO WIDTH_CHECK LAYER_A LAYER_B VIA_L {\n"
            "  TMP = SIZE LAYER_A BY LAYER_B\n"
            "  CONNECT LAYER_A LAYER_B BY VIA_L\n"
            "}\n"
            "CMACRO WIDTH_CHECK M1 M2 VIA1\n"
            "#ENDIF\n"
        )
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        self.assertEqual([], [diag.code for diag in result.errors])

    def test_validate_rule_body_cmacro_does_not_emit_unknown_reference_warnings(self):
        text = (
            "DMACRO CHECK_SHAPE Mx Mx_n { }\n"
            "RULE1 {\n"
            "  CMACRO CHECK_SHAPE Layer_A Layer_B\n"
            "}\n"
        )
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        codes = {diag.code for diag in result.errors + result.warnings}
        self.assertNotIn("semantic.reference.undefined", codes)

    def test_validate_expression_references_resolve_layers_and_variables(self):
        text = "LAYER M1 10\nVARIABLE WIDTH 0.1\nTMP = SIZE M1 BY WIDTH\n"
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        self.assertNotIn("semantic.reference.undefined", {diag.code for diag in result.errors})

    def test_validate_dfm_property_scopes_local_modifier_names(self):
        text = (
            "LAYER SHAPE_SET 1\n"
            "SHAPE_SET_X = ANGLE SHAPE_SET == 0\n"
            "SHAPE_SET_Y = ANGLE SHAPE_SET == 90\n"
            "SHAPE_SET_VERTICAL = DFM PROPERTY SHAPE_SET SHAPE_SET_X SHAPE_SET_Y OVERLAP ABUT ALSO MULTI\n"
            "  [LY = LENGTH(SHAPE_SET_Y)] > 0\n"
            "  [LX = LENGTH(SHAPE_SET_X)] > 0\n"
            "  [-= PROPERTY_REF(LY) - PROPERTY_REF(LX)] >= 0\n"
        )
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)

    def test_validate_property_block_scopes_header_names(self):
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
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)

    def test_validate_property_functions_skip_property_name_arguments(self):
        text = (
            "LAYER M1 1\n"
            "LAYER M2 2\n"
            "TMP = DFM PROPERTY M1 M2 OVERLAP MULTI ABUT ALSO\n"
            "  [LR = PROPERTY(M1,lr)] > 0\n"
            "  [WR = PROPERTY(M2,wr)] > 0\n"
            "  [-= PROPERTY_REF(LR) - PROPERTY_REF(WR)] >= 0\n"
        )
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)

    def test_validate_dfm_property_source_placeholders_from_property_functions(self):
        text = (
            "LAYER BASE 1\n"
            "TMP = DFM PROPERTY BASE NET_VOL_ASSIGN NODAL MULTI\n"
            "  [MAX_VOL = PROPERTY(NET_VOL_ASSIGN, max_vol)]\n"
            "  [MIN_VOL = PROPERTY(NET_VOL_ASSIGN, min_vol)]\n"
        )
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)

    def test_validate_dfm_text_property_number_name_placeholder(self):
        text = (
            "LAYER TXT 1\n"
            "TXT_ANN = DFM TEXT TXT PROPERTY NUMBER TXT_PROP\n"
            "TXT_VAL = DFM PROPERTY MERGE TXT_ANN [TXT_MAX = MAX(PROPERTY(TXT_ANN, TXT_PROP))]\n"
        )
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)

    def test_validate_dfm_rdb_names_do_not_emit_unknown_reference_warnings(self):
        result = validate_svrf(
            "RULE1 {\n  DFM RDB BAD_CHIP DTCD.R.9.1.TCDDMY_ALL NOEMPTY\n}\n",
            strict=True,
        )
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)
        self.assertNotIn(
            "semantic.reference.undefined",
            {diag.code for diag in result.warnings},
        )

    def test_validate_accepts_single_layer_connect_used_by_samples(self):
        result = validate_svrf("LAYER DOP_M0 1\nCONNECT DOP_M0\n", strict=True)
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)

    def test_validate_rule_check_scope_sees_local_assignments(self):
        text = "LAYER M1 1\nRULE1 {\n  B = COPY M1\n  MERGE B\n}\n"
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)

    def test_validate_description_varrefs_are_case_insensitive(self):
        text = "VARIABLE GRID 0.001\nRULE1 {\n  @ Need ^Grid\n  INT M1 < 0.1\n}\nLAYER M1 1\n"
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)

    def test_validate_property_block_accepts_implicit_device_terminals(self):
        text = (
            "DMACRO MOS_XRC_PRO fet_seed sd_seed proclayer1 proclayer2 {\n"
            "  [ PROPERTY W,AD\n"
            "    S = ENCLOSURE_VECTOR(proclayer2,5)\n"
            "    PER_S = perimeter_inside(S,proclayer1)\n"
            "    PER_D = perimeter_inside(D,proclayer1)\n"
            "    AD = AREA(D)*W/PER_D\n"
            "  ]\n"
            "}\n"
        )
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)

    def test_validate_lvs_filter_device_name_is_not_layer_reference(self):
        result = validate_svrf("LVS FILTER D(parasitic_rwd) OPEN\n", strict=True)
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)

    def test_validate_lvs_ground_and_power_name_placeholders(self):
        text = (
            "LAYER M1 1\n"
            "LVS GROUND NAME \"VSS\"\n"
            "LVS POWER NAME \"VDD\"\n"
            "TMP1 = NOT NET M1 LVS_GROUND_NAME\n"
            "TMP2 = NOT NET M1 LVS_POWER_NAME\n"
        )
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)

    def test_validate_device_aux_layers_shared_with_cmacro_args(self):
        text = (
            "LAYER SEED 1\n"
            "LAYER P1 2\n"
            "DMACRO RC X { }\n"
            "DEVICE MN(dev) SEED P1(S) <DFM_GATE> CMACRO RC DFM_GATE\n"
        )
        result = validate_svrf(text, strict=True)
        self.assertTrue(result.valid)
        self.assertEqual([], result.errors)

    def test_validate_reports_unknown_expression_reference(self):
        text = "LAYER M1 10\nTMP = M1 AND MISSING_REF\n"
        result = validate_svrf(text, strict=True)
        self.assertFalse(result.valid)
        self.assertIn("semantic.reference.undefined", {diag.code for diag in result.errors})

    def test_validate_classifies_unknown_scalar_parameter_like_reference(self):
        text = "LAYER M1 10\nTMP = SIZE M1 BY WIDTH_CONST\n"
        result = validate_svrf(text, strict=False)
        self.assertTrue(result.valid)
        codes = {diag.code for diag in result.warnings}
        self.assertIn("semantic.reference.scalar_undefined", codes)
        message = next(
            diag.message
            for diag in result.warnings
            if diag.code == "semantic.reference.scalar_undefined"
        )
        self.assertIn("WIDTH_CONST", message)
        diagnostic = next(
            diag
            for diag in result.warnings
            if diag.code == "semantic.reference.scalar_undefined"
        )
        self.assertEqual("WIDTH_CONST", diagnostic.metadata["symbol"])
        self.assertEqual("WIDTH_CONST", undefined_symbol_name(diagnostic))

    def test_validate_classifies_same_file_local_scope_only_reference(self):
        text = "LAYER M1 1\nRULE1 {\n  LOCAL_TMP = COPY M1\n  COPY LOCAL_TMP\n}\nTMP = LOCAL_TMP\n"
        result = validate_svrf(text, strict=False)
        self.assertTrue(result.valid)
        codes = {diag.code for diag in result.warnings}
        self.assertIn("semantic.reference.local_scope_only", codes)
        message = next(
            diag.message
            for diag in result.warnings
            if diag.code == "semantic.reference.local_scope_only"
        )
        self.assertIn("LOCAL_TMP", message)
        diagnostic = next(
            diag
            for diag in result.warnings
            if diag.code == "semantic.reference.local_scope_only"
        )
        self.assertEqual("LOCAL_TMP", diagnostic.metadata["symbol"])
        self.assertEqual("LOCAL_TMP", undefined_symbol_name(diagnostic))

    def test_validate_reclassifies_unknown_reference_as_companion_candidate(self):
        root = Path(__file__).resolve().parent / f"tmp_companion_symbol_{os.getpid()}"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        try:
            (root / "main.svrf").write_text("TMP = EXTERNAL_NET\n", encoding="utf-8")
            (root / "setup.ant").write_text("EXTERNAL_NET", encoding="utf-8")
            result = validate_svrf_file(root / "main.svrf", strict=False)
            self.assertTrue(result.valid)
            codes = {diag.code for diag in result.warnings}
            self.assertIn("semantic.reference.companion_candidate", codes)
            self.assertNotIn("semantic.reference.external_candidate", codes)
            message = next(
                diag.message
                for diag in result.warnings
                if diag.code == "semantic.reference.companion_candidate"
            )
            self.assertIn("EXTERNAL_NET", message)
            self.assertIn("setup.ant", message)
            diagnostic = next(
                diag
                for diag in result.warnings
                if diag.code == "semantic.reference.companion_candidate"
            )
            self.assertEqual("EXTERNAL_NET", diagnostic.metadata["symbol"])
            self.assertEqual("EXTERNAL_NET", undefined_symbol_name(diagnostic))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_reclassifies_any_regular_sibling_file_as_companion_candidate(self):
        companion_names = ("setup.13a", "setup.15a", "setup.custom", "setup")
        for companion_name in companion_names:
            with self.subTest(companion_name=companion_name):
                safe_name = companion_name.replace(".", "_")
                root = Path(__file__).resolve().parent / f"tmp_companion_file_{os.getpid()}_{safe_name}"
                if root.exists():
                    shutil.rmtree(root, ignore_errors=True)
                root.mkdir()
                try:
                    (root / "main.svrf").write_text("TMP = ANT_SYMBOL\n", encoding="utf-8")
                    (root / companion_name).write_text("ANT_SYMBOL", encoding="utf-8")
                    result = validate_svrf_file(root / "main.svrf", strict=False)

                    self.assertTrue(result.valid)
                    codes = {diag.code for diag in result.warnings}
                    self.assertIn("semantic.reference.companion_candidate", codes)
                    self.assertNotIn("semantic.reference.external_candidate", codes)
                finally:
                    shutil.rmtree(root, ignore_errors=True)

    def test_validate_reclassifies_unknown_reference_as_external_candidate(self):
        root = Path(__file__).resolve().parent / f"tmp_external_symbol_{os.getpid()}"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        try:
            (root / "main.svrf").write_text("TMP = RUNTIME_LAYER\n", encoding="utf-8")
            result = validate_svrf_file(root / "main.svrf", strict=False)
            self.assertTrue(result.valid)
            codes = {diag.code for diag in result.warnings}
            self.assertIn("semantic.reference.external_candidate", codes)
            self.assertNotIn("semantic.reference.companion_candidate", codes)
            message = next(
                diag.message
                for diag in result.warnings
                if diag.code == "semantic.reference.external_candidate"
            )
            self.assertIn("RUNTIME_LAYER", message)
            self.assertIn("omitted include", message)
            self.assertIn("tool runtime global", message)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_practical_policy_dedupes_repeated_unresolved_symbols(self):
        root = Path(__file__).resolve().parent / f"tmp_practical_dedupe_{os.getpid()}"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        try:
            (root / "main.svrf").write_text("TMP1 = RUNTIME_LAYER\nTMP2 = RUNTIME_LAYER\n", encoding="utf-8")
            result = validate_svrf_file(
                root / "main.svrf",
                strict=False,
                unresolved_policy="practical",
            )
            self.assertTrue(result.valid)
            unresolved = [
                diag
                for diag in result.warnings
                if diag.code == "semantic.reference.external_candidate"
            ]
            self.assertEqual(1, len(unresolved))
            self.assertEqual("practical", result.unresolved_policy)
            self.assertEqual(2, result.policy_summary.raw_unresolved_count)
            self.assertEqual(1, result.policy_summary.deduped_unresolved_count)
            self.assertEqual(0, result.policy_summary.manifest_resolved_count)
            self.assertEqual(1, result.policy_summary.remaining_unresolved_count)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_practical_policy_uses_symbol_manifest(self):
        root = Path(__file__).resolve().parent / f"tmp_practical_manifest_{os.getpid()}"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        try:
            (root / "main.svrf").write_text(
                "LAYER M1 1\nTMP1 = EXTERNAL_NET\nTMP2 = SIZE M1 BY LAYER_THICKNESS_M0\n",
                encoding="utf-8",
            )
            manifest = {
                "external_symbols": ["EXTERNAL_NET"],
                "scalar_parameters": ["LAYER_THICKNESS_M0"],
            }
            result = validate_svrf_file(
                root / "main.svrf",
                strict=False,
                unresolved_policy="practical",
                symbol_manifest=manifest,
            )
            self.assertTrue(result.valid)
            self.assertEqual([], result.errors)
            self.assertEqual([], result.warnings)
            self.assertEqual("practical", result.unresolved_policy)
            self.assertEqual(2, result.policy_summary.raw_unresolved_count)
            self.assertEqual(2, result.policy_summary.deduped_unresolved_count)
            self.assertEqual(2, result.policy_summary.manifest_resolved_count)
            self.assertEqual(0, result.policy_summary.remaining_unresolved_count)
            self.assertIn("LAYER_THICKNESS_M0", result.policy_summary.manifest_resolved_symbols)
            self.assertIn("EXTERNAL_NET", result.policy_summary.manifest_resolved_symbols)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_strict_policy_ignores_manifest_suppression(self):
        manifest = {"external_symbols": ["EXTERNAL_NET"]}
        result = validate_svrf(
            "TMP = EXTERNAL_NET\n",
            strict=False,
            unresolved_policy="strict",
            symbol_manifest=manifest,
        )
        self.assertTrue(result.valid)
        self.assertIn("semantic.reference.undefined", {diag.code for diag in result.warnings})
        self.assertEqual(1, result.policy_summary.raw_unresolved_count)
        self.assertEqual(1, result.policy_summary.remaining_unresolved_count)
        self.assertEqual(0, result.policy_summary.manifest_resolved_count)

    def test_validate_practical_policy_respects_manifest_file_globs(self):
        root = Path(__file__).resolve().parent / f"tmp_manifest_glob_{os.getpid()}"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        try:
            target = root / "main.svrf"
            target.write_text("TMP = EXTERNAL_NET\n", encoding="utf-8")
            manifest = {
                "rules": [
                    {
                        "file_globs": ["other*.svrf"],
                        "external_symbols": ["EXTERNAL_NET"],
                    }
                ]
            }
            result = validate_svrf_file(
                target,
                strict=False,
                unresolved_policy="practical",
                symbol_manifest=manifest,
            )
            self.assertTrue(result.valid)
            self.assertIn(
                "semantic.reference.external_candidate",
                {diag.code for diag in result.warnings},
            )
            self.assertEqual(0, result.policy_summary.manifest_resolved_count)

            manifest["rules"][0]["file_globs"] = ["main.svrf"]
            result = validate_svrf_file(
                target,
                strict=False,
                unresolved_policy="practical",
                symbol_manifest=manifest,
            )
            self.assertTrue(result.valid)
            self.assertEqual([], result.warnings)
            self.assertEqual(1, result.policy_summary.manifest_resolved_count)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_file_invalid_policy_returns_validation_result(self):
        target = Path(__file__).resolve().parent / "missing_policy_target.svrf"
        result = validate_svrf_file(target, unresolved_policy="bogus")
        self.assertFalse(result.valid)
        self.assertEqual(
            ["validation.policy.invalid_manifest"],
            [diag.code for diag in result.errors],
        )

    def test_validate_reports_unknown_description_varref(self):
        text = "LAYER M1 10\nrule1 {\n  @ Need ^NO_SUCH_VAR\n  INT M1 < 0.1\n}\n"
        result = validate_svrf(text, strict=True)
        self.assertFalse(result.valid)
        self.assertIn("semantic.varref.undefined", {diag.code for diag in result.errors})

    def test_validate_reports_missing_required_directive_argument(self):
        result = validate_svrf("LAYOUT PATH\n", strict=True)
        self.assertFalse(result.valid)
        self.assertIn("semantic.directive.missing_argument", {diag.code for diag in result.errors})

    def test_validate_reports_missing_required_lvs_directive_arguments(self):
        report_result = validate_svrf("LVS REPORT\n", strict=True)
        self.assertFalse(report_result.valid)
        self.assertIn("semantic.directive.missing_argument", {diag.code for diag in report_result.errors})

        softchk_result = validate_svrf("LVS SOFTCHK\n", strict=True)
        self.assertFalse(softchk_result.valid)
        self.assertIn("semantic.directive.missing_argument", {diag.code for diag in softchk_result.errors})

        compare_case_result = validate_svrf("LVS COMPARE CASE\n", strict=True)
        self.assertFalse(compare_case_result.valid)
        self.assertIn("semantic.directive.missing_argument", {diag.code for diag in compare_case_result.errors})

        ignore_ports_result = validate_svrf("LVS IGNORE PORTS\n", strict=True)
        self.assertFalse(ignore_ports_result.valid)
        self.assertIn("semantic.directive.missing_argument", {diag.code for diag in ignore_ports_result.errors})

        recognize_gates_result = validate_svrf("LVS RECOGNIZE GATES\n", strict=True)
        self.assertFalse(recognize_gates_result.valid)
        self.assertIn("semantic.directive.missing_argument", {diag.code for diag in recognize_gates_result.errors})

    def test_validate_reports_missing_required_erc_directive_argument(self):
        result = validate_svrf("ERC RESULTS DATABASE\n", strict=True)
        self.assertFalse(result.valid)
        self.assertIn("semantic.directive.missing_argument", {diag.code for diag in result.errors})

    def test_validate_reports_missing_required_drc_incremental_connect_argument(self):
        result = validate_svrf("DRC INCREMENTAL CONNECT\n", strict=True)
        self.assertFalse(result.valid)
        self.assertIn("semantic.directive.missing_argument", {diag.code for diag in result.errors})

    def test_validate_reports_missing_required_pex_report_target_argument(self):
        for text in (
            "PEX REPORT NETSUMMARY\n",
            "PEX REPORT POINT2POINT\n",
        ):
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertFalse(result.valid)
                self.assertIn("semantic.directive.argument_shape", {diag.code for diag in result.errors})

    def test_validate_reports_missing_required_pex_netlist_target_argument(self):
        result = validate_svrf("PEX NETLIST\n", strict=True)
        self.assertFalse(result.valid)
        self.assertIn("semantic.directive.missing_argument", {diag.code for diag in result.errors})

    def test_validate_reports_invalid_exact_directive_argument_shape(self):
        for text in (
            "DRC MAXIMUM RESULTS ALL EXTRA\n",
            "DRC KEEP EMPTY YES EXTRA\n",
        ):
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertFalse(result.valid)
                self.assertIn("semantic.directive.argument_shape", {diag.code for diag in result.errors})

    def test_validate_accepts_manual_softchk_forms(self):
        for text in (
            "LVS SOFTCHK PWELL\n",
            "LVS SOFTCHK PWELL UPPER ALL\n",
        ):
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertTrue(result.valid)

    def test_validate_accepts_manual_report_option_and_spice_strict_forms(self):
        for text in (
            "LVS REPORT OPTION NONE\n",
            "LVS REPORT OPTION A B C D S EC\n",
            "LVS SPICE STRICT WL NO\n",
            "PEX NETLIST LUMPED \"lumped.dist\" HSPICE LAYOUT GROUND VSS MASK EXTRA\n",
            "DRC RESULTS DATABASE out.gds GDSII APPEND _NEW\n",
            "DRC SUMMARY REPORT drc.sum APPEND HIER EXECUTED\n",
        ):
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertTrue(result.valid)

    def test_validate_accepts_manual_summary_results_and_magnify_forms(self):
        for text in (
            "DRC SUMMARY REPORT drc.sum APPEND HIER EXECUTED\n",
            "ERC SUMMARY REPORT erc.sum APPEND HIER\n",
            "ERC RESULTS DATABASE erc.db ASCII TOP\n",
            "DRC RESULTS DATABASE PRECISION 10 1000\n",
            "DRC MAGNIFY RESULTS X 0.5 Y 2\n",
            "DRC MAGNIFY RESULTS 0.5 PLACE\n",
            "DRC MAXIMUM RESULTS ESTIMATE 50\n",
            "DRC MAXIMUM RESULTS ESTIMATE ALL\n",
            "DRC MAXIMUM RESULTS NAR 50\n",
            "ERC MAXIMUM RESULTS ALL\n",
        ):
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertTrue(result.valid)

    def test_validate_accepts_manual_boolean_and_ordered_directive_forms(self):
        for text in (
            "LVS COMPARE CASE NAMES TYPES SUBTYPES VALUES\n",
            "LVS IGNORE PORTS YES\n",
            "DRC INCREMENTAL CONNECT NO\n",
            "DRC INCREMENTAL CONNECT WARNING DISABLE\n",
            "PEX NETLIST MUTUAL RESISTANCE NO\n",
            "PEX NETLIST VIRTUAL CONNECT YES\n",
        ):
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertTrue(result.valid)

    def test_validate_accepts_manual_recognize_gates_pex_report_and_results_database_forms(self):
        for text in (
            "LVS RECOGNIZE GATES SIMPLE MIX SUBTYPES XALSO WITHIN TOLERANCE WITH SUBSTRATE CELL LIST analog\n",
            "PEX REPORT NETSUMMARY net.summary FULL SOURCE VSS VDD CELL TOP SCALE 0.5 COLUMNS ADVANCED\n",
            "PEX REPORT POINT2POINT UNIT_LENGTH myInput.res myOutput.rep SOURCENAMES CALIBREVIEW SAMEPORT OPEN\n",
            "DRC RESULTS DATABASE output.oas OASIS INDEX NOVIEW PREFIX PRE APPEND SUF CBLOCK BEST_COMPRESSION NOSTRICT AUTOMAP SNAPREDUCE PSEUDO\n",
            "DRC RESULTS DATABASE \"PIPE gzip > drc_results.gdsii.gz\" GDS\n",
        ):
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertTrue(result.valid)

    def test_validate_accepts_manual_recognize_gates_tolerance_and_pex_netlist_forms(self):
        for text in (
            "LVS RECOGNIZE GATES TOLERANCE MP W SERIES 0 PARALLEL 0\n",
            "LVS RECOGNIZE GATES TOLERANCE MN P STRING SERIES LAYOUT SOURCE\n",
            "PEX NETLIST GROUNDLAYER TOP_GROUND GND1 M1 VSS\n",
            "PEX NETLIST UNSHORT DEVICE PINS NO\n",
            "PEX NETLIST UPPERCASE MODELNAMES YES PARAMETERS YES\n",
            "PEX NETLIST GROUNDNET GLOBAL NO\n",
            "PEX NETLIST POSITION FILE out.pos\n",
            "PEX NETLIST CONNECTION SECTION YES INST_LOC\n",
            "PEX NETLIST EXPORT PORTS YES\n",
            "PEX NETLIST LINEWRAP 100\n",
            "DRC RESULTS DATABASE LIBNAME mask_lib\n",
        ):
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertTrue(result.valid)

    def test_validate_reports_invalid_manual_directive_values(self):
        for text in (
            "LVS REPORT OPTION NONE A\n",
            "LVS REPORT OPTION UNKNOWN\n",
            "LVS SOFTCHK PWELL SIDEWAYS\n",
            "LVS SOFTCHK PWELL CONTACT EXTRA\n",
            "LVS SPICE STRICT WW YES\n",
            "LVS SPICE STRICT WL MAYBE\n",
        ):
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertFalse(result.valid)
                self.assertIn("semantic.directive.invalid_value", {diag.code for diag in result.errors})

    def test_validate_reports_invalid_boolean_and_ordered_directive_forms(self):
        cases = {
            "LVS COMPARE CASE VALUES NAMES\n": "semantic.directive.invalid_value",
            "LVS COMPARE CASE NAMES NAMES\n": "semantic.directive.invalid_value",
            "LVS IGNORE PORTS MAYBE\n": "semantic.directive.invalid_value",
            "DRC INCREMENTAL CONNECT MAYBE\n": "semantic.directive.invalid_value",
            "DRC INCREMENTAL CONNECT WARNING MAYBE\n": "semantic.directive.invalid_value",
            "PEX NETLIST MUTUAL RESISTANCE MAYBE\n": "semantic.directive.invalid_value",
            "PEX NETLIST VIRTUAL CONNECT MAYBE\n": "semantic.directive.invalid_value",
        }
        for text, code in cases.items():
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertFalse(result.valid)
                self.assertIn(code, {diag.code for diag in result.errors})

    def test_validate_reports_invalid_recognize_gates_pex_report_and_results_database_forms(self):
        cases = {
            "LVS RECOGNIZE GATES MAYBE\n": "semantic.directive.invalid_value",
            "LVS RECOGNIZE GATES SIMPLE CELL LIST\n": "semantic.directive.argument_shape",
            "LVS RECOGNIZE GATES SIMPLE WITH SUBSTRATE XALSO\n": "semantic.directive.invalid_value",
            "PEX REPORT NETSUMMARY net.summary SOURCE CELL TOP\n": "semantic.directive.argument_shape",
            "PEX REPORT NETSUMMARY net.summary COLUMNS WIDE\n": "semantic.directive.invalid_value",
            "PEX REPORT POINT2POINT in.res LAYOUTNAMES CALIBREVIEW\n": "semantic.directive.invalid_value",
            "PEX REPORT POINT2POINT in.res SAMEPORT MAYBE\n": "semantic.directive.invalid_value",
            "DRC RESULTS DATABASE \"PIPE gzip > drc_results.gdsii.gz\" ASCII\n": "semantic.directive.invalid_value",
            "DRC RESULTS DATABASE results.txt ASCII PREFIX PRE\n": "semantic.directive.invalid_value",
            "DRC RESULTS DATABASE output.oas NOVIEW\n": "semantic.directive.invalid_value",
        }
        for text, code in cases.items():
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertFalse(result.valid)
                self.assertIn(code, {diag.code for diag in result.errors})

    def test_validate_reports_invalid_recognize_gates_tolerance_and_pex_netlist_forms(self):
        cases = {
            "LVS RECOGNIZE GATES TOLERANCE MP W\n": "semantic.directive.argument_shape",
            "LVS RECOGNIZE GATES TOLERANCE MP W STRING 10\n": "semantic.directive.invalid_value",
            "PEX NETLIST GROUNDLAYER TOP_GROUND\n": "semantic.directive.argument_shape",
            "PEX NETLIST UNSHORT DEVICE PINS 0\n": "semantic.directive.invalid_value",
            "PEX NETLIST UPPERCASE KEYWORDS MAYBE\n": "semantic.directive.invalid_value",
            "PEX NETLIST UPPERCASE KEYWORDS YES KEYWORDS NO\n": "semantic.directive.invalid_value",
            "PEX NETLIST POSITION FILE\n": "semantic.directive.argument_shape",
            "PEX NETLIST CONNECTION SECTION NO INST_LOC\n": "semantic.directive.invalid_value",
            "PEX NETLIST LINEWRAP 79\n": "semantic.directive.invalid_value",
            "DRC RESULTS DATABASE LIBNAME\n": "semantic.directive.argument_shape",
            "DRC RESULTS DATABASE out.gds GDSII CBLOCK\n": "semantic.directive.invalid_value",
        }
        for text, code in cases.items():
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertFalse(result.valid)
                self.assertIn(code, {diag.code for diag in result.errors})

    def test_validate_reports_invalid_summary_results_and_magnify_forms(self):
        cases = {
            "DRC SUMMARY REPORT out EXECUTED APPEND\n": "semantic.directive.invalid_value",
            "ERC SUMMARY REPORT out HIER APPEND\n": "semantic.directive.invalid_value",
            "ERC RESULTS DATABASE erc.db TOP PSEUDO\n": "semantic.directive.invalid_value",
            "DRC RESULTS DATABASE PRECISION 10 1000 5\n": "semantic.directive.argument_shape",
            "DRC MAGNIFY RESULTS X 0.5 PLACE\n": "semantic.directive.invalid_value",
            "DRC MAGNIFY RESULTS X 0.5 X 2\n": "semantic.directive.invalid_value",
            "DRC MAXIMUM RESULTS ESTIMATE\n": "semantic.directive.argument_shape",
            "DRC MAXIMUM RESULTS FOO\n": "semantic.directive.invalid_value",
            "ERC MAXIMUM RESULTS FOO\n": "semantic.directive.invalid_value",
        }
        for text, code in cases.items():
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertFalse(result.valid)
                self.assertIn(code, {diag.code for diag in result.errors})

    def test_validate_reports_empty_group(self):
        result = validate_svrf("GROUP EMPTY_GROUP\n", strict=True)
        self.assertFalse(result.valid)
        self.assertIn("semantic.group.empty", {diag.code for diag in result.errors})

    def test_validate_reports_attach_missing_net(self):
        tree = Program(statements=[Attach(layer="M1", net="")])
        diagnostics = validate_semantics(tree, strict=True)
        self.assertIn("semantic.attach.missing_net", {diag.code for diag in diagnostics})

    def test_validate_reports_trace_property_missing_args(self):
        result = validate_svrf("TRACE PROPERTY MY_DEVICE\n", strict=True)
        self.assertFalse(result.valid)
        self.assertIn("semantic.trace_property.missing_args", {diag.code for diag in result.errors})

    def test_validate_reports_with_text_missing_filter(self):
        text = "RULE1 {\n  WITH TEXT\n}\n"
        result = validate_svrf(text, strict=True)
        self.assertFalse(result.valid)
        self.assertIn("semantic.drc.with_text.missing_filter", {diag.code for diag in result.errors})

    def test_validate_reports_missing_drc_operands(self):
        for text in (
            "RULE1 {\n  PATHCHK\n}\n",
            "RULE1 {\n  DFM PROPERTY\n}\n",
            "RULE1 {\n  NET AREA RATIO\n}\n",
        ):
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertFalse(result.valid)
                self.assertIn("semantic.drc.missing_operand", {diag.code for diag in result.errors})

    def test_validate_reports_missing_drc_constraints(self):
        for text in (
            "RULE1 {\n  NET AREA A\n}\n",
            "RULE1 {\n  NET INTERACT A\n}\n",
            "RULE1 {\n  NET AREA RATIO A\n}\n",
        ):
            with self.subTest(text=text):
                result = validate_svrf(text, strict=True)
                self.assertFalse(result.valid)
                self.assertIn("semantic.drc.missing_constraint", {diag.code for diag in result.errors})

    def test_validate_reports_missing_device_layer_modifier(self):
        result = validate_svrf("RULE1 {\n  DEVICE LAYER\n}\n", strict=True)
        self.assertFalse(result.valid)
        self.assertIn("semantic.device_layer.missing_modifier", {diag.code for diag in result.errors})

    def test_validate_reports_missing_pathchk_modifier(self):
        result = validate_svrf("RULE1 {\n  PATHCHK POWER\n}\n", strict=True)
        self.assertFalse(result.valid)
        self.assertIn("semantic.drc.missing_modifier", {diag.code for diag in result.errors})

    def test_validate_file_follows_include_for_macro_resolution(self):
        result = validate_svrf_file(FIXTURES / "root_with_macro_include.svrf", run_directory=FIXTURES)
        self.assertTrue(result.valid)
        self.assertNotIn("semantic.macro.undefined", {diag.code for diag in result.errors})

    def test_validate_file_follows_include_for_layer_resolution(self):
        result = validate_svrf_file(FIXTURES / "root_with_layer_include.svrf", strict=True, run_directory=FIXTURES)
        self.assertTrue(result.valid)
        self.assertNotIn("semantic.connect.unknown_layer", {diag.code for diag in result.errors})

    def test_validate_file_reports_missing_include(self):
        result = validate_svrf_file(FIXTURES / "root_missing_include.svrf", run_directory=FIXTURES)
        self.assertFalse(result.valid)
        self.assertIn("validation.include.missing_file", {diag.code for diag in result.errors})

    def test_validate_file_reports_nested_include_stack(self):
        result = validate_svrf_file(FIXTURES / "root_nested_missing.svrf", run_directory=FIXTURES)
        self.assertFalse(result.valid)
        diag = next(
            diag
            for diag in result.errors
            if diag.code == "validation.include.missing_file"
        )
        self.assertEqual(
            diag.include_stack,
            (str(FIXTURES / "root_nested_missing.svrf"),),
        )
        self.assertEqual(diag.filename, str(FIXTURES / "nested_mid.svrf"))
        self.assertIn("root_nested_missing.svrf", str(diag))

    def test_validate_file_reports_include_cycle(self):
        result = validate_svrf_file(FIXTURES / "cycle_a.svrf", run_directory=FIXTURES)
        self.assertFalse(result.valid)
        self.assertIn("validation.include.cycle", {diag.code for diag in result.errors})

    def test_validate_file_handles_deep_include_chain_iteratively(self):
        root = Path(__file__).resolve().parent / f"tmp_include_chain_{os.getpid()}"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        try:
            depth = 1100
            for idx in range(depth):
                lines = [f"LAYER M{idx} {idx + 1}\n"]
                if idx + 1 < depth:
                    lines.append(f'INCLUDE "f{idx + 1}.svrf"\n')
                (root / f"f{idx}.svrf").write_text("".join(lines), encoding="utf-8")

            result = validate_svrf_file(root / "f0.svrf", strict=True, run_directory=root)
            self.assertTrue(result.valid)
            self.assertEqual([], result.errors)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
