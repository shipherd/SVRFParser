"""DRC operation semantic contract data."""

from __future__ import annotations

from .operation_schema import OPERATION_SCHEMA_REGISTRY

_CONTRACTS = OPERATION_SCHEMA_REGISTRY.contracts

WITH_OPS = frozenset(name for name, entry in _CONTRACTS.items() if entry.requires_content)

DRCOP_MIN_OPERANDS = {name: entry.min_operands for name, entry in _CONTRACTS.items()
                      if entry.min_operands is not None}
DRCOP_MIN_CONSTRAINTS = {name: entry.min_constraints for name, entry in _CONTRACTS.items()
                         if entry.min_constraints is not None}
DRCOP_MIN_MODIFIERS = {name: entry.min_modifiers for name, entry in _CONTRACTS.items()
                       if entry.min_modifiers is not None}
