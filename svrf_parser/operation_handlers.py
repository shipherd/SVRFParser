"""DRC operation and operation-expression handlers for the live parser path."""

from __future__ import annotations

from . import ast
from .operation_expression_handlers import OperationExpressionParserMixin
from .operation_modifier_handlers import OperationModifierParserMixin
from .operation_normalizer import normalize_operation_parts
from .operation_schema import OPERATION_SCHEMA_REGISTRY
from .svrf_spec import PARSER_SPEC
from .tokens import TokenType

TT = TokenType

_COMPARISON_SYMBOLS = PARSER_SPEC.table("comparison_symbols")


class OperationParserMixin(OperationExpressionParserMixin, OperationModifierParserMixin):
    """SVRF-specific operation handlers used by expression dispatch."""

    def _parse_function_call(self):
        start = self._cur()
        name = self._parse_name()
        self._expect(TT.SYMBOL, "(")
        args = []
        while not self._at(TT.EOF) and not self._at_symbol(")"):
            if self._match(TT.SYMBOL, ","):
                continue
            args.append(self._parse_expression(stop_tokens={",", ")"}, stop_on_newline=False))
            self._match(TT.SYMBOL, ",")
        self._expect(TT.SYMBOL, ")")
        return ast.FuncCall(name=name, args=args, **self._loc(start))

    def _parse_prefix_boolean(self):
        start = self._expect(TT.IDENT)
        operands = []
        allow_parenthesized_newlines = self._prefix_boolean_allows_parenthesized_newlines()
        self._consume_prefix_boolean_newline(start.col, allow_parenthesized_newlines)
        while True:
            if self._cur().type == TT.NEWLINE:
                if self._consume_prefix_boolean_newline(start.col, allow_parenthesized_newlines):
                    continue
                break
            if self._at_statement_boundary("rule", allow_same_line_statement=False):
                break
            if not self._can_start_expression_token():
                break
            operands.append(self._parse_prefix_operand())
        return self._build_prefix_boolean_result(start, operands)

    def _prefix_boolean_allows_parenthesized_newlines(self):
        prev_idx = self.pos - 2
        while prev_idx >= 0 and self.tokens[prev_idx].type == TT.NEWLINE:
            prev_idx -= 1
        return (
            prev_idx >= 0
            and self.tokens[prev_idx].type == TT.SYMBOL
            and self.tokens[prev_idx].value == "("
        )

    def _consume_prefix_boolean_newline(self, start_col, allow_parenthesized_newlines):
        if self._cur().type != TT.NEWLINE:
            return False
        if not self._segmenter.continues_indented_expression_across_newline(
            self.pos,
            start_col,
            allow_parenthesized=allow_parenthesized_newlines,
        ):
            return False
        self.pos = self._next_non_newline_index()
        return True

    def _build_prefix_boolean_result(self, start, operands):
        if not operands:
            return ast.LayerRef(name=start.value, **self._loc(start))
        if len(operands) == 1:
            return operands[0]
        result = operands[0]
        for operand in operands[1:]:
            result = ast.BinaryOp(op=start.value, left=result, right=operand, **self._loc(start))
        return result

    def _parse_prefix_edge_binary(self):
        start = self._expect(TT.IDENT)
        op_parts = [start.value]
        if self._cur().type == TT.IDENT and self._cur().value in {"INSIDE", "OUTSIDE"}:
            op_parts.append(self._advance().value)
        self._expect(TT.IDENT, "EDGE")
        op_parts.append("EDGE")
        self._consume_rhs_newlines()
        left = self._parse_prefix_operand()
        self._consume_rhs_newlines()
        right = self._parse_prefix_operand()
        return ast.BinaryOp(op=" ".join(op_parts), left=left, right=right, **self._loc(start))

    def _parse_measurement_operation(self):
        start = self._expect(TT.IDENT)
        if self._at(TT.SYMBOL, "(") and self._peek().type == TT.SYMBOL and self._peek().value == ")":
            self._advance()
            self._advance()
            expr = ast.FuncCall(name=start.value, args=[], **self._loc(start))
            if self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS:
                constraints = self._parse_constraints()
                return ast.ConstrainedExpr(expr=expr, constraints=constraints, modifiers=[], **self._loc(start))
            return expr
        if self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS:
            constraints = self._parse_constraints()
            operand = self._parse_expression(50)
            expr = ast.UnaryOp(op=start.value, operand=operand, **self._loc(start))
            return ast.ConstrainedExpr(expr=expr, constraints=constraints, modifiers=[], **self._loc(start))
        operand = self._parse_expression(50)
        expr = ast.UnaryOp(op=start.value, operand=operand, **self._loc(start))
        if self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS:
            constraints = self._parse_constraints()
            return ast.ConstrainedExpr(expr=expr, constraints=constraints, modifiers=[], **self._loc(start))
        return expr

    def _parse_stamp_operation(self):
        start = self._expect(TT.IDENT, "STAMP")
        left = self._parse_expression(40)
        right = None
        if self._match(TT.IDENT, "BY"):
            right = self._parse_expression(40)
        return ast.BinaryOp(op="STAMP", left=left, right=right, **self._loc(start))

    def _parse_generic_operation(self):
        start_idx = self.pos
        schema = self._resolve_operation_schema(start_idx)
        start = self._expect(TT.IDENT)
        self.pos = max(self.pos, schema.end_idx)
        op_name = schema.name
        return self._parse_operation_from_schema(start, op_name, schema)

    def _parse_operation_from_schema(self, start, op_name, schema):
        modifier_starters = self._modifier_starters_for_operation(schema)
        strategy_handlers = {
            "device_layer": self._parse_device_layer_operation,
            "dfm_rdb": self._parse_dfm_rdb_operation,
            "pathchk": self._parse_pathchk_operation,
        }
        handler = strategy_handlers.get(schema.parse_strategy, self._parse_default_operation)
        return handler(start, op_name, schema, modifier_starters)

    def _parse_device_layer_operation(self, start, op_name, schema, modifier_starters):
        del schema, modifier_starters
        modifiers = []
        while not self._at_statement_boundary("rule", allow_same_line_statement=False):
            modifier = self._parse_compact_modifier()
            if modifier is None:
                break
            modifiers.append(modifier)
        return normalize_operation_parts(
            op_name,
            modifiers=modifiers,
            strategy="device_layer",
            location=self._loc(start),
        )

    def _parse_pathchk_operation(self, start, op_name, schema, modifier_starters):
        del schema
        operands = []
        constraints = []
        modifiers = []
        if not self._at_statement_boundary("rule", allow_same_line_statement=bool(modifiers)):
            operands.append(self._parse_expression(0))
        self._consume_operation_continuation_newlines()
        if self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS:
            constraints.extend(self._parse_constraints())
        self._consume_operation_continuation_newlines()
        if self._cur().type == TT.IDENT and self._cur().value in modifier_starters:
            modifiers.extend(self._parse_operation_modifiers(modifier_starters))
        return normalize_operation_parts(
            op_name,
            operands=operands,
            constraints=constraints,
            modifiers=modifiers,
            strategy="pathchk",
            location=self._loc(start),
        )

    def _parse_dfm_rdb_operation(self, start, op_name, schema, modifier_starters):
        del modifier_starters
        modifiers = []
        while True:
            token = self._cur()
            if token.type == TT.NEWLINE:
                if self._consume_operation_continuation_newlines():
                    continue
                break
            if token.type in (TT.EOF, TT.PREPROCESSOR, TT.RULE_COMMENT):
                break
            if token.type == TT.SYMBOL and token.value in {"}", "]", ")", ","}:
                break
            if self._starts_same_line_statement_at(self.pos, "rule"):
                break
            if token.type == TT.SYMBOL and token.value == "[":
                modifiers.append(self._parse_bracketed_scalar_sequence())
                continue
            if token.type == TT.SYMBOL and token.value == "(" and schema.parenthesized_scalar_modifiers:
                modifiers.append(self._parse_parenthesized_scalar_sequence())
                continue
            modifiers.append(self._parse_scalar_argument())
        return normalize_operation_parts(
            op_name,
            modifiers=modifiers,
            strategy="dfm_rdb",
            location=self._loc(start),
        )

    def _parse_default_operation(self, start, op_name, schema, modifier_starters):
        operands = []
        constraints = []
        modifiers = []

        while True:
            token = self._cur()
            if token.type == TT.NEWLINE:
                if self._consume_operation_continuation_newlines():
                    continue
                if schema.allow_nonstatement_expression_newline:
                    if self._segmenter.continues_nonstatement_expression_across_newline(self.pos, "top"):
                        self.pos = self._next_non_newline_index()
                        continue
                break
            if token.type in (TT.EOF, TT.PREPROCESSOR, TT.RULE_COMMENT):
                break
            if constraints or modifiers:
                if (
                    self._starts_same_line_statement_at(self.pos, "rule")
                    and not (token.type == TT.IDENT and token.value in modifier_starters)
                ):
                    break
            if token.type == TT.SYMBOL and token.value in {"}", "]", ")", ","}:
                break
            if token.type == TT.SYMBOL and token.value in _COMPARISON_SYMBOLS:
                constraints.extend(self._parse_constraints())
                continue
            if token.type == TT.SYMBOL and token.value == "[" and schema.bracket_modifier_mode == "expression":
                modifiers.append(self._parse_expression(stop_on_newline=False))
                continue
            if token.type == TT.SYMBOL and token.value == "(" and schema.parenthesized_scalar_modifiers:
                modifiers.append(self._parse_parenthesized_scalar_sequence())
                continue
            if token.type == TT.IDENT and token.value in modifier_starters:
                modifiers.extend(
                    self._parse_operation_modifiers(
                        modifier_starters,
                        bracket_modifier_mode=schema.bracket_modifier_mode,
                        parenthesized_scalar_modifiers=schema.parenthesized_scalar_modifiers,
                    )
                )
                break
            operands.append(self._parse_expression(35))

        self._consume_operation_continuation_newlines()
        if self._cur().type == TT.SYMBOL and self._cur().value in _COMPARISON_SYMBOLS:
            constraints.extend(self._parse_constraints())
        self._consume_operation_continuation_newlines()
        if not modifiers and self._cur().type == TT.IDENT and self._cur().value in modifier_starters:
            modifiers.extend(
                self._parse_operation_modifiers(
                    modifier_starters,
                    bracket_modifier_mode=schema.bracket_modifier_mode,
                    parenthesized_scalar_modifiers=schema.parenthesized_scalar_modifiers,
                )
            )

        return normalize_operation_parts(
            op_name,
            operands=operands,
            constraints=constraints,
            modifiers=modifiers,
            strategy=schema.parse_strategy or "default",
            location=self._loc(start),
        )

    def _resolve_operation_schema(self, start_idx):
        return OPERATION_SCHEMA_REGISTRY.resolve(
            self.tokens,
            start_idx,
            self._segmenter.next_non_newline_index,
        )
