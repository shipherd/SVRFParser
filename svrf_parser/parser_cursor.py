"""Cursor, diagnostic, and source-span helpers for the live parser."""

from __future__ import annotations

from . import ast
from .diagnostics import Diagnostic, SEVERITY_WARNING
from .exceptions import ParseError
from .tokens import TokenType

TT = TokenType


class ParserCursorMixin:
    """Parser session helpers that do not own grammar dispatch."""

    def _cur(self):
        if self.pos < self.length:
            return self.tokens[self.pos]
        return self.tokens[-1]

    def _peek(self, offset=1):
        idx = self.pos + offset
        if idx < self.length:
            return self.tokens[idx]
        return self.tokens[-1]

    def _peek_non_newline(self, offset=1):
        idx = self.pos + offset
        while idx < self.length and self.tokens[idx].type == TT.NEWLINE:
            idx += 1
        if idx < self.length:
            return self.tokens[idx]
        return self.tokens[-1]

    def _peek_after_newlines(self):
        idx = self.pos
        while idx < self.length and self.tokens[idx].type == TT.NEWLINE:
            idx += 1
        if idx < self.length:
            return self.tokens[idx]
        return self.tokens[-1]

    def _next_non_newline_index(self, idx=None):
        idx = self.pos if idx is None else idx
        while idx < self.length and self.tokens[idx].type == TT.NEWLINE:
            idx += 1
        return idx

    def _advance(self):
        token = self._cur()
        if self.pos < self.length:
            self.pos += 1
        return token

    def _skip_newlines(self):
        while self._cur().type == TT.NEWLINE:
            self._advance()

    def _at(self, type_, value=None):
        token = self._cur()
        if token.type != type_:
            return False
        return value is None or token.value == value

    def _at_ident(self, value):
        return self._cur().type == TT.IDENT and self._cur().value == value

    def _at_symbol(self, value):
        return self._cur().type == TT.SYMBOL and self._cur().value == value

    def _match(self, type_, value=None):
        if self._at(type_, value):
            return self._advance()
        return None

    def _match_ident(self, value):
        if self._at_ident(value):
            return self._advance()
        return None

    def _expect(self, type_, value=None, message=None):
        token = self._cur()
        if self._at(type_, value):
            return self._advance()
        expected = value if value is not None else type_.name
        raise ParseError(message or f"Expected {expected}", token.line, token.col, token)

    def _loc(self, token=None):
        token = self._cur() if token is None else token
        return {
            "line": token.line,
            "col": token.col,
            "end_line": token.end_line,
            "end_col": token.end_col,
            "start_offset": token.offset,
            "end_offset": token.end_offset,
            "source_text": self._slice(token.offset, token.end_offset),
            "filename": self.filename,
        }

    def _slice(self, start_offset, end_offset):
        if not self.source_text:
            return None
        start_offset = max(0, start_offset)
        end_offset = max(start_offset, end_offset)
        return self.source_text[start_offset:end_offset]

    def _diagnostic(
        self,
        code,
        message,
        token=None,
        line=None,
        col=None,
        end_line=None,
        end_col=None,
        start_offset=None,
        end_offset=None,
    ):
        token = self._cur() if token is None else token
        line = token.line if line is None else line
        col = token.col if col is None else col
        end_line = token.end_line if end_line is None else end_line
        end_col = token.end_col if end_col is None else end_col
        start_offset = token.offset if start_offset is None else start_offset
        end_offset = token.end_offset if end_offset is None else end_offset
        return Diagnostic(
            severity=SEVERITY_WARNING,
            code=code,
            message=message,
            filename=self.filename,
            line=line,
            col=col,
            end_line=end_line,
            end_col=end_col,
            start_offset=start_offset,
            end_offset=end_offset,
            snippet=self._slice(start_offset, end_offset),
        )

    def _warn(self, code, message, token=None, **kw):
        diagnostic = self._diagnostic(code, message, token=token, **kw)
        if self.strict:
            raise ParseError(
                message,
                diagnostic.line,
                diagnostic.col,
                token if token is not None else self._cur(),
            )
        self.warnings.append(diagnostic)
        return diagnostic

    def _find_span_start_token(self, start_idx):
        idx = min(max(0, start_idx), self.length - 1)
        while idx < self.length and self.tokens[idx].type == TT.NEWLINE:
            idx += 1
        if idx >= self.length:
            return None
        token = self.tokens[idx]
        if token.type == TT.EOF:
            return None
        return token

    def _find_span_end_token(self, end_idx):
        idx = min(max(0, end_idx), self.length)
        idx -= 1
        while idx >= 0 and self.tokens[idx].type == TT.NEWLINE:
            idx -= 1
        if idx < 0:
            return None
        token = self.tokens[idx]
        if token.type == TT.EOF:
            return None
        return token

    def _finish_node(self, node, start_idx, end_idx=None):
        if node is None or not isinstance(node, ast.AstNode):
            return node
        node.filename = self.filename
        if end_idx is None:
            end_idx = self.pos
        start_token = self._find_span_start_token(start_idx)
        end_token = self._find_span_end_token(end_idx)
        if start_token is None:
            return node
        if end_token is None or end_token.end_offset < start_token.offset:
            end_token = start_token
        node.set_span(
            start_token.line,
            start_token.col,
            end_token.end_line,
            end_token.end_col,
            start_token.offset,
            end_token.end_offset,
            self._slice(start_token.offset, end_token.end_offset),
        )
        return node
