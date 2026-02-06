"""Token types and Token class for the SVRF lexer."""

from enum import Enum, auto


class TokenType(Enum):
    # Literals
    IDENT = auto()
    INTEGER = auto()
    FLOAT = auto()
    STRING = auto()

    # Preprocessor
    PP_DEFINE = auto()
    PP_IFDEF = auto()
    PP_IFNDEF = auto()
    PP_ELSE = auto()
    PP_ENDIF = auto()
    PP_INCLUDE = auto()
    PP_ENCRYPT = auto()
    PP_ENDCRYPT = auto()
    PP_DECRYPT = auto()

    # Operators
    EQUALS = auto()       # =
    EQEQ = auto()         # ==
    BANGEQ = auto()        # !=
    LT = auto()            # <
    GT_OP = auto()         # >
    LE = auto()            # <=
    GE = auto()            # >=
    BANG = auto()           # !
    AMPAMP = auto()        # &&
    PIPEPIPE = auto()      # ||
    PLUS = auto()          # +
    MINUS = auto()         # -
    STAR = auto()          # *
    SLASH = auto()         # /
    CARET = auto()         # ^
    PERCENT = auto()       # %
    COLONCOLON = auto()    # ::

    # Delimiters
    LPAREN = auto()        # (
    RPAREN = auto()        # )
    LBRACE = auto()        # {
    RBRACE = auto()        # }
    LBRACKET = auto()      # [
    RBRACKET = auto()      # ]
    COMMA = auto()         # ,
    AT = auto()            # @
    SEMICOLON = auto()     # ;

    # Special
    NEWLINE = auto()
    EOF = auto()
    ENCRYPTED = auto()


class Token:
    __slots__ = ('type', 'value', 'line', 'col')

    def __init__(self, type: TokenType, value, line: int, col: int):
        self.type = type
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, L{self.line}:{self.col})"
