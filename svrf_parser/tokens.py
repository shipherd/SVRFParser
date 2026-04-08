"""Token model for the reconstructed regex-based SVRF lexer."""

from enum import Enum, auto


class TokenType(Enum):
    IDENT = auto()
    NUMBER = auto()
    STRING = auto()
    SYMBOL = auto()
    PREPROCESSOR = auto()
    ENCRYPTED = auto()
    RULE_COMMENT = auto()
    NEWLINE = auto()
    EOF = auto()


class Token:
    __slots__ = (
        "type",
        "value",
        "line",
        "col",
        "end_line",
        "end_col",
        "offset",
        "end_offset",
        "raw",
    )

    def __init__(
        self,
        type,
        value,
        line,
        col,
        end_line=None,
        end_col=None,
        offset=0,
        end_offset=0,
        raw=None,
    ):
        self.type = type
        self.value = value
        self.line = line
        self.col = col
        self.end_line = line if end_line is None else end_line
        self.end_col = col if end_col is None else end_col
        self.offset = offset
        self.end_offset = end_offset
        self.raw = value if raw is None else raw

    def __repr__(self):
        return (
            f"Token({self.type.name}, {self.value!r}, "
            f"L{self.line}:{self.col}-L{self.end_line}:{self.end_col}, "
            f"raw={self.raw!r})"
        )
