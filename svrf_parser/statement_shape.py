"""Packaged statement-internal shape registry."""

from __future__ import annotations

from dataclasses import dataclass

from .svrf_spec import STATEMENT_SHAPE_SPEC


@dataclass(frozen=True, slots=True)
class StatementShape:
    name: str
    family: str


class StatementShapeRegistry:
    def __init__(self, shapes):
        self.shapes = tuple(shapes)
        self._by_name = {shape.name: shape for shape in self.shapes}

    def get(self, name):
        return self._by_name.get(name)


STATEMENT_SHAPES = tuple(
    StatementShape(name=entry.name, family=entry.family)
    for entry in STATEMENT_SHAPE_SPEC.entries
)


STATEMENT_SHAPE_REGISTRY = StatementShapeRegistry(STATEMENT_SHAPES)
