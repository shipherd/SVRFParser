"""Statement parsing handlers for the live parser path."""

from __future__ import annotations

from . import ast
from .command_dictionary import STMT_STARTS, match_tokens
from .keywords import _DIRECTIVE_HEADS
from .exceptions import ParseError
from .dfm_spec_parser import DfmSpecParserMixin, _DFM_MODES
from .dfm_defaults import matches_defaults
from .perc_parser import PercParserMixin
from .ratio_clauses import RatioClauseParserMixin
from .statement_schema import STATEMENT_SCHEMA_REGISTRY
from .statement_shape_handlers import StatementShapeParserMixin
from .tokens import TokenType

TT = TokenType
NO_UNIT_DISPATCH = object()


class StatementParserMixin(StatementShapeParserMixin, DfmSpecParserMixin, PercParserMixin, RatioClauseParserMixin):
    """Statement CST dispatch and concrete statement-family handlers."""

    def _consume_head_from_statement_cst(self, expected_prefix=None):
        statement_cst = self._statement_cst_at_current()
        if statement_cst is None or statement_cst.head is None:
            return None, None
        if expected_prefix is not None and not statement_cst.head.matches_prefix(*expected_prefix):
            return None, None
        start = self._cur()
        if expected_prefix is not None:
            words = list(expected_prefix)
            next_idx = self.pos
            for offset, word in enumerate(expected_prefix):
                token = self.tokens[next_idx]
                if token.value != word:
                    return None, None
                next_idx += 1
                if offset + 1 < len(expected_prefix):
                    next_idx = self._next_non_newline_index(next_idx)
            self.pos = next_idx
            return start, words
        words = list(statement_cst.head.words)
        self.pos = statement_cst.body_start
        return start, words

    def _lookahead_statement_cst(self, mode):
        statement_cst = self._statement_cst_at_current(mode)
        if statement_cst is not None:
            return statement_cst
        token = self._cur()
        if token.type in (TT.EOF, TT.NEWLINE):
            return None
        if token.type == TT.SYMBOL and token.value in {"}", "]", ")"}:
            return None
        return self._segmenter.statement_cst(self.pos, mode)

    def _dispatch_statement_schema(self, mode, statement_cst=None):
        statement_cst = self._lookahead_statement_cst(mode) if statement_cst is None else statement_cst
        if statement_cst is None:
            return NO_UNIT_DISPATCH
        schema = STATEMENT_SCHEMA_REGISTRY.match(
            mode,
            statement_cst.head_words,
            parse_kind=statement_cst.parse_kind,
        )
        if schema is None:
            return NO_UNIT_DISPATCH
        return getattr(self, schema.parser_method)()

    def _parse_if_statement(self):
        statement_cst = self._active_statement_cst()
        mode = statement_cst.mode if statement_cst is not None else "macro"
        return self._parse_if_expr(mode)

    def _parse_preprocessor_from_cst(self):
        statement_cst = self._active_statement_cst()
        mode = statement_cst.mode if statement_cst is not None else "top"
        return self._parse_preprocessor(mode)

    def _parse_ifdef_from_preprocessor(self, mode=None):
        if mode is None:
            statement_cst = self._active_statement_cst()
            mode = statement_cst.mode if statement_cst is not None else "top"
        return self._parse_ifdef(mode)

    def _parse_expression_statement_from_cst(self):
        return self._parse_expression(stop_on_newline=True)

    def _parse_statement_from_cst(self, mode, statement_cst):
        if statement_cst is None:
            return NO_UNIT_DISPATCH
        token = self._cur()
        if token.type == TT.RULE_COMMENT:
            return self._parse_rule_comment_statement()
        if token.type == TT.SYMBOL and token.value in {"}", "]", ")"}:
            return self._handle_closing_delimiter_statement(token)
        dispatched = self._dispatch_statement_schema(mode, statement_cst)
        if dispatched is not NO_UNIT_DISPATCH:
            return dispatched
        if statement_cst.parse_kind == "unknown":
            return self._parse_unknown(mode)
        return NO_UNIT_DISPATCH

    def _parse_statement(self, mode):
        if (mode in {"top", "macro"} and self._cur().type == TT.IDENT and self._cur().value in STMT_STARTS
                and not self._segmenter.starts_assignment_at(self.pos) and not self._segmenter.starts_rule_check_at(self.pos, "top")):
            hit = match_tokens(self.tokens, self.pos)
            if hit and hit[0].route in {"closed", "statement"}:
                return self._parse_dictionary_directive(*hit)
        if mode == "ratio_clause":
            if self._cur().type == TT.PREPROCESSOR:
                return self._parse_ifdef(mode)
            return self._parse_ratio_piece(self._ratio_piece_end(self.pos, True))
        if mode in {"macro", "rule"} and self._at(TT.IDENT, "RDB") and not self._segmenter.starts_assignment_at(self.pos):
            end = self._ratio_piece_end(self.pos, True)
            if end > self.pos:
                return self._parse_ratio_piece(end)
        if mode == "macro" and self._at(TT.SYMBOL, "<"):
            layers = []
            while self._at(TT.SYMBOL, "<"):
                end = self._segmenter.scan_name_end(self.pos + 1)
                if end is None or self.tokens[end].value != ">":
                    break
                self._advance()
                layers.append(self._parse_name())
                self._advance()
                self._skip_newlines()
            if layers:
                return ast.DeviceAuxLayers(layers)
        if mode == "property" and (self._at(TT.SYMBOL, ",") or self._at(TT.IDENT, "PROPERTY")
                                   or self._at(TT.IDENT, "HIDDEN") and self._peek().value == "PROPERTY"):
            keyword = self._advance().value
            if keyword == "HIDDEN":
                self._advance()
                keyword = "HIDDEN PROPERTY"
            self._skip_newlines()
            properties = [self._parse_name()]
            while self._match(TT.SYMBOL, ","):
                self._skip_newlines()
                properties.append(self._parse_name())
            return ast.PropertyDeclaration(keyword, properties)
        if self._at(TT.IDENT, "DFM") and self._peek().value == "SPEC":
            kind = self.tokens[self.pos+2].value
            if kind in {"VIA", "SVRF"}:
                return self._parse_dfm_spec_via() if kind == "VIA" else self._parse_local_svrf()
        if self._at(TT.IDENT, "TVF") and self._peek_non_newline().value == "FUNCTION":
            start = self._advance()
            self._skip_newlines()
            self._expect(TT.IDENT, "FUNCTION")
            self._skip_newlines()
            args = []
            if self._at(TT.IDENT, "EDGE") or self._at(TT.IDENT, "ERROR"):
                args.append(self._advance().value)
                self._skip_newlines()
            args.append(self._parse_name(preserve_case=True))
            self._skip_newlines()
            args.append(self._expect(TT.TVF_BODY, message="Expected [/* TVF script */]").raw)
            return ast.Directive(keywords=["TVF", "FUNCTION"], arguments=args, **self._loc(start))
        if mode == "perc_load":
            return self._parse_perc_load_item()
        if mode in _DFM_MODES:
            if self._cur().type == TT.PREPROCESSOR:
                return self._parse_preprocessor(mode)
            if self._cur().type == TT.RULE_COMMENT:
                return self._parse_rule_comment_statement()
            return self._parse_dfm_fill_clause(mode)
        statement_cst = self._statement_cst_at_current(mode)
        unit_stmt = self._parse_statement_from_cst(mode, statement_cst)
        if unit_stmt is not NO_UNIT_DISPATCH:
            return unit_stmt
        if statement_cst is not None:
            return self._parse_unknown(mode)
        token = self._cur()
        if token.type == TT.PREPROCESSOR:
            return self._parse_preprocessor(mode)
        closing_stmt = self._handle_closing_delimiter_statement(token)
        if closing_stmt is not NO_UNIT_DISPATCH:
            return closing_stmt
        return self._parse_unknown(mode)

    def _parse_dictionary_directive(self, command, end):
        start = self._cur()
        head = command.name.split()
        self.pos = end
        values = []
        while True:
            i = self._next_non_newline_index(self.pos)
            token = self.tokens[i]
            if token.type in (TT.EOF, TT.PREPROCESSOR, TT.RULE_COMMENT) or (
                    token.type == TT.SYMBOL and token.value in {"}", "]", ")", "{"}):
                break
            if self._segmenter.starts_assignment_at(i) or self._segmenter.starts_rule_check_at(i, "top"):
                break
            option = token.type == TT.IDENT and command.forms and any(
                form[:len(values)+1] == (*values, token.value) for form in command.forms)
            if command.name == "DFM DEFAULTS" and token.type in (TT.IDENT, TT.NUMBER, TT.STRING):
                option = matches_defaults([*values, token.value], partial=True)
            if (token.type == TT.IDENT and not option
                    and (match_tokens(self.tokens, i) or self._segmenter.starts_line_statement_at(i))):
                break
            if i != self.pos and not option and len(values) >= command.min_args:
                break
            self.pos = i
            if token.type == TT.SYMBOL and token.value in {"(", "["}:
                depth = [")" if token.value == "(" else "]"]
                self._advance()
                while depth:
                    t = self._cur()
                    if t.type in (TT.EOF, TT.PREPROCESSOR) or (t.type == TT.SYMBOL and t.value in {"}", "{"}):
                        raise ParseError("Unterminated directive argument", t.line, t.col, t)
                    self._advance()
                    if t.type == TT.SYMBOL and t.value in {"[", "("}:
                        depth.append("]" if t.value == "[" else ")")
                    elif t.type == TT.SYMBOL and t.value in {"]", ")"} and t.value != depth.pop():
                        raise ParseError("Mismatched directive argument delimiter", t.line, t.col, t)
                values.append(self._operation_clause(i, self.pos))
            else:
                values.append(self._parse_scalar_argument())
        if command.route == "closed" and head[0] in _DIRECTIVE_HEADS:
            # Keep the historic Directive keyword/argument split for existing consumers.
            remaining = head[1:] + values
            legacy = head[:1]
            while remaining and type(remaining[0]) is str and remaining[0] in self._segmenter.config.directive_secondary_words:
                legacy.append(remaining.pop(0))
            if len(legacy) >= len(head):
                head, values = legacy, remaining
        return ast.Directive(keywords=head, arguments=values, **self._loc(start))

    def _handle_closing_delimiter_statement(self, token):
        if token.type != TT.SYMBOL or token.value not in {"}", "]", ")"}:
            return NO_UNIT_DISPATCH
        if self.strict:
            raise ParseError(
                f"Unexpected closing delimiter {token.value!r}",
                token.line,
                token.col,
                token,
            )
        self._advance()
        return None

    def _parse_rule_comment_statement(self):
        self._advance()
        return None
