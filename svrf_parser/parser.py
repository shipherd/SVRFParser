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
    'AND', 'OR', 'NOT', 'XOR', 'INSIDE', 'OUTSIDE', 'OUT', 'INTERACT',
    'TOUCH', 'ENCLOSE', 'BY', 'CUT',
})

# Binding powers for layer binary operators
_LAYER_BP = {
    'OR': 10,
    'XOR': 10,
    'AND': 20,
    'NOT': 20,
    'INSIDE': 30,
    'OUTSIDE': 30,
    'OUT': 30,
    'INTERACT': 30,
    'TOUCH': 30,
    'ENCLOSE': 30,
    'IN': 30,
    'COIN': 30,
    'COINCIDENT': 30,
    'CUT': 30,
    'BY': 35,
}

# Unary prefix operations in layer expressions
_UNARY_OPS = frozenset({
    'NOT', 'COPY', 'HOLES', 'DONUT', 'EXTENT',
})

# DRC check operations (prefix-style in rule check blocks)
_DRC_OPS = frozenset({
    'INT', 'EXT', 'ENC', 'ENCLOSE', 'DENSITY',
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

# Identifiers that can START a layer expression in _layer_nud()
# (explicit branches before the fallback).
_EXPR_STARTERS = frozenset({
    'NOT', 'COPY', 'PUSH', 'MERGE',
    'SIZE', 'SHIFT', 'GROW', 'SHRINK',
    'HOLES', 'DONUT', 'EXTENT', 'STAMP',
    'RECTANGLE', 'RECTANGLES', 'EXTENTS',
    'AREA', 'VERTEX', 'ANGLE', 'LENGTH',
    'CONVEX', 'EXPAND', 'DFM', 'RET',
    'OR', 'WITH', 'DRAWN',
    'INTERACT', 'ENCLOSE', 'CUT',
}) | _DRC_OPS

# SVRF keywords that should NOT be treated as layer names in expression
# context, unless they appear in the prescan symbol table.
_SVRF_KEYWORDS = (
    _DIRECTIVE_HEADS | _DRC_MODIFIERS | _EXPR_STARTERS | {
        'OF', 'BY', 'STEP', 'TRUNCATE', 'LAYER',
        'CONNECT', 'SCONNECT', 'DEVICE', 'DMACRO',
        'ATTACH', 'GROUP', 'TRACE', 'PROPERTY',
        'IF', 'ELSE', 'ENDIF',
        'CMACRO', 'UNDEROVER', 'OVERUNDER',
    }
)


class Parser:
    """SVRF parser using recursive descent + Pratt parsing."""

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.length = len(tokens)
        self.warnings = []
        self._block_depth = 0
        self._known_layers = self._prescan()

    # ------------------------------------------------------------------
    # Prescan: collect known layer/variable names (Pass 1)
    # ------------------------------------------------------------------
    def _prescan(self):
        """Lightweight scan of token stream to build symbol table.

        Recognizes:
          LAYER <name> <number>      → layer definition
          <name> = ...               → layer assignment
          VARIABLE <name> ...        → variable definition
          #DEFINE <name> ...         → macro definition
        """
        known = set()
        i = 0
        toks = self.tokens
        length = self.length
        while i < length:
            t = toks[i]
            if t.type == TT.IDENT:
                upper = t.value.upper()
                # LAYER <name> <number>
                if upper == 'LAYER' and i + 2 < length:
                    nxt = toks[i + 1]
                    nxt2 = toks[i + 2]
                    if nxt.type == TT.IDENT and nxt2.type in (TT.INTEGER, TT.FLOAT):
                        known.add(nxt.value.upper())
                # <name> = ...  (layer assignment)
                elif i + 1 < length and toks[i + 1].type == TT.EQUALS:
                    known.add(upper)
                # VARIABLE <name>
                elif upper == 'VARIABLE' and i + 1 < length:
                    nxt = toks[i + 1]
                    if nxt.type == TT.IDENT:
                        known.add(nxt.value.upper())
            elif t.type == TT.PP_DEFINE and i + 1 < length:
                nxt = toks[i + 1]
                if nxt.type == TT.IDENT:
                    known.add(nxt.value.upper())
            i += 1
        return known

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

    def _peek_skip_newlines(self, offset=1):
        """Peek at the next non-NEWLINE token without advancing."""
        p = self.pos + offset
        while p < self.length and self.tokens[p].type == TT.NEWLINE:
            p += 1
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

        # @ description line (inside rule check blocks)
        if tt == TT.AT:
            return self._parse_at_description()

        # [ property block (inside DMACRO)
        if tt == TT.LBRACKET:
            return self._parse_property_block()

        # Parenthesized expression inside block bodies:
        # e.g. (NW INTERACT NWDMY) AND TrGATE
        if tt == TT.LPAREN and self._block_depth > 0:
            return self._parse_bare_expression()

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

        # Rule check block: name { ... }  (the { may be on the next line)
        # Exclude control-flow keywords (ELSE, IF) which also use { }.
        if upper not in ('ELSE', 'IF'):
            if nxt.type == TT.LBRACE or (nxt.type == TT.NEWLINE and self._peek_skip_newlines().type == TT.LBRACE):
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
        # NET AREA RATIO / NET INTERACT are DRC ops inside rule check blocks,
        # not directives — let them fall through to bare expression parsing.
        if upper in _DIRECTIVE_HEADS:
            if upper == 'NET' and self._block_depth > 0:
                nxt = self._peek()
                if nxt.type == TT.IDENT and nxt.value.upper() in ('AREA', 'INTERACT'):
                    return self._parse_bare_expression()
            return self._parse_directive()

        # DVPARAMS is a directive-like statement inside rule check blocks
        if upper == 'DVPARAMS':
            return self._parse_directive()

        # RDB is a directive-like statement (RDB "path" layer1 layer2)
        if upper == 'RDB':
            return self._parse_directive()

        # IF / ELSE IF / ELSE blocks (can appear outside property blocks,
        # e.g. when #IFDEF splits a [PROPERTY ...] header across branches)
        if upper == 'IF':
            return self._parse_if_expr()

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
        # Handle digit-prefixed names: INTEGER + IDENT
        name = ''
        if self._at(TT.INTEGER) and self._peek().type == TT.IDENT:
            name = str(self._advance().value)
        name += self._advance().value  # name
        self._advance()  # =
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
                    self._advance()
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
        if t.type == TT.CARET:
            return 25
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

    def _can_start_layer_expr(self):
        """Check if current token can begin a layer expression.

        Uses the prescan symbol table to distinguish layer names from
        SVRF keywords that should terminate operand consumption.
        """
        t = self._cur()
        if t.type in (TT.LPAREN, TT.LBRACKET, TT.INTEGER,
                       TT.FLOAT, TT.STRING, TT.MINUS):
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

        if t.type != TT.IDENT:
            self._advance()
            return ast.NumberLiteral(value=0, **loc)

        upper = t.value.upper()

        if upper == 'DFM':
            return self._parse_dfm_op()
        if upper == 'RET':
            return self._parse_dfm_op()  # RET follows same pattern as DFM
        if upper in _DRC_OPS:
            return self._parse_drc_op()
        if upper == 'SIZE':
            return self._parse_size_op()
        if upper == 'SHIFT':
            return self._parse_size_op()  # same pattern: SHIFT layer BY dx dy
        if upper == 'AREA':
            return self._parse_area_op()
        if upper == 'VERTEX':
            return self._parse_unary_constrained_op()
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
        if upper == 'EXPAND' and self._peek().type == TT.IDENT and \
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
        if upper == 'RECTANGLE':
            return self._parse_rectangle_op()
        if upper == 'RECTANGLES':
            return self._parse_rectangles_op()
        if upper == 'EXTENTS':
            return self._parse_rectangles_op()  # same pattern: EXTENTS operand...
        if upper == 'NOT':
            self._advance()
            operand = self._parse_layer_expr(50)
            return ast.UnaryOp(op='NOT', operand=operand, **loc)
        if upper == 'COPY':
            self._advance()
            operand = self._parse_layer_expr(50)
            return ast.UnaryOp(op='COPY', operand=operand, **loc)
        if upper == 'PUSH':
            self._advance()
            operand = self._parse_layer_expr(0)
            return ast.UnaryOp(op='PUSH', operand=operand, **loc)
        if upper == 'MERGE':
            self._advance()
            operand = self._parse_layer_expr(50)
            return ast.UnaryOp(op='MERGE', operand=operand, **loc)
        if upper in ('GROW', 'SHRINK'):
            return self._parse_grow_shrink_op()
        if upper == 'HOLES':
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
        if upper == 'DONUT':
            self._advance()
            operand = self._parse_layer_expr(50)
            return ast.UnaryOp(op='DONUT', operand=operand, **loc)
        if upper == 'EXTENT':
            return self._parse_extent_op()
        if upper == 'STAMP':
            return self._parse_stamp_op()

        # OFFGRID: DRC op with operands and modifiers
        if upper == 'OFFGRID':
            return self._parse_offgrid_op()

        # ROTATE operand BY angle
        if upper == 'ROTATE':
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

        # DEVICE LAYER device_ref ANNOTATE layer (inside expressions)
        if upper == 'DEVICE' and self._peek().type == TT.IDENT and \
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

        # Prefix OR / OR EDGE: OR [EDGE] layer1 layer2 layer3 ...
        # Supports multiline continuation inside blocks:
        #   name = OR
        #            op1
        #            op2
        if upper == 'OR':
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

        # Prefix XOR: XOR A B (same pattern as prefix OR)
        if upper == 'XOR':
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

        # Prefix AND: AND layer1 layer2 layer3 ...
        if upper == 'AND':
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

        # GOOD: DRC passing-pattern specification inside rule check blocks
        # Pattern: GOOD L1 L2 OPPOSITE L3 L4 OPPOSITE // values
        if upper == 'GOOD':
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

        # NET AREA RATIO / NET AREA: antenna check operations
        if upper == 'NET':
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

        # Multi-word edge operators as prefix (e.g. after NOT):
        # COIN [INSIDE|OUTSIDE] EDGE, IN [INSIDE|OUTSIDE] EDGE,
        # TOUCH [INSIDE|OUTSIDE] EDGE, INSIDE EDGE, OUTSIDE EDGE
        if upper in ('COIN', 'IN', 'COINCIDENT'):
            nxt = self._peek()
            if nxt.type == TT.IDENT:
                nxt_u = nxt.value.upper()
                if nxt_u == 'EDGE':
                    self._advance()  # COIN/IN
                    self._advance()  # EDGE
                    operand = self._parse_layer_expr(50)
                    return ast.UnaryOp(op=upper + ' EDGE', operand=operand, **loc)
                if nxt_u in ('INSIDE', 'OUTSIDE'):
                    nxt2 = self._peek(2)
                    if nxt2 and nxt2.type == TT.IDENT and nxt2.value.upper() == 'EDGE':
                        self._advance()  # COIN/IN
                        middle = self._advance().value.upper()  # INSIDE/OUTSIDE
                        self._advance()  # EDGE
                        operand = self._parse_layer_expr(50)
                        return ast.UnaryOp(op=upper + ' ' + middle + ' EDGE', operand=operand, **loc)
        if upper == 'TOUCH':
            nxt = self._peek()
            if nxt.type == TT.IDENT:
                nxt_u = nxt.value.upper()
                if nxt_u == 'EDGE':
                    self._advance()  # TOUCH
                    self._advance()  # EDGE
                    operand = self._parse_layer_expr(50)
                    return ast.UnaryOp(op='TOUCH EDGE', operand=operand, **loc)
                if nxt_u in ('INSIDE', 'OUTSIDE'):
                    nxt2 = self._peek(2)
                    if nxt2 and nxt2.type == TT.IDENT and nxt2.value.upper() == 'EDGE':
                        self._advance()  # TOUCH
                        middle = self._advance().value.upper()  # INSIDE/OUTSIDE
                        self._advance()  # EDGE
                        operand = self._parse_layer_expr(50)
                        return ast.UnaryOp(op='TOUCH ' + middle + ' EDGE', operand=operand, **loc)
        if upper in ('INSIDE', 'OUTSIDE'):
            nxt = self._peek()
            if nxt.type == TT.IDENT and nxt.value.upper() == 'EDGE':
                self._advance()  # INSIDE/OUTSIDE
                self._advance()  # EDGE
                operand = self._parse_layer_expr(50)
                return ast.UnaryOp(op=upper + ' EDGE', operand=operand, **loc)
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

        # INTERACT/ENCLOSE as prefix unary (e.g. NOT INTERACT OD2)
        if upper in ('INTERACT', 'ENCLOSE', 'CUT'):
            self._advance()
            operand = self._parse_layer_expr(50)
            return ast.UnaryOp(op=upper, operand=operand, **loc)

        # WITH as prefix (e.g. NOT WITH EDGE layer, WITH WIDTH layer == val)
        if upper == 'WITH':
            # Parse as DRC op: WITH sub-op operand [constraints] [modifiers]
            return self._parse_with_prefix_op()

        if upper == 'DRAWN':
            self._advance()
            keywords = ['DRAWN']
            while self._at(TT.IDENT) and not self._at_eol():
                keywords.append(self._advance().value)
            return ast.Directive(keywords=keywords, arguments=[], **loc)
        if self._peek().type == TT.LPAREN:
            # Only treat as function call if ( is adjacent (no space),
            # e.g. AREA(M1) but not SQR_VIA (RECTANGLE ...)
            nxt = self._peek()
            if nxt.col == t.col + len(t.value):
                return self._parse_func_call()

        # Fallback: treat as layer reference.
        # (The _can_start_layer_expr() guard in greedy loops prevents
        # keywords like OF/BY/LAYER from reaching here in those contexts.)
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
            if upper in ('ANGLE', 'LENGTH', 'AREA'):
                # Check if followed by constraint (e.g. layer ANGLE == 45)
                nxt = self._peek()
                if nxt.type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
                    return 5
                return 0
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
    # LED (infix)
    # ------------------------------------------------------------------
    def _layer_led(self, left):
        t = self._cur()
        loc = self._loc()

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

            # IN EDGE / COIN EDGE / COIN INSIDE EDGE / COIN OUTSIDE EDGE
            # COINCIDENT EDGE / COINCIDENT INSIDE EDGE / COINCIDENT OUTSIDE EDGE
            if upper in ('IN', 'COIN', 'COINCIDENT'):
                self._advance()  # IN or COIN
                middle = ''
                if self._at(TT.IDENT) and self._cur().value.upper() in ('INSIDE', 'OUTSIDE'):
                    middle = ' ' + self._advance().value.upper()
                self._advance()  # EDGE
                op = upper + middle + ' EDGE'
                right = self._parse_layer_expr(30)
                result = ast.BinaryOp(op=op, left=left, right=right, **loc)
                return self._maybe_trailing_modifiers(result, loc)

            # WITH -> parse_with_op
            if upper == 'WITH':
                return self._parse_with_op(left)

            # TOUCH / TOUCH EDGE / TOUCH INSIDE EDGE / TOUCH OUTSIDE EDGE
            if upper == 'TOUCH':
                self._advance()
                if self._at(TT.IDENT) and self._cur().value.upper() in ('INSIDE', 'OUTSIDE'):
                    middle = self._cur().value.upper()
                    nxt = self._peek()
                    if nxt.type == TT.IDENT and nxt.value.upper() == 'EDGE':
                        self._advance()  # INSIDE/OUTSIDE
                        self._advance()  # EDGE
                        right = self._parse_layer_expr(30)
                        result = ast.BinaryOp(op='TOUCH ' + middle + ' EDGE',
                                            left=left, right=right, **loc)
                        return self._maybe_trailing_modifiers(result, loc)
                if self._at_val('EDGE'):
                    self._advance()
                    right = self._parse_layer_expr(30)
                    result = ast.BinaryOp(op='TOUCH EDGE', left=left,
                                        right=right, **loc)
                    return self._maybe_trailing_modifiers(result, loc)
                right = self._parse_layer_expr(30)
                result = ast.BinaryOp(op='TOUCH', left=left,
                                    right=right, **loc)
                return self._maybe_trailing_modifiers(result, loc)

            # HOLES / DONUT as postfix: layer HOLES -> HOLES layer
            if upper in ('HOLES', 'DONUT'):
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

            # ANGLE/LENGTH/AREA as infix measurement: layer ANGLE == 45
            if upper in ('ANGLE', 'LENGTH', 'AREA'):
                self._advance()  # ANGLE/LENGTH/AREA
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

            # RECTANGLE as postfix: layer RECTANGLE == val BY == val
            if upper == 'RECTANGLE':
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

            # EXPAND EDGE as postfix: (expr) EXPAND EDGE INSIDE BY val
            if upper == 'EXPAND':
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

            # NET as infix: layer NET INTERACT/AREA RATIO layer > value
            if upper == 'NET':
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

            # SIZE as infix: (expr) SIZE BY value modifiers
            if upper == 'SIZE':
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

            # Standard binary ops (AND, OR, NOT, INSIDE, OUTSIDE, etc.)
            bp = _LAYER_BP.get(upper, 0)
            if bp:
                self._advance()
                # INSIDE EDGE / OUTSIDE EDGE / TOUCH EDGE as two-word binary ops
                if upper in ('INSIDE', 'OUTSIDE', 'OUT', 'TOUCH') and self._at(TT.IDENT) and self._cur().value.upper() == 'EDGE':
                    self._advance()  # EDGE
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
                    right = self._parse_layer_expr(bp)
                    result = ast.BinaryOp(op=op_name, left=left,
                                        right=right, **loc)
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
                right = self._parse_layer_expr(bp)
                result = ast.BinaryOp(op=upper, left=left,
                                    right=right, **loc)
                # Spatial ops can have trailing constraints + modifiers
                if upper in ('INTERACT', 'INSIDE', 'OUTSIDE', 'OUT',
                             'ENCLOSE', 'TOUCH', 'CUT'):
                    return self._maybe_trailing_modifiers(result, loc)
                return result

        # Shouldn't reach here, but advance to avoid infinite loop
        self._advance()
        return left

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
                # Parenthesized expression as constraint value
                val = self._parse_layer_expr(0)
            constraints.append(ast.Constraint(op=op, value=val, **loc))
        return constraints

    # ------------------------------------------------------------------
    # DRC modifier consumption helper
    # ------------------------------------------------------------------
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
                self._advance()

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
                self._advance()
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
    def _parse_length_op(self):
        loc = self._loc()
        self._advance()  # LENGTH
        operand = self._parse_layer_expr(50)
        constraints = []
        if self._cur().type in (TT.LT, TT.GT_OP, TT.LE, TT.GE, TT.EQEQ, TT.BANGEQ):
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
                if upper_cur in ('INSIDE', 'OUTSIDE'):
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
                    self._advance()
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
                            self._advance()
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
