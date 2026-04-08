"""Tier 3 roundtrip tests: parse -> print -> re-parse -> compare."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from svrf_parser import parse
from svrf_parser.printer import SvrfPrinter
from tests.helpers import ast_equal


printer = SvrfPrinter()


def roundtrip_check(svrf_text):
    """Parse text, print it, re-parse, and compare ASTs."""
    tree1 = parse(svrf_text, filename="<roundtrip>")
    regenerated = printer.emit(tree1)
    tree2 = parse(regenerated, filename="<roundtrip2>")
    return ast_equal(tree1, tree2), regenerated, tree1, tree2


class RoundtripTestCase(unittest.TestCase):
    def assertRoundtrip(self, svrf_text):
        equal, regenerated, tree1, tree2 = roundtrip_check(svrf_text)
        self.assertTrue(
            equal,
            (
                f"Round-trip mismatch.\n"
                f"Original AST statements: {len(tree1.statements)}\n"
                f"Regenerated AST statements: {len(tree2.statements)}\n"
                f"Regenerated text:\n{regenerated}"
            ),
        )


class TestPreprocessorRoundtrip(RoundtripTestCase):
    def test_define_simple(self):
        self.assertRoundtrip("#DEFINE FOO")

    def test_define_with_value(self):
        self.assertRoundtrip("#DEFINE FOO 42")

    def test_ifdef(self):
        self.assertRoundtrip("#IFDEF FOO\nLAYER M1 1\n#ENDIF")

    def test_ifndef(self):
        self.assertRoundtrip("#IFNDEF FOO\nLAYER M1 1\n#ENDIF")

    def test_ifdef_else(self):
        self.assertRoundtrip("#IFDEF FOO\nLAYER M1 1\n#ELSE\nLAYER M1 2\n#ENDIF")

    def test_include(self):
        self.assertRoundtrip('#INCLUDE "path.svrf"')


class TestLayerRoundtrip(RoundtripTestCase):
    def test_layer_def(self):
        self.assertRoundtrip("LAYER M1 10")

    def test_layer_def_multi(self):
        self.assertRoundtrip("LAYER M1 10 11")

    def test_layer_map(self):
        self.assertRoundtrip("LAYER MAP 62 DATATYPE 0 1062")

    def test_layer_assignment(self):
        self.assertRoundtrip("M1_sized = SIZE M1 BY 0.1")


class TestBooleanRoundtrip(RoundtripTestCase):
    def test_and(self):
        self.assertRoundtrip("result = M1 AND M2")

    def test_or(self):
        self.assertRoundtrip("result = M1 OR M2")

    def test_not_infix(self):
        self.assertRoundtrip("result = M1 NOT M2")

    def test_not_unary(self):
        self.assertRoundtrip("result = NOT M1")


class TestSpatialRoundtrip(RoundtripTestCase):
    def test_inside(self):
        self.assertRoundtrip("result = M1 INSIDE M2")

    def test_outside(self):
        self.assertRoundtrip("result = M1 OUTSIDE M2")

    def test_interact(self):
        self.assertRoundtrip("result = M1 INTERACT M2")

    def test_touch(self):
        self.assertRoundtrip("result = M1 TOUCH M2")

    def test_enclose(self):
        self.assertRoundtrip("result = M1 ENCLOSE M2")

    def test_cut(self):
        self.assertRoundtrip("result = M1 CUT M2")


class TestDRCRoundtrip(RoundtripTestCase):
    def test_int_basic(self):
        self.assertRoundtrip("check1 {\n  INT M1 < 0.1\n}")

    def test_ext_basic(self):
        self.assertRoundtrip("check1 {\n  EXT M1 M2 < 0.2\n}")

    def test_enc_basic(self):
        self.assertRoundtrip("check1 {\n  ENC M1 M2 < 0.1\n}")


class TestConnectivityRoundtrip(RoundtripTestCase):
    def test_connect(self):
        self.assertRoundtrip("CONNECT M1 M2")

    def test_connect_by(self):
        self.assertRoundtrip("CONNECT M1 M2 BY VIA1")

    def test_sconnect(self):
        self.assertRoundtrip("SCONNECT M1 M2")


class TestDirectiveRoundtrip(RoundtripTestCase):
    def test_layout_path(self):
        self.assertRoundtrip('LAYOUT PATH "design.gds"')

    def test_precision(self):
        self.assertRoundtrip("PRECISION 1000")

    def test_title(self):
        self.assertRoundtrip('TITLE "My DRC Deck"')


class TestMiscRoundtrip(RoundtripTestCase):
    def test_group(self):
        self.assertRoundtrip("GROUP grp1 pattern")

    def test_attach(self):
        self.assertRoundtrip("ATTACH M1 VDD")

    def test_variable(self):
        self.assertRoundtrip("VARIABLE WIDTH 0.1")


class TestRuleCheckRoundtrip(RoundtripTestCase):
    def test_basic_block(self):
        self.assertRoundtrip("check1 {\n  INT M1 < 0.1\n}")

    def test_with_description(self):
        self.assertRoundtrip("check1 {\n  @ Description text\n  INT M1 < 0.1\n}")

    def test_multiple_ops(self):
        self.assertRoundtrip("check1 {\n  INT M1 < 0.1\n  EXT M1 M2 < 0.2\n}")


if __name__ == "__main__":
    unittest.main()
