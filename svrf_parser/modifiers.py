"""Typed modifier views with adapters for the historic AST representation."""

from __future__ import annotations

from dataclasses import dataclass

from . import ast
from .symbol_convention import SYMBOL_CONVENTION_REGISTRY


def modifier_value_context(name, fallback="generic"):
    name = str(name).upper()
    if name == "BY" or name.endswith(" BY") or name in SYMBOL_CONVENTION_REGISTRY.scalar_tuple_heads:
        return "scalar"
    return fallback


@dataclass(frozen=True, slots=True)
class NamedModifier:
    name: str
    value: object

    def context(self, fallback="generic"):
        if self.name.upper() == "BY" and isinstance(self.value, ast.LayerRef) and self.value.name == "NET":
            return "literal"
        return modifier_value_context(self.name, fallback)

    def to_legacy(self):
        return self.name, self.value


@dataclass(frozen=True, slots=True)
class RawModifier:
    value: object

    def context(self, fallback="generic"):
        return fallback

    def to_legacy(self):
        return self.value


def as_modifier(value):
    if isinstance(value, (NamedModifier, RawModifier)):
        return value
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
        return NamedModifier(value[0], value[1])
    return RawModifier(value)


def modifier_nodes(values):
    return tuple(as_modifier(value) for value in values)


def legacy_modifiers(values):
    return [as_modifier(value).to_legacy() for value in values]
