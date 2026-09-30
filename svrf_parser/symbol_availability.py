"""Configuration-independent availability of guarded symbol definitions."""

from __future__ import annotations

from enum import Enum


class Availability(Enum):
    ABSENT = "absent"
    UNAVAILABLE = "unavailable_branch"
    CONDITIONAL = "conditional"
    DEFINITE = "definite"


def guarded_availability(definition_paths, branch_path):
    """Check definition guards without choosing a preprocessor configuration."""
    paths = tuple(definition_paths)
    if not paths:
        return Availability.ABSENT
    choices = dict(branch_path)
    clauses = {
        frozenset((key, value) for key, value in path if key not in choices)
        for path in paths
        if all(key not in choices or choices[key] == value for key, value in path)
    }
    if not clauses:
        return Availability.UNAVAILABLE

    # Complementary branches cover their parent, including nested alternatives.
    pending = list(clauses)
    while pending:
        clause = pending.pop()
        if not clause:
            return Availability.DEFINITE
        for key, value in clause:
            opposite = (clause - {(key, value)}) | {(key, not value)}
            if opposite in clauses:
                parent = clause - {(key, value)}
                if parent not in clauses:
                    clauses.add(parent)
                    pending.append(parent)
    return Availability.CONDITIONAL
