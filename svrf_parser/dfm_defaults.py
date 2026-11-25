"""Option grammar for DFM DEFAULTS. A star denotes one scalar or grouped value."""

from .modifiers import QuotedScalar


PATTERNS = {
    "RDB": (
        "FILE *", "NOFILE", "FILEDIR *", "NODAL", "NODAL ALL", "NODAL OTHER", "NODAL NULL",
        "NOPSEUDO", "NOPSEUDO NULL", "NOEMPTY", "NOEMPTY NULL", "OUTPUT", "OUTPUT NULL",
        "ALL CELLS", "ALL CELLS NULL", "CELL SPACE", "CELL SPACE NULL", "JOINED", "JOINED NULL",
        "RESULT CELLS *", "CHECKNAME *", "MAXIMUM *", "QUOTENAMES", "QUOTENAMES NULL",
    ),
    "LAYOUT": ("FILE *", "TOP", "PREFIX *", "PREFIX * FILLONLY", "APPEND *", "APPEND * FILLONLY"),
    "FILL": ("COMPRESS PREFIX *", "COMPRESS VERSION *", "COMPRESS LOWERCASE SUFFIX"),
    "DV": ("EXCLUDE SHIELDED RESTRICTED", "EXCLUDE SHIELDED UNRESTRICTED", "EXCLUDE SHIELDED NULL"),
}
_OPTIONS = {k: tuple(tuple(p.split()) for p in v) for k, v in PATTERNS.items()}


def matches_defaults(args, *, partial=False):
    words = [v.upper() if isinstance(v, str) and not isinstance(v, QuotedScalar) else None for v in args]
    if not words or words[0] not in {"RDB", "FILL", "DV"}:
        return False
    group = words[0]
    start = 1
    if group == "RDB" and len(words) > 1 and words[1] in {"GDS", "OASIS"}:
        group, start = "LAYOUT", 2
    if start == len(words):
        return partial
    # NODAL ALL CELLS can mean NODAL followed by ALL CELLS. Keep both parses.
    good = {len(words)}
    for i in range(len(words) - 1, start - 1, -1):
        for pattern in _OPTIONS[group]:
            end = i + len(pattern)
            if end not in good and not (partial and end > len(words)):
                continue
            if all(key == "*" or key == words[i + j] for j, key in enumerate(pattern[:len(words)-i])):
                good.add(i)
                break
    return start in good
