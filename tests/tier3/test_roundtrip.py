"""Tier 3 roundtrip tests: parse -> print -> re-parse -> compare."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from svrf_parser import parse, parse_with_diagnostics
from svrf_parser.printer import SvrfPrinter
from tests.helpers import ast_equal, parse_one, parse_expr


printer = SvrfPrinter()


def roundtrip_check(svrf_text):
    """Parse text, print it, re-parse, and compare ASTs."""
    tree1 = parse(svrf_text, filename="<roundtrip>")
    regenerated = printer.emit(tree1)
    tree2 = parse(regenerated, filename="<roundtrip2>")
    assert ast_equal(tree1, tree2), (
        f"Round-trip mismatch.\n"
        f"Original AST statements: {len(tree1.statements)}\n"
        f"Regenerated AST statements: {len(tree2.statements)}\n"
        f"Regenerated text:\n{regenerated}"
    )


class TestPreprocessorRoundtrip:
    def test_define_simple(self):
        roundtrip_check("#DEFINE FOO")

    def test_define_with_value(self):
        roundtrip_check("#DEFINE FOO 42")

    def test_ifdef(self):
        roundtrip_check("#IFDEF FOO\nLAYER M1 1\n#ENDIF")

    def test_ifndef(self):
        roundtrip_check("#IFNDEF FOO\nLAYER M1 1\n#ENDIF")

    def test_ifdef_else(self):
        roundtrip_check("#IFDEF FOO\nLAYER M1 1\n#ELSE\nLAYER M1 2\n#ENDIF")

    def test_include(self):
        roundtrip_check('#INCLUDE "path.svrf"')


class TestLayerRoundtrip:
    def test_layer_def(self):
        roundtrip_check("LAYER M1 10")

    def test_layer_def_multi(self):
        roundtrip_check("LAYER M1 10 11")

    def test_layer_map(self):
        roundtrip_check("LAYER MAP 62 DATATYPE 0 1062")

    def test_layer_assignment(self):
        roundtrip_check("M1_sized = SIZE M1 BY 0.1")


class TestBooleanRoundtrip:
    def test_and(self):
        roundtrip_check("result = M1 AND M2")

    def test_or(self):
        roundtrip_check("result = M1 OR M2")

    def test_not_infix(self):
        roundtrip_check("result = M1 NOT M2")

    def test_not_unary(self):
        roundtrip_check("result = NOT M1")


class TestSpatialRoundtrip:
    def test_inside(self):
        roundtrip_check("result = M1 INSIDE M2")

    def test_outside(self):
        roundtrip_check("result = M1 OUTSIDE M2")

    def test_interact(self):
        roundtrip_check("result = M1 INTERACT M2")

    def test_touch(self):
        roundtrip_check("result = M1 TOUCH M2")

    def test_enclose(self):
        roundtrip_check("result = M1 ENCLOSE M2")

    def test_cut(self):
        roundtrip_check("result = M1 CUT M2")


class TestDRCRoundtrip:
    def test_int_basic(self):
        roundtrip_check("check1 {\n  INT M1 < 0.1\n}")

    def test_ext_basic(self):
        roundtrip_check("check1 {\n  EXT M1 M2 < 0.2\n}")

    def test_enc_basic(self):
        roundtrip_check("check1 {\n  ENC M1 M2 < 0.1\n}")


class TestConnectivityRoundtrip:
    def test_connect(self):
        roundtrip_check("CONNECT M1 M2")

    def test_connect_by(self):
        roundtrip_check("CONNECT M1 M2 BY VIA1")

    def test_sconnect(self):
        roundtrip_check("SCONNECT M1 M2")


class TestDirectiveRoundtrip:
    def test_layout_path(self):
        roundtrip_check('LAYOUT PATH "design.gds"')

    def test_precision(self):
        roundtrip_check("PRECISION 1000")

    def test_title(self):
        roundtrip_check('TITLE "My DRC Deck"')


class TestMiscRoundtrip:
    def test_group(self):
        roundtrip_check("GROUP grp1 pattern")

    def test_attach(self):
        roundtrip_check("ATTACH M1 VDD")

    def test_variable(self):
        roundtrip_check("VARIABLE WIDTH 0.1")


class TestRuleCheckRoundtrip:
    def test_basic_block(self):
        roundtrip_check("check1 {\n  INT M1 < 0.1\n}")

    def test_with_description(self):
        roundtrip_check("check1 {\n  @ Description text\n  INT M1 < 0.1\n}")

    def test_multiple_ops(self):
        roundtrip_check("check1 {\n  INT M1 < 0.1\n  EXT M1 M2 < 0.2\n}")
