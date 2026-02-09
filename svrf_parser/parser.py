"""Recursive descent + Pratt parser for SVRF source files."""

from .tokens import TokenType, Token
from . import ast_nodes as ast

TT = TokenType


class SVRFParseError(Exception):
    """Parse error with source location."""
    def __init__(self, msg, line=0, col=0):
        self.line = line
        self.col = col
        super().__init__(f"L{line}:{col}: {msg}")


# Keywords that start multi-word directives (not layer operations)
_DIRECTIVE_HEADS = frozenset({
    'LAYOUT', 'SOURCE', 'DRC', 'LVS', 'ERC', 'PEX', 'MASK',
    'FLAG', 'UNIT', 'TEXT', 'PORT', 'VIRTUAL', 'SVRF', 'PRECISION',
    'RESOLUTION', 'LABEL', 'TITLE', 'NET', 'PATHCHK',
    'DRAWN', 'STAMP',
    # Additional directive heads from the SVRF specification
    'DFM', 'RET', 'SONR', 'TDDRC', 'PERC', 'LITHO',
    'MDP', 'MDPMERGE', 'FRACTURE',
    'HCELL', 'FILTER', 'EXCLUDE', 'FLATTEN',
    'VARIABLE', 'ENVIRONMENT',
})

# Keywords that are layer boolean/spatial operators (used in Pratt parsing)
_BINARY_OPS = frozenset({
    'AND', 'OR', 'NOT', 'INSIDE', 'OUTSIDE', 'INTERACT', 'TOUCH',
    'ENCLOSE', 'BY',
})

# Binding powers for layer binary operators
_LAYER_BP = {
    'OR': 10,
    'AND': 20,
    'NOT': 20,
    'INSIDE': 30,
    'OUTSIDE': 30,
    'INTERACT': 30,
    'TOUCH': 30,
    'ENCLOSE': 30,
    'IN': 30,
    'COIN': 30,
    'BY': 35,
}

# Unary prefix operations in layer expressions
_UNARY_OPS = frozenset({
    'NOT', 'COPY', 'HOLES', 'DONUT', 'EXTENT',
})

# DRC check operations (prefix-style in rule check blocks)
_DRC_OPS = frozenset({
    'INT', 'EXT', 'ENC', 'DENSITY',
})

# Modifiers that can follow DRC operations
_DRC_MODIFIERS = frozenset({
    'ABUT', 'SINGULAR', 'REGION', 'OPPOSITE', 'NOTCH',
    'DRAWN', 'ORIGINAL', 'INSIDE', 'OUTSIDE',
    'CONNECTED', 'WINDOW', 'STEP', 'BACKUP',
    'RDB', 'PRINT', 'POLYGON', 'EMPTY', 'INNER',
    'CORNER', 'ACUTE', 'OBTUSE', 'CONVEX',
    'RECTANGLE', 'SQUARE', 'ORTHOGONAL',
    'CENTERS', 'ALSO', 'ONLY', 'COUNT',
    'PERIMETER', 'HIER', 'CELL',
    'PROJECTING', 'PARALLEL', 'PERPENDICULAR',
    'LENGTH', 'WITH', 'EDGE',
    'LVSCAREFUL',
})


class Parser:
    """SVRF parser using recursive descent + Pratt parsing."""

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.length = len(tokens)
        self.warnings = []
        self._block_depth = 0

    # ------------------------------------------------------------------
    # Token stream helpers
    # ------------------------------------------------------------------
    def _cur(self):
        if self.pos < self.length:
            return self.tokens[self.pos]
        return Token(TT.EOF, '', 0, 0)

    def _peek(self, offset=1):
        p = self.pos + offset
        if p < self.length:
            return self.tokens[p]
        return Token(TT.EOF, '', 0, 0)

    def _advance(self):
        tok = self._cur()
        if self.pos < self.length:
            self.pos += 1
        return tok

    def _at(self, tt):
        return self._cur().type == tt

    def _at_val(self, val):
        t = self._cur()
        return t.type == TT.IDENT and t.value.upper() == val.upper()

    def _match(self, tt):
        if self._cur().type == tt:
            return self._advance()
        return None

    def _match_val(self, val):
        t = self._cur()
        if t.type == TT.IDENT and t.value.upper() == val.upper():
            return self._advance()
        return None

    def _expect(self, tt):
        tok = self._match(tt)
        if tok is None:
            c = self._cur()
            raise SVRFParseError(
                f"Expected {tt.name}, got {c.type.name}({c.value!r})",
                c.line, c.col)
        return tok

    def _skip_newlines(self):
        while self._at(TT.NEWLINE):
            self._advance()

    def _at_eol(self):
        return self._at(TT.NEWLINE) or self._at(TT.EOF)

    def _skip_to_eol(self):
        while not self._at_eol():
            self._advance()

    def _consume_eol(self):
        if self._at(TT.NEWLINE):
            self._advance()

    def _loc(self):
        t = self._cur()
        return {'line': t.line, 'col': t.col}

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
        if tt in (TT.PP_ENCRYPT, TT.PP_DECRYPT):
            return self._parse_encrypted()
        if tt == TT.PP_ELSE:
            return None  # handled by _parse_ifdef
        if tt == TT.PP_ENDIF:
            return None  # handled by _parse_ifdef
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

        # Block close (shouldn't appear at top level, but be safe)
        if tt == TT.RBRACE:
            self._advance()
            return None

        # Identifier-based dispatch
        if tt == TT.IDENT:
            return self._dispatch_ident()

        # @ description line (inside rule check blocks)
        if tt == TT.AT:
            return self._parse_at_description()

        # [ property block (inside DMACRO)
        if tt == TT.LBRACKET:
            return self._parse_property_block()

        # Skip unknown tokens
        t = self._cur()
        self.warnings.append(
            f"L{t.line}:{t.col}: Skipped unknown token {t.type.name} ({t.value!r})"
        )
        self._advance()
        return None

    # ------------------------------------------------------------------
    # Identifier dispatch
    # ------------------------------------------------------------------
    def _dispatch_ident(self):
        t = self._cur()
        name = t.value
        upper = name.upper()
        loc = self._loc()

        # Check next token for assignment or block
        nxt = self._peek()

        # Layer assignment: name = expression
        if nxt.type == TT.EQUALS:
            return self._parse_assignment()

        # Rule check block: name { ... }
        if nxt.type == TT.LBRACE:
            return self._parse_rule_check_block()

        # Keyword-based dispatch
        if upper == 'LAYER':
            return self._parse_layer()
        if upper == 'VARIABLE':
            return self._parse_variable()
        if upper in ('CONNECT', 'SCONNECT'):
            return self._parse_connect()
        if upper == 'DEVICE':
            return self._parse_device()
        if upper == 'DMACRO':
            return self._parse_dmacro()
        if upper == 'ATTACH':
            return self._parse_attach()
        if upper == 'GROUP':
            return self._parse_group()
        if upper == 'TRACE':
            if self._peek().type == TT.IDENT and self._peek().value.upper() == 'PROPERTY':
                return self._parse_trace_property()
            return self._parse_directive()

        # Multi-word directives
        if upper in _DIRECTIVE_HEADS:
            return self._parse_directive()

        # Bare expression (DRC operations inside rule check blocks, or
        # unrecognized top-level statements).  Only warn at the top level –
        # inside { } blocks bare expressions are expected SVRF constructs.
        if self._block_depth == 0:
            self.warnings.append(
                f"L{t.line}:{t.col}: Unrecognized SVRF statement, "
                f"treating {name!r} as bare expression"
            )
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
            type_num = self._consume_int()
            internal_num = self._consume_int()
            self._skip_to_eol()
            self._consume_eol()
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
        if self._at(TT.IDENT):
            name = self._advance().value
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
            saved = self.pos
            s = self._parse_statement()
            if s is not None:
                stmts.append(s)
            if self.pos == saved:
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
            else:
                self._advance()
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
                arguments.append(str(self._advance().value))
        self._consume_eol()
        return ast.Directive(keywords=keywords, arguments=arguments, **loc)

    # ------------------------------------------------------------------
    # Layer assignment: name = expression
    # ------------------------------------------------------------------
    def _parse_assignment(self):
        loc = self._loc()
        name = self._advance().value  # name
        self._advance()  # =
        expr = self._parse_layer_expr(0)
        self._consume_eol()
        return ast.LayerAssignment(name=name, expression=expr, **loc)

    # ------------------------------------------------------------------
    # Rule check block: name { @desc body... }
    # ------------------------------------------------------------------
    def _parse_rule_check_block(self):
        loc = self._loc()
        name = self._advance().value  # name
        self._advance()  # {
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
                self._advance()
        if self._at(TT.RBRACKET):
            self._advance()
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
        # Bare expression / skip – stop before ] so we don't consume the
        # closing bracket of the enclosing property block.
        while not self._at_eol() and not self._at(TT.RBRACKET):
            self._advance()
        self._consume_eol()
        return None

    def _parse_prop_assignment(self):
        """Parse property assignment: name = arith_expr"""
        loc = self._loc()
        name = self._advance().value
        self._advance()  # =
        expr = self._parse_arith_expr(0)
        self._consume_eol()
        return ast.LayerAssignment(name=name, expression=expr, **loc)

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
                    self._advance()
            if self._at(TT.RBRACE):
                self._advance()
        self._consume_eol()
        # ELSE IF / ELSE
        elseifs = []
        else_body = []
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
                            self._advance()
                    if self._at(TT.RBRACE):
                        self._advance()
                self._consume_eol()
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
                            self._advance()
                    if self._at(TT.RBRACE):
                        self._advance()
                self._consume_eol()
                break
        return ast.IfExpr(condition=cond, then_body=then_body,
                          elseifs=elseifs, else_body=else_body, **loc)

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
            expr = self._parse_arith_expr(0)
            if self._at(TT.RPAREN):
                self._advance()
            return expr
        if t.type == TT.MINUS:
            self._advance()
            operand = self._parse_arith_expr(30)
            return ast.UnaryOp(op='-', operand=operand, **loc)
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
        # Fallback
        self._advance()
        return ast.NumberLiteral(value=0, **loc)

    def _arith_led_bp(self):
        t = self._cur()
        if t.type in (TT.EQEQ, TT.BANGEQ, TT.LT, TT.GT_OP, TT.LE, TT.GE):
            return 5
        if t.type in (TT.PLUS, TT.MINUS):
            return 10
        if t.type in (TT.STAR, TT.SLASH):
            return 20
        if t.type == TT.AMPAMP:
            return 3
        if t.type == TT.PIPEPIPE:
            return 2
        return 0

    def _arith_led(self, left, nbp):
        t = self._cur()
        loc = self._loc()
        op = self._advance().value
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
        except (SVRFParseError, Exception):
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

    # ------------------------------------------------------------------
    # NUD (prefix / atom)
    # ------------------------------------------------------------------
    def _layer_nud(self):
        t = self._cur()
        loc = self._loc()

        if t.type == TT.LPAREN:
            self._advance()
            expr = self._parse_layer_expr(0)
            if self._at(TT.RPAREN):
                self._advance()
            return expr

        if t.type == TT.LBRACKET:
            return self._parse_bracket_expr()

        if t.type == TT.INTEGER:
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

        if t.type != TT.IDENT:
            self._advance()
            return ast.NumberLiteral(value=0, **loc)

        upper = t.value.upper()

        if upper in _DRC_OPS:
            return self._parse_drc_op()
        if upper == 'SIZE':
            return self._parse_size_op()
        if upper == 'AREA':
            return self._parse_area_op()
        if upper == 'ANGLE':
            return self._parse_angle_op()
        if upper == 'LENGTH':
            return self._parse_length_op()
        if upper == 'CONVEX' and self._peek().type == TT.IDENT and \
                self._peek().value.upper() == 'EDGE':
            return self._parse_convex_edge_op()
        if upper == 'EXPAND' and self._peek().type == TT.IDENT and \
                self._peek().value.upper() == 'EDGE':
            return self._parse_expand_edge_op()
        if upper == 'RECTANGLE':
            return self._parse_rectangle_op()
        if upper == 'NOT':
            self._advance()
            operand = self._parse_layer_expr(50)
            return ast.UnaryOp(op='NOT', operand=operand, **loc)
        if upper == 'COPY':
            self._advance()
            operand = self._parse_layer_expr(50)
            return ast.UnaryOp(op='COPY', operand=operand, **loc)
        if upper == 'HOLES':
            self._advance()
            operand = self._parse_layer_expr(50)
            return ast.UnaryOp(op='HOLES', operand=operand, **loc)
        if upper == 'DONUT':
            self._advance()
            operand = self._parse_layer_expr(50)
            return ast.UnaryOp(op='DONUT', operand=operand, **loc)
        if upper == 'EXTENT':
            return self._parse_extent_op()
        if upper == 'STAMP':
            return self._parse_stamp_op()
        if upper == 'DRAWN':
            self._advance()
            keywords = ['DRAWN']
            while self._at(TT.IDENT) and not self._at_eol():
                keywords.append(self._advance().value)
            return ast.Directive(keywords=keywords, arguments=[], **loc)
        if self._peek().type == TT.LPAREN:
            return self._parse_func_call()

        self._advance()
        return ast.LayerRef(name=t.value, **loc)

    # ------------------------------------------------------------------
    # LED binding power
    # ------------------------------------------------------------------
    def _layer_led_bp(self):
        t = self._cur()
        if t.type == TT.NEWLINE or t.type == TT.EOF:
            return 0
        if t.type in (TT.RBRACE, TT.RBRACKET, TT.RPAREN):
            return 0
        if t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            return 5
        if t.type == TT.IDENT:
            upper = t.value.upper()
            bp = _LAYER_BP.get(upper, 0)
            if bp:
                # IN EDGE / COIN EDGE: only if followed by EDGE
                if upper in ('IN', 'COIN'):
                    nxt = self._peek()
                    if nxt.type == TT.IDENT and nxt.value.upper() == 'EDGE':
                        return bp
                    return 0
                return bp
            if upper == 'WITH':
                return 35
            # Stop words: don't treat as infix
            if upper in _DRC_MODIFIERS or upper in _DRC_OPS or \
                    upper in _DIRECTIVE_HEADS:
                return 0
            if upper in ('CMACRO', 'PROPERTY', 'IF', 'ELSE'):
                return 0
        # Arithmetic operators as infix in layer expressions (e.g. AA*GT)
        if t.type == TT.STAR:
            return 40
        if t.type == TT.MINUS:
            return 38
        if t.type == TT.PLUS:
            return 36
        return 0

    # ------------------------------------------------------------------
    # LED (infix)
    # ------------------------------------------------------------------
    def _layer_led(self, left):
        t = self._cur()
        loc = self._loc()

        # Comparison operators -> constraints
        if t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
            constraints = self._parse_constraints()
            return ast.ConstrainedExpr(expr=left, constraints=constraints, **loc)

        # Arithmetic infix: *, -, +
        if t.type == TT.STAR:
            self._advance()
            right = self._parse_layer_expr(40)
            return ast.BinaryOp(op='*', left=left, right=right, **loc)
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

            # IN EDGE / COIN EDGE (two-word binary ops)
            if upper in ('IN', 'COIN'):
                self._advance()  # IN or COIN
                self._advance()  # EDGE
                op = upper + ' EDGE'
                right = self._parse_layer_expr(30)
                return ast.BinaryOp(op=op, left=left, right=right, **loc)

            # WITH -> parse_with_op
            if upper == 'WITH':
                return self._parse_with_op(left)

            # TOUCH EDGE special case
            if upper == 'TOUCH':
                self._advance()
                if self._at_val('EDGE'):
                    self._advance()
                    right = self._parse_layer_expr(30)
                    return ast.BinaryOp(op='TOUCH EDGE', left=left,
                                        right=right, **loc)
                right = self._parse_layer_expr(30)
                return ast.BinaryOp(op='TOUCH', left=left,
                                    right=right, **loc)

            # Standard binary ops (AND, OR, NOT, INSIDE, OUTSIDE, etc.)
            bp = _LAYER_BP.get(upper, 0)
            if bp:
                self._advance()
                right = self._parse_layer_expr(bp)
                return ast.BinaryOp(op=upper, left=left,
                                    right=right, **loc)

        # Shouldn't reach here, but advance to avoid infinite loop
        self._advance()
        return left

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
            constraints.append(ast.Constraint(op=op, value=val, **loc))
        return constraints

    # ------------------------------------------------------------------
    # DRC operations: INT/EXT/ENC/DENSITY layer [layer] constraints mods
    # ------------------------------------------------------------------
    def _parse_drc_op(self):
        loc = self._loc()
        op = self._advance().value.upper()  # INT/EXT/ENC/DENSITY
        operands = []
        constraints = []
        modifiers = []

        # Collect operands (layer refs, bracket exprs)
        while not self._at_eol():
            t = self._cur()
            if t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ):
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
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ):
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
            elif t.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ):
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
                self._advance()

        return ast.DRCOp(op=op, operands=operands,
                         constraints=constraints, modifiers=modifiers, **loc)

    # ------------------------------------------------------------------
    # SIZE layer BY value [UNDEROVER|OVERUNDER]
    # ------------------------------------------------------------------
    def _parse_size_op(self):
        loc = self._loc()
        self._advance()  # SIZE
        operand = self._parse_layer_expr(50)
        modifiers = []
        if self._at_val('BY'):
            self._advance()
            if self._at(TT.INTEGER) or self._at(TT.FLOAT):
                modifiers.append(str(self._advance().value))
            elif self._at(TT.MINUS):
                self._advance()
                if self._at(TT.INTEGER):
                    modifiers.append(str(-self._advance().value))
                elif self._at(TT.FLOAT):
                    modifiers.append(str(-self._advance().value))
            elif self._at(TT.IDENT):
                modifiers.append(self._advance().value)
        # Optional modifiers
        while not self._at_eol() and self._at(TT.IDENT):
            upper = self._cur().value.upper()
            if upper in ('UNDEROVER', 'OVERUNDER', 'INSIDE', 'OUTSIDE',
                         'TRUNCATE', 'GROW', 'SHRINK'):
                modifiers.append(self._advance().value)
            else:
                break
        return ast.DRCOp(op='SIZE', operands=[operand],
                         constraints=[], modifiers=modifiers, **loc)

    # ------------------------------------------------------------------
    # AREA layer constraints
    # ------------------------------------------------------------------
    def _parse_area_op(self):
        loc = self._loc()
        self._advance()  # AREA
        operand = self._parse_layer_expr(50)
        constraints = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ):
            constraints = self._parse_constraints()
        return ast.ConstrainedExpr(
            expr=ast.UnaryOp(op='AREA', operand=operand, **loc),
            constraints=constraints, **loc)

    # ------------------------------------------------------------------
    # ANGLE operation
    # ------------------------------------------------------------------
    def _parse_angle_op(self):
        loc = self._loc()
        self._advance()  # ANGLE
        operand = self._parse_layer_expr(50)
        constraints = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ):
            constraints = self._parse_constraints()
        return ast.ConstrainedExpr(
            expr=ast.UnaryOp(op='ANGLE', operand=operand, **loc),
            constraints=constraints, **loc)

    # ------------------------------------------------------------------
    # LENGTH operation (prefix)
    # ------------------------------------------------------------------
    def _parse_length_op(self):
        loc = self._loc()
        self._advance()  # LENGTH
        operand = self._parse_layer_expr(50)
        constraints = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ):
            constraints = self._parse_constraints()
        return ast.ConstrainedExpr(
            expr=ast.UnaryOp(op='LENGTH', operand=operand, **loc),
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
        while not self._at_eol():
            if self._at(TT.IDENT):
                modifiers.append(self._advance().value)
            elif self._at(TT.INTEGER) or self._at(TT.FLOAT):
                modifiers.append(str(self._advance().value))
            else:
                break
        return ast.DRCOp(op='EXPAND EDGE', operands=[operand],
                         constraints=[], modifiers=modifiers, **loc)

    # ------------------------------------------------------------------
    # RECTANGLE layer [constraints] [ORTHOGONAL ONLY]
    # ------------------------------------------------------------------
    def _parse_rectangle_op(self):
        loc = self._loc()
        self._advance()  # RECTANGLE
        operand = self._parse_layer_expr(50)
        constraints = []
        modifiers = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ):
            constraints = self._parse_constraints()
        while not self._at_eol() and self._at(TT.IDENT):
            modifiers.append(self._advance().value)
        return ast.DRCOp(op='RECTANGLE', operands=[operand],
                         constraints=constraints, modifiers=modifiers, **loc)

    # ------------------------------------------------------------------
    # EXTENT [DRAWN] [ORIGINAL]
    # ------------------------------------------------------------------
    def _parse_extent_op(self):
        loc = self._loc()
        self._advance()  # EXTENT
        modifiers = []
        while self._at(TT.IDENT) and not self._at_eol():
            upper = self._cur().value.upper()
            if upper in ('DRAWN', 'ORIGINAL'):
                modifiers.append(self._advance().value)
            else:
                break
        return ast.DRCOp(op='EXTENT', operands=[],
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
            modifier = self._advance().value
        constraints = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ):
            constraints = self._parse_constraints()
        return ast.ConstrainedExpr(
            expr=ast.BinaryOp(op='WITH', left=left,
                              right=ast.LayerRef(name=modifier, **loc), **loc),
            constraints=constraints, **loc)

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
