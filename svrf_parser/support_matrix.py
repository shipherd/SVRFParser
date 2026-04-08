"""Manual-backed feature support matrix exposed at runtime."""

from __future__ import annotations

from dataclasses import dataclass

from .svrf_spec import SUPPORT_MATRIX_SPEC


@dataclass(frozen=True, slots=True)
class SupportMatrixEntry:
    name: str
    dialects: frozenset[str]
    feature_family: str
    support_level: str
    parser_support: str
    semantic_support: str
    note: str
    manual_refs: tuple[str, ...]
    tags: frozenset[str]


class SupportMatrixRegistry:
    def __init__(self, entries):
        self.entries = tuple(entries)
        self._by_name = {entry.name: entry for entry in self.entries}

    def get(self, name):
        return self._by_name.get(name)

    def by_dialect(self, dialect):
        return tuple(entry for entry in self.entries if dialect in entry.dialects)

    def by_support_level(self, support_level):
        return tuple(entry for entry in self.entries if entry.support_level == support_level)


SUPPORT_MATRIX_ENTRIES = tuple(
    SupportMatrixEntry(
        name=entry.name,
        dialects=entry.dialects,
        feature_family=entry.feature_family,
        support_level=entry.support_level,
        parser_support=entry.parser_support,
        semantic_support=entry.semantic_support,
        note=entry.note,
        manual_refs=entry.manual_refs,
        tags=entry.tags,
    )
    for entry in SUPPORT_MATRIX_SPEC.entries
)


SUPPORT_MATRIX_REGISTRY = SupportMatrixRegistry(SUPPORT_MATRIX_ENTRIES)
