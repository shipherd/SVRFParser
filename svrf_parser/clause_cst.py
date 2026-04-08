"""Clause-level CST nodes built from statement spans."""

from __future__ import annotations

from dataclasses import dataclass

from .statement_cst import StatementCst


@dataclass(frozen=True, slots=True)
class ClauseNode:
    start: int
    end: int

    @property
    def kind(self):
        return type(self).__name__


@dataclass(frozen=True, slots=True)
class KeywordRunClause(ClauseNode):
    words: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScalarClause(ClauseNode):
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperandClause(ClauseNode):
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModifierClause(ClauseNode):
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OpaqueEmbeddedLanguageChunk(ClauseNode):
    values: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class DelimitedGroupClause(ClauseNode):
    open_symbol: str
    close_symbol: str | None
    clauses: tuple[ClauseNode, ...]


@dataclass(frozen=True, slots=True)
class StatementClauseCst:
    statement: StatementCst
    header_clauses: tuple[ClauseNode, ...]
    body_clauses: tuple[ClauseNode, ...]

    @property
    def parse_kind(self):
        parse_kind = self.statement.parse_kind
        if parse_kind != "statement_head":
            return parse_kind
        head_words = self.statement.head_words
        if not head_words:
            return parse_kind
        primary = head_words[0]
        if primary in {"CMACRO", "FMACRO"}:
            return "macro_call"
        if primary == "GROUP":
            return "group"
        if primary == "CONNECT":
            return "connect"
        if primary == "SCONNECT":
            return "sconnect"
        if primary == "INCLUDE":
            return "include"
        if primary == "ATTACH":
            return "attach"
        if primary == "DEVICE":
            return "device"
        if head_words[:2] == ("TRACE", "PROPERTY"):
            return "trace_property"
        return parse_kind

    @property
    def mode(self):
        return self.statement.mode

    @property
    def all_clauses(self):
        return (*self.header_clauses, *self.body_clauses)

    @property
    def end(self):
        end = self.statement.end
        for clause in self.all_clauses:
            if clause.end > end:
                end = clause.end
        return end
