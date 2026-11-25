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
            return ast.UnaryOp(op=start.value, operand=operands[0], **self._loc(start))
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
        op_name = {"INTERNAL": "INT", "EXTERNAL": "EXT", "ENCLOSURE": "ENC"}.get(schema.name, schema.name)
        return self._parse_operation_from_schema(start, op_name, schema)

    def _parse_operation_from_schema(self, start, op_name, schema):
        modifier_starters = self._modifier_starters_for_operation(schema)
        strategy_handlers = {
            "dfm_mat": self._parse_dfm_mat_operation,
            "device_layer": self._parse_device_layer_operation,
            "dfm_rdb": self._parse_dfm_rdb_operation,
            "pathchk": self._parse_pathchk_operation,
            "fixed_geometry": self._parse_fixed_geometry,
            "directional_geometry": self._parse_directional_geometry,
        }
        handler = strategy_handlers.get(schema.parse_strategy, self._parse_default_operation)
        return handler(start, op_name, schema, modifier_starters)

    def _parse_directional_geometry(self, start, op_name, schema=None, modifier_starters=None, *, left=None):
        operands = [left] if left is not None else []
        modifiers = []
        expand = op_name == "EXPAND EDGE"
        directions = ({"IN": "INSIDE", "OUT": "OUTSIDE", "INSIDE": "INSIDE", "OUTSIDE": "OUTSIDE", "EXTEND": "EXTEND"}
                      if expand else {word: word for word in ("TOP", "BOTTOM", "LEFT", "RIGHT")})
        while True:
            i = self._next_non_newline_index(self.pos)
            t = self.tokens[i]
            j = self._next_non_newline_index(i+1) if t.type == TT.IDENT else i
            if t.type == TT.IDENT and t.value in directions and self.tokens[j].value == "BY":
                modifiers.append(directions[t.value])
                self.pos = i = j
                t = self.tokens[i]
            if t.type == TT.IDENT and t.value == "BY":
                self.pos = i+1
                self._skip_newlines()
                factor = expand and self._match(TT.IDENT, "FACTOR")
                self._skip_newlines()
                # Scalar context distinguishes 'distance (layer)' from a function call.
                modifiers.append(("BY FACTOR" if factor else "BY", self._parse_expression(35, context="scalar")))
            elif expand and t.type == TT.IDENT and t.value == "CORNER" and self.tokens[j].value == "FILL":
                self.pos = j+1
                modifiers.append("CORNER FILL")
            elif op_name == "GROW" and t.type == TT.IDENT and t.value == "SEQUENTIAL":
                self.pos = i+1
                modifiers.append("SEQUENTIAL")
            elif not operands and self._can_start_expression_token(t) and not self._starts_line_statement_at(i):
                self.pos = i
                operands.append(self._parse_expression(35, context="layer"))
            else:
                break
        return ast.DRCOp(op=op_name, operands=operands, modifiers=modifiers, **self._loc(start))

    def _parse_fixed_geometry(self, start, op_name, schema, modifier_starters):
        del schema, modifier_starters
        self._consume_rhs_newlines()
        operands = [self._parse_expression(50)]
        modifiers = []
        self._consume_rhs_newlines()
        if op_name == "MAGNIFY":
            self._expect(TT.IDENT, "BY")
            self._consume_rhs_newlines()
            modifiers.append(("BY", self._parse_expression(50, context="scalar")))
        else:
            operands.append(self._parse_expression(50, context="layer" if op_name == "ORNET" else "scalar"))
            if op_name == "SNAP" and self._at(TT.NEWLINE):
                idx = self._next_non_newline_index(self.pos)
                if self.tokens[idx].type == TT.NUMBER and not self._segmenter.starts_line_statement_at(idx):
                    self.pos = idx
            if op_name == "ORNET" and self._match(TT.IDENT, "BY"):
                if not (self._at(TT.IDENT, "NET") or self._at(TT.IDENT, "SHAPE")):
                    self._expect(TT.IDENT, "NET", "ORNET BY requires NET or SHAPE")
                modifiers.append("BY " + self._advance().value)
            elif op_name == "DEANGLE":
                if self._match(TT.IDENT, "ALL"):
                    modifiers.append("ALL")
                elif self._match(TT.IDENT, "SKEW"):
                    modifiers.append("SKEW")
                    if self._match(TT.IDENT, "ORTHOGONAL"):
                        self._expect(TT.IDENT, "ONLY")
                        modifiers.extend(("ORTHOGONAL", "ONLY"))
            elif (op_name == "SNAP" and self._can_start_expression_token()
                  and not self._at_statement_boundary("rule", allow_same_line_statement=True)
                  and not self._segmenter.starts_operation_at(self.pos)):
                operands.append(self._parse_expression(50, context="scalar"))
        return ast.DRCOp(op=op_name, operands=operands, modifiers=modifiers, **self._loc(start))

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
                next_word = self.tokens[self._next_non_newline_index()].value
                if (op_name.startswith("DFM DV ") and next_word in {"RDB", "DVPARAMS"}
                        or op_name == "DFM DV OVERRIDE" and not operands and next_word in {"CMACRO", "FMACRO"}):
                    self._skip_newlines()
                    continue
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
                modifiers.append(self._parse_expression(stop_on_newline=False, context="dfm"))
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
                        dv_filenames=op_name.startswith("DFM DV "),
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
                    dv_filenames=op_name.startswith("DFM DV "),
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
