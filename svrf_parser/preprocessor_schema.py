"""Declarative preprocessor-head registry for parser dispatch."""

from __future__ import annotations

from dataclasses import dataclass

from .tokens import TokenType

CONDITIONAL_OPENERS = frozenset({"#IFDEF", "#IFNDEF", "#IFDEF_EXP"})


def pragma_arguments(tokens):
    """Read case-sensitive strings, joining contiguous parts of unquoted paths."""
    args = []
    end = None
    for token in tokens:
        if token.type in (TokenType.NEWLINE, TokenType.EOF):
            break
        part = token.value if token.type == TokenType.STRING else token.raw
        if token.offset == end:
            args[-1] += part
        else:
            args.append(part)
        end = token.end_offset
    return args


@dataclass(frozen=True, slots=True)
class PreprocessorSchema:
    name: str
    tags: frozenset[str]
    parser_method: str

    def matches(self, tag):
        if self.tags:
            return tag in self.tags
        return True


class PreprocessorSchemaRegistry:
    def __init__(self, schemas):
        self.schemas = tuple(
            sorted(
                schemas,
                key=lambda schema: (1 if schema.tags else 0, len(schema.tags), schema.name),
                reverse=True,
            )
        )

    def match(self, tag):
        for schema in self.schemas:
            if schema.matches(tag):
                return schema
        return None


PREPROCESSOR_SCHEMAS = (
    PreprocessorSchema("define", frozenset({"#DEFINE"}), "_parse_define"),
    PreprocessorSchema("include", frozenset({"#INCLUDE"}), "_parse_pp_include"),
    PreprocessorSchema("undefine", frozenset({"#UNDEFINE"}), "_parse_undefine"),
    PreprocessorSchema("options", frozenset({"#PRAGMA", "#USING"}), "_parse_pp_option"),
    PreprocessorSchema(
        "conditional",
        CONDITIONAL_OPENERS,
        "_parse_ifdef_from_preprocessor",
    ),
    PreprocessorSchema(
        "encrypted_block",
        frozenset({"#ENCRYPT", "#DECRYPT"}),
        "_parse_encrypted_block",
    ),
    PreprocessorSchema(
        "noop",
        frozenset({"#ELSE", "#ENDIF"}),
        "_consume_noop_preprocessor",
    ),
    PreprocessorSchema("generic", frozenset(), "_parse_preprocessor_directive"),
)


PREPROCESSOR_SCHEMA_REGISTRY = PreprocessorSchemaRegistry(PREPROCESSOR_SCHEMAS)
