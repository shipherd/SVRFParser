"""Rule-check and property-block statement shell handlers."""

from __future__ import annotations

from . import ast
from .tokens import TokenType

TT = TokenType


class StatementBlockParserMixin:
    """Parse statement shells whose bodies are delegated to the active parser."""

    def _parse_statement_shape_rule_check(self, shape):
        del shape
        start, name = self._parse_rule_check_header()
        comments = self._parse_rule_check_comments()
        body = self._parse_rule_check_body()
        self._expect(TT.SYMBOL, "}")
        return ast.RuleCheckBlock(name=name, comments=comments or None, body=body, **self._loc(start))

    def _parse_statement_shape_property_block(self, shape):
        del shape
        start, properties = self._parse_property_block_header()
        body = self._parse_property_block_body()
        return self._finish_property_block(start, properties, body)

