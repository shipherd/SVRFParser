"""Operation-level CST nodes for DRC operation normalization."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class OperationCst:
    """Intermediate DRC operation shape before AST normalization."""

    op: str
    operands: tuple = field(default_factory=tuple)
    constraints: tuple = field(default_factory=tuple)
    modifiers: tuple = field(default_factory=tuple)
    strategy: str = "default"

