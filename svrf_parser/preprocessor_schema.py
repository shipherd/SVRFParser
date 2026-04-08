"""Declarative preprocessor-head registry for parser dispatch."""

from __future__ import annotations

from dataclasses import dataclass


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
    PreprocessorSchema(
        "conditional",
        frozenset({"#IFDEF", "#IFNDEF", "#IFDEF_EXP"}),
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
