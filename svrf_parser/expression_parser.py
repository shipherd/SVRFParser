"""Expression parsing mixin: Pratt parser for layer and arithmetic expressions."""

from .tokens import TokenType, Token
from . import ast_nodes as ast
from .parser_base import (
    SVRFParseError,
    _BINARY_OPS, _LAYER_BP, _UNARY_OPS,
    _DRC_OPS, _DRC_MODIFIERS, _EXPR_STARTERS, _SVRF_KEYWORDS,
    _DIRECTIVE_HEADS,
)

TT = TokenType


class ExpressionMixin:
    """Mixin providing expression parsing (Pratt parser) for the SVRF parser."""

    # ------------------------------------------------------------------
    # Arithmetic Pratt parser (for property block expressions)
    # ------------------------------------------------------------------
    def _parse_arith_expr(self, bp):
        left = self._arith_nud()
        while True:
            nbp = self._arith_led_bp()
            if nbp <= bp:
                break
            left = self._arith_led(left, nbp)
        return left

    def _arith_nud(self):
        t = self._cur()
        loc = self._loc()
        if t.type == TT.LPAREN:
            self._advance()
            self._skip_newlines()
            expr = self._parse_arith_expr(0)
            self._skip_newlines()
            if self._at(TT.RPAREN):
                self._advance()
            return expr
        if t.type == TT.MINUS:
            self._advance()
            operand = self._parse_arith_expr(30)
            return ast.UnaryOp(op='-', operand=operand, **loc)
        if t.type == TT.BANG:
            self._advance()
            operand = self._parse_arith_expr(30)
            return ast.UnaryOp(op='!', operand=operand, **loc)
        if t.type == TT.INTEGER:
            return ast.NumberLiteral(value=self._advance().value, **loc)
        if t.type == TT.FLOAT:
            return ast.NumberLiteral(value=self._advance().value, **loc)
        if t.type == TT.STRING:
            return ast.StringLiteral(value=self._advance().value, **loc)
        if t.type == TT.IDENT:
            name = t.value
            # Function call: IDENT(args...)
            if self._peek().type == TT.LPAREN:
                return self._parse_func_call()
            self._advance()
            return ast.LayerRef(name=name, **loc)
        # #IFDEF/#IFNDEF inside arithmetic expressions — skip the preprocessor
        # block and parse the then-body as the expression value.
        if t.type in (TT.PP_IFDEF, TT.PP_IFNDEF):
            self._advance()  # #IFDEF/#IFNDEF
            while not self._at_eol():
                self._advance()
            self._consume_eol()
            self._skip_newlines()
            # Parse then-body as arithmetic expression
            expr = self._parse_arith_expr(0)
            self._skip_newlines()
            # Skip #ELSE body if present
            if self._at(TT.PP_ELSE):
                self._advance()
                self._consume_eol()
                self._skip_newlines()
                depth = 1
                while not self._at(TT.EOF) and depth > 0:
                    if self._cur().type in (TT.PP_IFDEF, TT.PP_IFNDEF):
                        depth += 1
                    elif self._cur().type == TT.PP_ENDIF:
                        depth -= 1
                        if depth == 0:
                            break
                    self._advance()
            if self._at(TT.PP_ENDIF):
                self._advance()
                self._consume_eol()
            self._skip_newlines()
            return expr
        # Fallback
        self.warnings.append(
            f"L{t.line}:{t.col}: Unexpected token {t.type.name} ({t.value!r}) "
            f"in arithmetic expression, substituting 0")
        self._advance()
        return ast.NumberLiteral(value=0, **loc)

    def _arith_led_bp(self):
        t = self._cur()
        if t.type == TT.QUESTION:
            return 1  # ternary has lowest precedence
        if t.type == TT.PIPEPIPE:
            return 2
        if t.type == TT.AMPAMP:
            return 3
        if t.type in (TT.EQEQ, TT.BANGEQ, TT.LT, TT.GT_OP, TT.LE, TT.GE):
            return 5
        if t.type in (TT.PLUS, TT.MINUS):
            return 10
        if t.type in (TT.STAR, TT.SLASH):
            return 20
        if t.type == TT.CARET:
            return 25
        if t.type == TT.COLONCOLON:
            return 35  # scope resolution, highest precedence
        return 0

    def _arith_led(self, left, nbp):
        t = self._cur()
        loc = self._loc()
        # Ternary: cond ? then_expr : else_expr
        if t.type == TT.QUESTION:
            self._advance()  # ?
            self._skip_newlines()
            then_expr = self._parse_arith_expr(0)
            self._skip_newlines()
            if self._at(TT.COLON):
                self._advance()  # :
            self._skip_newlines()
            else_expr = self._parse_arith_expr(0)
            return ast.BinaryOp(op='?:', left=left,
                                right=ast.BinaryOp(op=':',
                                                   left=then_expr,
                                                   right=else_expr,
                                                   **loc), **loc)
        op = self._advance().value
        self._skip_newlines()
        right = self._parse_arith_expr(nbp)
        return ast.BinaryOp(op=op, left=left, right=right, **loc)

    # ------------------------------------------------------------------
    # Function call: IDENT(args...)
    # ------------------------------------------------------------------
    def _parse_func_call(self):
        loc = self._loc()
        name = self._advance().value
        self._advance()  # (
        args = []
        while not self._at(TT.RPAREN) and not self._at(TT.EOF):
            if self._at(TT.NEWLINE):
                self._advance()
                continue
            if self._at(TT.COMMA):
                self._advance()
                continue
            args.append(self._parse_arith_expr(0))
        if self._at(TT.RPAREN):
            self._advance()
        return ast.FuncCall(name=name, args=args, **loc)

    # ------------------------------------------------------------------
    # Line expression (for VARIABLE values)
    # ------------------------------------------------------------------
    def _parse_line_expression(self):
        """Parse a simple expression on the rest of the line."""
        loc = self._loc()
        if self._at_eol():
            return None
        # Try to parse as arithmetic expression (handles 0.036+GRID etc.)
        return self._parse_arith_expr(0)

    # ------------------------------------------------------------------
    # Bare expression (fallback for unknown statements in blocks)
    # ------------------------------------------------------------------
    def _parse_bare_expression(self):
        loc = self._loc()
        try:
            expr = self._parse_layer_expr(0)
            self._consume_eol()
            return expr
        except (SVRFParseError, Exception) as e:
            t = self._cur()
            self.warnings.append(
                f"L{t.line}:{t.col}: Exception in bare expression parse: {e}")
            self._skip_to_eol()
            self._consume_eol()
            return None

    # ==================================================================
    # Layer Expression Pratt Parser (CORE)
    # ==================================================================
    def _parse_layer_expr(self, bp):
        """Main Pratt loop for layer expressions."""
        left = self._layer_nud()
        while True:
            nbp = self._layer_led_bp()
            if nbp <= bp:
                break
            left = self._layer_led(left)
        return left

    def _can_start_layer_expr(self):
        """Check if current token can begin a layer expression.

        Uses the prescan symbol table to distinguish layer names from
        SVRF keywords that should terminate operand consumption.
        """
        t = self._cur()
        if t.type in (TT.LPAREN, TT.LBRACKET, TT.INTEGER,
                       TT.FLOAT, TT.STRING, TT.MINUS, TT.BANG):
            return True
        if t.type != TT.IDENT:
            return False
        upper = t.value.upper()
        if upper in self._known_layers:
            return True
        if upper in _EXPR_STARTERS:
            return True
        if upper in _SVRF_KEYWORDS:
            return False
        # Unknown identifier — assume layer name (conservative)
        return True

    # ------------------------------------------------------------------
    # NUD dispatch table: keyword -> handler method name
    # ------------------------------------------------------------------
    _NUD_DISPATCH = {
        'DFM': '_nud_dfm',
        'RET': '_nud_dfm',
        'INT': '_nud_drc_op',
        'EXT': '_nud_drc_op',
        'ENC': '_nud_drc_op',
        'ENCLOSE': '_nud_drc_op',
        'DENSITY': '_nud_drc_op',
        'SIZE': '_nud_size',
        'SHIFT': '_nud_size',
        'AREA': '_nud_area',
        'VERTEX': '_nud_vertex',
        'ANGLE': '_nud_angle',
        'LENGTH': '_nud_length',
        'RECTANGLE': '_nud_rectangle',
        'RECTANGLES': '_nud_rectangles',
        'EXTENTS': '_nud_rectangles',
        'NOT': '_nud_not',
        'COPY': '_nud_copy',
        'PUSH': '_nud_push',
        'MERGE': '_nud_merge',
        'GROW': '_nud_grow_shrink',
        'SHRINK': '_nud_grow_shrink',
        'HOLES': '_nud_holes',
        'DONUT': '_nud_donut',
        'EXTENT': '_nud_extent',
        'STAMP': '_nud_stamp',
        'OFFGRID': '_nud_offgrid',
        'ROTATE': '_nud_rotate',
        'DEVICE': '_nud_device',
        'OR': '_nud_or',
        'XOR': '_nud_xor',
        'AND': '_nud_and',
        'GOOD': '_nud_good',
        'NET': '_nud_net',
        'COIN': '_nud_coin_in',
        'IN': '_nud_coin_in',
        'COINCIDENT': '_nud_coin_in',
        'TOUCH': '_nud_touch',
        'INSIDE': '_nud_inside_outside',
        'OUTSIDE': '_nud_inside_outside',
        'INTERACT': '_nud_prefix_unary_op',
        'CUT': '_nud_prefix_unary_op',
        'WITH': '_nud_with',
        'PATHCHK': '_nud_pathchk',
        'DRAWN': '_nud_drawn',
        'PATH': '_nud_path',
        'CONVEX': '_nud_convex',
        'EXPAND': '_nud_expand',
    }

    # ------------------------------------------------------------------
    # NUD (prefix / atom)
    # ------------------------------------------------------------------
    def _layer_nud(self):
        t = self._cur()
        loc = self._loc()

        if t.type == TT.LPAREN:
            self._advance()
            self._block_depth += 1
            expr = self._parse_layer_expr(0)
            # Skip newlines to find ) — handles multiline (OR\n...\n)
            if self._at(TT.NEWLINE):
                self._skip_newlines()
            if self._at(TT.RPAREN):
                self._advance()
            self._block_depth -= 1
            return expr

        if t.type == TT.LBRACKET:
            return self._parse_bracket_expr()

        if t.type == TT.INTEGER:
            # Digit-prefixed layer name: 15V_GATE_CHECK (adjacent, no space)
            nxt = self._peek()
            if nxt.type == TT.IDENT and nxt.col == t.col + len(str(t.value)):
                name = str(self._advance().value) + self._advance().value
                return ast.LayerRef(name=name, **loc)
            return ast.NumberLiteral(value=self._advance().value, **loc)
        if t.type == TT.FLOAT:
            return ast.NumberLiteral(value=self._advance().value, **loc)
        if t.type == TT.STRING:
            return ast.StringLiteral(value=self._advance().value, **loc)

        if t.type == TT.MINUS:
            self._advance()
            if self._at(TT.INTEGER):
                return ast.NumberLiteral(value=-self._advance().value, **loc)
            if self._at(TT.FLOAT):
                return ast.NumberLiteral(value=-self._advance().value, **loc)
            operand = self._layer_nud()
            return ast.UnaryOp(op='-', operand=operand, **loc)

        if t.type == TT.BANG:
            self._advance()
            operand = self._parse_layer_expr(50)
            return ast.UnaryOp(op='NOT', operand=operand, **loc)

        if t.type != TT.IDENT:
            self.warnings.append(
                f"L{t.line}:{t.col}: Unexpected token {t.type.name} ({t.value!r}) "
                f"in layer expression, substituting 0")
            self._advance()
            return ast.NumberLiteral(value=0, **loc)

        upper = t.value.upper()

        handler_name = self._NUD_DISPATCH.get(upper)
        if handler_name:
            result = getattr(self, handler_name)(t, loc)
            if result is not None:
                return result

        # Function call check
        if self._peek().type == TT.LPAREN:
            nxt = self._peek()
            if nxt.col == t.col + len(t.value):
                return self._parse_func_call()

        # Fallback: treat as layer reference.
        # (The _can_start_layer_expr() guard in greedy loops prevents
        # keywords like OF/BY/LAYER from reaching here in those contexts.)
        self._advance()
        return ast.LayerRef(name=t.value, **loc)

    # ------------------------------------------------------------------
    # NUD handler methods (dispatched from _NUD_DISPATCH)
    # ------------------------------------------------------------------

    def _nud_dfm(self, t, loc):
        return self._parse_dfm_op()

    def _nud_drc_op(self, t, loc):
        return self._parse_drc_op()

    def _nud_size(self, t, loc):
        return self._parse_size_op()

    def _nud_area(self, t, loc):
        return self._parse_area_op()

    def _nud_vertex(self, t, loc):
        return self._parse_unary_constrained_op()

    def _nud_angle(self, t, loc):
        return self._parse_angle_op()

    def _nud_length(self, t, loc):
        return self._parse_length_op()

    def _nud_rectangle(self, t, loc):
        return self._parse_rectangle_op()

    def _nud_rectangles(self, t, loc):
        return self._parse_rectangles_op()

    def _nud_grow_shrink(self, t, loc):
        return self._parse_grow_shrink_op()

    def _nud_extent(self, t, loc):
        return self._parse_extent_op()

    def _nud_stamp(self, t, loc):
        return self._parse_stamp_op()

    def _nud_offgrid(self, t, loc):
        return self._parse_offgrid_op()

    def _nud_with(self, t, loc):
        return self._parse_with_prefix_op()

    def _nud_not(self, t, loc):
        self._advance()
        operand = self._parse_layer_expr(50)
        return ast.UnaryOp(op='NOT', operand=operand, **loc)

    def _nud_copy(self, t, loc):
        self._advance()
        operand = self._parse_layer_expr(50)
        return ast.UnaryOp(op='COPY', operand=operand, **loc)

    def _nud_push(self, t, loc):
        self._advance()
        operand = self._parse_layer_expr(0)
        return ast.UnaryOp(op='PUSH', operand=operand, **loc)

    def _nud_merge(self, t, loc):
        self._advance()
        operand = self._parse_layer_expr(50)
        return ast.UnaryOp(op='MERGE', operand=operand, **loc)

    def _nud_donut(self, t, loc):
        self._advance()
        operand = self._parse_layer_expr(50)
        return ast.UnaryOp(op='DONUT', operand=operand, **loc)

    def _nud_holes(self, t, loc):
        self._advance()
        operand = self._parse_layer_expr(50)
        modifiers = []
        while not self._at_eol() and self._at(TT.IDENT):
            mod_u = self._cur().value.upper()
            if mod_u in _DRC_MODIFIERS:
                modifiers.append(self._advance().value)
            else:
                break
        return ast.DRCOp(op='HOLES', operands=[operand],
                         constraints=[], modifiers=modifiers, **self._loc())

    def _nud_rotate(self, t, loc):
        self._advance()  # ROTATE
        operand = self._parse_layer_expr(50)
        modifiers = []
        while not self._at_eol():
            if self._at(TT.IDENT):
                modifiers.append(self._advance().value)
            elif self._at(TT.INTEGER) or self._at(TT.FLOAT):
                modifiers.append(str(self._advance().value))
            else:
                break
        return ast.DRCOp(op='ROTATE', operands=[operand],
                         constraints=[], modifiers=modifiers, **loc)

    def _nud_or(self, t, loc):
        nxt = self._peek()
        # Also trigger for multiline OR: OR at EOL inside a block
        if nxt.type in (TT.IDENT, TT.LPAREN, TT.INTEGER, TT.FLOAT) or \
                (nxt.type == TT.NEWLINE and self._block_depth > 0):
            self._advance()  # OR
            # Check for OR EDGE variant
            or_op = 'OR'
            if self._at(TT.IDENT) and self._cur().value.upper() == 'EDGE':
                self._advance()  # EDGE
                or_op = 'OR EDGE'
            operands = []
            while True:
                while not self._at_eol() and not self._at(TT.RPAREN) and not self._at(TT.RBRACKET) and self._can_start_layer_expr():
                    operands.append(self._parse_layer_expr(50))
                # Multiline continuation: peek past newlines for more operands
                if self._at_eol() and self._block_depth > 0:
                    saved = self.pos
                    self._consume_eol()
                    self._skip_newlines()
                    if self._can_start_layer_expr() and not self._at(TT.RBRACE):
                        # Don't consume next line if it starts a new statement
                        if self._at(TT.IDENT):
                            nxt_t = self._peek().type
                            if nxt_t == TT.EQUALS or nxt_t == TT.LBRACE:
                                self.pos = saved
                                break
                        # Digit-prefix assignment: INTEGER IDENT EQUALS
                        if self._at(TT.INTEGER):
                            nxt_t = self._peek()
                            if nxt_t.type == TT.IDENT:
                                nxt2 = self._peek(2)
                                if nxt2.type == TT.EQUALS:
                                    self.pos = saved
                                    break
                        continue  # more operands on next line
                    self.pos = saved
                break
            if len(operands) == 0:
                return ast.LayerRef(name='OR', **loc)
            if len(operands) == 1:
                return operands[0]
            # Build left-associative chain
            result = operands[0]
            for op in operands[1:]:
                result = ast.BinaryOp(op=or_op, left=result, right=op, **loc)
            return result
        return None  # fall through to LayerRef

    def _nud_xor(self, t, loc):
        nxt = self._peek()
        if nxt.type in (TT.IDENT, TT.LPAREN, TT.INTEGER, TT.FLOAT):
            self._advance()  # XOR
            operands = []
            while not self._at_eol() and not self._at(TT.RPAREN) and not self._at(TT.RBRACKET) and self._can_start_layer_expr():
                operands.append(self._parse_layer_expr(50))
            if len(operands) == 0:
                return ast.LayerRef(name='XOR', **loc)
            if len(operands) == 1:
                return operands[0]
            result = operands[0]
            for op in operands[1:]:
                result = ast.BinaryOp(op='XOR', left=result, right=op, **loc)
            return result
        return None  # fall through to LayerRef

    def _nud_and(self, t, loc):
        nxt = self._peek()
        if nxt.type in (TT.IDENT, TT.LPAREN, TT.INTEGER, TT.FLOAT):
            self._advance()  # AND
            operands = []
            while not self._at_eol() and not self._at(TT.RPAREN) and not self._at(TT.RBRACKET) and self._can_start_layer_expr():
                operands.append(self._parse_layer_expr(50))
            if len(operands) == 0:
                return ast.LayerRef(name='AND', **loc)
            if len(operands) == 1:
                return operands[0]
            result = operands[0]
            for op in operands[1:]:
                result = ast.BinaryOp(op='AND', left=result, right=op, **loc)
            return result
        return None  # fall through to LayerRef

    def _nud_good(self, t, loc):
        self._advance()  # GOOD
        modifiers = []
        while not self._at_eol():
            if self._at(TT.IDENT):
                modifiers.append(self._advance().value)
            elif self._at(TT.INTEGER) or self._at(TT.FLOAT):
                modifiers.append(str(self._advance().value))
            elif self._at(TT.LPAREN):
                modifiers.append(self._parse_layer_expr(0))
            else:
                break
        return ast.DRCOp(op='GOOD', operands=[],
                         constraints=[], modifiers=modifiers, **loc)

    def _nud_net(self, t, loc):
        nxt = self._peek()
        if nxt.type == TT.IDENT and nxt.value.upper() == 'AREA':
            self._advance()  # NET
            self._advance()  # AREA
            op_name = 'NET AREA'
            if self._at(TT.IDENT) and self._cur().value.upper() == 'RATIO':
                self._advance()  # RATIO
                op_name = 'NET AREA RATIO'
            operands = []
            while self._at(TT.IDENT) and not self._at_eol():
                upper_cur = self._cur().value.upper()
                if upper_cur in ('ACCUMULATE', 'RDB', 'PRINT', 'BY'):
                    break
                operands.append(self._parse_layer_expr(50))
            constraints = []
            if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                constraints = self._parse_constraints()
            modifiers = []
            self._parse_drc_modifiers(modifiers)
            self._parse_drc_multiline_continuation(modifiers)
            return ast.DRCOp(op=op_name, operands=operands,
                             constraints=constraints, modifiers=modifiers, **loc)
        # NET layer "string" ... — generic NET operation
        else:
            self._advance()  # NET
            operands = []
            while not self._at_eol():
                if self._at(TT.IDENT):
                    operands.append(self._parse_layer_expr(50))
                elif self._at(TT.STRING):
                    operands.append(ast.StringLiteral(value=self._advance().value, **self._loc()))
                elif self._at(TT.INTEGER) or self._at(TT.FLOAT):
                    operands.append(ast.NumberLiteral(value=self._advance().value, **self._loc()))
                elif self._at(TT.LPAREN):
                    operands.append(self._parse_layer_expr(0))
                else:
                    break
            return ast.DRCOp(op='NET', operands=operands,
                             constraints=[], modifiers=[], **loc)

    def _nud_coin_in(self, t, loc):
        upper = t.value.upper()
        nxt = self._peek()
        if nxt.type == TT.IDENT:
            nxt_u = nxt.value.upper()
            if nxt_u == 'EDGE':
                self._advance()  # COIN/IN/COINCIDENT
                self._advance()  # EDGE
                operand = self._parse_layer_expr(50)
                return ast.UnaryOp(op=upper + ' EDGE', operand=operand, **loc)
            if nxt_u in ('INSIDE', 'OUTSIDE'):
                nxt2 = self._peek(2)
                if nxt2 and nxt2.type == TT.IDENT and nxt2.value.upper() == 'EDGE':
                    self._advance()  # COIN/IN/COINCIDENT
                    middle = self._advance().value.upper()  # INSIDE/OUTSIDE
                    self._advance()  # EDGE
                    operand = self._parse_layer_expr(50)
                    return ast.UnaryOp(op=upper + ' ' + middle + ' EDGE', operand=operand, **loc)
        return None  # fall through to LayerRef

    def _nud_touch(self, t, loc):
        nxt = self._peek()
        if nxt.type == TT.IDENT:
            nxt_u = nxt.value.upper()
            if nxt_u == 'EDGE':
                self._advance()  # TOUCH
                self._advance()  # EDGE
                left_op = self._parse_layer_expr(50)
                if self._can_start_layer_expr() and not self._at_eol():
                    right_op = self._parse_layer_expr(50)
                    return ast.BinaryOp(op='TOUCH EDGE', left=left_op,
                                        right=right_op, **loc)
                return ast.UnaryOp(op='TOUCH EDGE', operand=left_op, **loc)
            if nxt_u in ('INSIDE', 'OUTSIDE'):
                nxt2 = self._peek(2)
                if nxt2 and nxt2.type == TT.IDENT and nxt2.value.upper() == 'EDGE':
                    self._advance()  # TOUCH
                    middle = self._advance().value.upper()  # INSIDE/OUTSIDE
                    self._advance()  # EDGE
                    left_op = self._parse_layer_expr(50)
                    if self._can_start_layer_expr() and not self._at_eol():
                        right_op = self._parse_layer_expr(50)
                        return ast.BinaryOp(op='TOUCH ' + middle + ' EDGE',
                                            left=left_op, right=right_op, **loc)
                    return ast.UnaryOp(op='TOUCH ' + middle + ' EDGE',
                                       operand=left_op, **loc)
        return None  # fall through to LayerRef

    def _nud_inside_outside(self, t, loc):
        upper = t.value.upper()
        nxt = self._peek()
        if nxt.type == TT.IDENT and nxt.value.upper() == 'EDGE':
            self._advance()  # INSIDE/OUTSIDE
            self._advance()  # EDGE
            left_op = self._parse_layer_expr(50)
            # INSIDE EDGE / OUTSIDE EDGE takes two operands
            if self._can_start_layer_expr() and not self._at_eol():
                right_op = self._parse_layer_expr(50)
                return ast.BinaryOp(op=upper + ' EDGE', left=left_op,
                                    right=right_op, **loc)
            return ast.UnaryOp(op=upper + ' EDGE', operand=left_op, **loc)
        # INSIDE CELL / OUTSIDE CELL: DRC op with cell name + pattern args
        if nxt.type == TT.IDENT and nxt.value.upper() == 'CELL':
            self._advance()  # INSIDE/OUTSIDE
            self._advance()  # CELL
            operands = []
            while not self._at_eol():
                if self._at(TT.IDENT):
                    operands.append(self._parse_layer_expr(50))
                elif self._at(TT.STRING):
                    operands.append(ast.StringLiteral(value=self._advance().value, **self._loc()))
                elif self._at(TT.LPAREN):
                    operands.append(self._parse_layer_expr(0))
                else:
                    break
            return ast.DRCOp(op=upper + ' CELL', operands=operands,
                             constraints=[], modifiers=[], **loc)
        # INSIDE/OUTSIDE as prefix unary op (e.g. NOT INSIDE B)
        self._advance()
        operand = self._parse_layer_expr(50)
        return ast.UnaryOp(op=upper, operand=operand, **loc)

    def _nud_prefix_unary_op(self, t, loc):
        upper = t.value.upper()
        self._advance()
        operand = self._parse_layer_expr(50)
        return ast.UnaryOp(op=upper, operand=operand, **loc)

    def _nud_pathchk(self, t, loc):
        self._advance()  # PATHCHK
        modifiers = []
        while not self._at_eol():
            t_cur = self._cur()
            if t_cur.type == TT.BANG:
                self._advance()
                if self._at(TT.IDENT):
                    modifiers.append('!' + self._advance().value)
                else:
                    modifiers.append('!')
            elif t_cur.type == TT.AMPAMP:
                self._advance()
                modifiers.append('&&')
            elif t_cur.type == TT.IDENT:
                modifiers.append(self._advance().value)
            elif t_cur.type == TT.STRING:
                modifiers.append(self._advance().value)
            else:
                break
        return ast.DRCOp(op='PATHCHK', operands=[],
                         constraints=[], modifiers=modifiers, **loc)

    def _nud_drawn(self, t, loc):
        self._advance()
        keywords = ['DRAWN']
        while self._at(TT.IDENT) and not self._at_eol():
            keywords.append(self._advance().value)
        return ast.Directive(keywords=keywords, arguments=[], **loc)

    def _nud_path(self, t, loc):
        if self._peek().type == TT.IDENT and \
                self._peek().value.upper() == 'LENGTH':
            self._advance()  # PATH
            return self._parse_length_op(op_name='PATH LENGTH')
        return None  # fall through to LayerRef

    def _nud_convex(self, t, loc):
        if self._peek().type == TT.IDENT and \
                self._peek().value.upper() == 'EDGE':
            return self._parse_convex_edge_op()
        return None  # fall through to LayerRef

    def _nud_expand(self, t, loc):
        if self._peek().type == TT.IDENT and \
                self._peek().value.upper() == 'EDGE':
            return self._parse_expand_edge_op()
        if self._peek().type == TT.IDENT and \
                self._peek().value.upper() == 'TEXT':
            self._advance()  # EXPAND
            self._advance()  # TEXT
            modifiers = []
            while not self._at_eol():
                if self._at(TT.IDENT):
                    modifiers.append(self._advance().value)
                elif self._at(TT.STRING):
                    modifiers.append(self._advance().value)
                elif self._at(TT.INTEGER) or self._at(TT.FLOAT):
                    modifiers.append(str(self._advance().value))
                else:
                    break
            return ast.DRCOp(op='EXPAND TEXT', operands=[],
                             constraints=[], modifiers=modifiers, **loc)
        return None  # fall through to LayerRef

    def _nud_device(self, t, loc):
        if self._peek().type == TT.IDENT and \
                self._peek().value.upper() == 'LAYER':
            self._advance()  # DEVICE
            self._advance()  # LAYER
            modifiers = []
            while not self._at_eol():
                if self._at(TT.IDENT):
                    modifiers.append(self._advance().value)
                elif self._at(TT.LPAREN):
                    self._advance()
                    inner = []
                    while not self._at(TT.RPAREN) and not self._at(TT.EOF):
                        inner.append(str(self._advance().value))
                    if self._at(TT.RPAREN):
                        self._advance()
                    modifiers[-1] = modifiers[-1] + '(' + ' '.join(inner) + ')' if modifiers else '(' + ' '.join(inner) + ')'
                else:
                    break
            return ast.DRCOp(op='DEVICE LAYER', operands=[],
                             constraints=[], modifiers=modifiers, **loc)
        return None  # fall through to LayerRef


    # ------------------------------------------------------------------
    # LED binding power
    # ------------------------------------------------------------------
    def _layer_led_bp(self):
        t = self._cur()
        if t.type == TT.NEWLINE or t.type == TT.EOF:
            return 0
        if t.type in (TT.RBRACE, TT.RBRACKET, TT.RPAREN):
            return 0
        if t.type == TT.QUESTION:
            return 1  # ternary has lowest precedence
        if t.type == TT.COLON:
            return 0  # colon terminates the then-branch of ternary
        if t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            return 5
        if t.type == TT.IDENT:
            upper = t.value.upper()
            bp = _LAYER_BP.get(upper, 0)
            if bp:
                # IN EDGE / COIN EDGE: only if followed by EDGE
                # Also handles COIN INSIDE EDGE, COIN OUTSIDE EDGE, etc.
                if upper in ('IN', 'COIN', 'COINCIDENT'):
                    nxt = self._peek()
                    if nxt.type == TT.IDENT:
                        nxt_u = nxt.value.upper()
                        if nxt_u == 'EDGE':
                            return bp
                        if nxt_u in ('INSIDE', 'OUTSIDE'):
                            nxt2 = self._peek(2)
                            if nxt2 and nxt2.type == TT.IDENT and nxt2.value.upper() == 'EDGE':
                                return bp
                    return 0
                # INSIDE EDGE / OUTSIDE EDGE as two-word binary ops
                if upper in ('INSIDE', 'OUTSIDE'):
                    nxt = self._peek()
                    if nxt.type == TT.IDENT and nxt.value.upper() == 'EDGE':
                        return bp
                return bp
            if upper == 'WITH':
                return 35
            if upper == 'SIZE':
                return 5
            if upper in ('HOLES', 'DONUT'):
                return 50
            if upper == 'NET':
                return 5  # NET INTERACT / NET AREA RATIO as infix
            if upper in ('ANGLE', 'LENGTH', 'AREA', 'VERTEX'):
                # Check if followed by constraint (e.g. layer ANGLE == 45)
                nxt = self._peek()
                if nxt.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                    return 5
                return 0
            # CONVEX EDGE as infix: layer CONVEX EDGE == 2
            if upper == 'CONVEX':
                nxt = self._peek()
                if nxt.type == TT.IDENT and nxt.value.upper() == 'EDGE':
                    return 5
                return 0
            # CONNECTED as postfix modifier (e.g. layer1 AND layer2 CONNECTED)
            if upper == 'CONNECTED':
                return 5
            # RECTANGLE as postfix DRC op (e.g. layer RECTANGLE == val BY == val)
            # Also fires for modifier-only: layer RECTANGLE ORTHOGONAL ONLY
            if upper == 'RECTANGLE':
                nxt = self._peek()
                if nxt.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                    return 5
                if nxt.type == TT.IDENT and nxt.value.upper() in (
                        'ORTHOGONAL', 'ONLY', 'ASPECT', 'BY',
                        'SINGULAR', 'ALSO', 'CENTERS'):
                    return 5
                return 0
            # EXPAND EDGE as postfix: (expr) EXPAND EDGE INSIDE BY val
            if upper == 'EXPAND':
                nxt = self._peek()
                if nxt.type == TT.IDENT and nxt.value.upper() == 'EDGE':
                    return 5
                return 0
            # Stop words: don't treat as infix
            if upper in _DRC_MODIFIERS or upper in _DRC_OPS or \
                    upper in _DIRECTIVE_HEADS:
                return 0
            if upper in ('CMACRO', 'PROPERTY', 'IF', 'ELSE'):
                return 0
        # Arithmetic operators as infix in layer expressions (e.g. AA*GT)
        if t.type == TT.CARET:
            return 45
        if t.type == TT.STAR:
            return 40
        if t.type == TT.SLASH:
            return 40
        if t.type == TT.MINUS:
            return 38
        if t.type == TT.PLUS:
            return 36
        return 0

    # ------------------------------------------------------------------
    # LED dispatch table: keyword -> handler method name
    # ------------------------------------------------------------------
    _LED_DISPATCH = {
        'IN': '_led_coin_in_edge',
        'COIN': '_led_coin_in_edge',
        'COINCIDENT': '_led_coin_in_edge',
        'WITH': '_led_with',
        'TOUCH': '_led_touch',
        'HOLES': '_led_holes_donut',
        'DONUT': '_led_holes_donut',
        'ANGLE': '_led_measurement',
        'LENGTH': '_led_measurement',
        'AREA': '_led_measurement',
        'VERTEX': '_led_measurement',
        'CONVEX': '_led_convex',
        'CONNECTED': '_led_connected',
        'RECTANGLE': '_led_rectangle',
        'EXPAND': '_led_expand',
        'NET': '_led_net',
        'SIZE': '_led_size',
        'AND': '_led_binary_op',
        'OR': '_led_binary_op',
        'NOT': '_led_binary_op',
        'XOR': '_led_binary_op',
        'INSIDE': '_led_binary_op',
        'OUTSIDE': '_led_binary_op',
        'OUT': '_led_binary_op',
        'INTERACT': '_led_binary_op',
        'ENCLOSE': '_led_binary_op',
        'CUT': '_led_binary_op',
        'BY': '_led_binary_op',
    }

    # ------------------------------------------------------------------
    # LED (infix)
    # ------------------------------------------------------------------
    def _layer_led(self, left):
        t = self._cur()
        loc = self._loc()

        # Ternary: cond ? then_expr : else_expr
        if t.type == TT.QUESTION:
            self._advance()  # ?
            self._skip_newlines()
            then_expr = self._parse_layer_expr(0)
            self._skip_newlines()
            if self._at(TT.COLON):
                self._advance()  # :
            self._skip_newlines()
            else_expr = self._parse_layer_expr(0)
            return ast.BinaryOp(op='?:', left=left,
                                right=ast.BinaryOp(op=':',
                                                   left=then_expr,
                                                   right=else_expr,
                                                   **loc), **loc)

        # Comparison operators -> constraints + optional trailing modifiers
        if t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
            # Consume trailing DRC modifiers (EVEN, ODD, SINGULAR, ALSO, etc.)
            modifiers = []
            while not self._at_eol() and self._at(TT.IDENT):
                mod_u = self._cur().value.upper()
                if mod_u in _DRC_MODIFIERS or mod_u in ('EVEN', 'ODD',
                        'PRIMARY', 'MULTI', 'NOT', 'MEASURE', 'ALL',
                        'ANNOTATE', 'NODAL', 'GOOD'):
                    modifiers.append(self._advance().value)
                else:
                    break
            return ast.ConstrainedExpr(expr=left, constraints=constraints,
                                       modifiers=modifiers, **loc)

        # Arithmetic infix: ^, *, /, -, +
        if t.type == TT.CARET:
            self._advance()
            right = self._parse_layer_expr(45)
            return ast.BinaryOp(op='^', left=left, right=right, **loc)
        if t.type == TT.STAR:
            self._advance()
            right = self._parse_layer_expr(40)
            return ast.BinaryOp(op='*', left=left, right=right, **loc)
        if t.type == TT.SLASH:
            self._advance()
            right = self._parse_layer_expr(40)
            return ast.BinaryOp(op='/', left=left, right=right, **loc)
        if t.type == TT.MINUS:
            self._advance()
            right = self._parse_layer_expr(38)
            return ast.BinaryOp(op='-', left=left, right=right, **loc)
        if t.type == TT.PLUS:
            self._advance()
            right = self._parse_layer_expr(36)
            return ast.BinaryOp(op='+', left=left, right=right, **loc)

        if t.type == TT.IDENT:
            upper = t.value.upper()
            handler_name = self._LED_DISPATCH.get(upper)
            if handler_name:
                return getattr(self, handler_name)(left, t, loc)

        # Shouldn't reach here, but advance to avoid infinite loop
        self.warnings.append(
            f"L{t.line}:{t.col}: Unexpected token {t.type.name} ({t.value!r}) "
            f"in layer expression LED (infix position)")
        self._advance()
        return left

    # ------------------------------------------------------------------
    # LED handler methods (dispatched from _LED_DISPATCH)
    # ------------------------------------------------------------------

    def _led_coin_in_edge(self, left, t, loc):
        """IN EDGE / COIN EDGE / COIN INSIDE EDGE / COIN OUTSIDE EDGE
        COINCIDENT EDGE / COINCIDENT INSIDE EDGE / COINCIDENT OUTSIDE EDGE"""
        upper = t.value.upper()
        self._advance()  # IN or COIN or COINCIDENT
        middle = ''
        if self._at(TT.IDENT) and self._cur().value.upper() in ('INSIDE', 'OUTSIDE'):
            middle = ' ' + self._advance().value.upper()
        self._advance()  # EDGE
        op = upper + middle + ' EDGE'
        if self._at_eol() and self._block_depth > 0:
            self._consume_eol()
            self._skip_newlines()
        right = self._parse_layer_expr(30)
        result = ast.BinaryOp(op=op, left=left, right=right, **loc)
        return self._maybe_trailing_modifiers(result, loc)

    def _led_with(self, left, t, loc):
        """WITH -> parse_with_op"""
        return self._parse_with_op(left)

    def _led_touch(self, left, t, loc):
        """TOUCH / TOUCH EDGE / TOUCH INSIDE EDGE / TOUCH OUTSIDE EDGE"""
        self._advance()
        if self._at(TT.IDENT) and self._cur().value.upper() in ('INSIDE', 'OUTSIDE'):
            middle = self._cur().value.upper()
            nxt = self._peek()
            if nxt.type == TT.IDENT and nxt.value.upper() == 'EDGE':
                self._advance()  # INSIDE/OUTSIDE
                self._advance()  # EDGE
                if self._at_eol() and self._block_depth > 0:
                    self._consume_eol()
                    self._skip_newlines()
                right = self._parse_layer_expr(30)
                result = ast.BinaryOp(op='TOUCH ' + middle + ' EDGE',
                                    left=left, right=right, **loc)
                return self._maybe_trailing_modifiers(result, loc)
        if self._at_val('EDGE'):
            self._advance()
            if self._at_eol() and self._block_depth > 0:
                self._consume_eol()
                self._skip_newlines()
            right = self._parse_layer_expr(30)
            result = ast.BinaryOp(op='TOUCH EDGE', left=left,
                                right=right, **loc)
            return self._maybe_trailing_modifiers(result, loc)
        right = self._parse_layer_expr(30)
        result = ast.BinaryOp(op='TOUCH', left=left,
                            right=right, **loc)
        return self._maybe_trailing_modifiers(result, loc)

    def _led_holes_donut(self, left, t, loc):
        """HOLES / DONUT as postfix: layer HOLES -> HOLES layer"""
        upper = t.value.upper()
        self._advance()
        modifiers = []
        while not self._at_eol() and self._at(TT.IDENT):
            mod_u = self._cur().value.upper()
            if mod_u in _DRC_MODIFIERS:
                modifiers.append(self._advance().value)
            else:
                break
        return ast.DRCOp(op=upper, operands=[left],
                         constraints=[], modifiers=modifiers, **loc)

    def _led_measurement(self, left, t, loc):
        """ANGLE/LENGTH/AREA/VERTEX as infix measurement: layer ANGLE == 45"""
        upper = t.value.upper()
        self._advance()  # ANGLE/LENGTH/AREA/VERTEX
        constraints = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE,
                                TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
        modifiers = []
        while not self._at_eol() and self._at(TT.IDENT):
            mod_u = self._cur().value.upper()
            if mod_u in _DRC_MODIFIERS or mod_u in (
                    'SINGULAR', 'ALSO', 'EVEN', 'ODD',
                    'PRIMARY', 'MULTI', 'NODAL', 'GOOD'):
                modifiers.append(self._advance().value)
            else:
                break
        return ast.DRCOp(op=upper, operands=[left],
                         constraints=constraints, modifiers=modifiers, **loc)

    def _led_convex(self, left, t, loc):
        """CONVEX EDGE as infix: layer CONVEX EDGE == 2"""
        self._advance()  # CONVEX
        if self._at_val('EDGE'):
            self._advance()  # EDGE
        operands = [left]
        # Consume optional modifiers like ANGLE1, ANGLE2, WITH LENGTH
        modifiers = []
        constraints = []
        while not self._at_eol() and not self._at(TT.RPAREN):
            if self._at(TT.IDENT):
                mod_u = self._cur().value.upper()
                if mod_u in ('ANGLE1', 'ANGLE2'):
                    modifiers.append(self._advance().value)
                    if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE,
                                            TT.EQEQ, TT.BANGEQ):
                        constraints.extend(self._parse_constraints())
                elif mod_u == 'WITH':
                    # WITH LENGTH <= val etc.
                    modifiers.append(self._advance().value)
                    while not self._at_eol() and not self._at(TT.RPAREN):
                        if self._at(TT.IDENT):
                            modifiers.append(self._advance().value)
                        elif self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE,
                                                  TT.EQEQ, TT.BANGEQ):
                            constraints.extend(self._parse_constraints())
                            break
                        else:
                            break
                elif mod_u in _DRC_MODIFIERS:
                    modifiers.append(self._advance().value)
                else:
                    break
            elif self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE,
                                      TT.EQEQ, TT.BANGEQ):
                constraints.extend(self._parse_constraints())
            else:
                break
        return ast.DRCOp(op='CONVEX EDGE', operands=operands,
                         constraints=constraints, modifiers=modifiers, **loc)

    def _led_connected(self, left, t, loc):
        """CONNECTED as postfix modifier: layer1 AND layer2 CONNECTED"""
        self._advance()  # CONNECTED
        return ast.DRCOp(op='CONNECTED', operands=[left],
                         constraints=[], modifiers=[], **loc)

    def _led_rectangle(self, left, t, loc):
        """RECTANGLE as postfix: layer RECTANGLE == val BY == val"""
        self._advance()  # RECTANGLE
        constraints = []
        modifiers = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE,
                                TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
        # BY == value (second dimension constraint)
        if self._at_val('BY'):
            self._advance()  # BY
            constraints.append(ast.Constraint(op='BY', value=None, **loc))
            if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE,
                                    TT.EQEQ, TT.BANGEQ):
                constraints.extend(self._parse_constraints())
        while not self._at_eol() and self._at(TT.IDENT):
            mod_u = self._cur().value.upper()
            if mod_u in _DRC_MODIFIERS or mod_u in ('ASPECT',):
                modifiers.append(self._advance().value)
                # ASPECT may be followed by a constraint: ASPECT == 1
                if mod_u == 'ASPECT' and not self._at_eol() and \
                        self._cur().type in (TT.LT, TT.GT_OP, TT.LE,
                                             TT.GE, TT.EQEQ, TT.BANGEQ):
                    constraints.extend(self._parse_constraints())
            else:
                break
        return ast.DRCOp(op='RECTANGLE', operands=[left],
                         constraints=constraints, modifiers=modifiers, **loc)

    def _led_expand(self, left, t, loc):
        """EXPAND EDGE as postfix: (expr) EXPAND EDGE INSIDE BY val"""
        self._advance()  # EXPAND
        self._advance()  # EDGE
        modifiers = []
        while not self._at_eol():
            if self._at(TT.IDENT):
                upper_cur = self._cur().value.upper()
                if upper_cur in ('INSIDE', 'OUTSIDE'):
                    modifiers.append(self._advance().value)
                    if self._at_val('BY'):
                        modifiers.append(self._advance().value)
                        # bp=35 allows arithmetic but blocks OUTSIDE(30)
                        if not self._at_eol():
                            modifiers.append(self._parse_layer_expr(35))
                else:
                    modifiers.append(self._advance().value)
            elif self._at(TT.INTEGER) or self._at(TT.FLOAT):
                modifiers.append(str(self._advance().value))
            else:
                break
        return ast.DRCOp(op='EXPAND EDGE', operands=[left],
                         constraints=[], modifiers=modifiers, **loc)

    def _led_net(self, left, t, loc):
        """NET as infix: layer NET INTERACT/AREA RATIO layer > value"""
        self._advance()  # NET
        # Build compound op name: NET INTERACT, NET AREA, NET AREA RATIO
        op_name = 'NET'
        while self._at(TT.IDENT) and not self._at_eol():
            nxt_u = self._cur().value.upper()
            if nxt_u in ('INTERACT', 'AREA', 'RATIO'):
                op_name += ' ' + self._advance().value.upper()
            else:
                break
        operands = [left]
        while self._at(TT.IDENT) and not self._at_eol():
            upper_cur = self._cur().value.upper()
            if upper_cur in ('ACCUMULATE', 'RDB', 'PRINT', 'BY'):
                break
            operands.append(self._parse_layer_expr(50))
        constraints = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
        modifiers = []
        self._parse_drc_modifiers(modifiers)
        self._parse_drc_multiline_continuation(modifiers)
        return ast.DRCOp(op=op_name, operands=operands,
                         constraints=constraints, modifiers=modifiers, **loc)

    def _led_size(self, left, t, loc):
        """SIZE as infix: (expr) SIZE BY value modifiers"""
        # Reuse _parse_size_op but inject left as the operand
        self._advance()  # SIZE
        modifiers = []
        if self._at_val('BY'):
            self._advance()
            by_expr = self._parse_layer_expr(35)
            modifiers.append(by_expr)
        while not self._at_eol():
            if self._at(TT.IDENT):
                mod_u = self._cur().value.upper()
                if mod_u in ('UNDEROVER', 'OVERUNDER', 'INSIDE', 'OUTSIDE',
                             'GROW', 'SHRINK'):
                    modifiers.append(self._advance().value)
                elif mod_u in ('OF', 'STEP', 'LAYER', 'TRUNCATE'):
                    modifiers.append(self._advance().value)
                    if not self._at_eol():
                        modifiers.append(self._parse_layer_expr(50))
                else:
                    break
            elif self._at(TT.INTEGER) or self._at(TT.FLOAT):
                modifiers.append(self._parse_layer_expr(50))
            elif self._at(TT.LPAREN):
                modifiers.append(self._parse_layer_expr(50))
            elif self._at(TT.STAR):
                self._advance()
                modifiers.append('*')
            else:
                break
        return ast.DRCOp(op='SIZE', operands=[left],
                         constraints=[], modifiers=modifiers, **loc)

    def _led_binary_op(self, left, t, loc):
        """Standard binary ops (AND, OR, NOT, INSIDE, OUTSIDE, etc.)"""
        upper = t.value.upper()
        bp = _LAYER_BP.get(upper, 0)
        if not bp:
            return None
        self._advance()
        # INSIDE EDGE / OUTSIDE EDGE / TOUCH EDGE as two-word binary ops
        if upper in ('INSIDE', 'OUTSIDE', 'OUT', 'TOUCH') and self._at(TT.IDENT) and self._cur().value.upper() == 'EDGE':
            self._advance()  # EDGE
            if self._at_eol() and self._block_depth > 0:
                self._consume_eol()
                self._skip_newlines()
            right = self._parse_layer_expr(bp)
            result = ast.BinaryOp(op=upper + ' EDGE', left=left,
                                right=right, **loc)
            return self._maybe_trailing_modifiers(result, loc)
        # INSIDE OF [LAYER] expr as compound binary op
        if upper == 'INSIDE' and self._at(TT.IDENT) and self._cur().value.upper() == 'OF':
            self._advance()  # OF
            if self._at(TT.IDENT) and self._cur().value.upper() == 'LAYER':
                self._advance()  # LAYER
            right = self._parse_layer_expr(bp)
            return ast.BinaryOp(op='INSIDE OF', left=left,
                                right=right, **loc)
        # OR EDGE as two-word binary op
        if upper == 'OR' and self._at(TT.IDENT) and self._cur().value.upper() == 'EDGE':
            self._advance()  # EDGE
            # Right operand may be on the next line (e.g. OR EDGE\n  (EXT ...))
            if self._at_eol() and self._block_depth > 0:
                self._consume_eol()
                self._skip_newlines()
            right = self._parse_layer_expr(bp)
            result = ast.BinaryOp(op='OR EDGE', left=left,
                                right=right, **loc)
            return self._maybe_trailing_modifiers(result, loc)
        # NOT TOUCH / NOT TOUCH EDGE as compound binary ops
        if upper == 'NOT' and self._at(TT.IDENT) and self._cur().value.upper() == 'TOUCH':
            self._advance()  # TOUCH
            op_name = 'NOT TOUCH'
            if self._at(TT.IDENT) and self._cur().value.upper() == 'EDGE':
                self._advance()  # EDGE
                op_name = 'NOT TOUCH EDGE'
            if self._at_eol() and self._block_depth > 0:
                self._consume_eol()
                self._skip_newlines()
            right = self._parse_layer_expr(bp)
            result = ast.BinaryOp(op=op_name, left=left,
                                right=right, **loc)
            return self._maybe_trailing_modifiers(result, loc)
        # NOT INSIDE / NOT INTERACT / NOT ENCLOSE / NOT CUT [EDGE] as compound binary ops
        if upper == 'NOT' and self._at(TT.IDENT) and self._cur().value.upper() in (
                'INSIDE', 'INTERACT', 'ENCLOSE', 'CUT'):
            not_rhs = self._advance().value.upper()
            op_name = 'NOT ' + not_rhs
            # NOT INSIDE EDGE / NOT ENCLOSE EDGE etc.
            if self._at(TT.IDENT) and self._cur().value.upper() == 'EDGE':
                self._advance()
                op_name += ' EDGE'
            if self._at_eol() and self._block_depth > 0:
                self._consume_eol()
                self._skip_newlines()
            right = self._parse_layer_expr(bp)
            result = ast.BinaryOp(op=op_name, left=left, right=right, **loc)
            return self._maybe_trailing_modifiers(result, loc)
        # NOT IN / NOT OUT / NOT OUTSIDE [EDGE] as compound binary ops
        if upper == 'NOT' and self._at(TT.IDENT) and self._cur().value.upper() in ('IN', 'OUT', 'OUTSIDE'):
            not_rhs = self._advance().value.upper()  # IN/OUT/OUTSIDE
            op_name = 'NOT ' + not_rhs
            # NOT OUT EDGE / NOT OUTSIDE EDGE
            if not_rhs in ('OUT', 'OUTSIDE') and \
                    self._at(TT.IDENT) and self._cur().value.upper() == 'EDGE':
                self._advance()  # EDGE
                op_name += ' EDGE'
            if self._at_eol() and self._block_depth > 0:
                self._consume_eol()
                self._skip_newlines()
            right = self._parse_layer_expr(bp)
            result = ast.BinaryOp(op=op_name, left=left,
                                right=right, **loc)
            return self._maybe_trailing_modifiers(result, loc)
        # ENCLOSE RECTANGLE: compound DRC op
        if upper == 'ENCLOSE' and self._at(TT.IDENT) and self._cur().value.upper() == 'RECTANGLE':
            self._advance()  # RECTANGLE
            operands = [left]
            while not self._at_eol():
                t = self._cur()
                if t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                    break
                if t.type == TT.IDENT and t.value.upper() in _DRC_MODIFIERS:
                    break
                if t.type == TT.IDENT and t.value.upper() in ('ASPECT', 'BY'):
                    break
                if t.type in (TT.IDENT, TT.INTEGER, TT.FLOAT, TT.LPAREN, TT.LBRACKET):
                    # bp=35 allows arithmetic (+/-) but blocks spatial ops
                    operands.append(self._parse_layer_expr(35))
                else:
                    break
            constraints = []
            if not self._at_eol() and self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                constraints = self._parse_constraints()
            modifiers = []
            while not self._at_eol():
                t = self._cur()
                if t.type == TT.IDENT:
                    modifiers.append(self._advance().value)
                elif t.type in (TT.INTEGER, TT.FLOAT):
                    modifiers.append(str(self._advance().value))
                else:
                    break
            return ast.DRCOp(op='ENCLOSE RECTANGLE', operands=operands,
                             constraints=constraints, modifiers=modifiers, **loc)
        # Infix OR/AND: right operand may be on the next line
        if upper in ('OR', 'AND') and self._at_eol() and self._block_depth > 0:
            self._consume_eol()
            self._skip_newlines()
        right = self._parse_layer_expr(bp)
        result = ast.BinaryOp(op=upper, left=left,
                            right=right, **loc)
        # Infix OR/AND: chain additional operands on the same line
        # e.g. A OR B C D -> OR(OR(OR(A,B),C),D)
        if upper in ('OR', 'AND'):
            while not self._at_eol() and not self._at(TT.RPAREN) and \
                    not self._at(TT.RBRACKET) and self._can_start_layer_expr():
                extra = self._parse_layer_expr(bp)
                result = ast.BinaryOp(op=upper, left=result,
                                    right=extra, **loc)
        # Spatial ops can have trailing constraints + modifiers
        if upper in ('INTERACT', 'INSIDE', 'OUTSIDE', 'OUT',
                     'ENCLOSE', 'TOUCH', 'CUT'):
            return self._maybe_trailing_modifiers(result, loc)
        return result

    # ------------------------------------------------------------------
    # Trailing modifiers after compound binary ops (ENDPOINT ONLY, etc.)
    # ------------------------------------------------------------------
    def _maybe_trailing_modifiers(self, result, loc):
        """Consume optional trailing constraints + modifiers after a binary op."""
        constraints = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE,
                                TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
        modifiers = []
        while not self._at_eol() and self._at(TT.IDENT):
            mod_u = self._cur().value.upper()
            if mod_u in _DRC_MODIFIERS or mod_u in (
                    'SINGULAR', 'ALSO', 'EVEN', 'ODD',
                    'PRIMARY', 'MULTI', 'NODAL', 'GOOD',
                    'CONNECTED', 'NOT', 'MEASURE', 'ALL',
                    'ANNOTATE', 'ENDPOINT', 'ONLY'):
                modifiers.append(self._advance().value)
            else:
                break
        if constraints or modifiers:
            return ast.ConstrainedExpr(expr=result,
                                       constraints=constraints,
                                       modifiers=modifiers, **loc)
        return result

    # ------------------------------------------------------------------
    # Constraints: chain of < > <= >= == != with values
    # ------------------------------------------------------------------
    def _parse_constraints(self):
        constraints = []
        while self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE,
                                    TT.EQEQ, TT.BANGEQ):
            loc = self._loc()
            op = self._advance().value
            val = None
            if self._at(TT.INTEGER):
                val = self._advance().value
            elif self._at(TT.FLOAT):
                val = self._advance().value
            elif self._at(TT.MINUS):
                self._advance()
                if self._at(TT.INTEGER):
                    val = -self._advance().value
                elif self._at(TT.FLOAT):
                    val = -self._advance().value
            elif self._at(TT.IDENT):
                val = self._advance().value
            elif self._at(TT.LPAREN):
                # Parenthesized expression as constraint value — parse at bp=10
                # to avoid consuming the next chained constraint (bp=5 for comparisons)
                self._advance()  # (
                val = self._parse_layer_expr(0)
                if self._at(TT.RPAREN):
                    self._advance()  # )
            constraints.append(ast.Constraint(op=op, value=val, **loc))
        return constraints

    # ------------------------------------------------------------------
    # Bracket expression: [layer_expr]
    # ------------------------------------------------------------------
    def _parse_bracket_expr(self):
        loc = self._loc()
        self._advance()  # [
        expr = self._parse_layer_expr(0)
        if self._at(TT.RBRACKET):
            self._advance()
        return expr

    def _consume_bracket_block(self):
        """Consume tokens from [ to matching ], handling nesting and newlines.

        Returns a string of the bracket content (excluding delimiters).
        Used for multi-line bracket expressions in DRC ops where the Pratt
        parser cannot handle the complex arithmetic spanning multiple lines.
        """
        self._advance()  # [
        depth = 1
        parts = []
        while depth > 0 and not self._at(TT.EOF):
            t = self._cur()
            if t.type == TT.LBRACKET:
                depth += 1
                parts.append('[')
            elif t.type == TT.RBRACKET:
                depth -= 1
                if depth > 0:
                    parts.append(']')
            elif t.type == TT.NEWLINE:
                parts.append(' ')
            else:
                parts.append(str(t.value))
            self._advance()
        return ' '.join(parts).strip()
