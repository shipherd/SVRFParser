"""Expression-level DRC operation handlers used by Pratt dispatch."""

from __future__ import annotations

from . import ast
from .keywords import _DRC_MODIFIERS
from .operation_normalizer import normalize_operation_parts
from .svrf_spec import PARSER_SPEC
from .tokens import TokenType

TT = TokenType

_COMPARISON_SYMBOLS = PARSER_SPEC.table("comparison_symbols")
_WITH_SECONDARY_OPS = PARSER_SPEC.table("with_secondary_ops")
_MODIFIER_STARTERS = PARSER_SPEC.table("modifier_starters")
_PREFIX_BOOLEAN_OPS = PARSER_SPEC.table("prefix_boolean_ops")
_WITH_TEXT_TRAILING_MODIFIERS = PARSER_SPEC.table("with_text_trailing_modifiers")


class OperationExpressionParserMixin:
    """Nud/led handlers for operation-like expressions."""

    def _parse_unary_ident_nud(self, token, loc, stop_tokens, stop_on_newline):
        if token.value == "NOT" and self._peek().type == TT.IDENT and self._peek().value in {"INSIDE", "OUTSIDE", "OUT"}:
            start = self._advance()
            middle = self._advance().value
            if self._cur().type == TT.IDENT and self._cur().value == "CELL":
                self._advance()
                operands = self._parse_cell_operands(stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
                return normalize_operation_parts(
                    f"{start.value} {middle} CELL",
                    operands=operands,
                    strategy="unary_ident",
                    location=loc,
                )
            operand = self._parse_expression(50, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
            return ast.UnaryOp(op=f"{start.value} {middle}", operand=operand, **loc)
        if token.value == "PUSH" and self._peek().type == TT.IDENT and self._peek().value == "MEDIUM":
            start = self._advance()
            mode = self._advance().value
            operand = self._parse_expression(50, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
            return normalize_operation_parts(
                start.value,
                operands=[operand],
                modifiers=[mode],
                strategy="unary_ident",
                location=loc,
            )
        if token.value in {"HOLES", "DONUT"}:
            start = self._advance()
            operand = self._parse_expression(50, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
            if (
                self._cur().type == TT.IDENT and self._cur().value in (_MODIFIER_STARTERS | _DRC_MODIFIERS)
            ) or (
                self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS
            ):
                modifiers = self._parse_operation_modifiers()
                return normalize_operation_parts(
                    start.value,
                    operands=[operand],
                    modifiers=modifiers,
                    strategy="unary_ident",
                    location=loc,
                )
            return ast.UnaryOp(op=start.value, operand=operand, **loc)
        self._advance()
        operand = self._parse_expression(50, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
        return ast.UnaryOp(op=token.value, operand=operand, **loc)

    def _parse_ternary_led(self, left, lbp, loc, stop_tokens, stop_on_newline):
        frames = []
        current_left = left
        current_loc = loc

        while True:
            self._advance()
            self._skip_newlines()
            then_expr = self._parse_expression(
                0,
                stop_tokens=stop_tokens | {":"},
                stop_on_newline=stop_on_newline,
            )
            self._match(TT.SYMBOL, ":")
            self._skip_newlines()
            else_expr = self._parse_expression(
                lbp,
                stop_tokens=stop_tokens,
                stop_on_newline=stop_on_newline,
            )
            frames.append((current_left, then_expr, current_loc))
            if self._at(TT.SYMBOL, "?") and self._led_binding_power() == lbp:
                current_left = else_expr
                current_loc = self._loc(self._cur())
                continue
            result = else_expr
            for cond_expr, then_branch, frame_loc in reversed(frames):
                result = ast.BinaryOp(
                    op="?:",
                    left=cond_expr,
                    right=ast.BinaryOp(op=":", left=then_branch, right=result, **frame_loc),
                    **frame_loc,
                )
            return result

    def _parse_symbol_binary_led(self, left, lbp, loc, stop_tokens, stop_on_newline):
        op = self._advance().value
        self._consume_rhs_newlines()
        right = self._parse_expression(lbp, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
        return ast.BinaryOp(op=op, left=left, right=right, **loc)

    def _parse_constraint_led(self, left, loc):
        constraints = self._parse_constraints()
        if self._cur().type == TT.IDENT and self._cur().value in _MODIFIER_STARTERS:
            modifiers = self._parse_operation_modifiers()
        else:
            modifiers = self._consume_constraint_modifiers()
        return ast.ConstrainedExpr(expr=left, constraints=constraints, modifiers=modifiers, **loc)

    def _parse_constraint_led_from_schema(self, left, lbp, loc, stop_tokens, stop_on_newline):
        del lbp, stop_tokens, stop_on_newline
        return self._parse_constraint_led(left, loc)

    def _parse_with_led(self, left, loc, stop_tokens, stop_on_newline):
        self._advance()
        op_parts = ["WITH"]
        if self._cur().type == TT.IDENT and self._cur().value in _WITH_SECONDARY_OPS:
            op_parts.append(self._advance().value)
        right = None
        if (
            self._can_start_expression_token()
            and not (self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS)
            and not self._at_statement_boundary("rule", allow_same_line_statement=False)
        ):
            self._consume_rhs_newlines()
            right = self._parse_expression(35, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
        op_name = " ".join(op_parts)
        if op_name == "WITH TEXT":
            operands = [left]
            if right is not None:
                operands.append(right)
            while (
                self._can_start_expression_token()
                and not (self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS)
                and not (self._cur().type == TT.IDENT and self._cur().value in _WITH_TEXT_TRAILING_MODIFIERS)
                and not self._at_statement_boundary("rule", allow_same_line_statement=False)
            ):
                operands.append(
                    self._parse_expression(35, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
                )
            modifiers = []
            while self._cur().type == TT.IDENT and self._cur().value in _WITH_TEXT_TRAILING_MODIFIERS:
                modifiers.append(self._advance().value)
            return normalize_operation_parts(
                op_name,
                operands=operands,
                modifiers=modifiers,
                strategy="with_text",
                location=loc,
            )
        expr = ast.BinaryOp(op=op_name, left=left, right=right, **loc)
        if self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS:
            return self._parse_constraint_led(expr, loc)
        if self._cur().type == TT.IDENT and self._cur().value in _MODIFIER_STARTERS:
            modifiers = self._parse_operation_modifiers()
            return normalize_operation_parts(
                op_name,
                operands=[left, right],
                modifiers=modifiers,
                strategy="with_modifier",
                location=loc,
            )
        return expr

    def _parse_with_led_from_schema(self, left, lbp, loc, stop_tokens, stop_on_newline):
        del lbp
        return self._parse_with_led(left, loc, stop_tokens, stop_on_newline)

    def _parse_holes_or_donut_led(self, left, loc):
        op = self._advance().value
        if self._cur().type == TT.IDENT and self._cur().value in (_MODIFIER_STARTERS | _DRC_MODIFIERS):
            modifiers = self._parse_operation_modifiers()
            return normalize_operation_parts(
                op,
                operands=[left],
                modifiers=modifiers,
                strategy="postfix_unary",
                location=loc,
            )
        return ast.UnaryOp(op=op, operand=left, **loc)

    def _parse_holes_or_donut_led_from_schema(self, left, lbp, loc, stop_tokens, stop_on_newline):
        del lbp, stop_tokens, stop_on_newline
        return self._parse_holes_or_donut_led(left, loc)

    def _parse_size_led(self, left, loc):
        self._advance()
        modifiers = []
        if self._match(TT.IDENT, "BY"):
            modifiers.append(("BY", self._parse_modifier_value()))
        constraints = []
        if self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS:
            constraints = self._parse_constraints()
        if self._cur().type == TT.IDENT and self._cur().value in (_MODIFIER_STARTERS | _DRC_MODIFIERS):
            modifiers.extend(self._parse_operation_modifiers())
        return normalize_operation_parts(
            "SIZE",
            operands=[left],
            constraints=constraints,
            modifiers=modifiers,
            strategy="size_led",
            location=loc,
        )

    def _parse_size_led_from_schema(self, left, lbp, loc, stop_tokens, stop_on_newline):
        del lbp, stop_tokens, stop_on_newline
        return self._parse_size_led(left, loc)

    def _parse_rectangle_led(self, left, loc):
        self._advance()
        constraints = []
        if self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS:
            constraints = self._parse_constraints()
        modifiers = []
        if self._cur().type == TT.IDENT and self._cur().value in (_MODIFIER_STARTERS | _DRC_MODIFIERS):
            modifiers = self._parse_operation_modifiers()
        return normalize_operation_parts(
            "RECTANGLE",
            operands=[left],
            constraints=constraints,
            modifiers=modifiers,
            strategy="rectangle_led",
            location=loc,
        )

    def _parse_rectangle_led_from_schema(self, left, lbp, loc, stop_tokens, stop_on_newline):
        del lbp, stop_tokens, stop_on_newline
        return self._parse_rectangle_led(left, loc)

    def _parse_expand_or_convex_edge_led(self, left, token, loc):
        self._advance()
        self._advance()
        modifiers = self._parse_operation_modifiers()
        return normalize_operation_parts(
            f"{token.value} EDGE",
            operands=[left],
            modifiers=modifiers,
            strategy="edge_modifier_led",
            location=loc,
        )

    def _parse_expand_or_convex_edge_led_from_schema(self, left, lbp, loc, stop_tokens, stop_on_newline):
        del lbp, stop_tokens, stop_on_newline
        return self._parse_expand_or_convex_edge_led(left, self._cur(), loc)

    def _parse_measurement_led(self, left, lbp, loc, stop_tokens, stop_on_newline):
        del lbp, stop_tokens, stop_on_newline
        op = self._advance().value
        expr = ast.UnaryOp(op=op, operand=left, **loc)
        if self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS:
            constraints = self._parse_constraints()
            return ast.ConstrainedExpr(expr=expr, constraints=constraints, modifiers=[], **loc)
        return expr

    def _parse_edge_binary_led(self, left, lbp, loc, stop_tokens, stop_on_newline):
        del lbp
        edge_op = self._current_edge_binary_op_parts()
        for _ in edge_op:
            self._advance()
        self._consume_rhs_newlines()
        right = self._parse_expression(30, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
        return ast.BinaryOp(op=" ".join(edge_op), left=left, right=right, **loc)

    def _parse_not_compound_led(self, left, loc, stop_tokens, stop_on_newline):
        self._advance()
        middle = self._advance().value
        if middle == "ENCLOSE" and self._match(TT.IDENT, "RECTANGLE"):
            operands = [left]
            while self._can_start_expression_token() and not self._at_statement_boundary("rule", allow_same_line_statement=False):
                operands.append(self._parse_expression(50, stop_on_newline=stop_on_newline))
            constraints = []
            if self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS:
                constraints.extend(self._parse_constraints())
            modifiers = []
            if self._cur().type == TT.IDENT and self._cur().value in _MODIFIER_STARTERS:
                modifiers.extend(self._parse_operation_modifiers())
            return normalize_operation_parts(
                "NOT ENCLOSE RECTANGLE",
                operands=operands,
                constraints=constraints,
                modifiers=modifiers,
                strategy="not_compound_led",
                location=loc,
            )
        if middle in {"TOUCH", "COIN", "COINCIDENT"}:
            op_parts = ["NOT", middle]
            if self._cur().type == TT.IDENT and self._cur().value in {"INSIDE", "OUTSIDE"}:
                op_parts.append(self._advance().value)
            if self._match(TT.IDENT, "EDGE"):
                op_parts.append("EDGE")
            self._consume_rhs_newlines()
            right = self._parse_expression(30, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
            return ast.BinaryOp(op=" ".join(op_parts), left=left, right=right, **loc)
        if middle in {"INSIDE", "OUTSIDE", "OUT"} and self._cur().type == TT.IDENT and self._cur().value == "CELL":
            self._advance()
            operands = [left]
            operands.extend(self._parse_cell_operands(stop_tokens=stop_tokens, stop_on_newline=stop_on_newline))
            return normalize_operation_parts(
                f"NOT {middle} CELL",
                operands=operands,
                strategy="not_compound_led",
                location=loc,
            )
        if self._match(TT.IDENT, "EDGE"):
            self._consume_rhs_newlines()
            right = self._parse_expression(30, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
            return ast.BinaryOp(op=f"NOT {middle} EDGE", left=left, right=right, **loc)
        self._consume_rhs_newlines()
        right = self._parse_expression(30, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
        return ast.BinaryOp(op=f"NOT {middle}", left=left, right=right, **loc)

    def _parse_not_compound_led_from_schema(self, left, lbp, loc, stop_tokens, stop_on_newline):
        del lbp
        return self._parse_not_compound_led(left, loc, stop_tokens, stop_on_newline)

    def _parse_generic_infix_led(self, left, lbp, loc, stop_tokens, stop_on_newline):
        op = self._advance().value
        self._consume_rhs_newlines()
        right = self._parse_expression(lbp, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
        result = ast.BinaryOp(op=op, left=left, right=right, **loc)
        if self._cur().type == TT.IDENT and self._cur().value in _MODIFIER_STARTERS:
            modifiers = self._parse_operation_modifiers()
            result = normalize_operation_parts(
                op,
                operands=[left, right],
                modifiers=modifiers,
                strategy="generic_infix_modifier",
                location=loc,
            )
        if op in _PREFIX_BOOLEAN_OPS:
            while self._can_start_expression_token() and not self._at_statement_boundary("rule", allow_same_line_statement=False):
                extra = self._parse_expression(lbp, stop_tokens=stop_tokens, stop_on_newline=stop_on_newline)
                result = ast.BinaryOp(op=op, left=result, right=extra, **loc)
        return result

    def _parse_generic_infix_led_from_schema(self, left, lbp, loc, stop_tokens, stop_on_newline):
        return self._parse_generic_infix_led(left, lbp, loc, stop_tokens, stop_on_newline)
