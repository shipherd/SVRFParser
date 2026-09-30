"""Parse PERC procedure selections without interpreting the referenced Tcl."""

from __future__ import annotations

from . import ast
from .tokens import TokenType

TT = TokenType
_CLAUSE_WORDS = frozenset({"INIT", "PATTERN", "XFORM", "SELECT", "SELECTTYPE", "PARALLEL"})


class PercParserMixin:
    def _perc_name_starts_at(self, index):
        token = self.tokens[index]
        if token.type == TT.SYMBOL:
            return token.value == "("
        if token.type not in {TT.IDENT, TT.STRING, TT.NUMBER}:
            return False
        if token.type == TT.IDENT and token.value in _CLAUSE_WORDS:
            return True
        return not (
            self._starts_line_statement_at(index)
            or self._segmenter.starts_operation_at(index)
            or self._segmenter.starts_assignment_at(index)
            or self._segmenter.starts_rule_check_at(index, "top")
        )

    def _perc_conditional_is_continuation(self, index):
        depth = 0
        while index < len(self.tokens):
            index = self._next_non_newline_index(index)
            token = self.tokens[index]
            if token.type == TT.PREPROCESSOR:
                if token.value in {"#IFDEF", "#IFNDEF"}:
                    depth += 1
                elif token.value == "#ENDIF":
                    depth -= 1
                    if depth == 0:
                        return True
                elif token.value != "#ELSE":
                    return False
                index += 1
                while self.tokens[index].type not in {TT.NEWLINE, TT.EOF}:
                    index += 1
                continue
            if token.type == TT.SYMBOL and token.value in {"(", ")"}:
                index += 1
                continue
            if not self._perc_name_starts_at(index):
                return False
            index += 1
            while self.tokens[index].type == TT.SYMBOL and self.tokens[index].value == "::":
                index += 1
                if self.tokens[index].type not in {TT.IDENT, TT.STRING, TT.NUMBER}:
                    return False
                index += 1
        return False

    def _starts_perc_load_item(self, index):
        token = self.tokens[index]
        if token.type == TT.PREPROCESSOR:
            return token.value in {"#IFDEF", "#IFNDEF"} and self._perc_conditional_is_continuation(index)
        return self._perc_name_starts_at(index)

    def _parse_perc_name(self):
        start = self.pos
        token = self._expect_name_token()
        value = token.value if token.type == TT.STRING else str(token.raw)
        while self._at_symbol("::"):
            value += self._advance().value
            part = self._expect_name_token()
            value += part.value if part.type == TT.STRING else str(part.raw)
        return self._finish_node(ast.StringLiteral(value=value, **self._loc(token)), start)

    def _expect_name_token(self):
        token = self._cur()
        if token.type in {TT.IDENT, TT.STRING, TT.NUMBER}:
            return self._advance()
        return self._expect(TT.IDENT, message="Expected a PERC procedure name")

    def _parse_perc_load_item(self):
        token = self._cur()
        if token.type == TT.PREPROCESSOR:
            return self._parse_preprocessor("perc_load")
        if self._match(TT.SYMBOL, "("):
            items = []
            self._skip_newlines()
            while not self._at_symbol(")"):
                items.append(self._parse_perc_name())
                self._skip_newlines()
            self._expect(TT.SYMBOL, ")")
            return ast.PercGroup(items=items, **self._loc(token))
        if token.type == TT.IDENT and token.value in _CLAUSE_WORDS:
            keyword = self._advance().value
            keywords = [keyword]
            arguments = []
            if keyword in {"INIT", "PATTERN", "XFORM"}:
                arguments.append(self._parse_perc_name())
            elif keyword == "SELECTTYPE":
                keywords.append(self._expect(TT.IDENT).value)
            return ast.Directive(keywords=keywords, arguments=arguments, **self._loc(token))
        return self._parse_perc_name()

    def _parse_perc_load(self):
        start = self._expect(TT.IDENT, "PERC")
        self._expect(TT.IDENT, "LOAD")
        function = self._parse_name()
        body = self._parse_sequence("perc_load", stop_preprocessors={"#ELSE", "#ENDIF"})
        return ast.PercLoad(function=function, body=body, **self._loc(start))
