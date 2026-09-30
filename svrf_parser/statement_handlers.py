"""Statement parsing handlers for the live parser path."""

from __future__ import annotations

from .exceptions import ParseError
from .dfm_spec_parser import DfmSpecParserMixin, _DFM_MODES
from .perc_parser import PercParserMixin
from .statement_schema import STATEMENT_SCHEMA_REGISTRY
from .statement_shape_handlers import StatementShapeParserMixin
from .tokens import TokenType

TT = TokenType
NO_UNIT_DISPATCH = object()


class StatementParserMixin(StatementShapeParserMixin, DfmSpecParserMixin, PercParserMixin):
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
