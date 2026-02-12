"""Property block parsing mixin for the SVRF parser."""

from .tokens import TokenType, Token
from . import ast_nodes as ast

TT = TokenType


class PropertyBlockMixin:
    """Mixin providing property block parsing for the SVRF parser."""

    # ------------------------------------------------------------------
    # Property block: [ PROPERTY props... body... ]
    # ------------------------------------------------------------------
    def _parse_property_block(self):
        loc = self._loc()
        self._advance()  # [
        self._skip_newlines()
        properties = []
        body = []
        # Check for PROPERTY keyword
        if self._at_val('PROPERTY'):
            self._advance()
            # Collect comma-separated property names
            while not self._at_eol() and not self._at(TT.RBRACKET):
                if self._at(TT.IDENT):
                    properties.append(self._advance().value)
                if self._at(TT.COMMA):
                    self._advance()
                else:
                    break
            self._consume_eol()
        # Parse body until ] or a scope-ending token
        while not self._at(TT.EOF) and not self._at(TT.RBRACKET):
            if self._cur().type in (TT.PP_ENDIF, TT.PP_ELSE, TT.RBRACE):
                break
            self._skip_newlines()
            if self._at(TT.RBRACKET) or self._at(TT.EOF):
                break
            if self._cur().type in (TT.PP_ENDIF, TT.PP_ELSE, TT.RBRACE):
                break
            saved = self.pos
            stmt = self._parse_prop_statement()
            if stmt is not None:
                body.append(stmt)
            if self.pos == saved:
                _st = self._cur()
                self.warnings.append(
                    f"L{_st.line}:{_st.col}: Parser stuck in property block at "
                    f"{_st.type.name} ({_st.value!r}), force advancing")
                self._advance()
        if self._at(TT.RBRACKET):
            self._advance()
        # Capture trailing tokens after ] on the same line
        # (e.g. "] RDB report.rep M1 M2 BY LAYER")
        if not self._at_eol():
            trail_loc = self._loc()
            keywords = []
            args = []
            while not self._at_eol():
                t = self._cur()
                if t.type == TT.IDENT:
                    keywords.append(self._advance().value)
                elif t.type in (TT.INTEGER, TT.FLOAT):
                    args.append(self._advance().value)
                elif t.type == TT.STRING:
                    args.append(self._advance().value)
                else:
                    # Operators and delimiters are valid in trailing content
                    # after property blocks (comparisons, parens, brackets, etc.)
                    args.append(str(self._advance().value))
            if keywords or args:
                body.append(ast.Directive(
                    keywords=keywords, arguments=args, **trail_loc))
        self._consume_eol()
        return ast.PropertyBlock(properties=properties, body=body, **loc)

    def _parse_prop_statement(self):
        """Parse a statement inside a property block."""
        t = self._cur()
        # Preprocessor inside property blocks
        if t.type == TT.PP_IFDEF or t.type == TT.PP_IFNDEF:
            return self._parse_ifdef()
        if t.type == TT.PP_DEFINE:
            return self._parse_define()
        if t.type == TT.PP_ELSE:
            return None
        if t.type == TT.PP_ENDIF:
            return None
        if t.type == TT.NEWLINE:
            self._advance()
            return None
        if t.type == TT.RBRACKET:
            return None
        # IF expression
        if t.type == TT.IDENT and t.value.upper() == 'IF':
            return self._parse_if_expr()
        # Assignment: ident = expr
        if t.type == TT.IDENT and self._peek().type == TT.EQUALS:
            return self._parse_prop_assignment()
        # Compound assignment: ident -= expr, ident += expr
        if t.type == TT.IDENT and self._peek().type == TT.MINUS:
            p2 = self._peek(2)
            if p2.type == TT.EQUALS:
                return self._parse_prop_compound_assignment('-=')
        if t.type == TT.IDENT and self._peek().type == TT.PLUS:
            p2 = self._peek(2)
            if p2.type == TT.EQUALS:
                return self._parse_prop_compound_assignment('+=')
        # Compound assignment starting with - : - = expr (shorthand for implicit var)
        if t.type == TT.MINUS and self._peek().type == TT.EQUALS:
            return self._parse_prop_compound_assignment('-=', implicit=True)
        # Compound assignment starting with + : + = expr (shorthand for implicit var)
        if t.type == TT.PLUS and self._peek().type == TT.EQUALS:
            return self._parse_prop_compound_assignment('+=', implicit=True)
        # Keyword statements: resolve, action, output, anchor, effective, tolerance, etc.
        if t.type == TT.IDENT and t.value.lower() in (
                'resolve', 'action', 'output', 'anchor', 'select',
                'stamp', 'text', 'label', 'print', 'effective', 'tolerance'):
            return self._parse_prop_keyword_stmt()
        # String-keyed assignment: "AREA" = AREA(proc_layer)
        if t.type == TT.STRING and self._peek().type == TT.EQUALS:
            loc = self._loc()
            name = self._advance().value
            self._advance()  # =
            expr = self._parse_arith_expr(0)
            if self._at(TT.SEMICOLON):
                self._advance()
            self._consume_eol()
            return ast.LayerAssignment(name=name, expression=expr, **loc)
        # Semicolon-terminated statement (e.g. "expr ;")
        if t.type == TT.SEMICOLON:
            self._advance()
            return None
        # Continuation tokens from multiline expressions (ternary, parens, operators)
        # These appear at the start of a line when the previous line's expression
        # spans multiple lines. Consume the rest of the line as an expression.
        if t.type in (TT.RPAREN, TT.QUESTION, TT.COLON, TT.STAR, TT.PLUS,
                      TT.SLASH, TT.PIPEPIPE, TT.AMPAMP):
            loc = self._loc()
            parts = []
            while not self._at_eol() and not self._at(TT.RBRACKET):
                parts.append(str(self._advance().value))
            self._consume_eol()
            if parts:
                return ast.Directive(keywords=[], arguments=parts, **loc)
            return None
        # Try to parse as arithmetic expression
        if t.type in (TT.IDENT, TT.INTEGER, TT.FLOAT, TT.STRING,
                       TT.LPAREN, TT.MINUS, TT.BANG):
            loc = self._loc()
            try:
                expr = self._parse_arith_expr(0)
                # Consume optional semicolon
                if self._at(TT.SEMICOLON):
                    self._advance()
                self._consume_eol()
                return expr
            except Exception:
                pass
        # Bare expression / skip – stop before ] so we don't consume the
        # closing bracket of the enclosing property block.
        skip_start = self._cur()
        parts = []
        while not self._at_eol() and not self._at(TT.RBRACKET):
            parts.append(str(self._advance().value))
        self._consume_eol()
        if parts:
            self.warnings.append(
                f"L{skip_start.line}:{skip_start.col}: Skipped unrecognized "
                f"property block content: {' '.join(parts[:5])}"
                f"{'...' if len(parts) > 5 else ''}")
        return None

    def _parse_prop_assignment(self):
        """Parse property assignment: name = arith_expr"""
        loc = self._loc()
        name = self._advance().value
        self._advance()  # =
        expr = self._parse_arith_expr(0)
        # Consume optional semicolon
        if self._at(TT.SEMICOLON):
            self._advance()
        self._consume_eol()
        return ast.LayerAssignment(name=name, expression=expr, **loc)

    def _parse_prop_compound_assignment(self, op, implicit=False):
        """Parse compound assignment: name -= expr or name += expr or - = expr."""
        loc = self._loc()
        if implicit:
            name = ''
            self._advance()  # - or +
            self._advance()  # =
        else:
            name = self._advance().value
            self._advance()  # - or +
            self._advance()  # =
        expr = self._parse_arith_expr(0)
        # Consume optional semicolon
        if self._at(TT.SEMICOLON):
            self._advance()
        self._consume_eol()
        return ast.LayerAssignment(name=f"{name}{op}", expression=expr, **loc)

    def _parse_prop_keyword_stmt(self):
        """Parse keyword statement in property block (resolve, action, output, etc.)."""
        loc = self._loc()
        keywords = []
        args = []
        while not self._at_eol() and not self._at(TT.RBRACKET) and not self._at(TT.SEMICOLON):
            t = self._cur()
            if t.type == TT.IDENT:
                keywords.append(self._advance().value)
            elif t.type in (TT.INTEGER, TT.FLOAT):
                args.append(self._advance().value)
            elif t.type == TT.STRING:
                args.append(self._advance().value)
            else:
                args.append(str(self._advance().value))
        if self._at(TT.SEMICOLON):
            self._advance()
        self._consume_eol()
        return ast.Directive(keywords=keywords, arguments=args, **loc)

    # ------------------------------------------------------------------
    # IF / ELSE IF / ELSE inside property blocks
    # ------------------------------------------------------------------
    def _parse_if_expr(self):
        loc = self._loc()
        self._advance()  # IF
        # Parse condition (may be in parens)
        cond = self._parse_arith_expr(0)
        # Expect {
        self._skip_newlines()
        then_body = []
        if self._at(TT.LBRACE):
            self._advance()
            self._skip_newlines()
            while not self._at(TT.RBRACE) and not self._at(TT.EOF):
                self._skip_newlines()
                if self._at(TT.RBRACE) or self._at(TT.EOF):
                    break
                saved = self.pos
                s = self._parse_prop_statement()
                if s is not None:
                    then_body.append(s)
                if self.pos == saved:
                    _st = self._cur()
                    self.warnings.append(
                        f"L{_st.line}:{_st.col}: Parser stuck in IF body at "
                        f"{_st.type.name} ({_st.value!r}), force advancing")
                    self._advance()
            if self._at(TT.RBRACE):
                self._advance()
        self._consume_eol()
        # ELSE IF / ELSE  (ELSE may be on same line as } or next line)
        elseifs = []
        else_body = []
        self._skip_newlines()
        while self._at_val('ELSE'):
            self._advance()  # ELSE
            if self._at_val('IF'):
                ei_loc = self._loc()
                self._advance()  # IF
                ei_cond = self._parse_arith_expr(0)
                self._skip_newlines()
                ei_body = []
                if self._at(TT.LBRACE):
                    self._advance()
                    self._skip_newlines()
                    while not self._at(TT.RBRACE) and not self._at(TT.EOF):
                        self._skip_newlines()
                        if self._at(TT.RBRACE) or self._at(TT.EOF):
                            break
                        saved = self.pos
                        s = self._parse_prop_statement()
                        if s is not None:
                            ei_body.append(s)
                        if self.pos == saved:
                            _st = self._cur()
                            self.warnings.append(
                                f"L{_st.line}:{_st.col}: Parser stuck in ELSE IF body at "
                                f"{_st.type.name} ({_st.value!r}), force advancing")
                            self._advance()
                    if self._at(TT.RBRACE):
                        self._advance()
                self._consume_eol()
                self._skip_newlines()
                elseifs.append((ei_cond, ei_body))
            else:
                self._skip_newlines()
                if self._at(TT.LBRACE):
                    self._advance()
                    self._skip_newlines()
                    while not self._at(TT.RBRACE) and not self._at(TT.EOF):
                        self._skip_newlines()
                        if self._at(TT.RBRACE) or self._at(TT.EOF):
                            break
                        saved = self.pos
                        s = self._parse_prop_statement()
                        if s is not None:
                            else_body.append(s)
                        if self.pos == saved:
                            _st = self._cur()
                            self.warnings.append(
                                f"L{_st.line}:{_st.col}: Parser stuck in ELSE body at "
                                f"{_st.type.name} ({_st.value!r}), force advancing")
                            self._advance()
                    if self._at(TT.RBRACE):
                        self._advance()
                self._consume_eol()
                break
        return ast.IfExpr(condition=cond, then_body=then_body,
                          elseifs=elseifs, else_body=else_body, **loc)
