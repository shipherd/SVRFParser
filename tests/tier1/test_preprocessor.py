"""Tier 1 unit tests: Preprocessor directives."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_one, assert_node_type, collect_warnings
from svrf_parser.ast_nodes import *


class TestDefine:
    def test_define_simple(self):
        node = parse_one("#DEFINE FOO")
        assert_node_type(node, Define, name="FOO", value=None)

    def test_define_with_value(self):
        node = parse_one("#DEFINE FOO 42")
        assert_node_type(node, Define, name="FOO", value="42")

    def test_define_with_string_value(self):
        node = parse_one("#DEFINE BAR hello world")
        assert_node_type(node, Define, name="BAR", value="hello world")


class TestIfDef:
    def test_ifdef_simple(self):
        node = parse_one("#IFDEF FOO\nLAYER M1 1\n#ENDIF")
        assert_node_type(node, IfDef, name="FOO", negated=False)
        assert len(node.then_body) == 1
        assert isinstance(node.then_body[0], LayerDef)

    def test_ifndef(self):
        node = parse_one("#IFNDEF FOO\nLAYER M1 1\n#ENDIF")
        assert_node_type(node, IfDef, name="FOO", negated=True)
        assert len(node.then_body) == 1

    def test_ifdef_else(self):
        text = "#IFDEF FOO\nLAYER M1 1\n#ELSE\nLAYER M2 2\n#ENDIF"
        node = parse_one(text)
        assert_node_type(node, IfDef, negated=False)
        assert len(node.then_body) == 1
        assert len(node.else_body) == 1

    def test_nested_ifdef(self):
        text = "#IFDEF A\n#IFDEF B\nLAYER M1 1\n#ENDIF\n#ENDIF"
        node = parse_one(text)
        assert_node_type(node, IfDef, name="A")
        assert len(node.then_body) == 1
        assert isinstance(node.then_body[0], IfDef)
        assert node.then_body[0].name == "B"


class TestInclude:
    def test_include(self):
        node = parse_one('#INCLUDE "path.svrf"')
        assert_node_type(node, Include, path="path.svrf")


class TestEncrypted:
    def test_encrypted_block(self):
        text = "#ENCRYPT\nsome encrypted content\n#ENDCRYPT"
        node = parse_one(text)
        assert_node_type(node, EncryptedBlock)
