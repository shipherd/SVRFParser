"""DFM declarations, local SVRF bodies and ordered fill continuation clauses."""

from __future__ import annotations

from . import ast
from .exceptions import LexerError, ParseError
from .lexer import Lexer
from .preprocessor_schema import CONDITIONAL_OPENERS
from .tokens import Token, TokenType, rebase_tokens

TT = TokenType

# DFM Spec Fill and its Shape, Spacegroup, and Optimizer variants have an
# ordered clause grammar, not the freely reordered layer-operation grammar.
_CLAUSE_HEADS = tuple(sorted({
    ("INSIDE", "OF", "LAYER"), ("INSIDE", "OF", "PROPLAYER"),
    ("INSIDE", "OF", "LAYER", "BY", "POLYGON"),
    ("INSIDE", "OF", "EXTENT"), ("INSIDE", "OF"),
    ("INITIAL", "INSIDE", "OF", "LAYER"), ("DEBUG", "SPACE"),
    ("COLOR", "SCHEME"), ("EDGE", "ALIGN"),
    *((word,) for word in (
        "OPTIMIZER RDB WINDOW GWINDOW INITIAL GROUPREGION FILLSHAPE RECTFILL "
        "POLYFILL ARRAYFILL STRETCHFILL STRIPE FILLSTACK OUTPUT PRIORITY DISPLACE "
        "STEP OFFSET SETBACK ALLOW ALLOWX ALLOWY AUTOROTATE FILLMIN FILLMAX REPEAT "
        "SHAPESPACE EFFORT SPACE SPACEX SPACEY SPACEXY SPACEGROUP RESTRICT "
        "ELLIPTICAL EUCLIDEAN OPPOSITE FLIPX ROTATION PARTITION HORIZONTAL "
        "VERTICAL CENTERED MINLENGTH MAXLENGTH ALIGN DISTRIBUTE MINGAP "
        "MINSTACK MAXSTACK EXTENDABLE MERGESHAPE FIELD CLOSETO VALIGNCUT "
        "HALIGNCUT VPERIODIC HPERIODIC VSHAPE HSHAPE WRAPS MAJOR GUARDED "
        "OPTIMIZABLE REDUCE"
    ).split()),
}, key=len, reverse=True))
_VARIANTS = frozenset({"SHAPE", "SPACEGROUP", "OPTIMIZER", "REGION", "WRAP", "DATA"})
_MAT_HEADS = tuple((word,) for word in (
    "NARROWTRACKX NARROWTRACKY NOTCHX NOTCHY BUMPX BUMPY JOGX JOGY "
    "ALIGNBY HALIGNBY VALIGNBY DISPLACE HDISPLACE VDISPLACE "
    "VPROXIMITY HPROXIMITY GAPX GAPY PITCHX PITCHY"
).split())
_DFM_MODES = frozenset({"dfm_fill", "dfm_mat"})
_MIN_ARGUMENTS = {head[0]: 1 for head in _MAT_HEADS}
_MIN_ARGUMENTS.update({"STEP": 1, "DISPLACE": 2, "STRIPE": 1, "SPACEXY": 3, "SPACE": 2, "SPACEX": 2, "SPACEY": 2})


class DfmSpecParserMixin:
    def _via_words(self, *words):
        self._skip_newlines()
        start = self.pos
        for word in words:
            self._skip_newlines()
            self._expect(TT.IDENT, word)
        return start

    def _via_clause(self, *words):
        start = self._via_words(*words)
        return self._finish_node(ast.DfmClause(keywords=list(words)), start)

    def _via_error(self, message):
        t = self._cur()
        raise ParseError(message, t.line, t.col, t)

    def _via_layer_list(self):
        names = []
        self._skip_newlines()
        while not self._at_ident("END") and not self._at_symbol(";") and not self._at_symbol("]"):
            t = self._cur()
            if (t.type not in (TT.IDENT, TT.NUMBER, TT.STRING) or self._segmenter.starts_assignment_at(self.pos)
                    or self._segmenter.starts_rule_check_at(self.pos, "top")):
                self._via_error("Expected a connectivity layer")
            name = self._parse_name()
            names.append(name if t.type == TT.IDENT else None)
            self._skip_newlines()
        return names

    def _via_semicolon(self, separated):
        if (separated and self._at_symbol(";") and self.tokens[self.pos-1].type != TT.NEWLINE
                and self.tokens[self.pos-1].end_offset == self._cur().offset):
            self._via_error("Separate the connectivity semicolon from the last layer")
        self._expect(TT.SYMBOL, ";")

    def _parse_via_redundancy(self, start):
        self._advance()
        self._skip_newlines()
        count = bool(self._match(TT.IDENT, "COUNT"))
        self._skip_newlines()
        name = self._expect(TT.STRING, message="Expected a quoted specification name").value if count else self._parse_name()
        body = []
        if count:
            begin = self._next_non_newline_index()
            target = self._via_clause("TARGET")
            self._skip_newlines()
            i = self.pos
            self._parse_name()
            target.arguments.append(self._operation_clause(i, self.pos))
            body.append(self._finish_node(target, begin))
        begin = self._next_non_newline_index()
        connectivity = self._via_clause("CONNECTIVITY")
        body.append(connectivity)
        self._skip_newlines()
        if count:
            i = self.pos
            if self._at_symbol("["):
                markers = set()
                while self._match(TT.SYMBOL, "["):
                    names = self._via_layer_list()
                    if (len(names) < 2 or "_TARGET_" in names or
                            ("BY" in names and (names.count("BY") != 1 or names.index("BY") != len(names)-2
                                               or names.index("BY") < 2))):
                        self._via_error("Invalid bracketed connectivity definition")
                    markers.update(names)
                    self._expect(TT.SYMBOL, "]")
                    self._skip_newlines()
                if not {"_TARGET1_", "_TARGET2_"} <= markers:
                    self._via_error("Expected both connectivity target markers")
            else:
                names = self._via_layer_list()
                if (len(names) < 3 or len(names) % 2 != 1 or names.count("_TARGET_") != 1
                        or names.index("_TARGET_") % 2 != 1 or {"BY", "_TARGET1_", "_TARGET2_"}.intersection(names)):
                    self._via_error("Invalid target connectivity stack")
            self._match(TT.SYMBOL, ";")
            connectivity.arguments.append(self._operation_clause(i, self.pos))
        else:
            while not self._at_ident("END"):
                i = self.pos
                if len(self._via_layer_list()) < 2:
                    self._via_error("A connectivity definition requires at least two layers")
                self._via_semicolon(separated=True)
                connectivity.arguments.append(self._operation_clause(i, self.pos))
                self._skip_newlines()
            if not connectivity.arguments:
                self._via_error("Expected a connectivity definition")
        self._finish_node(connectivity, begin)
        body.append(self._via_clause("END", "CONNECTIVITY"))
        j = self._next_non_newline_index()
        if (not count and self.tokens[j].type == TT.IDENT and self.tokens[j].value == "TREAT"
                and not self._segmenter.starts_assignment_at(j) and not self._segmenter.starts_rule_check_at(j, "top")):
            treat = self._via_clause("TREAT", "AS", "REDUNDANT")
            body.append(treat)
            self._skip_newlines()
            while not self._at_ident("END"):
                i = self.pos
                self._parse_name()
                self._via_words("WITH")
                self._skip_newlines()
                if not (self._match(TT.IDENT, "AREA") or self._match(TT.IDENT, "ASPECT")):
                    self._via_error("Expected AREA or ASPECT")
                self._skip_newlines()
                self._expect(TT.SYMBOL, ">")
                self._skip_newlines()
                self._parse_expression(35, context="scalar")
                self._skip_newlines()
                self._via_semicolon(separated=False)
                treat.arguments.append(self._operation_clause(i, self.pos))
                self._skip_newlines()
            self._finish_node(treat, j)
            body.append(self._via_clause("END"))
        return ast.DfmSpec(kind="VIA", variant="REDUNDANCY COUNT" if count else "REDUNDANCY",
                           name=name, body=body, **self._loc(start))

    def _parse_dfm_spec_via(self):
        start = self._cur()
        self._via_words("DFM", "SPEC", "VIA")
        self._skip_newlines()
        if self._at_ident("REDUNDANCY"):
            return self._parse_via_redundancy(start)
        name = self._parse_name()
        clauses = []
        for key in ("VIASHAPE", "ENC1", "ENC2"):
            self._skip_newlines()
            i = self.pos
            token = self._expect(TT.IDENT, key)
            self._skip_newlines()
            args = []
            for _ in range(2):
                j = self._next_non_newline_index(self.pos)
                t = self.tokens[j]
                if not self._can_start_expression_token(t) or t.value in {"ENC1", "ENC2"} or self._starts_line_statement_at(j):
                    break
                self.pos = j
                args.append(self._parse_expression(50, context="modifier"))
            if not args:
                raise ParseError(f"{key} requires one or two dimensions", token.line, token.col, token)
            clauses.append(self._finish_node(ast.DfmClause(keywords=[key], arguments=args, **self._loc(token)), i))
        return ast.DfmSpec(kind="VIA", name=name, body=clauses, **self._loc(start))

    def _local_name(self):
        token = self._cur()
        if token.type not in (TT.IDENT, TT.STRING):
            raise ParseError("Expected a local SVRF name", token.line, token.col, token)
        self._advance()
        return token.value

    def _local_body(self):
        opening = self._expect(TT.SYMBOL, "[")
        start = self.pos
        depth = 1
        while depth and not self._at(TT.EOF):
            if self._at_symbol("["):
                depth += 1
            elif self._at_symbol("]"):
                depth -= 1
                if not depth:
                    break
            self._advance()
        closing = self._expect(TT.SYMBOL, "]")
        raw = self.source_text[opening.end_offset:closing.offset]
        stripped = raw.strip()
        wrapped = stripped.startswith("/*") and stripped.find("*/", 2) == len(stripped)-2
        if wrapped:
            skip = len(raw)-len(raw.lstrip())+2
            prefix = raw[:skip].replace("\r\n", "\n").replace("\r", "\n")
            line = opening.end_line + prefix.count("\n")
            col = len(prefix.rsplit("\n", 1)[-1])+1 if "\n" in prefix else opening.end_col+skip
            try:
                tokens = Lexer(stripped[2:-2], filename=self.filename).tokens()
            except LexerError as exc:
                raise LexerError(exc.message, line+exc.line-1, exc.col+(col-1 if exc.line == 1 else 0)) from exc
            rebase_tokens(tokens, line, col, opening.end_offset+skip)
        else:
            eof = Token(TT.EOF, "", closing.line, closing.col, offset=closing.offset, end_offset=closing.offset)
            tokens = [*self.tokens[start:self.pos-1], eof]
        nested = type(self)(tokens, self.filename, self.source_text, self.strict)
        body = nested.parse().statements
        self.warnings.extend(nested.warnings)
        return body, wrapped

    def _parse_local_svrf(self):
        start = self._cur()
        self._via_words("DFM", "SPEC", "SVRF")
        self._skip_newlines()
        name = self._parse_name()
        self._skip_newlines()
        self._expect(TT.SYMBOL, "(")
        inputs, outputs, variables = [], [], []
        self._skip_newlines()
        while not self._at_symbol(":") or not inputs:
            layer = self._local_name()
            nodal = bool(self._match(TT.SYMBOL, "("))
            if nodal:
                self._expect(TT.IDENT, "NODAL")
                self._expect(TT.SYMBOL, ")")
            inputs.append((layer, nodal))
            self._skip_newlines()
        colon = self._advance()
        if self.tokens[self.pos-2].end_offset == colon.offset or self._cur().offset == colon.end_offset:
            raise ParseError("Local SVRF requires whitespace around ':'", colon.line, colon.col, colon)
        self._skip_newlines()
        while not self._at_symbol(")") or not outputs:
            outputs.append(self._local_name())
            self._skip_newlines()
        self._advance()
        self._skip_newlines()
        if self._match(TT.IDENT, "VARIABLES"):
            self._expect(TT.SYMBOL, "[")
            self._skip_newlines()
            while not self._at_symbol("]") or not variables:
                key = self._local_name()
                default = None
                if self._match(TT.SYMBOL, "="):
                    i = self.pos
                    negative = bool(self._match(TT.SYMBOL, "-"))
                    if not negative:
                        self._match(TT.SYMBOL, "+")
                    number = self._expect(TT.NUMBER)
                    default = self._finish_node(ast.NumberLiteral(value=-number.value if negative else number.value), i)
                variables.append((key, default))
                self._skip_newlines()
            self._advance()
            self._skip_newlines()
        body, wrapped = self._local_body()
        j = self._next_non_newline_index(self.pos)
        center = self.tokens[j].type == TT.IDENT and self.tokens[j].value == "CENTER" and not self._starts_line_statement_at(j)
        if center:
            self.pos = j+1
        return ast.LocalSvrf(name, inputs, outputs, variables, body, wrapped, center, **self._loc(start))

    def _dfm_spec_continuation_after(self, statement, previous=False):
        if isinstance(statement, ast.DfmSpec):
            return statement.kind != "VIA"
        if isinstance(statement, (ast.DfmClause, ast.Define, ast.Include)):
            return previous
        if isinstance(statement, ast.IfDef):
            outcomes = []
            for body in (statement.then_body, statement.else_body):
                active = previous
                for child in body:
                    active = self._dfm_spec_continuation_after(child, active)
                outcomes.append(active)
            return any(outcomes)
        return False

    def _dfm_fill_clause_head_at(self, index, mode="dfm_fill"):
        for head in (_MAT_HEADS if mode == "dfm_mat" else _CLAUSE_HEADS):
            if all(
                index + offset < len(self.tokens)
                and self.tokens[index + offset].type == TT.IDENT
                and self.tokens[index + offset].value == word
                for offset, word in enumerate(head)
            ):
                if not self._segmenter.starts_assignment_at(index):
                    return head
        return None

    def _dfm_fill_argument_boundary(self, index, mode="dfm_fill", *, needs_value=False):
        token = self.tokens[index]
        if token.type in {TT.EOF, TT.PREPROCESSOR, TT.RULE_COMMENT}:
            return True
        if token.type == TT.SYMBOL and token.value in {"}", ")", "]"}:
            return True
        if token.type == TT.IDENT and token.value in {"WIDTH", "LENGTH"}:
            following = self.tokens[index + 1]
            scalar_tail = (
                following.type in {TT.NEWLINE, TT.EOF, TT.PREPROCESSOR}
                or (following.type == TT.IDENT and following.value in {"WIDTH", "LENGTH"})
                or self._dfm_fill_clause_head_at(index + 1, mode) is not None
            )
            if needs_value or scalar_tail:
                return self._segmenter.starts_assignment_at(index) or self._segmenter.starts_rule_check_at(index, "top")
        return bool(
            self._dfm_fill_clause_head_at(index, mode)
            or self._segmenter.starts_assignment_at(index)
            or self._segmenter.starts_rule_check_at(index, "top")
            or self._segmenter.starts_operation_at(index)
            or self._starts_line_statement_at(index)
        )

    def _dfm_fill_clause_end(self, index, mode="dfm_fill"):
        head = self._dfm_fill_clause_head_at(index, mode)
        index += len(head or ())
        depth = []
        pairs = {"(": ")", "[": "]"}
        while index < len(self.tokens):
            token = self.tokens[index]
            if not depth and token.type != TT.NEWLINE and self._dfm_fill_argument_boundary(index, mode):
                break
            if token.type == TT.SYMBOL:
                if token.value in pairs:
                    depth.append(pairs[token.value])
                elif depth and token.value == depth[-1]:
                    depth.pop()
            if token.type == TT.EOF:
                break
            index += 1
        return index

    def _dfm_fill_conditional_is_continuation(self, index, mode):
        depth = 0
        has_clause = False
        while index < len(self.tokens):
            index = self._next_non_newline_index(index)
            token = self.tokens[index]
            if token.type == TT.PREPROCESSOR:
                if token.value in CONDITIONAL_OPENERS:
                    depth += 1
                elif token.value == "#ENDIF":
                    depth -= 1
                    if depth == 0:
                        return has_clause
                elif token.value not in {"#ELSE", "#DEFINE", "#UNDEFINE", "#INCLUDE"}:
                    return False
                index += 1
                while self.tokens[index].type not in {TT.NEWLINE, TT.EOF}:
                    index += 1
                continue
            if token.type == TT.RULE_COMMENT:
                index += 1
                continue
            if self._dfm_fill_clause_head_at(index, mode) is None and (mode != "dfm_fill" or self._dfm_fill_argument_boundary(index, mode)):
                return False
            has_clause = True
            index = self._dfm_fill_clause_end(index, mode)
        return False

    def _starts_dfm_fill_item(self, index, mode="dfm_fill"):
        token = self.tokens[index]
        if token.type == TT.PREPROCESSOR:
            if token.value in CONDITIONAL_OPENERS:
                return self._dfm_fill_conditional_is_continuation(index, mode)
            return token.value in {"#DEFINE", "#UNDEFINE", "#INCLUDE"}
        return bool(
            token.type == TT.RULE_COMMENT
            or self._dfm_fill_clause_head_at(index, mode)
            or (mode == "dfm_fill" and self._can_start_expression_token(token) and not self._dfm_fill_argument_boundary(index, mode))
        )

    def _parse_dfm_fill_arguments(self, mode="dfm_fill", *, minimum=0):
        arguments = []
        while True:
            index = self._next_non_newline_index(self.pos)
            if self._dfm_fill_argument_boundary(index, mode, needs_value=len(arguments) < minimum):
                break
            self.pos = index
            if self._cur().type == TT.SYMBOL and self._cur().value in {"<", "<=", ">", ">=", "==", "!=", "<>"}:
                arguments.extend(self._parse_constraints())
            else:
                start = self.pos
                if self._match(TT.SYMBOL, "["):
                    items = []
                    self._skip_newlines()
                    while not self._at_symbol("]"):
                        items.append(self._parse_expression(0, stop_tokens={"]"}, stop_on_newline=False, context="modifier"))
                        self._skip_newlines()
                    self._expect(TT.SYMBOL, "]")
                    value = self._finish_node(ast.BracketExpr(items=items, **self._loc(self.tokens[start])), start)
                else:
                    value = self._parse_expression(35, context="modifier")
                arguments.append(value)
        return arguments

    def _parse_dfm_fill_clause(self, mode="dfm_fill"):
        start = self.pos
        head = self._dfm_fill_clause_head_at(start, mode) or ()
        self.pos += len(head)
        minimum = _MIN_ARGUMENTS.get(head[0], 0) if head else 0
        node = ast.DfmClause(keywords=list(head), arguments=self._parse_dfm_fill_arguments(mode, minimum=minimum), **self._loc(self.tokens[start]))
        return self._finish_node(node, start)

    def _parse_dfm_spec_fill(self):
        start = self._cur()
        self._expect(TT.IDENT, "DFM")
        self._expect(TT.IDENT, "SPEC")
        kind = self._expect(TT.IDENT).value
        variant = self._advance().value if self._cur().type == TT.IDENT and self._cur().value in _VARIANTS else ""
        name = self._parse_name()
        arguments = self._parse_dfm_fill_arguments()
        body = self._parse_sequence("dfm_fill", stop_preprocessors={"#ELSE", "#ENDIF"})
        return ast.DfmSpec(kind=kind, name=name, variant=variant, arguments=arguments, body=body, **self._loc(start))

    def _parse_dfm_mat_operation(self, start, op_name, schema, modifier_starters):
        del schema, modifier_starters
        operands = [self._parse_expression(50)]
        clauses = self._parse_sequence("dfm_mat", stop_preprocessors={"#ELSE", "#ENDIF"})
        return ast.DRCOp(op=op_name, operands=operands, modifiers=clauses, **self._loc(start))
