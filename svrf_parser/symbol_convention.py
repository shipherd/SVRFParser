"""Reviewed symbol-convention inventory and runtime helpers."""

from __future__ import annotations

from dataclasses import dataclass

from .svrf_spec import SYMBOL_CONVENTION_SPEC


@dataclass(frozen=True, slots=True)
class SymbolConventionEntry:
    name: str
    category: str
    values: tuple[str, ...]
    note: str
    manual_refs: tuple[str, ...]
    tags: frozenset[str]


class SymbolConventionRegistry:
    def __init__(self, entries):
        self.entries = tuple(entries)
        self._by_name = {entry.name: entry for entry in self.entries}

    def get(self, name):
        return self._by_name.get(name)

    def values(self, name):
        entry = self.get(name)
        if entry is None:
            return ()
        return entry.values

    def value_set(self, name):
        return frozenset(self.values(name))

    @property
    def scalar_tuple_heads(self):
        return self.value_set("scalar_tuple_heads")

    @property
    def companion_file_suffixes(self):
        return self.values("companion_file_suffixes")

    @property
    def local_scope_kinds(self):
        return self.value_set("local_scope_kinds")

    @property
    def external_unresolved_contexts(self):
        return self.values("external_unresolved_contexts")


SYMBOL_CONVENTION_ENTRIES = tuple(
    SymbolConventionEntry(
        name=entry.name,
        category=entry.category,
        values=entry.values,
        note=entry.note,
        manual_refs=entry.manual_refs,
        tags=entry.tags,
    )
    for entry in SYMBOL_CONVENTION_SPEC.entries
)


SYMBOL_CONVENTION_REGISTRY = SymbolConventionRegistry(SYMBOL_CONVENTION_ENTRIES)
