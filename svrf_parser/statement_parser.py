"""Statement parsing mixin for the SVRF parser."""

from .tokens import TokenType, Token
from . import ast_nodes as ast
from .parser_base import _DIRECTIVE_HEADS

TT = TokenType


class StatementMixin:
    """Mixin providing statement-level parsing for the SVRF parser."""

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def parse(self):
        stmts = self._parse_body(top_level=True)
        return ast.Program(statements=stmts, **self._loc())

    def _parse_body(self, top_level=False, stop_at=None):
        """Parse a sequence of statements.
        stop_at: set of token types or ident values that end the body.
        """
        stmts = []
        while not self._at(TT.EOF):
            self._skip_newlines()
            if self._at(TT.EOF):
                break
            if stop_at and self._should_stop(stop_at):
                break
            saved = self.pos
            stmt = self._parse_statement()
            if stmt is not None:
                stmts.append(stmt)
            if self.pos == saved:
                t = self._cur()
                self.warnings.append(
                    f"L{t.line}:{t.col}: Parser stuck at {t.type.name} "
                    f"({t.value!r}), force advancing"
                )
                self._advance()
        return stmts

    def _should_stop(self, stop_at):
        t = self._cur()
        if t.type in stop_at:
            return True
        if t.type == TT.IDENT and t.value.upper() in stop_at:
            return True
        # Check preprocessor tokens
        if t.type in (TT.PP_ELSE, TT.PP_ENDIF, TT.PP_ENDCRYPT):
            if t.type in stop_at:
                return True
        return False

    # ------------------------------------------------------------------
    # Top-level statement dispatch
    # ------------------------------------------------------------------
    def _parse_statement(self):
        t = self._cur()
        tt = t.type

        # Preprocessor
        if tt == TT.PP_DEFINE:
            return self._parse_define()
        if tt in (TT.PP_IFDEF, TT.PP_IFNDEF):
            return self._parse_ifdef()
        if tt == TT.PP_INCLUDE:
            return self._parse_include()
        if tt == TT.PP_UNDEFINE:
            return self._parse_undefine()
        if tt in (TT.PP_ENCRYPT, TT.PP_DECRYPT):
            return self._parse_encrypted()
        if tt == TT.PP_ELSE:
            self._advance()
            self._consume_eol()
            return None  # handled by _parse_ifdef; orphaned at top level
        if tt == TT.PP_ENDIF:
            self._advance()
            self._consume_eol()
            return None  # handled by _parse_ifdef; orphaned at top level
        if tt == TT.PP_ENDCRYPT:
            self._advance()
            self._consume_eol()
            return None
        if tt == TT.ENCRYPTED:
            loc = self._loc()
            content = self._advance().value
            self._consume_eol()
            return ast.EncryptedBlock(content=content, **loc)

        # Newline / EOF
        if tt == TT.NEWLINE:
            self._advance()
            return None
        if tt == TT.EOF:
            return None

        # Closing delimiters at statement level — legitimate when #IFDEF/#ELSE
        # splits a rule check block, property block, or parenthesized expression
        # across preprocessor boundaries.
        if tt in (TT.RBRACE, TT.RBRACKET, TT.RPAREN, TT.COMMA):
            self._advance()
            return None

        # Identifier-based dispatch
        if tt == TT.IDENT:
            return self._dispatch_ident()

        # Digit-prefixed names: INTEGER immediately followed by IDENT
        # e.g. 125xmy4_S_3_DFM1 { ... } or 4t_para_gate { ... }
        if tt == TT.INTEGER:
            nxt = self._peek()
            if nxt.type == TT.IDENT:
                nxt2 = self._peek(2)
                # digit-name { => rule check block
                if nxt2 and (nxt2.type == TT.LBRACE or
                    (nxt2.type == TT.NEWLINE and self._peek_skip_newlines(2).type == TT.LBRACE)):
                    return self._parse_rule_check_block()
                # digit-name = => assignment
                if nxt2 and nxt2.type == TT.EQUALS:
                    return self._parse_assignment()
                # digit-name as bare expression (e.g. 18_15V_GATE NOT OD18)
                return self._parse_bare_expression()

        # @ description line (inside rule check blocks)
        if tt == TT.AT:
            return self._parse_at_description()

        # [ property block (inside DMACRO)
        if tt == TT.LBRACKET:
            return self._parse_property_block()

        # Parenthesized expression: e.g. (NW INTERACT NWDMY) AND TrGATE
        # or standalone (EXT ...) / (INT ...) at any level
        if tt == TT.LPAREN:
            return self._parse_bare_expression()

        # Continuation tokens from multiline expressions (operators, numbers,
        # strings, etc. that belong to the previous line's expression).
        # Consume the rest of the line silently.
        if tt in (TT.STAR, TT.PLUS, TT.SLASH, TT.LT, TT.GT_OP, TT.LE, TT.GE,
                  TT.EQEQ, TT.BANGEQ, TT.COLON, TT.SEMICOLON,
                  TT.FLOAT, TT.STRING, TT.MINUS, TT.BANG):
            self._skip_to_eol()
            self._consume_eol()
            return None

        # Unknown token — produce ErrorNode and skip to next statement boundary
        t = self._cur()
        loc = self._loc()
        skipped = []
        while not self._at_eol():
            skipped.append(str(self._advance().value))
        skipped_text = ' '.join(skipped) if skipped else str(t.value)
        if not skipped:
            self._advance()
        self._consume_eol()
        self.warnings.append(
            f"L{t.line}:{t.col}: Skipped unknown token {t.type.name} ({t.value!r})"
        )
        return ast.ErrorNode(
            message=f"Unrecognized token {t.type.name} ({t.value!r})",
            skipped_text=skipped_text, **loc)

    # ------------------------------------------------------------------
    # Identifier dispatch
    # ------------------------------------------------------------------
    _STMT_DISPATCH = {
        'LAYER': '_parse_layer',
        'VARIABLE': '_parse_variable',
        'CONNECT': '_parse_connect',
        'SCONNECT': '_parse_connect',
        'DEVICE': '_parse_device',
        'DMACRO': '_parse_dmacro',
        'ATTACH': '_parse_attach',
        'GROUP': '_parse_group',
        'IF': '_parse_if_expr',
        'CMACRO': '_parse_cmacro_invocation',
        'POLYGON': '_parse_polygon',
        'DVPARAMS': '_parse_directive',
        'RDB': '_parse_directive',
        'DISCONNECT': '_parse_directive',
    }

    def _dispatch_ident(self):
        t = self._cur()
        name = t.value
        upper = name.upper()

        nxt = self._peek()

        # Assignment: name = expression
        if nxt.type == TT.EQUALS:
            return self._parse_assignment()

        # Rule check block: name { ... }  (the { may be on the next line)
        # Exclude control-flow keywords (ELSE, IF) which also use { }.
        if upper not in ('ELSE', 'IF'):
            if nxt.type == TT.LBRACE or (nxt.type == TT.NEWLINE and self._peek_skip_newlines().type == TT.LBRACE):
                return self._parse_rule_check_block()

        # TRACE needs lookahead for PROPERTY
        if upper == 'TRACE':
            if self._peek().type == TT.IDENT and self._peek().value.upper() == 'PROPERTY':
                return self._parse_trace_property()
            return self._parse_directive()

        # Dispatch table lookup
        handler_name = self._STMT_DISPATCH.get(upper)
        if handler_name:
            return getattr(self, handler_name)()

        # Multi-word directives
        # NET AREA RATIO / NET INTERACT are DRC ops inside rule check blocks,
        # not directives — let them fall through to bare expression parsing.
        if upper in _DIRECTIVE_HEADS:
            if upper == 'NET' and self._block_depth > 0:
                nxt = self._peek()
                if nxt.type == TT.IDENT and nxt.value.upper() in ('AREA', 'INTERACT'):
                    return self._parse_bare_expression()
            return self._parse_directive()

        # Bare expression fallback
        return self._parse_bare_expression()

    # ------------------------------------------------------------------
    # Preprocessor
    # ------------------------------------------------------------------
    def _parse_define(self):
        loc = self._loc()
        self._advance()  # #DEFINE
        name = ''
        value = None
        if self._at(TT.IDENT):
            name = self._advance().value
        # Rest of line is the value
        parts = []
        while not self._at_eol():
            parts.append(str(self._advance().value))
        value = ' '.join(parts) if parts else None
        self._consume_eol()
        return ast.Define(name=name, value=value, **loc)

    def _parse_undefine(self):
        loc = self._loc()
        self._advance()  # #UNDEFINE
        name = ''
        if self._at(TT.IDENT):
            name = self._advance().value
        self._skip_to_eol()
        self._consume_eol()
        return ast.Directive(keywords=['#UNDEFINE'], arguments=[name], **loc)

    def _parse_cmacro_invocation(self):
        """Parse standalone CMACRO invocation: CMACRO name arg1 arg2 ..."""
        loc = self._loc()
        self._advance()  # CMACRO
        keywords = ['CMACRO']
        args = []
        while not self._at_eol():
            t = self._cur()
            if t.type == TT.IDENT:
                args.append(self._advance().value)
            elif t.type in (TT.INTEGER, TT.FLOAT):
                args.append(str(self._advance().value))
            elif t.type == TT.STRING:
                args.append(self._advance().value)
            else:
                self.warnings.append(
                    f"L{t.line}:{t.col}: Unexpected token {t.type.name} "
                    f"({t.value!r}) in CMACRO invocation, skipping")
                self._advance()
        self._consume_eol()
        return ast.Directive(keywords=keywords, arguments=args, **loc)

    def _parse_polygon(self):
        """Parse POLYGON statement: POLYGON x1 y1 x2 y2 name"""
        loc = self._loc()
        self._advance()  # POLYGON
        args = []
        while not self._at_eol():
            t = self._cur()
            if t.type == TT.IDENT:
                args.append(self._advance().value)
            elif t.type in (TT.INTEGER, TT.FLOAT):
                args.append(str(self._advance().value))
            elif t.type == TT.STRING:
                args.append(self._advance().value)
            else:
                self.warnings.append(
                    f"L{t.line}:{t.col}: Unexpected token {t.type.name} "
                    f"({t.value!r}) in POLYGON statement, skipping")
                self._advance()
        self._consume_eol()
        return ast.Directive(keywords=['POLYGON'], arguments=args, **loc)

    def _parse_ifdef(self):
        loc = self._loc()
        tok = self._advance()  # #IFDEF or #IFNDEF
        negated = tok.type == TT.PP_IFNDEF
        name = ''
        value = None
        if self._at(TT.IDENT):
            name = self._advance().value
        # Optional value on same line
        parts = []
        while not self._at_eol():
            parts.append(str(self._advance().value))
        value = ' '.join(parts) if parts else None
        self._consume_eol()

        # Parse then-body until #ELSE or #ENDIF
        then_body = []
        else_body = []
        while not self._at(TT.EOF):
            self._skip_newlines()
            if self._at(TT.EOF):
                break
            if self._at(TT.PP_ENDIF):
                self._advance()
                self._consume_eol()
                break
            if self._at(TT.PP_ELSE):
                self._advance()
                self._consume_eol()
                # Parse else-body until #ENDIF
                while not self._at(TT.EOF):
                    self._skip_newlines()
                    if self._at(TT.EOF):
                        break
                    if self._at(TT.PP_ENDIF):
                        self._advance()
                        self._consume_eol()
                        break
                    saved = self.pos
                    s = self._parse_statement()
                    if s is not None:
                        else_body.append(s)
                    if self.pos == saved:
                        self._advance()
                break
            saved = self.pos
            s = self._parse_statement()
            if s is not None:
                then_body.append(s)
            if self.pos == saved:
                self._advance()

        return ast.IfDef(name=name, value=value, negated=negated,
                         then_body=then_body, else_body=else_body, **loc)

    def _parse_include(self):
        loc = self._loc()
        self._advance()  # #INCLUDE
        path = ''
        if self._at(TT.STRING):
            path = self._advance().value
        self._skip_to_eol()
        self._consume_eol()
        return ast.Include(path=path, **loc)

    def _parse_encrypted(self):
        loc = self._loc()
        self._advance()  # #ENCRYPT or #DECRYPT
        self._consume_eol()
        content = ''
        if self._at(TT.ENCRYPTED):
            content = self._advance().value
            self._consume_eol()
        if self._at(TT.PP_ENDCRYPT):
            self._advance()
            self._consume_eol()
        return ast.EncryptedBlock(content=content, **loc)

    # ------------------------------------------------------------------
    # LAYER
    # ------------------------------------------------------------------
    def _parse_layer(self):
        loc = self._loc()
        self._advance()  # LAYER

        # LAYER MAP ...
        if self._at(TT.IDENT) and self._cur().value.upper() == 'MAP':
            self._advance()  # MAP
            gds_num = self._consume_int()
            map_type = 'DATATYPE'
            if self._at(TT.IDENT):
                mt = self._cur().value.upper()
                if mt in ('DATATYPE', 'TEXTTYPE'):
                    map_type = mt
                    self._advance()
            # Collect remaining tokens on the line; the type specification
            # may include range operators (>=1 <=129) or equality (==250).
            # The last integer on the line is always internal_num.
            remaining = []
            while not self._at_eol():
                remaining.append(self._advance())
            self._consume_eol()
            # Find last integer token for internal_num
            internal_num = 0
            type_num = 0
            last_int_idx = -1
            for idx in range(len(remaining) - 1, -1, -1):
                if remaining[idx].type == TT.INTEGER:
                    last_int_idx = idx
                    break
            if last_int_idx >= 0:
                internal_num = remaining[last_int_idx].value
                # First integer before last_int_idx is type_num (simple case)
                for idx in range(last_int_idx):
                    if remaining[idx].type == TT.INTEGER:
                        type_num = remaining[idx].value
                        break
            return ast.LayerMap(gds_num=gds_num, map_type=map_type,
                                type_num=type_num, internal_num=internal_num,
                                **loc)

        # LAYER IGNORE ...
        if self._at(TT.IDENT) and self._cur().value.upper() == 'IGNORE':
            self._advance()  # IGNORE
            num = self._consume_int()
            self._skip_to_eol()
            self._consume_eol()
            return ast.LayerDef(name='IGNORE', numbers=[num], **loc)

        # LAYER name number [number...]
        name = ''
        if self._at(TT.IDENT):
            name = self._advance().value
        nums = []
        while not self._at_eol():
            if self._at(TT.INTEGER):
                nums.append(self._advance().value)
            elif self._at(TT.IDENT):
                nums.append(self._advance().value)
            else:
                break
        self._skip_to_eol()
        self._consume_eol()
        return ast.LayerDef(name=name, numbers=nums, **loc)

    def _consume_int(self):
        if self._at(TT.INTEGER):
            return self._advance().value
        if self._at(TT.FLOAT):
            return int(self._advance().value)
        return 0

    # ------------------------------------------------------------------
    # VARIABLE
    # ------------------------------------------------------------------
    def _parse_variable(self):
        loc = self._loc()
        self._advance()  # VARIABLE
        name = ''
        if self._at(TT.IDENT):
            name = self._advance().value
        elif self._at(TT.INTEGER) and self._peek().type == TT.IDENT:
            # Handle names starting with digits (e.g. 2xmn_DN_6_WINDOW)
            name = str(self._advance().value) + self._advance().value
        # Consume multiple string values: VARIABLE POWER_NAME "?VDD?" "?VCC?"
        if self._at(TT.STRING):
            parts = []
            while self._at(TT.STRING) and not self._at_eol():
                parts.append(self._advance().value)
            expr = ast.StringLiteral(value=' '.join(parts), **self._loc()) if parts else None
        else:
            expr = self._parse_line_expression()
        self._consume_eol()
        return ast.VariableDef(name=name, expr=expr, **loc)

    # ------------------------------------------------------------------
    # CONNECT / SCONNECT
    # ------------------------------------------------------------------
    def _parse_connect(self):
        loc = self._loc()
        tok = self._advance()
        soft = tok.value.upper() == 'SCONNECT'
        layers = []
        via = None
        while not self._at_eol():
            if self._at(TT.IDENT) and self._cur().value.upper() == 'BY':
                self._advance()
                if self._at(TT.IDENT):
                    via = self._advance().value
                break
            if self._at(TT.IDENT):
                layers.append(self._advance().value)
            elif self._at(TT.INTEGER):
                layers.append(str(self._advance().value))
            else:
                break
        self._skip_to_eol()
        self._consume_eol()
        return ast.Connect(soft=soft, layers=layers,
                           via_layer=via, **loc)

    # ------------------------------------------------------------------
    # DEVICE
    # ------------------------------------------------------------------
    def _parse_device(self):
        loc = self._loc()
        self._advance()  # DEVICE
        dev_type = None
        dev_name = None
        # First token could be TYPE(name) or just name
        if self._at(TT.IDENT):
            first = self._advance()
            if self._at(TT.LPAREN):
                # TYPE(name) pattern
                dev_type = first.value
                self._advance()  # (
                if self._at(TT.IDENT):
                    dev_name = self._advance().value
                if self._at(TT.RPAREN):
                    self._advance()
            else:
                dev_name = first.value
        # Seed layer
        seed = ''
        if self._at(TT.IDENT):
            seed = self._advance().value
        # Pins, aux layers, CMACRO
        pins = []
        aux = []
        cmacro = None
        cmacro_args = []
        while not self._at_eol():
            if self._at(TT.IDENT) and self._cur().value.upper() == 'CMACRO':
                self._advance()
                if self._at(TT.IDENT):
                    cmacro = self._advance().value
                while not self._at_eol():
                    if self._at(TT.IDENT):
                        cmacro_args.append(self._advance().value)
                    elif self._at(TT.INTEGER):
                        cmacro_args.append(self._advance().value)
                    elif self._at(TT.FLOAT):
                        cmacro_args.append(self._advance().value)
                    elif self._at(TT.MINUS):
                        self._advance()
                        if self._at(TT.FLOAT):
                            cmacro_args.append(-self._advance().value)
                        elif self._at(TT.INTEGER):
                            cmacro_args.append(-self._advance().value)
                    else:
                        _st = self._cur()
                        self.warnings.append(
                            f"L{_st.line}:{_st.col}: Unexpected token {_st.type.name} "
                            f"({_st.value!r}) in DEVICE CMACRO args, skipping")
                        self._advance()
                break
            if self._at(TT.LT):
                # <aux_layer>
                self._advance()
                if self._at(TT.IDENT):
                    aux.append(self._advance().value)
                if self._at(TT.GT_OP):
                    self._advance()
                continue
            if self._at(TT.IDENT):
                layer = self._advance().value
                role = None
                if self._at(TT.LPAREN):
                    self._advance()
                    if self._at(TT.IDENT):
                        role = self._advance().value
                    if self._at(TT.RPAREN):
                        self._advance()
                pins.append((layer, role))
                continue
            self._advance()
        self._consume_eol()
        return ast.Device(device_type=dev_type, device_name=dev_name,
                          seed_layer=seed, pins=pins, aux_layers=aux,
                          cmacro=cmacro, cmacro_args=cmacro_args, **loc)

    # ------------------------------------------------------------------
    # DMACRO
    # ------------------------------------------------------------------
    def _parse_dmacro(self):
        loc = self._loc()
        self._advance()  # DMACRO
        name = ''
        # Handle digit-prefixed names: INTEGER + IDENT (e.g. 3T_MOS_PRO)
        if self._at(TT.INTEGER) and self._peek().type == TT.IDENT:
            name = str(self._advance().value)
        if self._at(TT.IDENT):
            name += self._advance().value
        params = []
        while not self._at_eol() and not self._at(TT.LBRACE):
            if self._at(TT.IDENT):
                params.append(self._advance().value)
            else:
                break
        # Parse body inside { }
        body = []
        if self._at(TT.LBRACE):
            self._advance()
            self._consume_eol()
            body = self._parse_block_body()
        else:
            self._consume_eol()
        return ast.DMacro(name=name, params=params, body=body, **loc)

    def _parse_block_body(self):
        """Parse statements inside { } until closing brace."""
        self._block_depth += 1
        stmts = []
        while not self._at(TT.EOF) and not self._at(TT.RBRACE):
            self._skip_newlines()
            if self._at(TT.RBRACE) or self._at(TT.EOF):
                break
            # Stop at preprocessor scope-ending tokens
            if self._cur().type in (TT.PP_ENDIF, TT.PP_ELSE):
                break
            saved = self.pos
            s = self._parse_statement()
            if s is not None:
                stmts.append(s)
            if self.pos == saved:
                t = self._cur()
                self.warnings.append(
                    f"L{t.line}:{t.col}: Parser stuck in block body at "
                    f"{t.type.name} ({t.value!r}), force advancing")
                self._advance()
        if self._at(TT.RBRACE):
            self._advance()
        self._consume_eol()
        self._block_depth -= 1
        return stmts

    # ------------------------------------------------------------------
    # ATTACH, GROUP, TRACE PROPERTY
    # ------------------------------------------------------------------
    def _parse_attach(self):
        loc = self._loc()
        self._advance()  # ATTACH
        layer = ''
        net = ''
        if self._at(TT.IDENT):
            layer = self._advance().value
        if self._at(TT.IDENT):
            net = self._advance().value
        elif self._at(TT.INTEGER):
            net = str(self._advance().value)
        self._skip_to_eol()
        self._consume_eol()
        return ast.Attach(layer=layer, net=net, **loc)

    def _parse_group(self):
        loc = self._loc()
        self._advance()  # GROUP
        name = ''
        pattern = ''
        if self._at(TT.IDENT):
            name = self._advance().value
        if self._at(TT.IDENT):
            pattern = self._advance().value
        self._skip_to_eol()
        self._consume_eol()
        return ast.Group(name=name, pattern=pattern, **loc)

    def _parse_trace_property(self):
        loc = self._loc()
        self._advance()  # TRACE
        self._advance()  # PROPERTY
        device = ''
        args = []
        # Device name, possibly TYPE(name)
        if self._at(TT.IDENT):
            device = self._advance().value
            if self._at(TT.LPAREN):
                self._advance()
                if self._at(TT.IDENT):
                    device = device + '(' + self._advance().value + ')'
                if self._at(TT.RPAREN):
                    self._advance()
        while not self._at_eol():
            if self._at(TT.IDENT):
                args.append(self._advance().value)
            elif self._at(TT.INTEGER):
                args.append(str(self._advance().value))
            elif self._at(TT.FLOAT):
                args.append(str(self._advance().value))
            elif self._at(TT.STRING):
                args.append(self._advance().value)
            else:
                break
        self._consume_eol()
        return ast.TraceProperty(device=device, args=args, **loc)

    # ------------------------------------------------------------------
    # Generic directive parser
    # ------------------------------------------------------------------
    def _parse_directive(self):
        loc = self._loc()
        keywords = []
        # Greedily consume uppercase identifiers as keywords
        while self._at(TT.IDENT):
            val = self._cur().value
            upper = val.upper()
            # Stop if next is EQUALS (it's an assignment, not a keyword)
            if self._peek().type == TT.EQUALS:
                break
            # Stop if this looks like a non-keyword argument (lowercase layer name
            # after we already have keywords, and it's not a known directive word)
            if keywords and upper not in _DIRECTIVE_HEADS and upper not in {
                'SYSTEM', 'GDSII', 'OASIS', 'SPICE', 'PRIMARY', 'PATH',
                'RESULTS', 'DATABASE', 'SUMMARY', 'REPORT', 'KEEP', 'CHECK',
                'MAXIMUM', 'INCREMENTAL', 'MAGNIFY', 'PROCESS', 'BOX',
                'RECORD', 'CLONE', 'ROTATED', 'PLACEMENTS', 'INPUT',
                'EXCEPTION', 'SEVERITY', 'ALLOW', 'DUPLICATE', 'CELL',
                'ERROR', 'DEPTH', 'BASE', 'ORDER', 'CASE', 'COMPARE',
                'OPTION', 'NAME', 'STRICT', 'PREFER', 'PINS', 'RECOGNIZE',
                'GATES', 'ABORT', 'SUPPLY', 'IGNORE', 'PORTS', 'REDUCE',
                'PARALLEL', 'SERIES', 'SPLIT', 'FILTER', 'UNUSED',
                'PROPERTY', 'GROUND', 'POWER', 'SPICE', 'MULTIPLIER',
                'REPLICATE', 'DEVICES', 'SWAPPABLE', 'CAPACITOR',
                'BIPOLAR', 'MOS', 'DIODES', 'CAPACITORS', 'RESISTORS',
                'SOFTCHK', 'CONTACT', 'COLON', 'CONNECT',
                'EXCLUDE', 'FALSE', 'NOTCH', 'NONSIMPLE', 'ACUTE',
                'SKEW', 'OFFGRID', 'EMPTY', 'ALL', 'NAR',
                'YES', 'NO', 'NONE', 'ON', 'TRUE',
                'DENSITY', 'HIER', 'ASCII', 'HSPICE', 'LUMPED',
                'DISTRIBUTED', 'DIRECTORY', 'QUERY', 'XRC', 'CCI',
                'NETLIST', 'CAPACITANCE', 'RESISTANCE', 'LENGTH',
                'FF', 'OHM', 'PRECISION', 'RESOLUTION', 'MAGNIFY',
                'AUTO', 'MANUAL', 'MASK',
            } and not upper.isupper():
                break
            keywords.append(self._advance().value)
        # Collect remaining tokens on the line as arguments
        arguments = []
        while not self._at_eol():
            t = self._cur()
            if t.type == TT.STRING:
                arguments.append(self._advance().value)
            elif t.type == TT.INTEGER:
                arguments.append(self._advance().value)
            elif t.type == TT.FLOAT:
                arguments.append(self._advance().value)
            elif t.type == TT.IDENT:
                arguments.append(self._advance().value)
            elif t.type == TT.MINUS:
                self._advance()
                if self._at(TT.INTEGER):
                    arguments.append(-self._advance().value)
                elif self._at(TT.FLOAT):
                    arguments.append(-self._advance().value)
                else:
                    arguments.append('-')
            elif t.type == TT.LBRACKET:
                # Property block
                pb = self._parse_property_block()
                return ast.Directive(keywords=keywords, arguments=arguments,
                                     property_block=pb, **loc)
            else:
                # Operators and delimiters are valid in directive arguments
                # (e.g. > for redirect, () for grouping, comparisons, etc.)
                arguments.append(str(self._advance().value))
        self._consume_eol()
        return ast.Directive(keywords=keywords, arguments=arguments, **loc)

    # ------------------------------------------------------------------
    # Layer assignment: name = expression
    # ------------------------------------------------------------------
    def _parse_assignment(self):
        loc = self._loc()
        # Handle digit-prefixed names: INTEGER + IDENT
        name = ''
        if self._at(TT.INTEGER) and self._peek().type == TT.IDENT:
            name = str(self._advance().value)
        name += self._advance().value  # name
        self._advance()  # =
        # Expression may start on the next line
        if self._at_eol():
            self._consume_eol()
            self._skip_newlines()
        expr = self._parse_layer_expr(0)
        self._consume_eol()
        return ast.LayerAssignment(name=name, expression=expr, **loc)

    # ------------------------------------------------------------------
    # Rule check block: name { @desc body... }
    # ------------------------------------------------------------------
    def _parse_rule_check_block(self):
        loc = self._loc()
        # Handle digit-prefixed names: INTEGER + IDENT
        name = ''
        if self._at(TT.INTEGER) and self._peek().type == TT.IDENT:
            name = str(self._advance().value)
        name += self._advance().value  # IDENT name
        self._skip_newlines()         # { may be on the next line
        self._advance()               # {
        self._skip_newlines()
        desc = None
        if self._at(TT.AT):
            desc = self._parse_at_description()
        body = self._parse_block_body()
        return ast.RuleCheckBlock(name=name, description=desc, body=body, **loc)

    # ------------------------------------------------------------------
    # @ description line
    # ------------------------------------------------------------------
    def _parse_at_description(self):
        loc = self._loc()
        self._advance()  # @
        parts = []
        while not self._at_eol():
            parts.append(str(self._advance().value))
        text = ' '.join(parts)
        self._consume_eol()
        return ast.Directive(keywords=['@'], arguments=[text], **loc)
