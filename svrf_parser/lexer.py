"""Regex-based lexer for SVRF source files."""

from __future__ import annotations

import re

from .exceptions import LexerError
from .keywords import _KEYWORD_ALIASES
from .tokens import Token, TokenType

TT = TokenType

_TOKEN_RE = re.compile(
    r"""
    (?P<WHITESPACE>[ \t\f]+)
  | (?P<NEWLINE>\r\n|\r|\n)
  | (?P<LINECOMMENT>//[^\r\n]*)
  | (?P<BLOCKCOMMENT>/\*.*?\*/)
  | (?P<PREPROCESSOR>\#[A-Za-z_][A-Za-z0-9_]*)
  | (?P<OPERATOR>==|!=|<=|>=|\|\||&&|::)
  | (?P<SYMBOL>[{}\[\](),=<>+\-*/^%?:$~@!;.])
  | (?P<NUMBER>(?!\d+(?:[A-DF-Za-df-z_]|[Ee](?![+\-]?\d)))(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+\-]?\d+)?)(?![A-Za-z_.])
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


class Lexer:
    """Tokenizer for SVRF source text."""

    def __init__(self, text, filename="<input>"):
        self.text = text or ""
        self.filename = filename
        self.length = len(self.text)
        self.pos = 0
        self.line = 1
        self.col = 1
        self._tokens = []
        self._tokenize()

    def tokens(self):
        return self._tokens

    def _tokenize(self):
        while self.pos < self.length:
            ch = self.text[self.pos]
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

            if kind == "WHITESPACE":
                self._advance(lexeme)
                continue

            if kind == "NEWLINE":
                self._advance(lexeme)
                self._append_token(
                    TT.NEWLINE,
                    "\n",
                    line,
                    col,
                    start_offset,
                    raw=lexeme,
                )
                continue

            if kind in ("LINECOMMENT", "BLOCKCOMMENT"):
                self._advance(lexeme)
                continue

            if kind == "PREPROCESSOR":
                value = lexeme.upper()
                self._advance(lexeme)
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
                self._advance(lexeme)
                self._append_token(TT.SYMBOL, lexeme, line, col, start_offset)
                continue

            if kind == "SYMBOL":
                self._advance(lexeme)
                if lexeme == "@":
                    self._scan_rule_comment(line, col, start_offset)
                else:
                    self._append_token(TT.SYMBOL, lexeme, line, col, start_offset)
                continue

            if kind == "NUMBER":
                self._advance(lexeme)
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
                self._advance(lexeme)
                value = lexeme.upper()
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

            raise LexerError(
                f"Unexpected character {lexeme!r}",
                self.line,
                self.col,
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
        i = 0
        while i < len(lexeme):
            ch = lexeme[i]
            self.pos += 1
            if ch == "\r":
                if i + 1 < len(lexeme) and lexeme[i + 1] == "\n":
                    self.pos += 1
                    i += 1
                self.line += 1
                self.col = 1
            elif ch == "\n":
                self.line += 1
                self.col = 1
            else:
                self.col += 1
            i += 1

    def _scan_string(self, quote):
        line = self.line
        col = self.col
        start_offset = self.pos
        self.pos += 1
        self.col += 1
        chars = []

        while self.pos < self.length:
            ch = self.text[self.pos]
            if ch == quote:
                self.pos += 1
                self.col += 1
                raw = quote + "".join(chars) + quote
                self._tokens.append(
                    Token(
                        TT.STRING,
                        self._unescape_string(chars),
                        line,
                        col,
                        self.line,
                        self.col,
                        start_offset,
                        self.pos,
                        raw=raw,
                    )
                )
                return
            if ch in "\r\n":
                raw = quote + "".join(chars)
                self._tokens.append(
                    Token(
                        TT.STRING,
                        self._unescape_string(chars),
                        line,
                        col,
                        self.line,
                        self.col,
                        start_offset,
                        self.pos,
                        raw=raw,
                    )
                )
                return
            if ch == "\\" and self.pos + 1 < self.length:
                chars.append(ch)
                self.pos += 1
                self.col += 1
                ch = self.text[self.pos]
            chars.append(ch)
            self.pos += 1
            self.col += 1

        raw = quote + "".join(chars)
        self._tokens.append(
            Token(
                TT.STRING,
                self._unescape_string(chars),
                line,
                col,
                self.line,
                self.col,
                start_offset,
                self.pos,
                raw=raw,
            )
        )

    def _unescape_string(self, chars):
        value = []
        i = 0
        while i < len(chars):
            ch = chars[i]
            if ch == "\\" and i + 1 < len(chars):
                nxt = chars[i + 1]
                value.append(_ESCAPE_MAP.get(nxt, nxt))
                i += 2
                continue
            value.append(ch)
            i += 1
        return "".join(value)

    def _scan_rule_comment(self, line, col, start_offset):
        while self.pos < self.length and self.text[self.pos] in (" ", "\t"):
            self.pos += 1
            self.col += 1
        start = self.pos
        while self.pos < self.length and self.text[self.pos] not in "\r\n":
            self.pos += 1
            self.col += 1
        text = self.text[start:self.pos].rstrip()
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
        chunks = []
        start_line = self.line
        start_col = self.col
        start_offset = self.pos

        while self.pos < self.length:
            if not chunks and self.text[self.pos] in "\r\n":
                line = self.text[self.pos]
                if line == "\r" and self.pos + 1 < self.length and self.text[self.pos + 1] == "\n":
                    line = "\r\n"
                self._advance(line)
                start_line = self.line
                start_col = self.col
                start_offset = self.pos
                continue

            line_start = self.pos
            line_line = self.line
            line_col = self.col
            while self.pos < self.length and self.text[self.pos] not in "\r\n":
                self.pos += 1
                self.col += 1
            line_text = self.text[line_start:self.pos]

            if line_text.lstrip(" \t").upper().startswith("#ENDCRYPT"):
                self.pos = line_start
                self.line = line_line
                self.col = line_col
                break

            chunks.append(line_text)

            if self.pos < self.length and self.text[self.pos] in "\r\n":
                newline = self.text[self.pos]
                if newline == "\r" and self.pos + 1 < self.length and self.text[self.pos + 1] == "\n":
                    newline = "\r\n"
                self._advance(newline)
                chunks.append("\n")

        payload = "".join(chunks).rstrip("\n")
        if payload:
            self._tokens.append(
                Token(
                    TT.ENCRYPTED,
                    payload,
                    start_line,
                    start_col,
                    self.line,
                    self.col,
                    start_offset,
                    self.pos,
                    raw=payload,
                )
            )
