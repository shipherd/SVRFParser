"""Lexer for SVRF source files. Converts raw text into a token stream."""

from .tokens import TokenType, Token

TT = TokenType

_PP_MAP = {
    'DEFINE': TT.PP_DEFINE,
    'IFDEF': TT.PP_IFDEF,
    'IFNDEF': TT.PP_IFNDEF,
    'ELSE': TT.PP_ELSE,
    'ENDIF': TT.PP_ENDIF,
    'INCLUDE': TT.PP_INCLUDE,
    'ENCRYPT': TT.PP_ENCRYPT,
    'ENDCRYPT': TT.PP_ENDCRYPT,
    'DECRYPT': TT.PP_DECRYPT,
}


class Lexer:
    """Tokenizer for SVRF source text."""

    def __init__(self, text: str, filename: str = "<input>"):
        self.text = text
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.col = 1
        self.length = len(text)
        self._tokens = []
        self._tokenize()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def tokens(self):
        return self._tokens

    # ------------------------------------------------------------------
    # Core scanning helpers
    # ------------------------------------------------------------------
    def _ch(self):
        if self.pos < self.length:
            return self.text[self.pos]
        return '\0'

    def _peek(self, offset=1):
        p = self.pos + offset
        if p < self.length:
            return self.text[p]
        return '\0'

    def _advance(self):
        ch = self.text[self.pos]
        self.pos += 1
        if ch == '\n':
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _match(self, expected):
        if self.pos < self.length and self.text[self.pos] == expected:
            self._advance()
            return True
        return False

    def _emit(self, tt, value):
        self._tokens.append(Token(tt, value, self._tok_line, self._tok_col))

    def _mark(self):
        self._tok_line = self.line
        self._tok_col = self.col

    # ------------------------------------------------------------------
    # Main tokenize loop
    # ------------------------------------------------------------------
    def _tokenize(self):
        while self.pos < self.length:
            self._mark()
            ch = self._ch()

            # Newline
            if ch == '\n':
                self._advance()
                self._emit_newline()
                continue

            # Carriage return
            if ch == '\r':
                self._advance()
                if self._ch() == '\n':
                    self._advance()
                self._emit_newline()
                continue

            # Whitespace (not newline)
            if ch in (' ', '\t'):
                self._skip_whitespace()
                continue

            # Line comment //
            if ch == '/' and self._peek() == '/':
                self._skip_line_comment()
                continue

            # Block comment /* */
            if ch == '/' and self._peek() == '*':
                self._skip_block_comment()
                continue

            # Preprocessor directive #
            if ch == '#':
                self._scan_preprocessor()
                continue

            # String literals
            if ch == '"' or ch == "'":
                self._scan_string(ch)
                continue

            # Numbers
            if ch.isdigit() or (ch == '.' and self._peek().isdigit()):
                self._scan_number()
                continue

            # Identifiers
            if ch.isalpha() or ch == '_':
                self._scan_identifier()
                continue

            # Operators and delimiters
            self._scan_operator()

        self._mark()
        self._emit(TT.EOF, '')

    # ------------------------------------------------------------------
    # Newline handling
    # ------------------------------------------------------------------
    def _emit_newline(self):
        if self._tokens and self._tokens[-1].type != TT.NEWLINE:
            self._emit(TT.NEWLINE, '\n')

    # ------------------------------------------------------------------
    # Whitespace and comments
    # ------------------------------------------------------------------
    def _skip_whitespace(self):
        while self.pos < self.length and self._ch() in (' ', '\t'):
            self._advance()

    def _skip_line_comment(self):
        while self.pos < self.length and self._ch() != '\n':
            self._advance()

    def _skip_block_comment(self):
        self._advance()  # /
        self._advance()  # *
        while self.pos < self.length:
            if self._ch() == '*' and self._peek() == '/':
                self._advance()
                self._advance()
                return
            self._advance()

    # ------------------------------------------------------------------
    # Preprocessor
    # ------------------------------------------------------------------
    def _scan_preprocessor(self):
        self._advance()  # skip #
        # Read directive name
        start = self.pos
        while self.pos < self.length and self._ch().isalpha():
            self._advance()
        name = self.text[start:self.pos].upper()

        tt = _PP_MAP.get(name)
        if tt is None:
            # Unknown preprocessor directive, treat as identifier
            self._emit(TT.IDENT, '#' + self.text[start:self.pos])
            return

        if tt == TT.PP_ENCRYPT:
            self._emit(TT.PP_ENCRYPT, '#ENCRYPT')
            self._scan_encrypted_block()
            return

        if tt == TT.PP_DECRYPT:
            self._emit(TT.PP_DECRYPT, '#DECRYPT')
            self._scan_encrypted_block()
            return

        if tt == TT.PP_ENDCRYPT:
            self._emit(TT.PP_ENDCRYPT, '#ENDCRYPT')
            return

        self._emit(tt, '#' + name)

    def _scan_encrypted_block(self):
        """Capture everything until #ENDCRYPT or end of file as encrypted content."""
        # Skip rest of current line
        while self.pos < self.length and self._ch() != '\n':
            self._advance()
        if self.pos < self.length:
            self._advance()  # skip newline

        start = self.pos
        while self.pos < self.length:
            if self._ch() == '#':
                # Check for #ENDCRYPT
                rest = self.text[self.pos:self.pos + 10].upper()
                if rest.startswith('#ENDCRYPT') or rest.startswith('#END'):
                    break
            self._advance()

        content = self.text[start:self.pos]
        if content.strip():
            self._mark()
            self._emit(TT.ENCRYPTED, content)

        # Scan #ENDCRYPT if present
        if self.pos < self.length and self._ch() == '#':
            self._mark()
            self._advance()  # #
            s = self.pos
            while self.pos < self.length and self._ch().isalpha():
                self._advance()
            self._emit(TT.PP_ENDCRYPT, '#ENDCRYPT')

    # ------------------------------------------------------------------
    # String literals
    # ------------------------------------------------------------------
    def _scan_string(self, quote):
        self._advance()  # opening quote
        parts = []
        while self.pos < self.length:
            ch = self._ch()
            if ch == quote:
                self._advance()
                self._emit(TT.STRING, ''.join(parts))
                return
            if ch == '\\':
                self._advance()
                parts.append(self._advance() if self.pos < self.length else '\\')
            elif ch == '\n':
                # Unterminated string at newline - emit what we have
                break
            else:
                parts.append(self._advance())
        self._emit(TT.STRING, ''.join(parts))

    # ------------------------------------------------------------------
    # Number literals
    # ------------------------------------------------------------------
    def _scan_number(self):
        start = self.pos
        has_dot = False
        has_exp = False

        while self.pos < self.length:
            ch = self._ch()
            if ch.isdigit():
                self._advance()
            elif ch == '.' and not has_dot and not has_exp:
                has_dot = True
                self._advance()
            elif ch in ('e', 'E') and not has_exp:
                has_exp = True
                has_dot = True  # treat as float
                self._advance()
                if self.pos < self.length and self._ch() in ('+', '-'):
                    self._advance()
            else:
                break

        text = self.text[start:self.pos]
        if has_dot or has_exp:
            self._emit(TT.FLOAT, float(text))
        else:
            self._emit(TT.INTEGER, int(text))

    # ------------------------------------------------------------------
    # Identifiers
    # ------------------------------------------------------------------
    def _scan_identifier(self):
        start = self.pos
        while self.pos < self.length:
            ch = self._ch()
            if ch.isalnum() or ch == '_':
                self._advance()
            elif ch == ':' and self._peek().isalnum():
                # Colon-identifiers like DRC:1
                self._advance()
            elif ch == '?' and self.pos > start:
                # Wildcard suffix like AA_?
                self._advance()
                break
            elif ch == '.' and self._peek().isalnum():
                # Dotted identifiers
                self._advance()
            else:
                break
        text = self.text[start:self.pos]
        self._emit(TT.IDENT, text)

    # ------------------------------------------------------------------
    # Operators and delimiters
    # ------------------------------------------------------------------
    def _scan_operator(self):
        ch = self._advance()

        if ch == '=':
            if self._match('='):
                self._emit(TT.EQEQ, '==')
            else:
                self._emit(TT.EQUALS, '=')
        elif ch == '!':
            if self._match('='):
                self._emit(TT.BANGEQ, '!=')
            else:
                self._emit(TT.BANG, '!')
        elif ch == '<':
            if self._match('='):
                self._emit(TT.LE, '<=')
            else:
                self._emit(TT.LT, '<')
        elif ch == '>':
            if self._match('='):
                self._emit(TT.GE, '>=')
            else:
                self._emit(TT.GT_OP, '>')
        elif ch == '&':
            if self._match('&'):
                self._emit(TT.AMPAMP, '&&')
            else:
                self._emit(TT.IDENT, '&')
        elif ch == '|':
            if self._match('|'):
                self._emit(TT.PIPEPIPE, '||')
            else:
                self._emit(TT.IDENT, '|')
        elif ch == '+':
            self._emit(TT.PLUS, '+')
        elif ch == '-':
            self._emit(TT.MINUS, '-')
        elif ch == '*':
            self._emit(TT.STAR, '*')
        elif ch == '/':
            self._emit(TT.SLASH, '/')
        elif ch == '^':
            self._emit(TT.CARET, '^')
        elif ch == '%':
            self._emit(TT.PERCENT, '%')
        elif ch == '(':
            self._emit(TT.LPAREN, '(')
        elif ch == ')':
            self._emit(TT.RPAREN, ')')
        elif ch == '{':
            self._emit(TT.LBRACE, '{')
        elif ch == '}':
            self._emit(TT.RBRACE, '}')
        elif ch == '[':
            self._emit(TT.LBRACKET, '[')
        elif ch == ']':
            self._emit(TT.RBRACKET, ']')
        elif ch == ',':
            self._emit(TT.COMMA, ',')
        elif ch == '@':
            self._emit(TT.AT, '@')
        elif ch == ';':
            self._emit(TT.SEMICOLON, ';')
        elif ch == ':':
            if self._match(':'):
                self._emit(TT.COLONCOLON, '::')
            else:
                self._emit(TT.IDENT, ':')
        elif ch == '$':
            # Environment variable reference $VAR
            start = self.pos
            while self.pos < self.length and (self._ch().isalnum() or self._ch() == '_'):
                self._advance()
            self._emit(TT.IDENT, '$' + self.text[start:self.pos])
        elif ch == '~':
            self._emit(TT.IDENT, '~')
        else:
            # Skip unknown characters
            pass
