"""DRC operation semantic contract data."""

from __future__ import annotations

WITH_OPS = frozenset({"WITH TEXT", "WITH WIDTH", "WITH EDGE", "WITH NEIGHBOR"})

DRCOP_MIN_OPERANDS = {
    "DFM DV": 1,
    "DFM PROPERTY": 1,
    "DFM PROPERTY NET": 1,
    "DFM SPACE": 1,
    "DFM TEXT": 1,
    "NET": 1,
    "NET AREA": 1,
    "NET AREA RATIO": 1,
    "NET INTERACT": 1,
    "PATHCHK": 1,
}

DRCOP_MIN_CONSTRAINTS = {
    "NET AREA": 1,
    "NET AREA RATIO": 1,
    "NET INTERACT": 1,
}

DRCOP_MIN_MODIFIERS = {
    "DEVICE LAYER": 1,
    "PATHCHK": 1,
}
