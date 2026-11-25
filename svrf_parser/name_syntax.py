"""Bounded scans of SVRF names shared by statement headers and operands."""

from .tokens import TokenType as TT

NAME_PART_TYPES = (TT.IDENT, TT.STRING, TT.NUMBER)


def name_part_value(token):
    if token.type == TT.IDENT:
        return str(token.value if token.raw is None else token.raw).upper()
    if token.type == TT.STRING:
        return token.value
    if token.type == TT.NUMBER:
        return str(token.raw)
    return None


def scan_name_end(tokens, idx, limit):
    if idx >= limit or tokens[idx].type not in NAME_PART_TYPES:
        return None
    while True:
        idx += 1
        while idx < limit and tokens[idx].type == TT.NEWLINE:
            idx += 1
        if idx == limit or tokens[idx].type != TT.SYMBOL or tokens[idx].value not in {":", "::"}:
            return idx
        idx += 1
        while idx < limit and tokens[idx].type == TT.NEWLINE:
            idx += 1
        if idx == limit or tokens[idx].type not in NAME_PART_TYPES:
            return None


def name_from_span(tokens, start, end):
    if end == start + 1:
        return name_part_value(tokens[start])
    return "".join(token.value if token.type == TT.SYMBOL else name_part_value(token)
                   for token in tokens[start:end] if token.type != TT.NEWLINE)
