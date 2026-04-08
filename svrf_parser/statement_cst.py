"""Lightweight CST objects for pre-classified statement spans."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StatementHead:
    kind: str
    start: int
    end: int
    words: tuple[str, ...]

    @property
    def primary(self):
        if not self.words:
            return None
        return self.words[0]

    def matches_prefix(self, *words):
        words = tuple(words)
        if not words:
            return True
        return self.words[: len(words)] == words


@dataclass(frozen=True, slots=True)
class RuleCheckHeader:
    name: str
    body_start: int


@dataclass(frozen=True, slots=True)
class PropertyBlockHeader:
    properties: tuple[str, ...]
    body_start: int


@dataclass(frozen=True, slots=True)
class StatementCst:
    mode: str
    parse_kind: str
    start: int
    end: int
    head: StatementHead | None
    rule_check_header: RuleCheckHeader | None
    property_block_header: PropertyBlockHeader | None
    leading_delimiter: str | None
    boundary_kind: str
    boundary_value: str | None
    continued_across_newline: bool

    @property
    def body_start(self):
        if self.head is None:
            return self.start
        return self.head.end

    @property
    def head_kind(self):
        if self.head is None:
            return self.parse_kind
        return self.head.kind

    @property
    def head_value(self):
        if self.head is None:
            return None
        return self.head.primary

    @property
    def head_words(self):
        if self.head is None:
            return ()
        return self.head.words
