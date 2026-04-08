"""Rule-check and property-block statement shell handlers."""

from __future__ import annotations

from . import ast
from .exceptions import ParseError
from .normalizer import normalize_property_block_clause_shell, normalize_rule_check_clause_shell
from .tokens import TokenType

TT = TokenType


class StatementBlockParserMixin:
    """Parse statement shells whose bodies are delegated to the active parser."""

    def _parse_statement_shape_rule_check(self, shape):
        del shape
        clause_cst = self._active_statement_clause_cst("rule_check")
        if clause_cst is not None:
            return self._parse_rule_check_from_clause_cst(clause_cst)
        start, name = self._parse_rule_check_header()
        comments = self._parse_rule_check_comments()
        body = self._parse_rule_check_body()
        self._expect(TT.SYMBOL, "}")
        return ast.RuleCheckBlock(name=name, comments=comments or None, body=body, **self._loc(start))

    def _parse_statement_shape_property_block(self, shape):
        del shape
        clause_cst = self._active_statement_clause_cst("property_block")
        if clause_cst is not None:
            return self._parse_property_block_from_clause_cst(clause_cst)
        start, properties = self._parse_property_block_header()
        body = self._parse_property_block_body()
        return self._finish_property_block(start, properties, body)

    def _parse_rule_check_from_clause_cst(self, clause_cst):
        statement_cst = clause_cst.statement
        if statement_cst.rule_check_header is None:
            token = self._cur()
            raise ParseError("Missing rule-check CST header metadata", token.line, token.col, token)
        start = self._cur()
        self.pos = statement_cst.rule_check_header.body_start
        comments = self._parse_rule_check_comments()
        body = self._parse_rule_check_body()
        self._expect(TT.SYMBOL, "}")
        return normalize_rule_check_clause_shell(
            clause_cst,
            comments=comments or None,
            body=body,
            location=self._loc(start),
        )

    def _parse_property_block_from_clause_cst(self, clause_cst):
        statement_cst = clause_cst.statement
        if statement_cst.property_block_header is None:
            token = self._cur()
            raise ParseError("Missing property-block CST header metadata", token.line, token.col, token)
        start = self._cur()
        self.pos = statement_cst.property_block_header.body_start
        body = self._parse_property_block_body()
        block = normalize_property_block_clause_shell(
            clause_cst,
            body=body,
            location=self._loc(start),
        )
        return self._finish_property_block_node(block)

