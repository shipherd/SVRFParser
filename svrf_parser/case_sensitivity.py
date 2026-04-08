"""Manual-backed case-sensitivity rules exposed at runtime."""

from __future__ import annotations

from dataclasses import dataclass

from .svrf_spec import CASE_SENSITIVITY_SPEC


@dataclass(frozen=True, slots=True)
class CaseSensitivityRule:
    name: str
    category: str
    case_mode: str
    scope: str
    note: str
    manual_refs: tuple[str, ...]
    tags: frozenset[str]


class CaseSensitivityRegistry:
    def __init__(self, rules):
        self.rules = tuple(rules)
        self._by_name = {rule.name: rule for rule in self.rules}

    def get(self, name):
        return self._by_name.get(name)

    def by_scope(self, scope):
        return tuple(rule for rule in self.rules if rule.scope == scope)

    def by_case_mode(self, case_mode):
        return tuple(rule for rule in self.rules if rule.case_mode == case_mode)


CASE_SENSITIVITY_RULES = tuple(
    CaseSensitivityRule(
        name=entry.name,
        category=entry.category,
        case_mode=entry.case_mode,
        scope=entry.scope,
        note=entry.note,
        manual_refs=entry.manual_refs,
        tags=entry.tags,
    )
    for entry in CASE_SENSITIVITY_SPEC.entries
)


CASE_SENSITIVITY_REGISTRY = CaseSensitivityRegistry(CASE_SENSITIVITY_RULES)
