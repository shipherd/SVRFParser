"""Base class for the SVRF parser: error type, keyword sets, token stream helpers."""

from .tokens import TokenType, Token
from . import ast_nodes as ast
from .keywords import (
    _DIRECTIVE_HEADS, _BINARY_OPS, _LAYER_BP, _UNARY_OPS,
    _DRC_OPS, _DRC_MODIFIERS, _EXPR_STARTERS, _SVRF_KEYWORDS,
)

TT = TokenType


class SVRFParseError(Exception):
    """Parse error with source location."""
    def __init__(self, msg, line=0, col=0):
        self.line = line
        self.col = col
        super().__init__(f"L{line}:{col}: {msg}")


class ParserBase:
    """Token stream management and shared utilities for the SVRF parser."""

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.length = len(tokens)
        self.warnings = []
        self._block_depth = 0
        self._known_layers = self._prescan()

    # ------------------------------------------------------------------
    # Prescan: collect known layer/variable names (Pass 1)
    # ------------------------------------------------------------------
    def _prescan(self):
        """Lightweight scan of token stream to build symbol table.

        Recognizes:
          LAYER <name> <number>      -> layer definition
          <name> = ...               -> layer assignment
          VARIABLE <name> ...        -> variable definition
          #DEFINE <name> ...         -> macro definition
          DMACRO <name> ...          -> macro name
          Definitions inside #IFDEF/#IFNDEF blocks (both branches)
        """
        known = set()
        i = 0
        toks = self.tokens
        length = self.length
        while i < length:
            t = toks[i]
            if t.type == TT.IDENT:
                upper = t.value.upper()
                # LAYER <name> <number>
                if upper == 'LAYER' and i + 2 < length:
                    nxt = toks[i + 1]
                    nxt2 = toks[i + 2]
                    if nxt.type == TT.IDENT and nxt2.type in (TT.INTEGER, TT.FLOAT):
                        known.add(nxt.value.upper())
                # <name> = ...  (layer assignment)
                elif i + 1 < length and toks[i + 1].type == TT.EQUALS:
                    known.add(upper)
                # VARIABLE <name>
                elif upper == 'VARIABLE' and i + 1 < length:
                    nxt = toks[i + 1]
                    if nxt.type == TT.IDENT:
                        known.add(nxt.value.upper())
                # DMACRO <name>
                elif upper == 'DMACRO' and i + 1 < length:
                    nxt = toks[i + 1]
                    if nxt.type == TT.IDENT:
                        known.add(nxt.value.upper())
            elif t.type == TT.PP_DEFINE and i + 1 < length:
                nxt = toks[i + 1]
                if nxt.type == TT.IDENT:
                    known.add(nxt.value.upper())
            # #IFDEF/#IFNDEF — continue scanning (both branches are collected
            # automatically since prescan is a flat linear scan that ignores
            # preprocessor nesting).
            i += 1
        return known

    def _register_symbol(self, name):
        """Incrementally register a newly discovered symbol during parsing."""
        self._known_layers.add(name.upper())

    # ------------------------------------------------------------------
    # Token stream helpers
    # ------------------------------------------------------------------
    def _cur(self):
        if self.pos < self.length:
            return self.tokens[self.pos]
        return Token(TT.EOF, '', 0, 0)

    def _peek(self, offset=1):
        p = self.pos + offset
        if p < self.length:
            return self.tokens[p]
        return Token(TT.EOF, '', 0, 0)

    def _peek_skip_newlines(self, offset=1):
        """Peek at the next non-NEWLINE token without advancing."""
        p = self.pos + offset
        while p < self.length and self.tokens[p].type == TT.NEWLINE:
            p += 1
        if p < self.length:
            return self.tokens[p]
        return Token(TT.EOF, '', 0, 0)

    def _advance(self):
        tok = self._cur()
        if self.pos < self.length:
            self.pos += 1
        return tok

    def _at(self, tt):
        return self._cur().type == tt

    def _at_val(self, val):
        t = self._cur()
        return t.type == TT.IDENT and t.value.upper() == val.upper()

    def _match(self, tt):
        if self._cur().type == tt:
            return self._advance()
        return None

    def _match_val(self, val):
        t = self._cur()
        if t.type == TT.IDENT and t.value.upper() == val.upper():
            return self._advance()
        return None

    def _expect(self, tt):
        tok = self._match(tt)
        if tok is None:
            c = self._cur()
            raise SVRFParseError(
                f"Expected {tt.name}, got {c.type.name}({c.value!r})",
                c.line, c.col)
        return tok

    def _skip_newlines(self):
        while self._at(TT.NEWLINE):
            self._advance()

    def _at_eol(self):
        return self._at(TT.NEWLINE) or self._at(TT.EOF)

    def _skip_to_eol(self):
        while not self._at_eol():
            self._advance()

    def _consume_eol(self):
        if self._at(TT.NEWLINE):
            self._advance()

    def _loc(self):
        t = self._cur()
        return {'line': t.line, 'col': t.col}
