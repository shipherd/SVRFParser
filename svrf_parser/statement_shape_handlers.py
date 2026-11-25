"""Statement-shape parsing handlers for the live parser path."""

from __future__ import annotations

from . import ast
from .clause_cst import DelimitedGroupClause, OperandClause, ScalarClause
from .exceptions import ParseError
from .include_syntax import EMBEDDED_INCLUDE_HEADS
from .normalizer import normalize_statement_clause_cst
from .statement_shape import STATEMENT_SHAPE_REGISTRY
from .statement_block_handlers import StatementBlockParserMixin
from .tokens import TokenType

TT = TokenType


class StatementShapeParserMixin(StatementBlockParserMixin):
    """Concrete statement-family shape handlers."""

    def _parse_include_statement(self):
        return self._parse_statement_shape("include")

    def _parse_connect_statement(self):
        return self._parse_statement_shape("connect")

    def _parse_sconnect_statement(self):
        return self._parse_statement_shape("sconnect")

    def _parse_statement_shape(self, shape_name):
        shape = STATEMENT_SHAPE_REGISTRY.get(shape_name)
        if shape is None:
            token = self._cur()
            raise ParseError(
                f"Unknown statement shape {shape_name!r}",
                token.line,
                token.col,
                token,
            )
        return getattr(self, f"_parse_statement_shape_{shape.family}")(shape)

    def _try_normalize_active_statement_clause_cst(self, *parse_kinds, validator=None):
        clause_cst = self._active_statement_clause_cst(*parse_kinds)
        if clause_cst is None:
            return None
        if validator is not None and not validator(clause_cst):
            return None
        try:
            normalized = normalize_statement_clause_cst(clause_cst)
        except ValueError:
            return None
        self.pos = clause_cst.end
        return normalized

    def _active_statement_clause_cst(self, *parse_kinds):
        statement_cst = self._statement_cst_at_current()
        if statement_cst is None:
            return None
        clause_cst = self._segmenter.statement_clause_cst(statement_cst.start, statement_cst.mode)
        if clause_cst is None:
            return None
        if parse_kinds and clause_cst.parse_kind not in set(parse_kinds):
            return None
        return clause_cst

    def _can_normalize_simple_macro_call_clause_cst(self, clause_cst):
        if self._at(TT.IDENT, "FMACRO") or not clause_cst.body_clauses:
            return False
        for clause in clause_cst.body_clauses:
            if any(v in ("-", "+") for v in getattr(clause, "values", ())):
                return False
            if isinstance(clause, DelimitedGroupClause):
                return False
            if not isinstance(clause, (OperandClause, ScalarClause)):
                return False
        first_values = getattr(clause_cst.body_clauses[0], "values", ())
        return bool(first_values)

    def _can_normalize_directive_clause_cst(self, clause_cst):
        for clause in clause_cst.body_clauses:
            if isinstance(clause, DelimitedGroupClause) and clause.open_symbol != "[":
                return False
        return True

    def _parse_statement_scalar_arguments(self, *, allow_same_line_statement=True):
        arguments = []
        while not self._at_statement_limit("top", allow_same_line_statement=allow_same_line_statement):
            arguments.append(self._parse_scalar_argument())
        return arguments

    def _parse_statement_shape_include(self, shape):
        del shape
        return self._parse_include(embedded=False)

    def _parse_fixed_specification(self):
        start, words = self._consume_head_from_statement_cst()
        args = []
        while True:
            if self._at(TT.NEWLINE):
                idx = self._next_non_newline_index(self.pos)
                if (not self._can_start_expression_token(self.tokens[idx])
                        or self._segmenter.starts_line_statement_at(idx) or self._segmenter.starts_operation_at(idx)
                        or (words == ["SNAP", "OFFGRID"] and args)):
                    break
                self.pos = idx
            if self._at_statement_boundary("top", allow_same_line_statement=True):
                break
            args.append(self._parse_signed_scalar_argument())
        return ast.Directive(keywords=words, arguments=args, **self._loc(start))

    def _parse_signed_scalar_argument(self):
        if self._at_symbol("-") or self._at_symbol("+"):
            value = self._parse_expression(50, context="scalar")
            return value.value if isinstance(value, ast.NumberLiteral) else value
        return self._parse_scalar_argument()

    def _at_device_netlist_option(self):
        return self._at(TT.IDENT, "NETLIST") and self._peek().type == TT.IDENT and self._peek().value in {"ELEMENT", "MODEL"}

    def _parse_statement_shape_layer(self, shape):
        del shape
        start, keywords = self._consume_head_from_statement_cst(("LAYER",))
        if keywords is None:
            start = self._expect(TT.IDENT, "LAYER")
        if self._cur().type == TT.IDENT and self._cur().value == "MAP":
            return self._parse_layer_map(start)

        name = self._parse_name()
        numbers = []
        while not self._at_statement_limit("top", allow_same_line_statement=True):
            if self._cur().type in (TT.IDENT, TT.STRING):
                token = self._advance()
                numbers.append(token.value if token.type == TT.IDENT else token.value)
                continue
            if self._cur().type == TT.NUMBER:
                numbers.append(self._advance().value)
                continue
            break
        return ast.LayerDef(name=name, numbers=numbers, **self._loc(start))

    def _parse_statement_shape_named_scalar_list(self, shape):
        if shape.name != "group":
            token = self._cur()
            raise ParseError(
                f"Unsupported named-scalar-list statement shape {shape.name!r}",
                token.line,
                token.col,
                token,
            )
        normalized = self._try_normalize_active_statement_clause_cst(
            "group",
            validator=lambda clause_cst: bool(clause_cst.body_clauses)
            and bool(getattr(clause_cst.body_clauses[0], "values", ())),
        )
        if normalized is not None:
            return normalized
        start, keywords = self._consume_head_from_statement_cst(("GROUP",))
        if keywords is None:
            start = self._expect(TT.IDENT, "GROUP")
        name = self._parse_name()
        members = self._parse_statement_scalar_arguments(allow_same_line_statement=True)
        return ast.Group(name=name, members=members, **self._loc(start))

    def _parse_statement_shape_scalar_directive(self, shape):
        del shape
        prefix = (self._cur().value,) if self._cur().type == TT.IDENT else None
        start, keywords = self._consume_head_from_statement_cst(prefix)
        if keywords is None:
            start = self._expect(TT.IDENT)
            keywords = [start.value]
        args = self._parse_statement_scalar_arguments(allow_same_line_statement=True)
        return ast.Directive(keywords=keywords, arguments=args, **self._loc(start))

    def _parse_statement_shape_connect(self, shape):
        soft = shape.name == "sconnect"
        normalized = self._try_normalize_active_statement_clause_cst("sconnect" if soft else "connect")
        if normalized is not None:
            return normalized
        start, keywords = self._consume_head_from_statement_cst(("SCONNECT",) if soft else ("CONNECT",))
        if keywords is None:
            start = self._advance()
        layers = []
        via_layer = None
        link_name = None
        abut_also = False

        while not self._at_statement_limit("top", allow_same_line_statement=True):
            if self._match(TT.IDENT, "BY"):
                via_layer = self._parse_name()
                continue
            if self._match(TT.IDENT, "LINK"):
                link_name = self._parse_name()
                continue
            if self._match(TT.IDENT, "ABUT"):
                if self._match(TT.IDENT, "ALSO"):
                    abut_also = True
                else:
                    self._warn(
                        "parser.connect.expected_also",
                        "Expected ALSO after ABUT",
                    )
                continue
            if self._cur().type in (TT.IDENT, TT.STRING, TT.NUMBER):
                layers.append(self._parse_name())
                continue
            break

        return ast.Connect(
            soft=soft,
            layers=layers,
            via_layer=via_layer,
            link_name=link_name,
            abut_also=abut_also,
            **self._loc(start),
        )

    def _parse_statement_shape_device(self, shape):
        del shape
        start, keywords = self._consume_head_from_statement_cst(("DEVICE",))
        if keywords is None:
            start = self._expect(TT.IDENT, "DEVICE")
        device_type = None
        device_name = None
        seed_layer = ""
        pins = []
        aux_layers = []
        cmacro = None
        cmacro_args = []
        netlist_options = []
        connection_mode = text_model_layer = None
        text_property_layers = []
        swap_lists = []
        signature = template = None

        def option_at(i):
            words = tuple(t.value if t.type == TT.IDENT else None for t in self.tokens[i:i+3])
            return (words[:1] in {("TEMPLATE",), ("SIGNATURE",)}
                    or words[:2] in {("BY", "NET"), ("BY", "SHAPE"), ("NETLIST", "MODEL"), ("NETLIST", "ELEMENT")}
                    or words in {("TEXT", "MODEL", "LAYER"), ("TEXT", "PROPERTY", "LAYER")})

        def layer_list():
            layers = [self._parse_name()]
            while (self._cur().type in (TT.IDENT, TT.STRING) and not option_at(self.pos)
                   and not self._at_ident("CMACRO") and not self._at_statement_boundary("top", allow_same_line_statement=True)):
                layers.append(self._parse_name())
            return layers

        def swap_pins(close):
            pins = [self._parse_name(), self._parse_name()]
            while not self._match(TT.SYMBOL, close):
                pins.append(self._parse_name())
            return pins

        if self._cur().type in (TT.IDENT, TT.STRING):
            element = self._parse_name()
            if self._match(TT.SYMBOL, "("):
                device_type = element
                device_name = self._parse_name()
                self._expect(TT.SYMBOL, ")")
            else:
                device_name = element

        if self._cur().type in (TT.IDENT, TT.STRING):
            seed_layer = self._parse_name()

        while True:
            if self._at(TT.NEWLINE):
                i = self._next_non_newline_index(self.pos)
                if not option_at(i):
                    break
                self.pos = i
            if option_at(self.pos) and self._match(TT.IDENT, "BY"):
                connection_mode = self._advance().value
                continue
            if option_at(self.pos) and self._match(TT.IDENT, "TEXT"):
                model = self._advance().value == "MODEL"
                self._expect(TT.IDENT, "LAYER")
                if model:
                    text_model_layer = self._parse_name()
                else:
                    text_property_layers.extend(layer_list())
                continue
            if self._match(TT.IDENT, "TEMPLATE"):
                template = self._parse_name(preserve_case=True)
                continue
            if self._match(TT.IDENT, "SIGNATURE"):
                value = None if self._match(TT.SYMBOL, "?") else self._expect(TT.STRING).value
                signature = (value, layer_list())
                continue
            if self._match(TT.SYMBOL, "("):
                if self._at_symbol("["):
                    group = []
                    while self._match(TT.SYMBOL, "["):
                        group.append(swap_pins("]"))
                    self._expect(TT.SYMBOL, ")")
                    swap_lists.append(group)
                else:
                    swap_lists.append(swap_pins(")"))
                continue
            if self._at_device_netlist_option():
                self._advance()
                kind = self._advance().value
                netlist_options.append((kind, self._parse_name(preserve_case=True)))
                continue
            if self._cur().type == TT.IDENT and self._cur().value == "CMACRO":
                self._advance()
                cmacro = self._parse_name()
                while not option_at(self.pos) and not self._at_statement_limit(
                    "top",
                    allow_same_line_statement=False,
                    use_active_unit=False,
                ):
                    cmacro_args.append(self._parse_signed_scalar_argument())
                continue
            if self._at_statement_boundary("top", allow_same_line_statement=True):
                break
            if self._cur().type == TT.SYMBOL and self._cur().value == "[":
                aux_layers.append(self._parse_bracketed_scalar_sequence())
                continue
            if self._match(TT.SYMBOL, "<"):
                aux_layers.append(self._parse_name())
                self._match(TT.SYMBOL, ">")
                continue
            if self._cur().type in (TT.IDENT, TT.STRING):
                pin_name = self._parse_name()
                role = None
                end_role = self._segmenter.scan_name_end(self.pos+1) if self._at_symbol("(") else None
                if end_role is not None and end_role < self.length and self.tokens[end_role].value == ")":
                    self._advance()
                    role = self._parse_name()
                    self._skip_newlines()
                    self._expect(TT.SYMBOL, ")")
                pins.append((pin_name, role))
                continue
            break

        return ast.Device(
            device_type=device_type,
            device_name=device_name,
            seed_layer=seed_layer,
            pins=pins,
            aux_layers=aux_layers,
            cmacro=cmacro,
            cmacro_args=cmacro_args,
            netlist_options=netlist_options,
            connection_mode=connection_mode,
            text_model_layer=text_model_layer,
            text_property_layers=text_property_layers,
            swap_lists=swap_lists, signature=signature, template=template,
            **self._loc(start),
        )

    def _parse_statement_shape_dmacro(self, shape):
        del shape
        start, keywords = self._consume_head_from_statement_cst(("DMACRO",))
        if keywords is None:
            start = self._expect(TT.IDENT, "DMACRO")
        name = self._parse_name()
        params = []
        while self._cur().type in (TT.IDENT, TT.STRING, TT.NUMBER):
            params.append(self._parse_name())
        # Alternative conditional definitions need not have the same signature.
        arity = len(params)
        self._macro_arities[name] = arity if self._macro_arities.get(name, arity) == arity else None
        self._skip_newlines()
        self._expect(TT.SYMBOL, "{", "Expected '{' to start DMACRO body")
        body = self._parse_sequence(mode="macro", stop_symbols={"}"})
        self._expect(TT.SYMBOL, "}")
        return ast.DMacro(name=name, params=params, body=body, **self._loc(start))

    def _parse_statement_shape_macro_call(self, shape):
        del shape
        normalized = self._try_normalize_active_statement_clause_cst(
            "macro_call",
            validator=self._can_normalize_simple_macro_call_clause_cst,
        )
        if normalized is not None:
            return normalized
        return self._parse_macro_invocation(inline=False)

    def _parse_macro_invocation(self, *, inline):
        previous = self._segmenter.previous_non_newline_index(self.pos-1)
        assignment_rhs = inline and previous >= 0 and self.tokens[previous].value == "="
        start = self._advance()
        kind = start.value
        name = self._parse_name()
        arguments = []

        if kind == "FMACRO":
            self._expect(TT.SYMBOL, "(", "FMACRO requires a parenthesized argument list")
            self._skip_newlines()
            while not self._at(TT.EOF) and not self._at_symbol(")"):
                if self._match(TT.SYMBOL, ","):
                    self._skip_newlines()
                    continue
                arguments.append(self._parse_macro_argument())
                self._skip_newlines()
            self._expect(TT.SYMBOL, ")")
        else:
            arity = self._macro_arities.get(name) if inline else None
            while not self._at_statement_limit("top", allow_same_line_statement=True, use_active_unit=not inline):
                if inline and ((len(arguments) == arity and not assignment_rhs)
                               or self._cur().value in (")", "]", ",", "RDB", "DVPARAMS")
                               or ((bool(arguments) if arity is None else len(arguments) >= arity)
                                   and self._led_binding_power() > 0)):
                    break
                arguments.append(self._parse_macro_argument())
                if self._cur().type == TT.NEWLINE:
                    break

        return ast.MacroCall(kind=kind, name=name, arguments=arguments, **self._loc(start))

    def _parse_macro_argument(self):
        if self._at(TT.IDENT):
            start = self.pos
            token = self._cur()
            return self._finish_node(ast.LayerRef(name=self._parse_name(), **self._loc(token)), start)
        # Whitespace separates arguments. Only parentheses group infix arithmetic.
        return self._parse_expression(50, stop_tokens={")", ","}, stop_on_newline=True, context="scalar")

    def _parse_statement_shape_variable(self, shape):
        del shape
        start, keywords = self._consume_head_from_statement_cst(("VARIABLE",))
        if keywords is None:
            start = self._expect(TT.IDENT, "VARIABLE")
        name = self._parse_name()
        values = []
        environment = False

        embedded_include = self._parse_embedded_include_continuation()
        if embedded_include is not None:
            values.append(embedded_include)
        elif self._match(TT.IDENT, "ENVIRONMENT"):
            environment = True
        else:
            while not self._at_statement_limit("top", allow_same_line_statement=True):
                if self._at_ident("INCLUDE"):
                    values.append(self._parse_include(embedded=True))
                    continue
                if self._cur().type == TT.STRING and not (
                    self._peek().type == TT.SYMBOL
                    and self._peek().value in {"+", "-", "*", "/", "^", "%"}
                ):
                    token = self._advance()
                    values.append(ast.StringLiteral(value=token.value, **self._loc(token)))
                    continue
                values.append(
                    self._parse_expression(stop_on_newline=True, context="scalar")
                )
                if self._cur().type == TT.NEWLINE:
                    break

        return ast.VariableDef(
            name=name,
            values=values,
            environment=environment,
            **self._loc(start),
        )

    def _parse_statement_shape_attach(self, shape):
        del shape
        normalized = self._try_normalize_active_statement_clause_cst("attach")
        if normalized is not None:
            return normalized
        start, keywords = self._consume_head_from_statement_cst(("ATTACH",))
        if keywords is None:
            start = self._expect(TT.IDENT, "ATTACH")
        layer = self._parse_name()
        net = self._parse_name()
        return ast.Attach(layer=layer, net=net, **self._loc(start))

    def _parse_statement_shape_trace_property(self, shape):
        del shape
        start, keywords = self._consume_head_from_statement_cst(("TRACE", "PROPERTY"))
        if keywords is None:
            start = self._expect(TT.IDENT, "TRACE")
            self._expect(TT.IDENT, "PROPERTY")
        device = self._parse_compact_modifier()
        args = self._parse_statement_scalar_arguments(allow_same_line_statement=True)
        return ast.TraceProperty(device=device, args=args, **self._loc(start))

    def _parse_statement_shape_directive(self, shape):
        del shape
        normalized = self._try_normalize_active_statement_clause_cst(
            "directive",
            validator=self._can_normalize_directive_clause_cst,
        )
        if normalized is not None:
            self._attach_embedded_include_continuation(normalized)
            return normalized
        start, keywords = self._parse_directive_head()
        arguments = self._parse_directive_arguments()
        node = ast.Directive(keywords=keywords, arguments=arguments, **self._loc(start))
        self._attach_embedded_include_continuation(node)
        return node

    def _parse_embedded_include_continuation(self):
        index = self._next_non_newline_index()
        token = self.tokens[index]
        if token.type != TT.IDENT or token.value != "INCLUDE":
            return None
        self.pos = index
        return self._finish_node(self._parse_include(embedded=True), index)

    def _attach_embedded_include_continuation(self, node):
        if not node.arguments and tuple(node.keywords) in EMBEDDED_INCLUDE_HEADS:
            include = self._parse_embedded_include_continuation()
            if include is not None:
                node.arguments.append(include)

