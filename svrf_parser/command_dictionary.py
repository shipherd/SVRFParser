"""Exact reference-dictionary heads and the subset with closed option grammars."""

import json
from dataclasses import dataclass
from importlib.resources import files

from .modifiers import QuotedScalar
from .tokens import TokenType as TT


@dataclass(frozen=True, slots=True)
class Command:
    name: str
    kind: str
    forms: tuple | None
    min_args: int
    route: str | None


def _route(name, kind, forms):
    first = name.split()[0]
    if kind == "operation":
        if (first == "DFM" and name.count(" ") >= 2 and not name.startswith(("DFM DV ", "DFM MAT "))
                or name in {"DENSITY CONVOLVE", "DRAWN ACUTE", "DRAWN ANGLED", "DRAWN OFFGRID",
                            "DRAWN SKEW", "DRC EXECUTE LUP_GROW", "EXPAND TEXT", "EXTENT CELL",
                            "EXTENT DRAWN", "NET AREA RATIO ACCUMULATE", "NET AREA RATIO COUPLED",
                            "NET AREA RATIO PRINT", "OFFGRID DIRECTIONAL", "TDDRC"}):
            return "operation"
        return None
    if forms is not None and name not in {"SNAP OFFGRID", "DISCONNECT"}:
        return "closed"
    if name in {"LAYER DIRECTORY", "LVS GLOBAL LAYOUT NAME", "LVS RECON ERC SELECT DEVICE",
                "LVS WRITE INJECTED LAYOUT NETLIST", "LVS WRITE LAYOUT NETLIST",
                "PERC LDL LAYOUT REDUCE CELL LIST", "PERC LDL LAYOUT REDUCE TOP LAYERS"}:
        return "statement"
    if first in {"CAPACITANCE", "PARASITIC", "RESISTANCE"} or (
        first == "DFM" and not name.startswith(("DFM SPEC FILL", "DFM SPEC SPACE", "DFM SPEC OPTIMIZE", "DFM SPEC VIA"))
    ):
        return "statement"
    return None


TOPICS = tuple(tuple(row) for row in json.loads(
    files("svrf_parser.svrf_spec.data").joinpath("command_dictionary.json").read_text(encoding="ascii")))


def _index():
    groups = {}
    for _, kind, head, forms, minimum in TOPICS:
        if head:
            groups.setdefault(head, []).append((kind, forms, minimum))
    commands = {}
    trie = {}
    for head, records in groups.items():
        kind = records[0][0]
        forms = None
        if all(k == kind and f is not None for k, f, _ in records):
            forms = tuple(sorted({tuple(s.split()) for _, fs, _ in records for s in fs}))
        command = Command(head, kind, forms, min(m for _, _, m in records), _route(head, kind, forms))
        commands[head] = command
        branch = trie
        for word in head.split():
            branch = branch.setdefault(word, {})
        branch[None] = command
    return commands, trie


COMMANDS, _TRIE = _index()
FIRST_WORDS = frozenset(_TRIE)
OP_STARTS = frozenset(c.name.split()[0] for c in COMMANDS.values() if c.route == "operation")
STMT_STARTS = frozenset(c.name.split()[0] for c in COMMANDS.values() if c.route in {"closed", "statement"})


def match_tokens(tokens, index):
    """Longest primary keyword, ignoring newlines but never crossing other tokens."""
    branch = _TRIE
    found = None
    while index < len(tokens) and tokens[index].type == TT.IDENT:
        t = tokens[index]
        branch = branch.get(t.value) or branch.get(t.raw.upper())
        if branch is None:
            break
        index += 1
        if None in branch:
            found = (branch[None], index)
        if index < len(tokens) and tokens[index].type == TT.NEWLINE:
            while index < len(tokens) and tokens[index].type == TT.NEWLINE:
                index += 1
            if (index + 1 < len(tokens) and tokens[index + 1].type == TT.SYMBOL
                    and tokens[index + 1].value in {"=", "{"}):
                break
    return found


def match_words(words):
    branch = _TRIE
    found = None
    for i, word in enumerate(words):
        if not isinstance(word, str) or isinstance(word, QuotedScalar):
            break
        branch = branch.get(word.upper())
        if branch is None:
            break
        if None in branch:
            found = (branch[None], i + 1)
    return found
