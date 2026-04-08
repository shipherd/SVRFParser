"""Statement-shape parsing handlers for the live parser path."""

from __future__ import annotations

from . import ast
from .clause_cst import DelimitedGroupClause, ModifierClause, OperandClause, ScalarClause
from .exceptions import ParseError
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

    def _can_normalize_simple_device_clause_cst(self, clause_cst):
        if not clause_cst.body_clauses:
            return False
        seen_cmacro = False
        for idx, clause in enumerate(clause_cst.body_clauses):
            if isinstance(clause, DelimitedGroupClause):
                return False
            if isinstance(clause, ScalarClause):
                return False
            if isinstance(clause, OperandClause):
                if idx == 0:
                    continue
                if not seen_cmacro:
                    return False
                continue
            if isinstance(clause, ModifierClause):
                values = getattr(clause, "values", ())
                if values[:1] == ("CMACRO",):
                    seen_cmacro = True
                    continue
                if not seen_cmacro:
                    return False
                continue
        values = getattr(clause_cst.body_clauses[0], "values", ())
        return len(values) >= 2

    def _can_normalize_simple_macro_call_clause_cst(self, clause_cst):
        if not clause_cst.body_clauses:
            return False
        for clause in clause_cst.body_clauses:
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
        normalized = self._try_normalize_active_statement_clause_cst(
            "device",
            validator=self._can_normalize_simple_device_clause_cst,
        )
        if normalized is not None:
            return normalized
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

        if self._cur().type == TT.IDENT:
            token = self._advance()
            if self._match(TT.SYMBOL, "("):
                device_type = token.value
                device_name = self._parse_name()
                self._expect(TT.SYMBOL, ")")
            else:
                device_name = token.value

        if self._cur().type in (TT.IDENT, TT.STRING):
            seed_layer = self._parse_name()

        while True:
            if self._cur().type == TT.IDENT and self._cur().value == "CMACRO":
                self._advance()
                cmacro = self._parse_name()
                while not self._at_statement_limit(
                    "top",
                    allow_same_line_statement=False,
                    use_active_unit=False,
                ):
                    cmacro_args.append(self._parse_scalar_argument())
                break
            if self._at_statement_limit("top", allow_same_line_statement=True):
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
                if self._match(TT.SYMBOL, "("):
                    role = self._parse_name()
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
        prefix = (self._cur().value,) if self._cur().type == TT.IDENT else None
        start, keywords = self._consume_head_from_statement_cst(prefix)
        if keywords is None:
            start = self._advance()
            kind = start.value
        else:
            kind = keywords[0]
        name = self._parse_name()
        arguments = []

        if kind == "FMACRO" and self._match(TT.SYMBOL, "("):
            while not self._at(TT.EOF) and not self._at_symbol(")"):
                if self._match(TT.SYMBOL, ","):
                    continue
                arguments.append(self._parse_expression(stop_tokens={")", ","}, stop_on_newline=False))
                self._match(TT.SYMBOL, ",")
            self._expect(TT.SYMBOL, ")")
        else:
            while not self._at_statement_limit("top", allow_same_line_statement=True):
                arguments.append(self._parse_expression(stop_on_newline=True))
                if self._cur().type == TT.NEWLINE:
                    break

        return ast.MacroCall(kind=kind, name=name, arguments=arguments, **self._loc(start))

    def _parse_statement_shape_variable(self, shape):
        del shape
        start, keywords = self._consume_head_from_statement_cst(("VARIABLE",))
        if keywords is None:
            start = self._expect(TT.IDENT, "VARIABLE")
        name = self._parse_name()
        values = []
        environment = False

        if self._match(TT.IDENT, "ENVIRONMENT"):
            environment = True
        else:
            while not self._at_statement_limit("top", allow_same_line_statement=True):
                if self._at_ident("INCLUDE"):
                    values.append(self._parse_include(embedded=True))
                    continue
                if self._cur().type == TT.STRING:
                    token = self._advance()
                    values.append(ast.StringLiteral(value=token.value, **self._loc(token)))
                    continue
                values.append(
                    self._parse_expression(stop_on_newline=True)
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
            return normalized
        start, keywords = self._parse_directive_head()
        arguments = self._parse_directive_arguments()
        return ast.Directive(keywords=keywords, arguments=arguments, **self._loc(start))

