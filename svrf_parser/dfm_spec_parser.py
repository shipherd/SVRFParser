"""Ordered, non-scoping DFM fill declarations and their continuation clauses."""

from __future__ import annotations

from . import ast
from .tokens import TokenType

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
    def _dfm_spec_continuation_after(self, statement, previous=False):
        if isinstance(statement, ast.DfmSpec):
            return True
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
                if token.value in {"#IFDEF", "#IFNDEF"}:
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
            if token.value in {"#IFDEF", "#IFNDEF"}:
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
