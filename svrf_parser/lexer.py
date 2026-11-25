"""Regex-based lexer for SVRF source files."""

from __future__ import annotations

import re

from .exceptions import LexerError
from .keywords import _KEYWORD_ALIASES
from .tokens import Token, TokenType
from .tvf import is_tvf_script

TT = TokenType

_TOKEN_RE = re.compile(
    r"""
    (?P<WHITESPACE>[ \t\f]+)
  | (?P<NEWLINE>\r\n|\r|\n)
  | (?P<LINECOMMENT>//[^\r\n]*)
  | (?P<BLOCKCOMMENT>/\*.*?\*/)
  | (?P<PREPROCESSOR>\#[A-Za-z_][A-Za-z0-9_]*)
  | (?P<OPERATOR>==|!=|<=|>=|\|\||&&|::)
  | (?P<NUMBER>(?!\d+(?:[A-DF-Za-df-z_]|[Ee](?![+\-]?\d)))(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+\-]?\d+)?)(?![A-Za-z_.])
  | (?P<SYMBOL>[{}\[\](),=<>+\-*/^%?:$~@!;.])
  | (?P<IDENT>(?:[A-Za-z_][A-Za-z0-9_.]*|\d+[A-Za-z_][A-Za-z0-9_.]*)\??)
  | (?P<MISMATCH>.)
    """,
    re.VERBOSE | re.DOTALL,
)

_ESCAPE_MAP = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "\\": "\\",
    '"': '"',
    "'": "'",
}

_REST_OF_LINE = re.compile(r"[^\r\n]*")
_ENDCRYPT = re.compile(r"#ENDCRYPT(?![A-Z0-9_])", re.IGNORECASE | re.ASCII)
_TVF_HEADER = re.compile(r"""TVF\s+FUNCTION\s+(?:(?:EDGE|ERROR)\s+)?(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s\[\]{}]+)\s*(\[)\s*/\*""", re.I | re.ASCII)


def tvf_body_span(text, start, end):
    header = _TVF_HEADER.match(text, start, end)
    if header is None:
        return None
    close = text.find("*/", header.end(), end)
    if close >= 0:
        close += 2
        while close < end and text[close].isspace():
            close += 1
        if close < end and text[close] == "]":
            return header.start(1), close + 1
    return header.start(1), None


_STRING_SPECIAL = {'"': re.compile(r'["\\\r\n]'), "'": re.compile(r"['\\\r\n]")}


def encrypted_payload_end(text, start):
    """Return the start of the closing directive's indentation, or EOF."""
    for marker in _ENDCRYPT.finditer(text, start):
        pos = marker.start()
        while pos > start and text[pos - 1] in " \t":
            pos -= 1
        if pos == start or text[pos - 1] in "\r\n":
            return pos
    return len(text)


class Lexer:
    """Tokenizer for SVRF source text."""

    def __init__(self, text, filename="<input>", *, recover_invalid=False, _svrf_only=False):
        self.text = text or ""
        self.filename = filename
        self._recover_invalid = recover_invalid
        self.length = len(self.text)
        self.pos = 0
        self.line = 1
        self.col = 1
        self._tokens = []
        if not _svrf_only and is_tvf_script(self.text):
            self._advance(self.text)
            self._append_token(TT.TVF_SCRIPT, self.text, 1, 1, 0)
            self._append_token(TT.EOF, "", self.line, self.col, self.pos)
        else:
            self._tokenize()

    def tokens(self):
        return self._tokens

    def _tokenize(self):
        tvf = None
        while self.pos < self.length:
            ch = self.text[self.pos]
            if tvf and self.pos == tvf[0]:
                offset, end = tvf
                if end is None:
                    raise LexerError("Unterminated TVF function block", self.line, self.col)
                line, col = self.line, self.col
                raw = self.text[offset:end]
                self._advance(raw)
                self._append_token(TT.TVF_BODY, raw, line, col, offset, raw=raw)
                tvf = None
                continue
            if ch in ('"', "'"):
                self._scan_string(ch)
                continue

            match = _TOKEN_RE.match(self.text, self.pos)
            if match is None:
                raise LexerError("Unable to match token", self.line, self.col)

            kind = match.lastgroup
            lexeme = match.group(0)
            line = self.line
            col = self.col
            start_offset = self.pos

            if kind == "BLOCKCOMMENT":
                self._advance(lexeme)
                continue

            self.pos = match.end()
            if kind == "NEWLINE":
                self.line += 1
                self.col = 1
                self._append_token(
                    TT.NEWLINE,
                    "\n",
                    line,
                    col,
                    start_offset,
                    raw=lexeme,
                )
                continue

            self.col += self.pos - start_offset
            if kind in ("WHITESPACE", "LINECOMMENT"):
                continue

            if kind == "PREPROCESSOR":
                value = lexeme.upper()
                self._append_token(
                    TT.PREPROCESSOR,
                    value,
                    line,
                    col,
                    start_offset,
                    raw=lexeme,
                )
                if value in {"#ENCRYPT", "#DECRYPT"}:
                    self._scan_encrypted_payload()
                continue

            if kind == "OPERATOR":
                self._append_token(TT.SYMBOL, lexeme, line, col, start_offset)
                continue

            if kind == "SYMBOL":
                if lexeme == "@":
                    self._scan_rule_comment(line, col, start_offset)
                else:
                    self._append_token(TT.SYMBOL, lexeme, line, col, start_offset)
                continue

            if kind == "NUMBER":
                value = float(lexeme) if ("." in lexeme or "e" in lexeme.lower()) else int(lexeme)
                self._append_token(
                    TT.NUMBER,
                    value,
                    line,
                    col,
                    start_offset,
                    raw=lexeme,
                )
                continue

            if kind == "IDENT":
                value = lexeme.upper()
                if value == "TVF":
                    tvf = tvf_body_span(self.text, start_offset, self.length)
                value = _KEYWORD_ALIASES.get(value, value)
                self._append_token(
                    TT.IDENT,
                    value,
                    line,
                    col,
                    start_offset,
                    raw=lexeme,
                )
                continue

            if self._recover_invalid:
                self._append_token(TT.INVALID, lexeme, line, col, start_offset)
                continue
            raise LexerError(
                f"Unexpected character {lexeme!r}",
                line,
                col,
            )

        self._tokens.append(
            Token(
                TT.EOF,
                "",
                self.line,
                self.col,
                self.line,
                self.col,
                self.pos,
                self.pos,
                raw="",
            )
        )

    def _append_token(self, type_, value, line, col, start_offset, raw=None):
        self._tokens.append(
            Token(
                type_,
                value,
                line,
                col,
                self.line,
                self.col,
                start_offset,
                self.pos,
                raw=raw,
            )
        )

    def _advance(self, lexeme):
        length = len(lexeme)
        self.pos += length
        last_break = max(lexeme.rfind("\r"), lexeme.rfind("\n"))
        if last_break < 0:
            self.col += length
            return
        self.line += lexeme.count("\n")
        if "\r" in lexeme:
            self.line += lexeme.count("\r") - lexeme.count("\r\n")
        self.col = length - last_break

    def _scan_string(self, quote):
        line = self.line
        col = self.col
        start_offset = self.pos
        cursor = start_offset + 1
        parts = []
        special = _STRING_SPECIAL[quote]
        while match := special.search(self.text, cursor):
            end = match.start()
            parts.append(self.text[cursor:end])
            ch = match[0]
            if ch == quote:
                end += 1
                break
            if ch != "\\":
                break
            if end + 1 == self.length:
                parts.append("\\")
                end += 1
                break
            escaped = self.text[end + 1]
            cursor = end + 2
            if escaped in "\r\n":
                parts.append("\n")
                if escaped == "\r" and self.text.startswith("\n", cursor):
                    cursor += 1
            else:
                parts.append(_ESCAPE_MAP.get(escaped, escaped))
        else:
            parts.append(self.text[cursor:])
            end = self.length
        raw = self.text[start_offset:end]
        self._advance(raw)
        self._append_token(TT.STRING, "".join(parts), line, col, start_offset, raw=raw)

    def _scan_rule_comment(self, line, col, start_offset):
        match = _REST_OF_LINE.match(self.text, self.pos)
        text = match.group().lstrip(" \t").rstrip()
        self.col += match.end() - self.pos
        self.pos = match.end()
        self._tokens.append(
            Token(
                TT.RULE_COMMENT,
                text,
                line,
                col,
                self.line,
                self.col,
                start_offset,
                self.pos,
                raw=text,
            )
        )

    def _scan_encrypted_payload(self):
        end = encrypted_payload_end(self.text, self.pos)
        if self.pos == end:
            return
        if self.text.startswith("\r\n", self.pos):
            self._advance("\r\n")
        elif self.text[self.pos] in "\r\n":
            self._advance(self.text[self.pos])

        # Only the newline adjoining each directive belongs to the wrapper.
        body_end = end
        if end < self.length:
            if self.text.endswith("\r\n", self.pos, end):
                body_end -= 2
            elif self.text.endswith(("\r", "\n"), self.pos, end):
                body_end -= 1
        payload = self.text[self.pos:body_end]
        start_line = self.line
        start_col = self.col
        start_offset = self.pos
        if payload:
            self._advance(payload)
            self._append_token(
                TT.ENCRYPTED, payload, start_line, start_col, start_offset, raw=payload,
            )
        if body_end < end:
            self._advance(self.text[body_end:end])
