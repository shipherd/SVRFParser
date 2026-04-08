"""Modifier and constraint parsing helpers for DRC operations."""

from __future__ import annotations

from . import ast
from .exceptions import ParseError
from .keywords import _DRC_MODIFIERS
from .svrf_spec import PARSER_SPEC
from .tokens import TokenType

TT = TokenType

_COMPARISON_SYMBOLS = PARSER_SPEC.table("comparison_symbols")
_MODIFIER_STARTERS = PARSER_SPEC.table("modifier_starters")
_DFM_PROPERTY_MODIFIERS = PARSER_SPEC.table("dfm_property_modifiers")
_RET_OPTION_STARTERS = PARSER_SPEC.table("ret_option_starters") | frozenset({"EMULATION"})


class OperationModifierParserMixin:
    """Shared modifier parsing used by operation-body and expression handlers."""

    def _parse_parenthesized_scalar_sequence(self):
        start = self._expect(TT.SYMBOL, "(")
        depth = 1
        end_token = start
        while not self._at(TT.EOF) and depth > 0:
            token = self._cur()
            if token.type == TT.NEWLINE:
                self._advance()
                continue
            token = self._advance()
            if token.type == TT.SYMBOL and token.value == "(":
                depth += 1
            elif token.type == TT.SYMBOL and token.value == ")":
                depth -= 1
            end_token = token
            if depth == 0:
                break
        if depth > 0:
            self._expect(TT.SYMBOL, ")")
            end_token = self.tokens[self.pos - 1]
        text = self._slice(start.offset, end_token.end_offset)
        return text if text is not None else "(" + str(end_token.raw) + ")"

    def _parse_constraints(self):
        constraints = []
        while self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS:
            op = self._advance()
            value = self._parse_expression(35)
            constraints.append(ast.Constraint(op=op.value, value=value, **self._loc(op)))
        return constraints

    def _consume_constraint_modifiers(self):
        modifiers = []
        while self._cur().type == TT.IDENT and self._cur().value in _DRC_MODIFIERS:
            modifiers.append(self._advance().value)
        return modifiers

    def _modifier_starters_for_operation(self, schema):
        modifier_starters = _MODIFIER_STARTERS
        if schema.modifier_family == "dfm_property":
            modifier_starters = modifier_starters | _DFM_PROPERTY_MODIFIERS
        elif schema.modifier_family == "ret":
            modifier_starters = modifier_starters | _RET_OPTION_STARTERS
        return modifier_starters

    def _parse_operation_modifiers(
        self,
        modifier_starters=None,
        *,
        bracket_modifier_mode="scalar",
        parenthesized_scalar_modifiers=False,
    ):
        if modifier_starters is None:
            modifier_starters = _MODIFIER_STARTERS
        modifiers = []
        while True:
            token = self._cur()
            if token.type == TT.NEWLINE:
                if self._consume_operation_continuation_newlines():
                    continue
                break
            if token.type in (TT.EOF, TT.PREPROCESSOR, TT.RULE_COMMENT):
                break
            if (
                token.type == TT.IDENT
                and token.value == "EXTENTS"
                and modifiers
                and modifiers[-1] == "REGION"
            ):
                self._advance()
                modifiers[-1] = "REGION EXTENTS"
                continue
            if (
                modifiers
                and self._starts_same_line_statement_at(self.pos, "rule")
                and not (token.type == TT.IDENT and token.value in modifier_starters)
            ):
                break
            if token.type == TT.SYMBOL and token.value in {"}", "]", ")", ","}:
                break
            if token.type == TT.SYMBOL and token.value in _COMPARISON_SYMBOLS:
                modifiers.extend(self._parse_constraints())
                continue
            if token.type == TT.SYMBOL and token.value == "[" and bracket_modifier_mode == "expression":
                modifiers.append(self._parse_expression(stop_on_newline=False))
                continue
            if token.type == TT.SYMBOL and token.value == "[":
                modifiers.append(self._parse_scalar_argument())
                continue
            if token.type == TT.SYMBOL and token.value == "(" and parenthesized_scalar_modifiers:
                modifiers.append(self._parse_parenthesized_scalar_sequence())
                continue
            if token.type == TT.IDENT and token.value == "BY":
                self._advance()
                if self._at_statement_boundary("rule", allow_same_line_statement=False):
                    modifiers.append("BY")
                elif self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS:
                    modifiers.append("BY")
                    modifiers.extend(self._parse_constraints())
                else:
                    modifiers.append(("BY", self._parse_modifier_value()))
                continue
            if token.type == TT.IDENT and token.value == "ABUT" and self._peek().type == TT.IDENT and self._peek().value == "ALSO":
                self._advance()
                self._advance()
                modifiers.append("ABUT ALSO")
                continue
            if token.type == TT.IDENT and token.value == "ABUT" and self._peek().type == TT.SYMBOL and self._peek().value in {"<", ">"}:
                modifiers.append(self._consume_abut_modifier())
                continue
            modifiers.append(self._parse_scalar_argument())
        return modifiers

    def _consume_abut_modifier(self):
        start = self._expect(TT.IDENT, "ABUT")
        parts = [start.value]
        while True:
            token = self._cur()
            if token.type == TT.NUMBER:
                parts.append(str(token.raw))
                self._advance()
                continue
            if token.type == TT.SYMBOL and token.value in {"<", ">"}:
                parts.append(token.value)
                self._advance()
                continue
            break
        return "".join(parts)

    def _parse_compact_modifier(self):
        token = self._cur()
        if token.type == TT.IDENT:
            value = token.value
            self._advance()
            if self._match(TT.SYMBOL, "("):
                inner = []
                while not self._at(TT.EOF) and not self._at_symbol(")"):
                    inner.append(str(self._advance().raw))
                self._match(TT.SYMBOL, ")")
                return f"{value}({''.join(inner).strip()})"
            return value
        if token.type == TT.STRING:
            return self._advance().value
        if token.type == TT.NUMBER:
            return str(self._advance().raw)
        return None

    def _parse_modifier_value(self):
        left = self._parse_modifier_atom()
        while self._cur().type == TT.SYMBOL and self._cur().value in {"+", "-", "*", "/", "^"}:
            op = self._advance().value
            right = self._parse_modifier_atom()
            left = ast.BinaryOp(op=op, left=left, right=right, **self._loc())
        return left

    def _parse_modifier_atom(self):
        token = self._cur()
        loc = self._loc(token)
        if token.type == TT.NUMBER:
            self._advance()
            return ast.NumberLiteral(value=token.value, **loc)
        if token.type == TT.STRING:
            self._advance()
            return ast.StringLiteral(value=token.value, **loc)
        if token.type == TT.IDENT:
            self._advance()
            return ast.LayerRef(name=token.value, **loc)
        if token.type == TT.SYMBOL and token.value == "(":
            self._advance()
            expr = self._parse_modifier_value()
            self._expect(TT.SYMBOL, ")")
            return expr
        if token.type == TT.SYMBOL and token.value == "-":
            self._advance()
            if self._cur().type == TT.NUMBER:
                value_token = self._advance()
                return ast.NumberLiteral(value=-value_token.value, **loc)
            operand = self._parse_modifier_atom()
            return ast.UnaryOp(op="-", operand=operand, **loc)
        raise ParseError(
            f"Unexpected token {token.raw!r} in modifier value",
            token.line,
            token.col,
            token,
        )
