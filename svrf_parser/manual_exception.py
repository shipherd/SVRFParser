"""Reviewed manual-exception inventory exposed at runtime."""

from __future__ import annotations

from dataclasses import dataclass

from .svrf_spec import MANUAL_EXCEPTION_SPEC


@dataclass(frozen=True, slots=True)
class ManualExceptionEntry:
    name: str
    category: str
    applies_to: tuple[str, ...]
    effect: str
    note: str
    manual_refs: tuple[str, ...]
    tags: frozenset[str]


class ManualExceptionRegistry:
    def __init__(self, entries):
        self.entries = tuple(entries)
        self._by_name = {entry.name: entry for entry in self.entries}

    def get(self, name):
        return self._by_name.get(name)

    def by_category(self, category):
        return tuple(entry for entry in self.entries if entry.category == category)

    def tagged(self, tag):
        return tuple(entry for entry in self.entries if tag in entry.tags)


MANUAL_EXCEPTION_ENTRIES = tuple(
    ManualExceptionEntry(
        name=entry.name,
        category=entry.category,
        applies_to=entry.applies_to,
        effect=entry.effect,
        note=entry.note,
        manual_refs=entry.manual_refs,
        tags=entry.tags,
    )
    for entry in MANUAL_EXCEPTION_SPEC.entries
)


MANUAL_EXCEPTION_REGISTRY = ManualExceptionRegistry(MANUAL_EXCEPTION_ENTRIES)
