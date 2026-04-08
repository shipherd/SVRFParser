"""Packaged statement-head registry for parser dispatch."""

from __future__ import annotations

from dataclasses import dataclass

from .svrf_spec import STATEMENT_SCHEMA_SPEC


@dataclass(frozen=True, slots=True)
class StatementSchema:
    name: str
    modes: frozenset[str]
    parser_method: str
    head_prefix: tuple[str, ...] = ()
    parse_kinds: frozenset[str] = frozenset()

    def matches(self, mode, head_words=(), parse_kind=None):
        if mode not in self.modes:
            return False
        if self.parse_kinds and parse_kind not in self.parse_kinds:
            return False
        head_words = tuple(head_words or ())
        if self.head_prefix:
            return head_words[: len(self.head_prefix)] == self.head_prefix
        return bool(self.parse_kinds)


class StatementSchemaRegistry:
    def __init__(self, schemas):
        self.schemas = tuple(
            sorted(
                schemas,
                key=lambda schema: (
                    1 if schema.head_prefix else 0,
                    len(schema.head_prefix),
                    1 if schema.parse_kinds else 0,
                    schema.name,
                ),
                reverse=True,
            )
        )
        self._by_mode_and_head = {}
        self._by_mode_and_parse_kind = {}
        for schema in self.schemas:
            for mode in schema.modes:
                if schema.head_prefix:
                    self._by_mode_and_head.setdefault((mode, schema.head_prefix[0]), []).append(schema)
                elif schema.parse_kinds:
                    for parse_kind in schema.parse_kinds:
                        self._by_mode_and_parse_kind.setdefault((mode, parse_kind), []).append(schema)

    def match(self, mode, head_words=(), parse_kind=None):
        head_words = tuple(head_words or ())
        if not head_words and parse_kind is None:
            return None
        candidates = []
        if head_words:
            candidates.extend(self._by_mode_and_head.get((mode, head_words[0]), ()))
        if parse_kind is not None:
            candidates.extend(self._by_mode_and_parse_kind.get((mode, parse_kind), ()))
        for schema in candidates:
            if schema.matches(mode, head_words=head_words, parse_kind=parse_kind):
                return schema
        return None


STATEMENT_SCHEMAS = tuple(
    StatementSchema(
        name=entry.name,
        modes=entry.modes,
        parser_method=entry.parser_method,
        head_prefix=entry.head_prefix,
        parse_kinds=entry.parse_kinds,
    )
    for entry in STATEMENT_SCHEMA_SPEC.entries
)


STATEMENT_SCHEMA_REGISTRY = StatementSchemaRegistry(STATEMENT_SCHEMAS)
