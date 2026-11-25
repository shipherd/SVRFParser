"""Regressions for documented syntax that previously appeared to parse cleanly."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from svrf_parser import ast, parse, parse_with_diagnostics, validate_svrf
from svrf_parser.exceptions import ParseError
from svrf_parser.printer import SvrfPrinter
from svrf_parser.visitor import WalkVisitor


class ManualGapTests(unittest.TestCase):
    def test_geometry_assignments_and_roundtrip(self):
        for op, tail in (
            ("MAGNIFY", "M1 BY 2"), ("DEANGLE", "M1 .02 SKEW ORTHOGONAL ONLY"),
            ("DEANGLE", "M1 .02 ALL"), ("SNAP", "M1 2"), ("SNAP", "M1 2 4"),
            ("ORNET", "M1 M2"), ("ORNET", "M1 M2 BY SHAPE"), ("ORNET", "M1 M2 BY NET"),
        ):
            with self.subTest(op=op, tail=tail):
                source = f"LAYER M1 1\nLAYER M2 2\nOUT1 = {op} {tail}\n"
                program = parse(source, strict=True)
                self.assertEqual(3, len(program.statements))
                operation = program.statements[-1].expression
                self.assertIsInstance(operation, ast.DRCOp)
                self.assertEqual(op, operation.op)
                self.assertEqual(program.to_dict(False), parse(SvrfPrinter().emit(program)).to_dict(False))
                result = validate_svrf(source, strict=True)
                self.assertTrue(result.valid, result.diagnostics)

    def test_compound_specifications_do_not_create_layers_or_operations(self):
        program = parse("LAYER M1 1\nLAYER M2 2\nLAYER RESOLUTION M1 M2 2 4\nSNAP OFFGRID YES", strict=True)
        resolution, snap = program.statements[2:]
        self.assertEqual((["LAYER", "RESOLUTION"], ["M1", "M2", 2, 4]), (resolution.keywords, resolution.arguments))
        self.assertEqual((["SNAP", "OFFGRID"], ["YES"]), (snap.keywords, snap.arguments))
        quoted = parse('LAYER "RESOLUTION" 1', strict=True)
        self.assertEqual(quoted.to_dict(False), parse(SvrfPrinter().emit(quoted), strict=True).to_dict(False))

    def test_multiline_forms_and_geometry_contracts(self):
        source = ("LAYER M1 1\nLAYER RESOLUTION\nM1\n2\nSNAP OFFGRID\nYES\n"
                  "A = SNAP M1 2\n  4\nB = MAGNIFY M1\n BY 2")
        program = parse(source, strict=True)
        self.assertEqual(5, len(program.statements))
        self.assertEqual([2, 4], [v.value for v in program.statements[3].expression.operands[1:]])
        self.assertTrue(validate_svrf(source, strict=True).valid)
        for statement in ("A = MAGNIFY M1 BY 0", "A = DEANGLE M1 -1", "A = SNAP M1 .5",
                          "LAYER RESOLUTION M1 0", "SNAP OFFGRID MAYBE"):
            with self.subTest(statement=statement):
                self.assertFalse(validate_svrf("LAYER M1 1\n" + statement, strict=True).valid)

    def test_wrapped_recovery_keeps_rules_on_both_sides_and_locations(self):
        for bad in ("UNRECOGNIZED EXTRA WORDS", "|bad|"):
            source = f"#DECRYPT\r\nFIRST {{ COPY M1 }}\r\n{bad}\r\nLAST {{ COPY M2 }}\r\n#ENDCRYPT"
            program, warnings = parse_with_diagnostics(source)
            wrapper = program.statements[0]
            self.assertEqual("partial", wrapper.parse_status)
            self.assertEqual(["FIRST", "LAST"], [s.name for s in wrapper.body if isinstance(s, ast.RuleCheckBlock)])
            self.assertTrue(any(d.line == 3 and d.start_offset == source.index(bad) for d in warnings), warnings)
            self.assertEqual(source.index("LAST"), wrapper.body[-1].start_offset)
            with self.assertRaises(ParseError) as raised:
                parse(source, strict=True)
            self.assertEqual(3, raised.exception.line)
            self.assertEqual(source.index(bad), raised.exception.token.offset)
        block = parse("#ENCRYPT\n|cipher|\nINCLUDE not_a_file\n#ENDCRYPT", strict=True).statements[0]
        self.assertEqual(("opaque", []), (block.parse_status, block.body))

    def test_partial_payload_does_not_load_files(self):
        source = '#ENCRYPT\nR { COPY M1 }\n|bad|\nINCLUDE never_open_this\n#ENDCRYPT'
        result = validate_svrf(source, filename="synthetic.svrf")
        self.assertEqual("partial", result.program.statements[0].parse_status)
        self.assertNotIn("validation.include.missing_file", [d.code for d in result.diagnostics])

    def test_preprocessor_directives_retain_identity_and_case(self):
        source = '#PRAGMA ENV ProbeName "Mixed value"\n#USING KEYWORD FMACRO\n#IFDEF_EXP MODE "^Fast.*"\nLAYER X 1\n#ENDIF'
        program = parse(source, strict=True)
        pragma, using, conditional = program.statements
        self.assertEqual((["#PRAGMA", "ENV"], ["ProbeName", "Mixed value"]), (pragma.keywords, pragma.arguments))
        self.assertEqual(["#USING", "KEYWORD"], using.keywords)
        self.assertEqual("#IFDEF_EXP", conditional.directive)
        walk = WalkVisitor()
        conditional.accept(walk)
        self.assertTrue(any(isinstance(n, ast.LayerDef) for n in walk.nodes))
        printed = SvrfPrinter().emit(program)
        self.assertIn('#IFDEF_EXP MODE "^Fast.*"', printed)
        self.assertEqual(program.to_dict(False), parse(printed, strict=True).to_dict(False))
        shell = parse('#IFDEF_EXP $CaseSensitive "^X"\nLAYER X 1\n#ENDIF', strict=True)
        self.assertEqual("$CaseSensitive", shell.statements[0].name)

    def test_include_comments_and_environment_defaults(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"REVIEW_EMPTY_VALUE": ""}):
            Path(tmp, "MixedCase").write_bytes(b"LAYER M1 1\n")
            source = ('/*\nINCLUDE missing\n#PRAGMA ENV REVIEW_NO_SUCH_VAR missing\n*/\n'
                      '#PRAGMA ENV REVIEW_NO_SUCH_VAR MixedCase\nINCLUDE $REVIEW_NO_SUCH_VAR\n'
                      '#PRAGMA DEFENV REVIEW_EMPTY_VALUE MixedCase\n')
            with patch.dict(os.environ):
                os.environ.pop("REVIEW_NO_SUCH_VAR", None)
                for key in ("REVIEW_NO_SUCH_VAR", "REVIEW_EMPTY_VALUE"):
                    text = source if key == "REVIEW_NO_SUCH_VAR" else source.replace("INCLUDE $REVIEW_NO_SUCH_VAR\n", "") + "INCLUDE $REVIEW_EMPTY_VALUE\n"
                    result = validate_svrf(text, strict=True, run_directory=tmp, include_in_block_comments=False)
                    self.assertTrue(result.valid, result.diagnostics)
                    self.assertIn("M1", [s.name for s in result.program.statements if isinstance(s, ast.LayerDef)])

    def test_macro_signatures_and_cycles(self):
        prefix = "LAYER M1 1\nDMACRO W lay lim { INT lay < lim }\n"
        for args, valid in (("M1 2", True), ("M1", False), ("M1 2 3", False)):
            result = validate_svrf(prefix + f"R {{ CMACRO W {args} }}", strict=True)
            self.assertEqual(valid, result.valid, result.diagnostics)
            if not valid:
                self.assertIn("semantic.macro.argument_count", [d.code for d in result.errors])
        for source in ("DMACRO A lay { CMACRO A lay }",
                       "DMACRO A lay { CMACRO B lay }\nDMACRO B lay { CMACRO A lay }"):
            result = validate_svrf(source, strict=True)
            self.assertIn("semantic.macro.recursive", [d.code for d in result.errors])

    def test_include_defaults_follow_textual_order_not_process_state(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            key = "SVRF_REGRESSION_DEFAULT"
            os.environ.pop(key, None)
            Path(tmp, "defs").write_text(f"#PRAGMA ENV {key} child\n", encoding="utf8")
            Path(tmp, "child").write_text("LAYER M1 1\n", encoding="utf8")
            include = "INCLUDE $" + key + "\n"

            def check(source):
                return validate_svrf(source, run_directory=tmp, strict=True)

            self.assertTrue(check("INCLUDE defs\n" + include).valid)
            self.assertNotIn(key, os.environ)
            for prefix in ("", "/*\nINCLUDE defs\n*/\n", "#IFDEF CHOICE\nINCLUDE defs\n#ENDIF\n"):
                result = check(prefix + include)
                self.assertIn("validation.include.unresolved_variable", [d.code for d in result.errors])
            os.environ[key] = "child"
            self.assertTrue(check(f"#PRAGMA DEFENV {key} other\n" + include).valid)
            os.environ[key] = ""
            self.assertFalse(check(f"#PRAGMA ENV {key} child\n" + include).valid)
            self.assertTrue(check(f"#PRAGMA DEFENV {key} child\n" + include).valid)

    def test_macro_enablement_arity_and_argument_grouping(self):
        prefix = "LAYER M1 1\nDMACRO W a b { COPY a }\n"
        for call in ("CMACRO W M1 -0.25", "FMACRO W(M1 -0.25)", "CMACRO W M1 (3 + 4)", "FMACRO W(M1 (3 + 4))"):
            with self.subTest(call=call):
                source = prefix + call + "\n#USING KEYWORD FMACRO"
                result = validate_svrf(source, strict=True)
                self.assertTrue(result.valid, result.diagnostics)
                node = result.program.statements[-2]
                self.assertEqual(2, len(node.arguments))
                self.assertEqual(node.to_dict(False), parse(SvrfPrinter().emit(node)).statements[0].to_dict(False))
        result = validate_svrf(prefix + "FMACRO W(M1 1)", strict=True)
        self.assertIn("semantic.macro.fmacro_not_enabled", [d.code for d in result.errors])
        with self.assertRaises(ParseError):
            parse("FMACRO W M1 2", strict=True)
        for option in ("#USING KEYWORD OTHER", "#USING KEYWORD FMACRO\n#USING KEYWORD FMACRO",
                       "#PRAGMA ENV NO_VALUE", "#PRAGMA DEFENV X $OTHER"):
            self.assertFalse(validate_svrf(prefix + option, strict=True).valid)

    def test_mutually_exclusive_macro_definitions_do_not_form_a_cycle(self):
        source = ("#IFDEF CHOICE\nDMACRO A x { CMACRO B x }\nDMACRO B x { COPY x }\n"
                  "#ELSE\nDMACRO A x y { COPY x }\nDMACRO B x y { CMACRO A x y }\n#ENDIF")
        result = validate_svrf(source, strict=True)
        self.assertTrue(result.valid, result.diagnostics)
        result = validate_svrf(source + "\nLAYER M1 1\nCMACRO A M1", strict=True)
        self.assertIn("semantic.macro.conditional_argument_count", [d.code for d in result.errors])

    def test_device_macro_arguments_end_before_netlist_options(self):
        source = ("LAYER M1 1\nDMACRO W a b { COPY a }\n"
                  "DEVICE MOS M1 M1 CMACRO W M1 -0.25 NETLIST ELEMENT devTag")
        result = validate_svrf(source, strict=True)
        self.assertTrue(result.valid, result.diagnostics)
        node = result.program.statements[-1]
        self.assertEqual(["M1", -0.25], node.cmacro_args)
        self.assertEqual([("ELEMENT", "devTag")], node.netlist_options)
        self.assertEqual(node.to_dict(False), parse(SvrfPrinter().emit(node)).statements[0].to_dict(False))

    def test_polygon_and_fill_shape_contracts(self):
        for source, valid in (
            ("POLYGON 0 0 1", False), ("POLYGON 0 0 2 2 1 1", False),
            ("POLYGON 0 0 2 2 1", True), ("POLYGON 0 0 2 0 2 2 1", True),
            ("POLYGON -2 -1 2 1 M1", True), ("POLYGON 2 2 0 0 M1", False),
            ("DFM SPEC FILL SHAPE TILE UNKNOWN_OPTION", False),
            ("DFM SPEC FILL SHAPE TILE RECTFILL 0 0 2", False),
            ("DFM SPEC FILL SHAPE TILE RECTFILL 0 0 1 1 BOGUS", False),
            ("DFM SPEC FILL SHAPE TILE RECTFILL 0 0 1 1 STRIPE 2", False),
            ("DFM SPEC FILL SHAPE TILE ARRAYFILL 0 0 1 1", False),
            ("DFM SPEC FILL SHAPE TILE ARRAYFILL 0 0 1 1 ASTEP 2 NCOL 3 NROW 4", True),
            ("DFM SPEC FILL SHAPE TILE\n#IFDEF CHOICE\nSTRIPE 1\n#ELSE\nRECTFILL 0 0 1 1\n#ENDIF", True),
            ("DFM SPEC FILL SHAPE TILE POLYFILL 0 0 2 0 2 2", True),
        ):
            with self.subTest(source=source):
                result = validate_svrf("LAYER M1 1\n" + source, strict=True)
                self.assertEqual(valid, result.valid, result.diagnostics)
