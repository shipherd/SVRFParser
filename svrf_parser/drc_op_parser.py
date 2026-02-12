"""DRC operation parsing mixin for the SVRF parser."""

from .tokens import TokenType, Token
from . import ast_nodes as ast
from .parser_base import _DRC_OPS, _DRC_MODIFIERS, _DIRECTIVE_HEADS, _SVRF_KEYWORDS

TT = TokenType


class DRCOpMixin:
    """Mixin providing DRC operation parsing for the SVRF parser."""

    # Known keywords that can start a DRC modifier continuation line
    _MOD_CONTINUATION = frozenset({
        'RDB', 'PRINT', 'POLYGON', 'ACCUMULATE', 'ALSO', 'ONLY',
    })

    def _parse_drc_modifiers(self, modifiers):
        """Consume DRC modifiers (greedy until EOL) and append to list."""
        while not self._at_eol():
            t = self._cur()
            if t.type == TT.IDENT:
                modifiers.append(self._advance().value)
            elif t.type in (TT.INTEGER, TT.FLOAT):
                modifiers.append(str(self._advance().value))
            elif t.type == TT.STRING:
                modifiers.append(self._advance().value)
            elif t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                for c in self._parse_constraints():
                    modifiers.append(f"{c.op}{c.value}")
            elif t.type == TT.LBRACKET:
                be = self._parse_bracket_expr()
                modifiers.append(be)
            elif t.type == TT.MINUS:
                self._advance()
                if self._at(TT.INTEGER):
                    modifiers.append(str(-self._advance().value))
                elif self._at(TT.FLOAT):
                    modifiers.append(str(-self._advance().value))
                else:
                    modifiers.append('-')
            elif t.type in (TT.PLUS, TT.STAR, TT.SLASH, TT.CARET):
                # Arithmetic operators in modifier values (e.g. 0.079+TOLERANCE)
                modifiers.append(str(self._advance().value))
            elif t.type == TT.LPAREN:
                # Balanced parenthesized sub-expression in modifiers
                # e.g. (OPPOSITE 0) or (value+offset)
                self._advance()  # (
                depth = 1
                parts = ['(']
                while not self._at(TT.EOF) and depth > 0:
                    ct = self._cur()
                    if ct.type == TT.LPAREN:
                        depth += 1
                    elif ct.type == TT.RPAREN:
                        depth -= 1
                        if depth == 0:
                            self._advance()
                            parts.append(')')
                            break
                    parts.append(str(self._advance().value))
                modifiers.append(' '.join(parts))
            elif t.type == TT.BANG:
                # ! used in modifier context (e.g. !CONNECTED)
                modifiers.append(str(self._advance().value))
            elif t.type == TT.COMMA:
                # Comma separating modifier values
                modifiers.append(str(self._advance().value))
            else:
                # Stop at true expression boundary tokens (RPAREN, RBRACE, etc.)
                break

    def _parse_drc_multiline_continuation(self, modifiers):
        """Handle multi-line DRC op continuations (bracket blocks + modifier lines).

        After the single-line modifier loop ends at EOL, this method peeks past
        newlines for:
          1. [ ... ] bracket expressions (possibly multi-line)
          2. Lines starting with known modifier keywords (RDB, PRINT, etc.)
        and continues consuming modifiers from those continuation lines.
        """
        if self._block_depth == 0:
            return
        while self._at_eol():
            saved = self.pos
            self._consume_eol()
            self._skip_newlines()
            if self._at(TT.LBRACKET):
                # Multi-line bracket expression
                bracket_str = self._consume_bracket_block()
                modifiers.append(bracket_str)
                self._parse_drc_modifiers(modifiers)
            elif (self._at(TT.IDENT) and
                  self._cur().value.upper() in self._MOD_CONTINUATION):
                # Modifier continuation line (e.g. RDB ... BY LAYER)
                self._parse_drc_modifiers(modifiers)
            else:
                self.pos = saved
                break

    # ------------------------------------------------------------------
    # DRC operations: INT/EXT/ENC/DENSITY layer [layer] constraints mods
    # ------------------------------------------------------------------
    def _parse_drc_op(self):
        loc = self._loc()
        op = self._advance().value.upper()  # INT/EXT/ENC/DENSITY
        # ENCLOSE RECTANGLE / ENC RECTANGLE: two-word DRC op
        if op in ('ENC', 'ENCLOSE') and self._at(TT.IDENT) and \
                self._cur().value.upper() == 'RECTANGLE':
            op = op + ' RECTANGLE'
            self._advance()
        operands = []
        constraints = []
        modifiers = []

        # Collect operands (layer refs, bracket exprs)
        while not self._at_eol():
            t = self._cur()
            if t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                break
            if t.type == TT.IDENT and t.value.upper() in _DRC_MODIFIERS:
                break
            if t.type == TT.LBRACKET:
                # Bracket exprs may contain special syntax (!,  -=, function calls)
                # that the Pratt parser can't handle; consume as string
                content = self._consume_bracket_block()
                operands.append(ast.StringLiteral(value=content, **self._loc()))
                continue
            if t.type == TT.LPAREN:
                self._advance()
                expr = self._parse_layer_expr(0)
                if self._at(TT.RPAREN):
                    self._advance()
                operands.append(expr)
                continue
            if t.type == TT.IDENT:
                operands.append(ast.LayerRef(name=self._advance().value,
                                             **self._loc()))
                continue
            break

        # Constraints
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()

        # Modifiers (greedy until EOL)
        self._parse_drc_modifiers(modifiers)
        self._parse_drc_multiline_continuation(modifiers)

        return ast.DRCOp(op=op, operands=operands,
                         constraints=constraints, modifiers=modifiers, **loc)

    # ------------------------------------------------------------------
    # DFM operations: DFM PROPERTY/DV/SPACE/COPY/TEXT/DP ...
    # ------------------------------------------------------------------
    def _parse_dfm_op(self):
        loc = self._loc()
        self._advance()  # DFM
        sub_op = ''
        if self._at(TT.IDENT):
            sub_op = self._advance().value.upper()
        op = 'DFM ' + sub_op if sub_op else 'DFM'
        # DFM DP has a sub-sub-op (CONFLICT, RING, WARNING, MASK0, MASK1)
        if sub_op == 'DP' and self._at(TT.IDENT):
            dp_sub = self._advance().value.upper()
            op = 'DFM DP ' + dp_sub
        # DFM PROPERTY NET is a sub-command for net-level properties
        if sub_op == 'PROPERTY' and self._at(TT.IDENT) and self._cur().value.upper() == 'NET':
            self._advance()  # NET
            op = 'DFM PROPERTY NET'
        operands = []
        constraints = []
        modifiers = []
        # Collect operands (layer refs, bracket exprs, paren exprs)
        while not self._at_eol():
            t = self._cur()
            if t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                break
            if t.type == TT.IDENT and t.value.upper() in _DRC_MODIFIERS:
                break
            if t.type == TT.IDENT and t.value.upper() == 'DVPARAMS':
                break
            if t.type == TT.IDENT and t.value.upper() in ('NOT', 'MEASURE',
                    'ANNOTATE', 'NODAL', 'MULTI', 'PRIMARY',
                    'OVERLAP', 'ABUT', 'ALSO', 'ACCUMULATE',
                    'GOOD', 'EVEN', 'ODD', 'ALL',
                    'PROPERTY', 'NUMBER', 'INVALID'):
                break
            if t.type == TT.LBRACKET:
                # Bracket exprs may contain special syntax (-=, +=, function calls)
                content = self._consume_bracket_block()
                operands.append(ast.StringLiteral(value=content, **self._loc()))
                continue
            if t.type == TT.LPAREN:
                # Check for parenthesized modifier like (OPPOSITE 0)
                nxt = self._peek()
                if nxt.type == TT.IDENT and nxt.value.upper() in (
                        'OPPOSITE', 'PARALLEL', 'PERPENDICULAR'):
                    self._advance()  # (
                    while not self._at(TT.RPAREN) and not self._at_eol():
                        if self._at(TT.IDENT):
                            modifiers.append(self._advance().value)
                        elif self._at(TT.INTEGER) or self._at(TT.FLOAT):
                            modifiers.append(str(self._advance().value))
                        else:
                            _st = self._cur()
                            self.warnings.append(
                                f"L{_st.line}:{_st.col}: Unexpected token {_st.type.name} "
                                f"({_st.value!r}) in DFM parenthesized modifier, skipping")
                            self._advance()
                    if self._at(TT.RPAREN):
                        self._advance()
                    continue
                self._advance()
                expr = self._parse_layer_expr(0)
                if self._at(TT.RPAREN):
                    self._advance()
                operands.append(expr)
                continue
            if t.type == TT.IDENT:
                operands.append(ast.LayerRef(name=self._advance().value,
                                             **self._loc()))
                continue
            break

        # DFM COPY multiline continuation: operand lists can span lines
        # Pattern: DFM COPY\n  (EXT ...)\n  (INT ...)\n  layerRef\n  ...
        if sub_op == 'COPY':
            while self._at_eol():
                saved = self.pos
                self._consume_eol()
                self._skip_newlines()
                t = self._cur()
                # Parenthesized expression on next line
                if t.type == TT.LPAREN:
                    self._advance()  # (
                    expr = self._parse_layer_expr(0)
                    if self._at(TT.RPAREN):
                        self._advance()
                    operands.append(expr)
                    continue
                # Bare layer ref on next line (not a new statement)
                if t.type == TT.IDENT:
                    nxt_t = self._peek().type
                    # Stop if it looks like a new statement
                    if nxt_t == TT.EQUALS or nxt_t == TT.LBRACE:
                        self.pos = saved
                        break
                    if t.value.upper() in _DIRECTIVE_HEADS or t.value.upper() in _SVRF_KEYWORDS:
                        self.pos = saved
                        break
                    operands.append(ast.LayerRef(name=self._advance().value,
                                                 **self._loc()))
                    continue
                # Anything else — not a continuation
                self.pos = saved
                break

        # DFM PROPERTY multiline continuation: operand lists can span lines
        if sub_op == 'PROPERTY':
            _dfm_mod_stop = frozenset({
                'NOT', 'MEASURE', 'ANNOTATE', 'NODAL', 'MULTI', 'PRIMARY',
                'OVERLAP', 'ABUT', 'ALSO', 'ACCUMULATE',
                'GOOD', 'EVEN', 'ODD', 'ALL',
                'PROPERTY', 'NUMBER', 'INVALID',
            })
            while self._at_eol():
                saved = self.pos
                self._consume_eol()
                self._skip_newlines()
                # Scan ahead: is this line purely IDENT tokens?
                scan = self.pos
                ident_count = 0
                looks_like_operands = False
                while scan < self.length:
                    st = self.tokens[scan]
                    if st.type in (TT.NEWLINE, TT.EOF):
                        looks_like_operands = ident_count > 0
                        break
                    if st.type == TT.IDENT:
                        u = st.value.upper()
                        if u in _dfm_mod_stop or u in _DRC_MODIFIERS:
                            looks_like_operands = ident_count > 0
                            break
                        ident_count += 1
                    else:
                        break  # non-IDENT token → not a continuation
                    scan += 1
                if not looks_like_operands:
                    self.pos = saved
                    break
                # Consume operands from this continuation line
                while not self._at_eol():
                    t = self._cur()
                    if t.type == TT.IDENT and t.value.upper() in _DRC_MODIFIERS:
                        break
                    if t.type == TT.IDENT and t.value.upper() in _dfm_mod_stop:
                        break
                    if t.type == TT.IDENT:
                        operands.append(ast.LayerRef(
                            name=self._advance().value, **self._loc()))
                    else:
                        break

        # Constraints
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
        # Modifiers (greedy until EOL)
        while not self._at_eol():
            t = self._cur()
            if t.type == TT.IDENT:
                modifiers.append(self._advance().value)
            elif t.type in (TT.INTEGER, TT.FLOAT):
                modifiers.append(str(self._advance().value))
            elif t.type == TT.STRING:
                modifiers.append(self._advance().value)
            elif t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                for c in self._parse_constraints():
                    modifiers.append(f"{c.op}{c.value}")
            elif t.type == TT.LBRACKET:
                content = self._consume_bracket_block()
                modifiers.append(ast.StringLiteral(value=content, **self._loc()))
            elif t.type == TT.LPAREN:
                self._advance()
                expr = self._parse_layer_expr(0)
                if self._at(TT.RPAREN):
                    self._advance()
                modifiers.append(expr)
            elif t.type == TT.MINUS:
                self._advance()
                if self._at(TT.INTEGER):
                    modifiers.append(str(-self._advance().value))
                elif self._at(TT.FLOAT):
                    modifiers.append(str(-self._advance().value))
                else:
                    modifiers.append('-')
            elif t.type in (TT.PLUS, TT.STAR, TT.SLASH, TT.CARET):
                modifiers.append(str(self._advance().value))
            elif t.type in (TT.BANG, TT.COMMA):
                modifiers.append(str(self._advance().value))
            else:
                break
        return ast.DRCOp(op=op, operands=operands,
                         constraints=constraints, modifiers=modifiers, **loc)

    # ------------------------------------------------------------------
    # SIZE layer BY value [UNDEROVER|OVERUNDER]
    # ------------------------------------------------------------------
    def _parse_size_op(self):
        loc = self._loc()
        op = self._advance().value.upper()  # SIZE or SHIFT
        operand = self._parse_layer_expr(50)
        modifiers = []
        if self._at_val('BY'):
            self._advance()
            # Parse the BY value as an expression to handle arithmetic
            # like SIZE BY 31.5/2 or SIZE BY (VIA0_W_1+VIA0_R_3_S2)*8+GRID
            by_expr = self._parse_layer_expr(35)
            modifiers.append(by_expr)
        # Optional modifiers: INSIDE OF layer, STEP value, UNDEROVER, etc.
        while not self._at_eol():
            if self._at(TT.IDENT):
                upper = self._cur().value.upper()
                if upper in ('UNDEROVER', 'OVERUNDER', 'INSIDE', 'OUTSIDE',
                             'GROW', 'SHRINK'):
                    modifiers.append(self._advance().value)
                elif upper in ('BEVEL', 'CORNER', 'ACUTE', 'OBTUSE', 'CONVEX'):
                    modifiers.append(self._advance().value)
                    # These modifiers can take a numeric argument
                    if not self._at_eol() and self._at(TT.INTEGER):
                        modifiers.append(self._advance().value)
                elif upper in ('OF', 'STEP', 'LAYER', 'TRUNCATE'):
                    modifiers.append(self._advance().value)
                    # Consume the following value/layer as expression
                    if not self._at_eol():
                        modifiers.append(self._parse_layer_expr(50))
                else:
                    break
            elif self._at(TT.INTEGER) or self._at(TT.FLOAT):
                modifiers.append(self._parse_layer_expr(50))
            elif self._at(TT.LPAREN):
                modifiers.append(self._parse_layer_expr(50))
            elif self._at(TT.STAR):
                # e.g. STEP M13_S_1*0.7
                self._advance()
                modifiers.append('*')
            else:
                break
        return ast.DRCOp(op=op, operands=[operand],
                         constraints=[], modifiers=modifiers, **loc)

    # ------------------------------------------------------------------
    # AREA layer constraints
    # ------------------------------------------------------------------
    def _parse_area_op(self):
        loc = self._loc()
        self._advance()  # AREA
        operand = self._parse_layer_expr(50)
        constraints = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
        return ast.ConstrainedExpr(
            expr=ast.UnaryOp(op='AREA', operand=operand, **loc),
            constraints=constraints, **loc)

    def _parse_unary_constrained_op(self):
        """Generic: OP operand [constraints] — e.g. VERTEX layer >= 8"""
        loc = self._loc()
        op = self._advance().value.upper()
        operand = self._parse_layer_expr(50)
        constraints = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
        return ast.ConstrainedExpr(
            expr=ast.UnaryOp(op=op, operand=operand, **loc),
            constraints=constraints, **loc)

    # ------------------------------------------------------------------
    # ANGLE operation
    # ------------------------------------------------------------------
    def _parse_angle_op(self):
        loc = self._loc()
        self._advance()  # ANGLE
        operand = self._parse_layer_expr(50)
        constraints = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
        return ast.ConstrainedExpr(
            expr=ast.UnaryOp(op='ANGLE', operand=operand, **loc),
            constraints=constraints, **loc)

    # ------------------------------------------------------------------
    # LENGTH operation (prefix)
    # ------------------------------------------------------------------
    def _parse_length_op(self, op_name='LENGTH'):
        loc = self._loc()
        self._advance()  # LENGTH (or second word of PATH LENGTH)
        # Two syntaxes: LENGTH layer < value  OR  LENGTH < value layer
        constraints = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
        operand = self._parse_layer_expr(50)
        if not constraints and self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
        return ast.ConstrainedExpr(
            expr=ast.UnaryOp(op=op_name, operand=operand, **loc),
            constraints=constraints, **loc)

    # ------------------------------------------------------------------
    # CONVEX EDGE layer ANGLE/LENGTH modifiers
    # ------------------------------------------------------------------
    def _parse_convex_edge_op(self):
        loc = self._loc()
        self._advance()  # CONVEX
        self._advance()  # EDGE
        operand = self._parse_layer_expr(50)
        modifiers = []
        while not self._at_eol():
            t = self._cur()
            if t.type == TT.IDENT:
                upper = t.value.upper()
                if upper in ('ANGLE1', 'ANGLE2', 'LENGTH1', 'LENGTH2',
                             'ANGLE', 'LENGTH', 'WITH'):
                    modifiers.append(self._advance().value)
                    while self._cur().type in (TT.LT, TT.GT_OP, TT.LE,
                                               TT.GE, TT.EQEQ, TT.BANGEQ):
                        op_tok = self._advance().value
                        val = None
                        if self._at(TT.INTEGER) or self._at(TT.FLOAT):
                            val = self._advance().value
                        elif self._at(TT.IDENT):
                            val = self._advance().value
                        modifiers.append(f"{op_tok}{val}")
                    continue
                else:
                    break
            else:
                break
        return ast.DRCOp(op='CONVEX EDGE', operands=[operand],
                         constraints=[], modifiers=modifiers, **loc)

    # ------------------------------------------------------------------
    # EXPAND EDGE layer INSIDE|OUTSIDE BY value
    # ------------------------------------------------------------------
    def _parse_expand_edge_op(self):
        loc = self._loc()
        self._advance()  # EXPAND
        self._advance()  # EDGE
        operand = self._parse_layer_expr(50)
        modifiers = []
        # Pattern: [INSIDE|OUTSIDE BY expr]...
        while not self._at_eol():
            if self._at(TT.IDENT):
                upper_cur = self._cur().value.upper()
                if upper_cur in ('INSIDE', 'OUTSIDE', 'IN', 'OUT'):
                    modifiers.append(self._advance().value)
                    if self._at_val('BY'):
                        modifiers.append(self._advance().value)
                        # Parse value as expression (handles 0.051+VAR)
                        # bp=35 allows arithmetic (+/-) but blocks OUTSIDE(30)
                        if not self._at_eol():
                            modifiers.append(self._parse_layer_expr(35))
                else:
                    modifiers.append(self._advance().value)
            elif self._at(TT.INTEGER) or self._at(TT.FLOAT):
                modifiers.append(str(self._advance().value))
            else:
                break
        return ast.DRCOp(op='EXPAND EDGE', operands=[operand],
                         constraints=[], modifiers=modifiers, **loc)

    # ------------------------------------------------------------------
    # OFFGRID layer (grid) (offset) [INSIDE OF LAYER ref] [modifiers]
    # ------------------------------------------------------------------
    def _parse_offgrid_op(self):
        loc = self._loc()
        self._advance()  # OFFGRID
        # Check for DIRECTIONAL variant
        if self._at(TT.IDENT) and self._cur().value.upper() == 'DIRECTIONAL':
            self._advance()  # DIRECTIONAL
        operands = []
        # Collect operands (layer refs and parenthesized expressions)
        # Use bp=50 to prevent INSIDE/OUTSIDE from being consumed as binary ops
        while not self._at_eol():
            if self._at(TT.LPAREN):
                operands.append(self._parse_layer_expr(50))
            elif self._at(TT.IDENT):
                upper_cur = self._cur().value.upper()
                if upper_cur in ('INSIDE', 'OUTSIDE', 'ABSOLUTE',
                                 'HINT', 'RDB', 'PRINT', 'ACCUMULATE'):
                    break
                operands.append(self._parse_layer_expr(50))
            else:
                break
        modifiers = []
        self._parse_drc_modifiers(modifiers)
        # Multiline continuation for TOP/BOTTOM/LEFT/RIGHT direction lines
        # Pattern: TOP 0.041+DRCGRID 0.120 FACE
        while self._at_eol() and self._block_depth > 0:
            saved = self.pos
            self._consume_eol()
            self._skip_newlines()
            if self._at(TT.IDENT) and self._cur().value.upper() in (
                    'TOP', 'BOTTOM', 'LEFT', 'RIGHT'):
                modifiers.append(self._advance().value)
                # Consume values on this line (expr expr FACE/NOFACE)
                while not self._at_eol():
                    if self._at(TT.IDENT):
                        mod_u = self._cur().value.upper()
                        if mod_u in ('FACE', 'NOFACE', 'DRCGRID'):
                            modifiers.append(self._advance().value)
                        else:
                            break
                    elif self._at(TT.INTEGER) or self._at(TT.FLOAT):
                        modifiers.append(self._parse_layer_expr(35))
                    elif self._at(TT.PLUS) or self._at(TT.MINUS):
                        modifiers.append(self._parse_layer_expr(35))
                    elif self._at(TT.LPAREN):
                        modifiers.append(self._parse_layer_expr(35))
                    else:
                        break
                continue
            self.pos = saved
            break
        return ast.DRCOp(op='OFFGRID', operands=operands,
                         constraints=[], modifiers=modifiers, **loc)

    # ------------------------------------------------------------------
    # RECTANGLE layer [constraints] [ORTHOGONAL ONLY]
    # ------------------------------------------------------------------
    def _parse_rectangle_op(self):
        loc = self._loc()
        self._advance()  # RECTANGLE
        # RECTANGLE ENCLOSURE: two-word DRC op like INT/EXT/ENC
        if self._at(TT.IDENT) and self._cur().value.upper() == 'ENCLOSURE':
            self._advance()  # ENCLOSURE
            op = 'RECTANGLE ENCLOSURE'
            operands = []
            constraints = []
            modifiers = []
            # Collect operands
            while not self._at_eol():
                t = self._cur()
                if t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                    break
                if t.type == TT.IDENT and t.value.upper() in _DRC_MODIFIERS:
                    break
                if t.type == TT.LBRACKET:
                    operands.append(self._parse_bracket_expr())
                    continue
                if t.type == TT.LPAREN:
                    self._advance()
                    expr = self._parse_layer_expr(0)
                    if self._at(TT.RPAREN):
                        self._advance()
                    operands.append(expr)
                    continue
                if t.type == TT.IDENT:
                    operands.append(ast.LayerRef(name=self._advance().value,
                                                 **self._loc()))
                    continue
                break
            # Constraints
            if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                constraints = self._parse_constraints()
            # Modifiers (greedy until EOL)
            while not self._at_eol():
                t = self._cur()
                if t.type == TT.IDENT:
                    modifiers.append(self._advance().value)
                elif t.type in (TT.INTEGER, TT.FLOAT):
                    modifiers.append(str(self._advance().value))
                elif t.type == TT.STRING:
                    modifiers.append(self._advance().value)
                elif t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                    for c in self._parse_constraints():
                        modifiers.append(f"{c.op}{c.value}")
                elif t.type == TT.LBRACKET:
                    be = self._parse_bracket_expr()
                    modifiers.append(be)
                elif t.type == TT.MINUS:
                    self._advance()
                    if self._at(TT.INTEGER):
                        modifiers.append(str(-self._advance().value))
                    elif self._at(TT.FLOAT):
                        modifiers.append(str(-self._advance().value))
                    else:
                        modifiers.append('-')
                elif t.type in (TT.PLUS, TT.STAR, TT.SLASH, TT.CARET):
                    modifiers.append(str(self._advance().value))
                elif t.type == TT.LPAREN:
                    self._advance()
                    depth = 1
                    parts = ['(']
                    while not self._at(TT.EOF) and depth > 0:
                        ct = self._cur()
                        if ct.type == TT.LPAREN: depth += 1
                        elif ct.type == TT.RPAREN:
                            depth -= 1
                            if depth == 0:
                                self._advance()
                                parts.append(')')
                                break
                        parts.append(str(self._advance().value))
                    modifiers.append(' '.join(parts))
                else:
                    break
            # Multiline continuation: next line starts with a modifier keyword
            _rect_enc_mods = frozenset({
                'SINGULAR', 'GOOD', 'OPPOSITE', 'PARALLEL', 'PERPENDICULAR',
                'REGION', 'ABUT', 'ALSO', 'ONLY', 'ENDPOINT', 'CENTERS',
                'MEASURE', 'ANNOTATE', 'NODAL', 'MULTI', 'PRIMARY',
                'EVEN', 'ODD', 'ALL', 'CONNECTED', 'ACCUMULATE',
            })
            while self._at_eol():
                saved = self.pos
                self._consume_eol()
                self._skip_newlines()
                if self._at(TT.IDENT) and self._cur().value.upper() in _rect_enc_mods:
                    while not self._at_eol():
                        t = self._cur()
                        if t.type == TT.IDENT:
                            modifiers.append(self._advance().value)
                        elif t.type in (TT.INTEGER, TT.FLOAT):
                            modifiers.append(str(self._advance().value))
                        elif t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                            for c in self._parse_constraints():
                                modifiers.append(f"{c.op}{c.value}")
                        else:
                            break
                else:
                    self.pos = saved
                    break
            return ast.DRCOp(op=op, operands=operands,
                             constraints=constraints, modifiers=modifiers, **loc)
        operands = []
        # Only parse operand if next token is NOT a constraint operator
        # and NOT a modifier keyword (ORTHOGONAL, ONLY, etc.)
        if not self._at_eol() and self._cur().type not in (
                TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            if not (self._at(TT.IDENT) and self._cur().value.upper() in (
                    _DRC_MODIFIERS | {'ASPECT'})):
                operands.append(self._parse_layer_expr(50))
        constraints = []
        modifiers = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
        # BY == value (second dimension constraint)
        if self._at_val('BY'):
            self._advance()  # BY
            by_constraints = []
            if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                by_constraints = self._parse_constraints()
            # Store BY constraints with a BY marker constraint
            constraints.append(ast.Constraint(op='BY', value=None, **loc))
            constraints.extend(by_constraints)
        # Trailing modifiers: ORTHOGONAL, ONLY, ASPECT, etc.
        while not self._at_eol() and self._at(TT.IDENT):
            upper = self._cur().value.upper()
            if upper in _DRC_MODIFIERS or upper == 'ASPECT':
                modifiers.append(self._advance().value)
                # ASPECT may be followed by a constraint: ASPECT > 1
                if upper == 'ASPECT' and not self._at_eol() and \
                        self._cur().type in (TT.LT, TT.GT_OP, TT.LE,
                                             TT.GE, TT.EQEQ, TT.BANGEQ):
                    constraints.extend(self._parse_constraints())
            else:
                break
        return ast.DRCOp(op='RECTANGLE', operands=operands,
                         constraints=constraints, modifiers=modifiers, **loc)

    # ------------------------------------------------------------------
    # RECTANGLES w h dx dy INSIDE OF LAYER layer
    # ------------------------------------------------------------------
    def _parse_rectangles_op(self):
        loc = self._loc()
        op = self._advance().value.upper()  # RECTANGLES or EXTENTS
        args = []
        modifiers = []
        while not self._at_eol() and self._can_start_layer_expr():
            args.append(self._parse_layer_expr(50))
        # Parse trailing modifier phrase: INSIDE OF [LAYER] <name>
        #                                 OUTSIDE OF [LAYER] <name>
        while not self._at_eol():
            if self._at(TT.IDENT):
                modifiers.append(self._advance().value)
            elif self._at(TT.INTEGER) or self._at(TT.FLOAT):
                modifiers.append(self._parse_layer_expr(50))
            else:
                break
        return ast.DRCOp(op=op, operands=args,
                         constraints=[], modifiers=modifiers, **loc)

    # ------------------------------------------------------------------
    # EXTENT [DRAWN] [ORIGINAL] [CELL cellname ...]
    # ------------------------------------------------------------------
    def _parse_extent_op(self):
        loc = self._loc()
        self._advance()  # EXTENT
        modifiers = []
        while self._at(TT.IDENT) and not self._at_eol():
            upper = self._cur().value.upper()
            if upper in ('DRAWN', 'ORIGINAL'):
                modifiers.append(self._advance().value)
            elif upper == 'CELL':
                modifiers.append(self._advance().value)
                # CELL takes a cell name argument
                if self._at(TT.IDENT) and not self._at_eol():
                    modifiers.append(self._advance().value)
            else:
                break
        # Consume remaining operands (layer names)
        operands = []
        while not self._at_eol() and self._can_start_layer_expr():
            operands.append(self._parse_layer_expr(50))
        return ast.DRCOp(op='EXTENT', operands=operands,
                         constraints=[], modifiers=modifiers, **loc)

    # ------------------------------------------------------------------
    # GROW/SHRINK operand [TOP|BOTTOM|LEFT|RIGHT BY value]...
    # ------------------------------------------------------------------
    def _parse_grow_shrink_op(self):
        loc = self._loc()
        op = self._advance().value.upper()  # GROW or SHRINK
        operand = self._parse_layer_expr(50)
        modifiers = []
        while not self._at_eol() and self._at(TT.IDENT):
            upper = self._cur().value.upper()
            if upper in ('TOP', 'BOTTOM', 'LEFT', 'RIGHT'):
                modifiers.append(self._advance().value)
                if self._at_val('BY'):
                    modifiers.append(self._advance().value)
                    if not self._at_eol():
                        modifiers.append(self._parse_layer_expr(35))
            elif upper in ('SEQUENTIAL', 'CLIP', 'TRUNCATE', 'BEVEL',
                           'CORNER', 'INSIDE', 'OUTSIDE', 'OVERUNDER',
                           'UNDEROVER'):
                modifiers.append(self._advance().value)
                # Some trailing modifiers take a numeric argument
                if not self._at_eol() and (self._at(TT.INTEGER) or self._at(TT.FLOAT)):
                    modifiers.append(self._advance().value)
            else:
                break
        return ast.DRCOp(op=op, operands=[operand],
                         constraints=[], modifiers=modifiers, **loc)

    # ------------------------------------------------------------------
    # STAMP layer BY layer
    # ------------------------------------------------------------------
    def _parse_stamp_op(self):
        loc = self._loc()
        self._advance()  # STAMP
        operand = self._parse_layer_expr(50)
        target = None
        if self._at_val('BY'):
            self._advance()
            target = self._parse_layer_expr(50)
        return ast.BinaryOp(op='STAMP', left=operand,
                            right=target, **loc)

    # ------------------------------------------------------------------
    # WITH WIDTH/EDGE/LENGTH constraint
    # ------------------------------------------------------------------
    def _parse_with_op(self, left):
        loc = self._loc()
        self._advance()  # WITH
        modifier = ''
        if self._at(TT.IDENT):
            upper_mod = self._cur().value.upper()
            if upper_mod in ('EDGE', 'WIDTH', 'LENGTH', 'AREA', 'TEXT', 'NEIGHBOR'):
                modifier = self._advance().value.upper()
        # WITH TEXT / WITH NEIGHBOR take multiple operands + modifiers -> use DRCOp
        if modifier == 'TEXT':
            operands = [left]
            while not self._at_eol():
                t = self._cur()
                if t.type == TT.IDENT and t.value.upper() in _DRC_MODIFIERS:
                    break
                if t.type == TT.IDENT and t.value.upper() in ('PRIMARY', 'MULTI',
                        'ACCUMULATE', 'NOT', 'MEASURE', 'ANNOTATE', 'NODAL'):
                    break
                if t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                    break
                if t.type == TT.IDENT:
                    operands.append(ast.LayerRef(name=self._advance().value, **self._loc()))
                elif t.type == TT.STRING:
                    operands.append(ast.StringLiteral(value=self._advance().value, **self._loc()))
                else:
                    break
            constraints = []
            if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                constraints = self._parse_constraints()
            modifiers = []
            while not self._at_eol() and self._at(TT.IDENT):
                modifiers.append(self._advance().value)
            return ast.DRCOp(op='WITH TEXT', operands=operands,
                             constraints=constraints, modifiers=modifiers, **loc)
        # WITH NEIGHBOR layer >= N SPACE <= val [INSIDE OF LAYER (...)]
        if modifier == 'NEIGHBOR':
            operands = [left]
            while not self._at_eol():
                t = self._cur()
                if t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                    break
                if t.type == TT.IDENT and t.value.upper() in _DRC_MODIFIERS:
                    break
                if t.type == TT.IDENT and t.value.upper() in ('SPACE', 'NOTCH',
                        'PRIMARY', 'MULTI', 'INSIDE', 'OUTSIDE'):
                    break
                if t.type in (TT.IDENT, TT.LPAREN):
                    operands.append(self._parse_layer_expr(50))
                elif t.type in (TT.INTEGER, TT.FLOAT):
                    operands.append(ast.NumberLiteral(value=self._advance().value, **self._loc()))
                else:
                    break
            constraints = []
            if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                constraints = self._parse_constraints()
            mod_list = []
            # Consume modifier+constraint pairs (e.g. SPACE <= 0.5 INSIDE OF LAYER (...))
            while not self._at_eol():
                if self._at(TT.IDENT):
                    mod_u = self._cur().value.upper()
                    if mod_u in ('SPACE', 'NOTCH', 'INSIDE', 'OUTSIDE',
                                 'OF', 'LAYER') or mod_u in _DRC_MODIFIERS:
                        mod_list.append(self._advance().value)
                    else:
                        break
                elif self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                    mod_list.extend(self._parse_constraints())
                elif self._at(TT.LPAREN):
                    mod_list.append(self._parse_layer_expr(0))
                elif self._at(TT.INTEGER) or self._at(TT.FLOAT):
                    mod_list.append(ast.NumberLiteral(value=self._advance().value, **self._loc()))
                else:
                    break
            return ast.DRCOp(op='WITH NEIGHBOR', operands=operands,
                             constraints=constraints, modifiers=mod_list, **loc)
        # After WITH EDGE/WIDTH/LENGTH, there may be a parenthesized expression
        # (e.g. WITH EDGE (LENGTH (...) == 0) == 0.040) or direct expression
        # (e.g. WITH WIDTH SR_POLY == value) or direct constraints.
        sub_expr = None
        if self._at(TT.LPAREN):
            sub_expr = self._parse_layer_expr(0)
        elif self._at(TT.IDENT) and not self._at_eol():
            sub_expr = self._parse_layer_expr(50)
        constraints = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
        op_name = 'WITH ' + modifier if modifier else 'WITH'
        if sub_expr:
            right = sub_expr
        elif not modifier:
            right = ast.LayerRef(name='', **loc)
        else:
            right = None
        return ast.ConstrainedExpr(
            expr=ast.BinaryOp(op=op_name, left=left, right=right, **loc),
            constraints=constraints, **loc)

    def _parse_with_prefix_op(self):
        """Parse WITH in prefix/NUD position (e.g. NOT WITH EDGE layer)."""
        loc = self._loc()
        self._advance()  # WITH
        modifier = ''
        if self._at(TT.IDENT):
            upper_mod = self._cur().value.upper()
            if upper_mod in ('EDGE', 'WIDTH', 'LENGTH', 'AREA', 'TEXT', 'NEIGHBOR'):
                modifier = self._advance().value.upper()
        op_name = 'WITH ' + modifier if modifier else 'WITH'
        operands = []
        while not self._at_eol():
            t = self._cur()
            if t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                break
            if t.type == TT.IDENT and t.value.upper() in _DRC_MODIFIERS:
                break
            if t.type == TT.IDENT and t.value.upper() in ('PRIMARY', 'MULTI',
                    'ACCUMULATE', 'NOT', 'MEASURE', 'ANNOTATE', 'NODAL'):
                break
            if t.type in (TT.IDENT, TT.STRING):
                operands.append(self._parse_layer_expr(50))
            elif t.type == TT.LPAREN:
                operands.append(self._parse_layer_expr(0))
            elif t.type in (TT.INTEGER, TT.FLOAT):
                operands.append(ast.NumberLiteral(value=self._advance().value, **self._loc()))
            else:
                break
        constraints = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
        modifiers = []
        # Consume modifier+constraint pairs in a loop (e.g. SPACE < value CENTERS)
        while not self._at_eol():
            if self._at(TT.IDENT):
                mod_u = self._cur().value.upper()
                if mod_u in _DRC_MODIFIERS or mod_u in ('SPACE', 'NOTCH',
                        'EVEN', 'ODD', 'INSIDE', 'OUTSIDE', 'OF', 'LAYER'):
                    modifiers.append(self._advance().value)
                else:
                    break
            elif self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                modifiers.extend(self._parse_constraints())
            elif self._at(TT.LPAREN):
                modifiers.append(self._parse_layer_expr(0))
            elif self._at(TT.INTEGER) or self._at(TT.FLOAT):
                modifiers.append(ast.NumberLiteral(value=self._advance().value, **self._loc()))
            else:
                break
        return ast.DRCOp(op=op_name, operands=operands,
                         constraints=constraints, modifiers=modifiers, **loc)
