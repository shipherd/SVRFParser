"""Pratt expression parsing subsystem shared by the live parser."""

from __future__ import annotations

from . import ast
from .exceptions import ParseError
from .expression_schema import (
    LED_EXPRESSION_SCHEMA_REGISTRY,
    PREFIX_EXPRESSION_SCHEMA_REGISTRY,
)
from .keywords import _DRC_MODIFIERS
from .svrf_spec import PARSER_SPEC
from .tokens import TokenType

TT = TokenType

_MEASUREMENT_OPS = PARSER_SPEC.table("measurement_ops")
_UNARY_OPS = PARSER_SPEC.table("unary_ops")
_PREFIX_BOOLEAN_OPS = PARSER_SPEC.table("prefix_boolean_ops")
_GENERIC_PREFIX_OPS = PARSER_SPEC.table("generic_prefix_ops")
_COMPARISON_SYMBOLS = PARSER_SPEC.table("comparison_symbols")
_ARITHMETIC_BP = PARSER_SPEC.table("arithmetic_bp")
_INFIX_BP = PARSER_SPEC.table("infix_bp")
_MODIFIER_STARTERS = PARSER_SPEC.table("modifier_starters")
_NOT_COMPOUND_OPS = PARSER_SPEC.table("not_compound_ops")
_FUNCTION_LIKE_NAMES = PARSER_SPEC.table("function_like_names")


class ExpressionParserMixin:
    """Pratt expression dispatcher.

    The mixin intentionally delegates SVRF-specific operations back to the
    concrete parser. This keeps one live parse path while separating generic
    expression dispatch from statement-family parsing.
    """

    def _parse_expression(self, rbp=0, stop_tokens=None, stop_on_newline=True):
        start = self.pos
        stop_tokens = stop_tokens or set()
        if not stop_on_newline:
            self._skip_newlines()
        left = self._nud(stop_tokens, stop_on_newline)
        while True:
            token = self._cur()
            if token.type == TT.NEWLINE:
                if self._consume_expression_continuation_newlines():
                    continue
                if not stop_on_newline:
                    nxt = self._peek_after_newlines()
                    if nxt.type == TT.SYMBOL and (nxt.value in stop_tokens or nxt.value in {"}", "]", ")", ","}):
                        self._advance()
                        continue
                break
            if token.type in (TT.EOF, TT.PREPROCESSOR, TT.RULE_COMMENT):
                break
            if token.type == TT.SYMBOL and token.value in stop_tokens:
                break
            if token.type == TT.SYMBOL and token.value in {"}", "]", ")"} and token.value not in stop_tokens:
                break
            lbp = self._led_binding_power()
            if lbp <= rbp:
                break
            left = self._led(left, lbp, stop_tokens, stop_on_newline)
        return self._finish_node(left, start)

    def _nud(self, stop_tokens, stop_on_newline):
        token = self._cur()
        loc = self._loc(token)

        if token.type == TT.NUMBER:
            self._advance()
            return ast.NumberLiteral(value=token.value, **loc)

        if token.type == TT.STRING:
            self._advance()
            return ast.StringLiteral(value=token.value, **loc)

        if token.type == TT.SYMBOL and token.value == "(":
            return self._parse_parenthesized_nud(loc)

        if token.type == TT.SYMBOL and token.value == "[":
            return self._parse_bracket_nud(loc)

        if token.type == TT.SYMBOL and token.value == "-":
            return self._parse_signed_nud("-", loc, stop_tokens, stop_on_newline)

        if token.type == TT.SYMBOL and token.value == "+":
            return self._parse_signed_nud("+", loc, stop_tokens, stop_on_newline)

        if token.type == TT.SYMBOL and token.value == "!":
            self._advance()
            operand = self._parse_expression(50, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
            return ast.UnaryOp(op="NOT", operand=operand, **loc)

        if token.type == TT.SYMBOL and token.value == "~":
            self._advance()
            operand = self._parse_expression(50, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
            return ast.UnaryOp(op="~", operand=operand, **loc)

        if token.type == TT.SYMBOL and token.value == "$":
            self._advance()
            name = self._parse_name()
            return ast.LayerRef(name=f"${name}", **loc)

        if token.type == TT.IDENT:
            return self._parse_ident_nud(token, loc, stop_tokens, stop_on_newline)

        raise ParseError(
            f"Unexpected token {token.raw!r} in expression",
            token.line,
            token.col,
            token,
        )

    def _parse_parenthesized_nud(self, loc):
        self._advance()
        expr = self._parse_expression(0, stop_tokens={")"}, stop_on_newline=False)
        if self._cur().type == TT.IDENT and self._cur().value in (_MODIFIER_STARTERS | _DRC_MODIFIERS):
            modifiers = self._parse_operation_modifiers()
            if isinstance(expr, ast.DRCOp):
                expr = ast.DRCOp(
                    op=expr.op,
                    operands=list(expr.operands),
                    constraints=list(expr.constraints),
                    modifiers=list(expr.modifiers) + list(modifiers),
                    **loc,
                )
            elif isinstance(expr, ast.BinaryOp):
                expr = ast.DRCOp(
                    op=expr.op,
                    operands=[expr.left, expr.right],
                    constraints=[],
                    modifiers=modifiers,
                    **loc,
                )
            elif isinstance(expr, ast.UnaryOp):
                expr = ast.DRCOp(
                    op=expr.op,
                    operands=[expr.operand],
                    constraints=[],
                    modifiers=modifiers,
                    **loc,
                )
        self._expect(TT.SYMBOL, ")")
        return expr

    def _parse_bracket_nud(self, loc):
        self._advance()
        save = self.pos
        try:
            expr = self._parse_expression(0, stop_tokens={"]"}, stop_on_newline=False)
            self._expect(TT.SYMBOL, "]")
            return expr
        except ParseError:
            self.pos = save
            return ast.StringLiteral(value=self._consume_bracket_fallback_text(), **loc)

    def _parse_signed_nud(self, sign, loc, stop_tokens, stop_on_newline):
        self._advance()
        if self._at(TT.SYMBOL, "="):
            self._advance()
            operand = self._parse_expression(35, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
            return ast.UnaryOp(op=f"{sign}=", operand=operand, **loc)
        if sign == "-" and self._cur().type == TT.NUMBER:
            value_token = self._advance()
            return ast.NumberLiteral(value=-value_token.value, **loc)
        operand = self._parse_expression(50, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
        return ast.UnaryOp(op=sign, operand=operand, **loc)

    def _collect_prefix_expression_tags(self, token):
        tags = {"layer_ref"}
        if self._segmenter.starts_assignment_at(self.pos):
            tags.add("assignment_reference")
        if token.value in _MEASUREMENT_OPS:
            tags.add("measurement")
        if token.value in {"INSIDE", "OUTSIDE", "OUT"} and self._peek().type == TT.IDENT and self._peek().value == "CELL":
            tags.add("inside_outside_cell")
        if self._current_edge_binary_op_parts() is not None:
            tags.add("edge_binary_prefix")
        if token.value in _PREFIX_BOOLEAN_OPS:
            tags.add("prefix_boolean")
        if token.value in _UNARY_OPS:
            tags.add("unary_ident")
        callable_name, spaced = self._peek_callable_name_before_paren()
        if (
            callable_name is not None
            and callable_name not in _GENERIC_PREFIX_OPS
            and (not spaced or callable_name in _FUNCTION_LIKE_NAMES)
        ):
            tags.add("callable_name")
        spaced_operand = self._current_token_is_spaced_operand_before_paren()
        if spaced_operand:
            tags.add("spaced_operand_before_paren")
        if (
            not spaced_operand
            and self._peek().type == TT.SYMBOL
            and self._peek().value == "("
            and token.value not in _GENERIC_PREFIX_OPS
        ):
            tags.add("plain_function_call")
        if token.value == "STAMP":
            tags.add("stamp")
        if token.value in _GENERIC_PREFIX_OPS:
            tags.add("generic_prefix_op")
        return frozenset(tags)

    def _resolve_prefix_expression_schema(self, token):
        return PREFIX_EXPRESSION_SCHEMA_REGISTRY.match(self._collect_prefix_expression_tags(token))

    def _parse_ident_nud(self, token, loc, stop_tokens, stop_on_newline):
        schema = self._resolve_prefix_expression_schema(token)
        handler = getattr(self, schema.parser_method)
        return handler(token, loc, stop_tokens, stop_on_newline)

    def _parse_ident_layer_ref(self, token, loc, stop_tokens, stop_on_newline):
        del token, stop_tokens, stop_on_newline
        return ast.LayerRef(name=self._parse_name(), **loc)

    def _parse_ident_measurement_nud(self, token, loc, stop_tokens, stop_on_newline):
        del token, loc, stop_tokens, stop_on_newline
        return self._parse_measurement_operation()

    def _parse_inside_outside_cell_nud(self, token, loc, stop_tokens, stop_on_newline):
        del token
        start = self._advance()
        self._advance()
        operands = self._parse_cell_operands(stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
        return ast.DRCOp(op=f"{start.value} CELL", operands=operands, constraints=[], modifiers=[], **loc)

    def _parse_prefix_edge_binary_nud(self, token, loc, stop_tokens, stop_on_newline):
        del token, loc, stop_tokens, stop_on_newline
        return self._parse_prefix_edge_binary()

    def _parse_prefix_boolean_nud(self, token, loc, stop_tokens, stop_on_newline):
        del token, loc, stop_tokens, stop_on_newline
        return self._parse_prefix_boolean()

    def _parse_ident_unary_nud(self, token, loc, stop_tokens, stop_on_newline):
        return self._parse_unary_ident_nud(token, loc, stop_tokens, stop_on_newline)

    def _parse_function_call_nud(self, token, loc, stop_tokens, stop_on_newline):
        del token, loc, stop_tokens, stop_on_newline
        return self._parse_function_call()

    def _parse_stamp_nud(self, token, loc, stop_tokens, stop_on_newline):
        del token, loc, stop_tokens, stop_on_newline
        return self._parse_stamp_operation()

    def _parse_generic_operation_nud(self, token, loc, stop_tokens, stop_on_newline):
        del token, loc, stop_tokens, stop_on_newline
        return self._parse_generic_operation()

    def _collect_led_expression_tags(self, token):
        tags = set()
        if token.type == TT.SYMBOL:
            if token.value == "?":
                tags.add("ternary_question")
            elif token.value == "=":
                tags.add("equals_symbol")
            elif token.value in _COMPARISON_SYMBOLS:
                tags.add("comparison_symbol")
            elif token.value in _ARITHMETIC_BP:
                tags.add("arithmetic_symbol")
            return frozenset(tags)

        if token.type != TT.IDENT:
            return frozenset(tags)

        if token.value in _MEASUREMENT_OPS:
            tags.add("measurement")
        if token.value == "SIZE":
            tags.add("size")
        if token.value in {"HOLES", "DONUT"}:
            tags.add("holes_or_donut")
        if token.value == "RECTANGLE":
            nxt = self._peek()
            if nxt.type == TT.SYMBOL and nxt.value in _COMPARISON_SYMBOLS:
                tags.add("rectangle")
            if nxt.type == TT.IDENT and nxt.value in (_MODIFIER_STARTERS | _DRC_MODIFIERS):
                tags.add("rectangle")
        if self._current_edge_binary_op_parts() is not None:
            tags.add("edge_binary")
        if token.value == "WITH":
            tags.add("with")
        if token.value in {"EXPAND", "CONVEX"} and self._peek().type == TT.IDENT and self._peek().value == "EDGE":
            tags.add("expand_or_convex_edge")
        if token.value == "NOT" and self._peek().type == TT.IDENT and self._peek().value in _NOT_COMPOUND_OPS:
            tags.add("not_compound")
        if token.value in _INFIX_BP:
            tags.add("generic_ident")
        return frozenset(tags)

    def _resolve_led_expression_schema(self):
        return LED_EXPRESSION_SCHEMA_REGISTRY.match(self._collect_led_expression_tags(self._cur()))

    def _binding_power_for_led_schema(self, schema, token):
        if schema is None:
            return 0
        if schema.binding_power_source == "static":
            return schema.binding_power or 0
        if schema.binding_power_source == "arithmetic_symbol":
            return _ARITHMETIC_BP.get(token.value, 0)
        if schema.binding_power_source == "infix_ident":
            return _INFIX_BP.get(token.value, 0)
        if schema.binding_power_source == "edge_binary":
            edge_op = self._current_edge_binary_op_parts()
            if edge_op is None:
                return 0
            return _INFIX_BP.get(edge_op[0], 0)
        return 0

    def _led_binding_power(self):
        token = self._cur()
        return self._binding_power_for_led_schema(self._resolve_led_expression_schema(), token)

    def _led(self, left, lbp, stop_tokens, stop_on_newline):
        token = self._cur()
        loc = self._loc(token)
        schema = self._resolve_led_expression_schema()
        handler = getattr(self, schema.parser_method)
        return handler(left, lbp, loc, stop_tokens, stop_on_newline)
