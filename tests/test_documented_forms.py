"""Manual-based regressions independent of either parser's output."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from svrf_parser import parse, validate_svrf, validate_svrf_file
from svrf_parser.printer import SvrfPrinter


def codes(text):
    return [d.code for d in validate_svrf(text, strict=True, follow_includes=False).diagnostics]


class DocumentedForms(unittest.TestCase):
    def roundtrip(self, text):
        tree = parse(text, strict=True)
        emitted = SvrfPrinter().emit(tree)
        self.assertEqual(tree.to_dict(False), parse(emitted, strict=True).to_dict(False))
        return tree.statements, emitted

    def test_map(self):
        nodes, out = self.roundtrip("LAYER MAP >=6 <=8 DATATYPE <4 92\nLAYER MAP 5 TEXTTYPE 2 90 7")
        self.assertEqual([(c.op, c.value.value) for c in nodes[0].gds_num], [('>=', 6), ('<=', 8)])
        self.assertEqual(nodes[1].internal_num, 90)
        self.assertEqual(nodes[1].target_texttype, 7)
        self.assertIn("TEXTTYPE 2 90 7", out)
        self.assertEqual(codes("LAYER MAP 1 TEXTTYPE 2 1048575 65535"), [])
        self.assertIn("semantic.layer_map.target_range", codes("LAYER MAP 1 TEXTTYPE 2 1048576 65536"))

    def test_dimensions(self):
        for long, short, args in [('INTERNAL', 'INT', 'M'), ('EXTERNAL', 'EXT', 'M'), ('ENCLOSURE', 'ENC', 'M N')]:
            s = f"LAYER M 1\nLAYER N 2\nR {{ {long} {args} < 1 }}"
            nodes, _ = self.roundtrip(s)
            self.assertEqual([n.op for n in nodes[-1].body], [short])
            self.assertEqual(codes(s), [])
            self.assertIn('semantic.drc.missing_constraint', codes(s.replace(' < 1', '')))

    def test_declarations_after_modifiers(self):
        text = ('LAYER MET 1\nRULE { EXTERNAL MET < 1 OPPOSITE }\n'
                'RESULT = EXTERNAL MET < 2 OPPOSITE\nLAYER NEXT 2\nLAYER MAP 2 DATATYPE 0 12')
        nodes, _ = self.roundtrip(text)
        self.assertEqual([type(n).__name__ for n in nodes[-3:]], ["LayerAssignment", "LayerDef", "LayerMap"])

    def test_expand_edge_operand_after_distance(self):
        defs = "LAYER SEG 1\nLAYER MASK 2\nVARIABLE DIST 1\n"
        expr = "((ANGLE == 90 SEG) NOT TOUCH EDGE MASK)"
        before = defs + "RESULT = EXPAND EDGE OUT BY DIST " + expr
        after = defs + "RESULT = EXPAND EDGE " + expr + " OUTSIDE BY DIST"
        nodes, _ = self.roundtrip(before)
        self.assertEqual(nodes[-1].expression.operands[0].op, "NOT TOUCH EDGE")
        self.assertEqual(parse(before).to_dict(False), parse(after).to_dict(False))
        self.assertEqual(codes(before), [])

    def test_with_edge_operand_after_constraint(self):
        defs = "LAYER POLYS 1\nLAYER EDGES 2\nLAYER OTHERS 3\n"
        nodes, _ = self.roundtrip(defs + "RESULT = (POLYS WITH EDGE == 1 EDGES) NOT WITH EDGE OTHERS")
        op = nodes[-1].expression
        self.assertEqual(op.op, "NOT WITH EDGE")
        self.assertEqual(op.left.expr.right.name, "EDGES")
        self.assertEqual(op.left.constraints[0].value.value, 1)

    def test_directional_geometry(self):
        defs = "LAYER A 1\nLAYER B 2\nVARIABLE GAP 1\n"
        for op in ("GROW", "SHRINK"):
            text = defs + f"RESULT = {op} TOP BY GAP BOTTOM BY GAP ((EXTENTS A) OR B)"
            nodes, _ = self.roundtrip(text)
            self.assertEqual(nodes[-1].expression.operands[0].op, "OR")
            self.assertEqual(codes(text), [])
        nodes, _ = self.roundtrip(defs + "RESULT = GROW (INTERACT A (OR A B)) LEFT BY GAP")
        self.assertEqual(len(nodes[-1].expression.operands[0].operands), 2)

    def test_tvf(self):
        script = '[/*\r\nproc demo {} { return "[OK]" }\r\n*/]'
        nodes, out = self.roundtrip('TVF FUNCTION EDGE Demo ' + script + '\nLAYER NEXT 4')
        self.assertEqual(nodes[0].arguments[-1], script)
        self.assertIn(script, out)
        self.assertEqual(nodes[1].name, 'NEXT')
        self.roundtrip('TVF FUNCTION "EDGE" ' + script)

    def test_device(self):
        s = "LAYER SEED 1\nLAYER WIRE 2\nLAYER LABELS 3\nDEVICE NFET SEED WIRE(G) BY NET TEXT MODEL LAYER LABELS"
        nodes, _ = self.roundtrip(s)
        self.assertEqual(len(nodes), 4)
        self.assertEqual(nodes[-1].pins, [('WIRE', 'G')])
        self.assertEqual(codes(s), [])

    def test_device_options(self):
        src = ('LAYER SEED 1\nLAYER WIRE 2\nLAYER LABELS 3\n'
               'DEVICE FET SEED WIRE(S) WIRE(D) <WIRE> (S D) ([S D] [G B]) BY SHAPE\n'
               ' TEXT MODEL LAYER LABELS TEXT PROPERTY LAYER LABELS WIRE\n'
               ' SIGNATURE "sigCase" SEED WIRE TEMPLATE "DeviceCase" [0.5]\nLAYER OTHER 4')
        nodes, _ = self.roundtrip(src)
        device = nodes[-2]
        self.assertEqual(device.connection_mode, "SHAPE")
        self.assertEqual(device.swap_lists, [["S", "D"], [["S", "D"], ["G", "B"]]])
        self.assertEqual(device.text_property_layers, ["LABELS", "WIRE"])
        self.assertEqual(device.signature, ("sigCase", ["SEED", "WIRE"]))
        self.assertEqual(device.template, "DeviceCase")
        self.assertEqual(codes(src), [])
        self.assertIn("semantic.device.unknown_text_layer", codes(src.replace("MODEL LAYER LABELS", "MODEL LAYER MISSING_TEXT")))
        nodes, _ = self.roundtrip('DEVICE "my FET" SEED "wire pin"\n BY NET\n TEXT MODEL LAYER LABELS')
        self.assertEqual([(n.device_name, n.pins, n.connection_mode, n.text_model_layer) for n in nodes],
                         [("my FET", [("wire pin", None)], "NET", "LABELS")])

    def test_tvf_does_not_expand_includes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "root"
            (root / "child").write_bytes(b"LAYER FROM_CHILD 1")
            src.write_bytes(b'TVF FUNCTION ERROR Proc [/*\r\nINCLUDE absent\r\n#INCLUDE also_absent\r\n*/]\r\nINCLUDE child')
            result = validate_svrf_file(src, strict=True, run_directory=root)
            self.assertFalse(any("include" in d.code for d in result.diagnostics))
            self.assertIn("FROM_CHILD", [getattr(n, "name", None) for n in result.program.statements])

    def test_control_and_macros(self):
        self.assertEqual(codes('#DEFINE MODE A\n#UNDEFINE MODE\n#DEFINE MODE B'), [])
        self.assertIn('semantic.duplicate_preprocessor', codes('#DEFINE MODE A\n#DEFINE MODE B'))
        prefix = '#USING KEYWORD FMACRO\nDMACRO PAIR P Q { P OR Q }\nLAYER M 1\nLAYER N 2\n'
        for call in ('FMACRO PAIR (M N)', 'CMACRO PAIR M N'):
            nodes, _ = self.roundtrip(prefix + 'OUT = ' + call)
            self.assertEqual(nodes[-1].expression.name, 'PAIR')
            self.assertEqual(codes(prefix + 'OUT = ' + call), [])
            self.assertEqual(codes(prefix + 'OUT = (' + call + ') AND M'), [])
            self.assertEqual(codes(prefix + 'OUT = M OR ' + call), [])
        self.assertIn("semantic.macro.argument_count", codes(prefix + 'OUT = FMACRO PAIR(M)'))
        self.assertIn("semantic.macro.argument_count", codes(prefix + 'OUT = CMACRO PAIR M N M'))
        self.assertIn("semantic.macro.undefined", codes(prefix + 'OUT = FMACRO UNKNOWN(M)'))
        src = prefix + 'OUT = DFM DV OVERRIDE\n  CMACRO PAIR M N\n  DVPARAMS N VMIN 0 VMAX 1 SYNC\n  RDB "case file.rdb"'
        nodes, _ = self.roundtrip(src)
        self.assertEqual(nodes[-1].expression.operands[0].name, "PAIR")
        self.assertEqual(codes(src), [])
        self.assertEqual(codes('#DEFINE F 1\n#IFDEF SW\n#UNDEFINE F\n#ELSE\n#UNDEFINE F\n#ENDIF\n#DEFINE F 2'), [])
        self.assertIn('semantic.duplicate_preprocessor', codes('#DEFINE F 1\n#IFDEF SW\n#UNDEFINE F\n#ENDIF\n#DEFINE F 2'))

    def test_dfm(self):
        via = 'DFM SPEC VIA UNIT_VIA VIASHAPE 1 ENC1 0.2 ENC2 0.2'
        nodes, _ = self.roundtrip(via)
        self.assertEqual(nodes[0].kind, 'VIA')
        self.assertEqual(codes(via), [])
        for body in ('OUT = COPY SRC', '/*\nOUT = COPY SRC\n*/'):
            src = f'DFM SPEC SVRF WORK (SRC(NODAL) : OUT) VARIABLES [WIDTH = 2] [\n{body}\n] CENTER'
            nodes, _ = self.roundtrip(src)
            self.assertEqual(nodes[0].outputs, ['OUT'])
            self.assertEqual(nodes[0].body[0].name, 'OUT')
            self.assertEqual(codes(src), [])

    def test_local_scope_and_spans(self):
        src = ('VARIABLE OUTER_GRID 2\nLAYER GLOBAL_WIRE 10\n'
               'DFM SPEC SVRF WORK (SRC : LOCAL_RESULT) VARIABLES [STEP_X = -2 SCALE_Y] [/*\n'
               'INTERMEDIATE = SIZE SRC BY OUTER_GRID\nLOCAL_RESULT = SIZE INTERMEDIATE BY STEP_X\n*/] CENTER')
        nodes, _ = self.roundtrip(src)
        spec = nodes[-1]
        self.assertTrue(spec.center and spec.wrapped)
        self.assertEqual(spec.body[0].line, 4)
        self.assertEqual(spec.body[0].start_offset, src.index('INTERMEDIATE ='))
        self.assertEqual(codes(src), [])
        self.assertTrue(codes(src.replace("SIZE SRC BY", "SIZE GLOBAL_WIRE BY")))
        self.assertTrue(codes(src + "\nBAD = COPY INTERMEDIATE"))
        self.assertIn("semantic.dfm.local_output", codes(src.replace(": LOCAL_RESULT", ": NEVER_DERIVED")))
        self.assertIn("semantic.dfm.local_variable", codes(src.replace("STEP_X = -2", "OUTER_GRID = -2")))
        self.assertIn("semantic.dfm.via_dimension", codes("DFM SPEC VIA VV VIASHAPE 1 2 ENC1 -1 ENC2 0"))

    def test_validation(self):
        self.assertTrue(codes('RESOLUTION 0'))
        self.assertEqual(codes('RESOLUTION 1 2'), [])
        for invalid in ("-1", "1.5", "1 2 3"):
            self.assertIn("semantic.directive.invalid_value", codes("RESOLUTION " + invalid))
        self.assertTrue(codes('LAYER M 1\nOUT = DFM DV ANALYZE M'))
        self.assertEqual(codes('LAYER M 1\nOUT = DFM DV ANALYZE M RDB "out.rdb"'), [])
        _, text = self.roundtrip('LAYER M 1\nOUT = DFM DV ANALYZE M\nRDB "Case Sensitive.rdb" NOPSEUDO')
        self.assertIn('"Case Sensitive.rdb"', text)
        for end in ("RDB", 'RDB ""', "RDB NOPSEUDO"):
            self.assertIn("semantic.drc.missing_modifier", codes("LAYER M 1\nOUT = DFM DV ANALYZE M " + end))
        layers = [f'MET{i}' for i in range(33)]
        defs = ''.join(f'LAYER {name} {i}\n' for i, name in enumerate(layers))
        self.assertEqual(codes(defs + 'CONNECT ' + ' '.join(layers[:32])), [])
        self.assertTrue(codes(defs + 'CONNECT ' + ' '.join(layers)))
        nodes, _ = self.roundtrip('SCONNECT MET0 MET1 LINK "vdd" ABUT ALSO')
        self.assertEqual(nodes[0].link_name, "vdd")
