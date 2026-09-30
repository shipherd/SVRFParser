"""Hand-written recursive-descent parser for core SVRF constructs."""

from __future__ import annotations

import copy
import re

from . import ast
from .expression_parser import ExpressionParserMixin
from .exceptions import ParseError, SVRFParseError
from .keywords import _DIRECTIVE_HEADS, _LAYER_BP
from .lexer import Lexer
from .operation_handlers import OperationParserMixin
from .parser_cursor import ParserCursorMixin
from .preprocessor_schema import PREPROCESSOR_SCHEMA_REGISTRY
from .segmenter import SegmenterConfig, StatementSegmenter
from .statement_handlers import StatementParserMixin
from .svrf_constructs import count_svrf_constructs
from .svrf_spec import PARSER_SPEC
from .tokens import TokenType

TT = TokenType

_MEASUREMENT_OPS = PARSER_SPEC.table("measurement_ops")
_UNARY_OPS = PARSER_SPEC.table("unary_ops")
_PREFIX_BOOLEAN_OPS = PARSER_SPEC.table("prefix_boolean_ops")
_GENERIC_PREFIX_OPS = PARSER_SPEC.table("generic_prefix_ops")
_COMPARISON_SYMBOLS = PARSER_SPEC.table("comparison_symbols")
_ARITHMETIC_BP = PARSER_SPEC.table("arithmetic_bp")
_INFIX_BP = PARSER_SPEC.table("infix_bp")
_WITH_SECONDARY_OPS = PARSER_SPEC.table("with_secondary_ops")
_DIRECTIVE_SECONDARY_WORDS = PARSER_SPEC.table("directive_secondary_words")
_SIMPLE_KEYWORD_DIRECTIVES = PARSER_SPEC.table("simple_keyword_directives")
_DIRECTIVE_SAME_LINE_HEADS = PARSER_SPEC.table("directive_same_line_heads")
_TOP_LEVEL_EXPLICIT_HEADS = PARSER_SPEC.table("top_level_explicit_heads")
_MODIFIER_STARTERS = PARSER_SPEC.table("modifier_starters")
_DFM_PROPERTY_MODIFIERS = PARSER_SPEC.table("dfm_property_modifiers")
_RET_OPTION_STARTERS = PARSER_SPEC.table("ret_option_starters") | frozenset({"EMULATION"})
_EDGE_BINARY_PREFIX_OPS = PARSER_SPEC.table("edge_binary_prefix_ops")
_RULE_BODY_SAME_LINE_STARTERS = PARSER_SPEC.table("rule_body_same_line_starters") | frozenset(
    {"CMACRO", "FMACRO"}
)
_NOT_COMPOUND_OPS = PARSER_SPEC.table("not_compound_ops")
_WITH_TEXT_TRAILING_MODIFIERS = PARSER_SPEC.table("with_text_trailing_modifiers")

_DOC_MATH_FUNCTION_NAMES = PARSER_SPEC.family("doc_math_function_names")
_DOC_DFM_COORDINATE_FUNCTION_NAMES = PARSER_SPEC.family("doc_dfm_coordinate_function_names")
_DOC_DFM_MEASUREMENT_FUNCTION_NAMES = PARSER_SPEC.family("doc_dfm_measurement_function_names")
_DOC_DFM_COMPARISON_FUNCTION_NAMES = PARSER_SPEC.family("doc_dfm_comparison_function_names")
_DOC_DFM_PER_SHAPE_FUNCTION_NAMES = PARSER_SPEC.family("doc_dfm_per_shape_function_names")
_DOC_DFM_PROPERTY_FUNCTION_NAMES = PARSER_SPEC.family("doc_dfm_property_function_names")
_DOC_DFM_NET_FUNCTION_NAMES = PARSER_SPEC.family("doc_dfm_net_function_names")
_DOC_DFM_VECTOR_FUNCTION_NAMES = PARSER_SPEC.family("doc_dfm_vector_function_names")
_DOC_DFM_MISC_FUNCTION_NAMES = PARSER_SPEC.family("doc_dfm_misc_function_names")
_DOC_STRING_FUNCTION_NAMES = PARSER_SPEC.family("doc_string_function_names")
_DOC_DFM_FUNCTION_NAMES = PARSER_SPEC.family("doc_dfm_function_names")
_DOC_DEVICE_PROPERTY_FUNCTION_NAMES = PARSER_SPEC.family("doc_device_property_function_names")
_DOC_TRACE_PROPERTY_FUNCTION_NAMES = PARSER_SPEC.family("doc_trace_property_function_names")
_DOC_EFFECTIVE_PROPERTY_FUNCTION_NAMES = PARSER_SPEC.family("doc_effective_property_function_names")
_DOC_LVS_PROPERTY_INITIALIZE_FUNCTION_NAMES = PARSER_SPEC.family("doc_lvs_property_initialize_function_names")
_DOC_DEVICE_ANNOTATION_FUNCTION_NAMES = PARSER_SPEC.family("doc_device_annotation_function_names")
_DOC_HISTORICAL_ENCLOSURE_FUNCTION_NAMES = PARSER_SPEC.family("doc_historical_enclosure_function_names")
_DOC_BUILTIN_LANGUAGE_FUNCTION_NAMES = PARSER_SPEC.family("doc_builtin_language_function_names")
_DOC_ALL_FUNCTION_NAMES = PARSER_SPEC.family("doc_all_function_names")
_FUNCTION_LIKE_NAMES = PARSER_SPEC.table("function_like_names")


class Parser(ParserCursorMixin, StatementParserMixin, OperationParserMixin, ExpressionParserMixin):
    """Parse a token stream into an SVRF AST."""

    def __init__(self, tokens, filename="<input>", source_text="", strict=False):
        self.tokens = tokens
        self.filename = filename
        self.source_text = source_text or ""
        self.strict = strict
        self.pos = 0
        self.length = len(tokens)
        self.warnings = []
        self._current_statement_cst = None
        self._expression_context = "scalar"
        self._segmenter = StatementSegmenter(
            tokens,
            SegmenterConfig(
                directive_heads=frozenset(_DIRECTIVE_HEADS),
                directive_same_line_heads=_DIRECTIVE_SAME_LINE_HEADS,
                directive_secondary_words=_DIRECTIVE_SECONDARY_WORDS,
                top_level_line_heads=frozenset(_TOP_LEVEL_EXPLICIT_HEADS | {"TRACE", "IF", "POLYGON", "RDB", "TVF"}),
                top_level_same_line_heads=frozenset(_TOP_LEVEL_EXPLICIT_HEADS | {"POLYGON", "RDB", "TVF"}),
                expression_like_directive_heads=frozenset(
                    _GENERIC_PREFIX_OPS
                    | _UNARY_OPS
                    | _PREFIX_BOOLEAN_OPS
                    | _MEASUREMENT_OPS
                    | _EDGE_BINARY_PREFIX_OPS
                ),
                rule_body_same_line_starters=_RULE_BODY_SAME_LINE_STARTERS,
                comparison_symbols=_COMPARISON_SYMBOLS,
                arithmetic_symbols=frozenset(_ARITHMETIC_BP),
                expression_operator_words=frozenset(
                    set(_INFIX_BP)
                    | _EDGE_BINARY_PREFIX_OPS
                    | _PREFIX_BOOLEAN_OPS
                    | _UNARY_OPS
                    | _GENERIC_PREFIX_OPS
                    | _MEASUREMENT_OPS
                    | {"WITH"}
                ),
                expression_prefix_words=frozenset(
                    _GENERIC_PREFIX_OPS
                    | _PREFIX_BOOLEAN_OPS
                    | _UNARY_OPS
                    | _MEASUREMENT_OPS
                    | _EDGE_BINARY_PREFIX_OPS
                    | {"WITH", "NOT"}
                ),
                modifier_starters=_MODIFIER_STARTERS,
                prefix_boolean_ops=_PREFIX_BOOLEAN_OPS,
                group_continuation_keywords=frozenset(
                    _PREFIX_BOOLEAN_OPS
                    | _UNARY_OPS
                    | _GENERIC_PREFIX_OPS
                    | _MEASUREMENT_OPS
                    | _EDGE_BINARY_PREFIX_OPS
                    | {"WITH", "NOT"}
                ),
                measurement_ops=_MEASUREMENT_OPS,
            ),
        )

    def parse(self):
        start = self.pos
        statements = self._parse_sequence(mode="top")
        line = statements[0].line if statements else 1
        col = statements[0].col if statements else 1
        program = ast.Program(statements=statements, line=line, col=col)
        return self._finish_node(program, start)

    def _starts_line_statement_at(self, idx):
        return self._segmenter.starts_line_statement_at(idx)

    def _next_non_newline_token(self, idx):
        return self._segmenter.next_non_newline_token(idx)

    def _looks_like_same_line_top_directive_at(self, idx):
        return self._segmenter.looks_like_same_line_top_directive_at(idx)

    def _starts_same_line_statement_at(self, idx, mode):
        return self._segmenter.starts_same_line_statement_at(idx, mode)

    def _at_directive_boundary(self):
        return self._segmenter.at_directive_boundary(self.pos)

    def _is_deferred_property_header(self, stmt):
        if isinstance(stmt, ast.PropertyBlock):
            return not stmt.body
        if not isinstance(stmt, ast.IfDef):
            return False
        bodies = []
        if stmt.then_body:
            bodies.append(stmt.then_body)
        if stmt.else_body:
            bodies.append(stmt.else_body)
        if not bodies:
            return False
        for body in bodies:
            if len(body) != 1 or not isinstance(body[0], ast.PropertyBlock) or body[0].body:
                return False
        return True

    def _attach_shared_property_body(self, stmt, shared_body):
        if isinstance(stmt, ast.PropertyBlock) and not stmt.body:
            stmt.body = copy.deepcopy(shared_body)
            return True
        if not isinstance(stmt, ast.IfDef):
            return False

        attached = False
        for body in (stmt.then_body, stmt.else_body):
            if len(body) == 1 and isinstance(body[0], ast.PropertyBlock) and not body[0].body:
                body[0].body = copy.deepcopy(shared_body)
                attached = True
        return attached

    def _parse_sequence(self, mode, stop_symbols=None, stop_preprocessors=None):
        statements = []
        stop_symbols = stop_symbols or set()
        stop_preprocessors = stop_preprocessors or set()
        pending_property_headers = []
        pending_property_body_start = None
        pending_dfm_spec = False

        while True:
            next_idx = self._segmenter.next_non_newline_index(self.pos)
            self.pos = next_idx
            token = self._cur()
            if token.type == TT.EOF:
                break
            if (
                pending_property_headers
                and mode in {"macro", "property"}
                and token.type == TT.SYMBOL
                and token.value == "]"
            ):
                shared_body = statements[pending_property_body_start:]
                del statements[pending_property_body_start:]
                for stmt_index in pending_property_headers:
                    self._attach_shared_property_body(statements[stmt_index], shared_body)
                pending_property_headers = []
                pending_property_body_start = None
                self._advance()
                continue
            if token.type == TT.PREPROCESSOR and token.value in stop_preprocessors:
                break
            if token.type == TT.SYMBOL and token.value in stop_symbols:
                break
            if mode in {"dfm_fill", "dfm_mat"} and not self._starts_dfm_fill_item(self.pos, mode):
                break
            if mode == "perc_load" and not self._starts_perc_load_item(self.pos):
                break

            statement_cst = self._segmenter.next_statement_cst(
                self.pos,
                mode,
                stop_symbols=stop_symbols,
                stop_preprocessors=stop_preprocessors,
            )
            if statement_cst is None:
                break
            start = statement_cst.start
            self.pos = start
            prev_statement_cst = self._current_statement_cst
            self._current_statement_cst = statement_cst
            try:
                if mode not in {"dfm_fill", "dfm_mat"} and pending_dfm_spec and self._starts_dfm_fill_item(self.pos):
                    if token.type == TT.PREPROCESSOR:
                        stmt = self._parse_preprocessor("dfm_fill")
                    elif token.type == TT.RULE_COMMENT:
                        stmt = self._parse_rule_comment_statement()
                    else:
                        stmt = self._parse_dfm_fill_clause()
                else:
                    stmt = self._parse_statement(mode)
            except ParseError as exc:
                if self.strict:
                    raise
                skipped = self._recover_after_error(
                    statement_cst,
                    stop_symbols,
                    stop_preprocessors,
                )
                diagnostic = self._warn(
                    "parser.parse_error",
                    f"{str(exc).split(': ', 1)[-1]} [{self._describe_statement_cst(statement_cst)}]",
                    token=exc.token,
                    line=exc.line,
                    col=exc.col,
                )
                stmt = ast.ErrorNode(
                    message=str(diagnostic),
                    skipped_text=skipped,
                    line=exc.line,
                    col=exc.col,
                )
            finally:
                self._current_statement_cst = prev_statement_cst
            if stmt is not None:
                statements.append(self._finish_node(stmt, start))
                pending_dfm_spec = self._dfm_spec_continuation_after(stmt, pending_dfm_spec)
                if mode in {"macro", "property"}:
                    if self._is_deferred_property_header(statements[-1]):
                        pending_property_headers.append(len(statements) - 1)
                        pending_property_body_start = len(statements)
            if self.pos == start:
                self._warn(
                    "parser.stuck",
                    f"Parser stuck at {token.raw!r} in {self._describe_statement_cst(statement_cst)}, force advancing",
                    token=token,
                )
                if statement_cst.end > start:
                    self.pos = statement_cst.end
                else:
                    self._advance()

        return statements

    def _statement_cst_at_current(self, mode=None):
        statement_cst = self._current_statement_cst
        if statement_cst is None:
            return None
        if mode is not None and statement_cst.mode != mode:
            return None
        if statement_cst.start != self.pos:
            return None
        return statement_cst

    def _active_statement_cst(self, mode=None):
        statement_cst = self._current_statement_cst
        if statement_cst is None:
            return None
        if mode is not None and statement_cst.mode != mode:
            return None
        return statement_cst

    def _at_active_statement_end(self, mode=None):
        statement_cst = self._active_statement_cst(mode)
        if statement_cst is None:
            return False
        return self.pos >= statement_cst.end

    def _at_statement_limit(self, mode, allow_same_line_statement=False, use_active_unit=True):
        if use_active_unit and self._at_active_statement_end(mode):
            return True
        return self._at_statement_boundary(
            mode,
            allow_same_line_statement=allow_same_line_statement,
        )

    def _describe_statement_cst(self, statement_cst):
        if statement_cst is None:
            return "statement"
        head = statement_cst.parse_kind
        if statement_cst.head_kind != statement_cst.parse_kind:
            head = f"{head}/{statement_cst.head_kind}"
        if statement_cst.head_value is not None:
            head = f"{head}:{statement_cst.head_value}"
        boundary = statement_cst.boundary_kind
        if statement_cst.boundary_value is not None:
            boundary = f"{boundary}:{statement_cst.boundary_value}"
        return f"{head} -> {boundary}"

    def _at_statement_boundary(self, mode, allow_same_line_statement=False):
        return self._segmenter.at_statement_boundary(
            self.pos,
            mode,
            allow_same_line_statement=allow_same_line_statement,
        )

    def _recover_after_error(self, statement_cst, stop_symbols, stop_preprocessors):
        parts = [
            str(self.tokens[idx].raw)
            for idx in range(statement_cst.start, statement_cst.end)
        ]
        target_end = statement_cst.end
        while self.pos < target_end:
            self._advance()
        if statement_cst.end > statement_cst.start:
            return " ".join(parts).strip()
        if not parts:
            while True:
                token = self._cur()
                if token.type == TT.EOF:
                    break
                if token.type == TT.NEWLINE:
                    self._advance()
                    break
                if token.type == TT.PREPROCESSOR and token.value in stop_preprocessors:
                    break
                if token.type == TT.SYMBOL and token.value in stop_symbols:
                    break
                parts.append(str(token.raw))
                self._advance()
        return " ".join(parts).strip()

    def _can_start_expression_token(self, token=None):
        token = self._cur() if token is None else token
        if token.type in (TT.IDENT, TT.NUMBER, TT.STRING):
            return True
        return token.type == TT.SYMBOL and token.value in {"(", "[", "-", "+", "!", "~", "$"}

    def _current_edge_binary_op_parts(self):
        token = self._cur()
        if token.type != TT.IDENT or token.value not in _EDGE_BINARY_PREFIX_OPS:
            return None

        nxt = self._peek()
        if nxt.type != TT.IDENT:
            return None
        if nxt.value == "EDGE":
            return [token.value, "EDGE"]
        if nxt.value in {"INSIDE", "OUTSIDE"}:
            nxt2 = self._peek(2)
            if nxt2.type == TT.IDENT and nxt2.value == "EDGE":
                return [token.value, nxt.value, "EDGE"]
        return None

    def _consume_operation_continuation_newlines(self):
        consumed = False
        while self._cur().type == TT.NEWLINE and self._segmenter.continues_operation_across_newline(self.pos):
            self._advance()
            consumed = True
        return consumed

    def _consume_expression_continuation_newlines(self):
        consumed = False
        while self._cur().type == TT.NEWLINE and self._segmenter.continues_across_newline(self.pos):
            self._advance()
            consumed = True
        return consumed

    def _consume_rhs_newlines(self):
        consumed = False
        while self._cur().type == TT.NEWLINE and self._segmenter.continues_rhs_across_newline(self.pos):
            self._advance()
            consumed = True
        return consumed

    def _current_token_is_spaced_operand_before_paren(self):
        token = self._cur()
        nxt = self._peek()
        if token.type != TT.IDENT or nxt.type != TT.SYMBOL or nxt.value != "(":
            return False
        if nxt.line != token.end_line or nxt.col == token.end_col:
            return False
        return token.value not in (
            _FUNCTION_LIKE_NAMES
            | _GENERIC_PREFIX_OPS
            | _PREFIX_BOOLEAN_OPS
            | _UNARY_OPS
            | _MEASUREMENT_OPS
            | _EDGE_BINARY_PREFIX_OPS
            | {"WITH", "NOT"}
        )

    def _peek_callable_name_before_paren(self):
        save = self.pos
        try:
            name = self._parse_name()
        except ParseError:
            self.pos = save
            return None, False
        last_token = self.tokens[self.pos - 1] if self.pos > save else None
        nxt = self._cur()
        self.pos = save
        if last_token is None or nxt.type != TT.SYMBOL or nxt.value != "(":
            return None, False
        spaced = nxt.line != last_token.end_line or nxt.col != last_token.end_col
        return name, spaced

    def _parse_prefix_operand(self):
        token = self._cur()
        loc = self._loc(token)
        if self._current_token_is_spaced_operand_before_paren():
            self._advance()
            return ast.LayerRef(name=token.value, **loc)
        return self._parse_expression(50)

    def _parse_layer(self):
        return self._parse_statement_shape("layer")

    def _parse_layer_map(self, start):
        tokens = []
        while not self._at_statement_limit("top", allow_same_line_statement=True):
            tokens.append(self._advance())
        gds_num = 0
        map_type = "DATATYPE"
        type_num = 0
        internal_num = 0
        ints = [token.value for token in tokens if token.type == TT.NUMBER and isinstance(token.value, int)]
        if ints:
            gds_num = ints[0]
            internal_num = ints[-1]
            if len(ints) > 2:
                type_num = ints[1]
        for token in tokens:
            if token.type == TT.IDENT and token.value in {"DATATYPE", "TEXTTYPE"}:
                map_type = token.value
                break
        return ast.LayerMap(
            gds_num=gds_num,
            map_type=map_type,
            type_num=type_num,
            internal_num=internal_num,
            **self._loc(start),
        )

    def _parse_variable(self):
        return self._parse_statement_shape("variable")

    def _parse_include(self, embedded=False):
        start, keywords = self._consume_head_from_statement_cst(("INCLUDE",))
        if keywords is None:
            start = self._expect(TT.IDENT, "INCLUDE")
        path_parts = []
        while not self._at_statement_limit(
            "top",
            allow_same_line_statement=not embedded,
            use_active_unit=not embedded,
        ):
            token = self._cur()
            path_parts.append(token.value if token.type == TT.STRING else str(token.raw))
            self._advance()
        path = "".join(path_parts).strip()
        return ast.Include(path=path, embedded=embedded, preprocessor=False, **self._loc(start))

    def _parse_group(self):
        return self._parse_statement_shape("group")

    def _parse_simple_keyword_directive(self):
        return self._parse_statement_shape("simple_keyword_directive")

    def _parse_device(self):
        return self._parse_statement_shape("device")

    def _parse_dmacro(self):
        return self._parse_statement_shape("dmacro")

    def _parse_macro_call(self):
        return self._parse_statement_shape("macro_call")

    def _parse_attach(self):
        return self._parse_statement_shape("attach")

    def _parse_trace_property(self):
        return self._parse_statement_shape("trace_property")

    def _parse_directive(self):
        return self._parse_statement_shape("directive")

    def _parse_directive_head(self):
        start, keywords = self._consume_head_from_statement_cst()
        if keywords is not None:
            return start, keywords
        start = self._expect(TT.IDENT)
        keywords = [start.value]
        while self._cur().type == TT.IDENT and self._cur().value in _DIRECTIVE_SECONDARY_WORDS:
            keywords.append(self._advance().value)
        return start, keywords

    def _parse_directive_arguments(self):
        arguments = []
        while True:
            if self._cur().type == TT.NEWLINE:
                if self._consume_directive_continuation_newline():
                    continue
                break
            if self._at_directive_boundary():
                break
            arguments.append(self._parse_scalar_argument())
        return arguments

    def _consume_directive_continuation_newline(self):
        if self._cur().type != TT.NEWLINE:
            return False
        if not self._segmenter.continues_directive_across_newline(self.pos):
            return False
        self.pos = self._next_non_newline_index()
        return True

    def _parse_assignment(self):
        start = self._cur()
        name = self._parse_name()
        self._skip_newlines()
        self._expect(TT.SYMBOL, "=")
        self._consume_rhs_newlines()
        if self._at_statement_boundary("top", allow_same_line_statement=False):
            self._warn(
                "parser.assignment.empty",
                f"Empty assignment for {name}",
                token=start,
            )
            return ast.LayerAssignment(name=name, expression=None, **self._loc(start))
        expression = self._parse_expression(stop_on_newline=True)
        return ast.LayerAssignment(name=name, expression=expression, **self._loc(start))

    def _parse_rule_check(self):
        return self._parse_statement_shape("rule_check")

    def _parse_rule_check_header(self):
        statement_cst = self._statement_cst_at_current("top")
        if statement_cst is None or statement_cst.rule_check_header is None:
            token = self._cur()
            raise ParseError(
                "Missing rule-check CST header metadata",
                token.line,
                token.col,
                token,
            )
        start = self._cur()
        self.pos = statement_cst.rule_check_header.body_start
        return start, statement_cst.rule_check_header.name

    def _parse_rule_check_comments(self):
        comments = []
        while self._cur().type == TT.RULE_COMMENT:
            comments.append(self._parse_rule_comment())
            self._skip_newlines()
        return comments

    def _parse_rule_check_body(self):
        return self._parse_sequence(mode="rule", stop_symbols={"}"})

    def _parse_rule_comment(self):
        token = self._expect(TT.RULE_COMMENT)
        return self._split_comment_segments(token.value, self._loc(token))

    @staticmethod
    def _split_comment_segments(text, loc):
        segments = []
        last = 0
        for match in re.finditer(r"\\(\^)|(\^)([A-Za-z_][A-Za-z0-9_]*)", text):
            if match.group(1):
                if match.start() > last:
                    segments.append(text[last:match.start()])
                segments.append("^")
                last = match.end()
                continue
            if match.start() > last:
                segments.append(text[last:match.start()])
            segments.append(ast.VarRef(name=match.group(3), **loc))
            last = match.end()
        if last < len(text):
            segments.append(text[last:])

        merged = []
        for seg in segments:
            if isinstance(seg, str) and merged and isinstance(merged[-1], str):
                merged[-1] += seg
            else:
                merged.append(seg)
        return merged or [""]

    def _parse_preprocessor(self, mode):
        token = self._cur()
        schema = PREPROCESSOR_SCHEMA_REGISTRY.match(token.value)
        if schema is None:
            return self._parse_preprocessor_directive()
        if schema.parser_method == "_parse_ifdef_from_preprocessor":
            return self._parse_ifdef_from_preprocessor(mode)
        return getattr(self, schema.parser_method)()

    def _consume_noop_preprocessor(self):
        self._advance()
        self._collect_line_text()
        return None

    def _parse_define(self):
        start = self._expect(TT.PREPROCESSOR, "#DEFINE")
        name = self._parse_name(allow_missing=True)
        value = self._collect_line_text() or None
        return ast.Define(name=name or "", value=value, **self._loc(start))

    def _parse_undefine(self):
        start = self._expect(TT.PREPROCESSOR, "#UNDEFINE")
        name = self._parse_name(allow_missing=True)
        self._collect_line_text()
        return ast.Directive(keywords=["#UNDEFINE"], arguments=[name] if name else [], **self._loc(start))

    def _parse_pp_include(self):
        start = self._expect(TT.PREPROCESSOR, "#INCLUDE")
        path_parts = []
        while self._cur().type not in (TT.EOF, TT.NEWLINE):
            token = self._cur()
            path_parts.append(token.value if token.type == TT.STRING else str(token.raw))
            self._advance()
        self._match(TT.NEWLINE)
        return ast.Include(
            path="".join(path_parts).strip(),
            embedded=False,
            preprocessor=True,
            **self._loc(start),
        )

    def _parse_preprocessor_directive(self):
        start = self._expect(TT.PREPROCESSOR)
        args = self._collect_line_arguments()
        return ast.Directive(keywords=[start.value], arguments=args, **self._loc(start))

    def _parse_ifdef(self, mode):
        start = self._expect(TT.PREPROCESSOR)
        negated = start.value == "#IFNDEF"
        name = self._parse_name(allow_missing=True)
        value = self._collect_line_text() or None

        then_header, then_property = self._parse_ifdef_branch_header(mode, {"#ELSE", "#ENDIF"})
        then_body = self._parse_ifdef_branch_body(mode, then_header, then_property, {"#ELSE", "#ENDIF"})
        else_body, else_header, else_property = self._parse_ifdef_else_branch(mode)

        self._expect(TT.PREPROCESSOR, "#ENDIF", "Expected #ENDIF to close conditional")
        self._collect_line_text()

        then_body, else_body = self._finalize_ifdef_shared_bodies(
            mode,
            then_header,
            else_header,
            then_property,
            else_property,
            then_body,
            else_body,
        )
        return ast.IfDef(
            name=name or "",
            value=value,
            negated=negated,
            then_body=then_body,
            else_body=else_body,
            **self._loc(start),
        )

    def _parse_ifdef_branch_header(self, mode, stop_preprocessors):
        if mode == "top":
            return self._try_parse_conditional_rule_header(stop_preprocessors), None
        if mode in ("macro", "property"):
            return None, self._try_parse_conditional_property_header(stop_preprocessors)
        return None, None

    def _parse_ifdef_branch_body(self, mode, rule_header, property_header, stop_preprocessors):
        if rule_header is not None or property_header is not None:
            return []
        return self._parse_sequence(mode=mode, stop_preprocessors=stop_preprocessors)

    def _parse_ifdef_else_branch(self, mode):
        else_body = []
        else_header = None
        else_property = None
        if not self._at(TT.PREPROCESSOR, "#ELSE"):
            return else_body, else_header, else_property
        self._advance()
        self._collect_line_text()
        else_header, else_property = self._parse_ifdef_branch_header(mode, {"#ENDIF"})
        if else_header is None and else_property is None:
            else_body = self._parse_sequence(mode=mode, stop_preprocessors={"#ENDIF"})
        return else_body, else_header, else_property

    def _finalize_ifdef_shared_bodies(
        self,
        mode,
        then_header,
        else_header,
        then_property,
        else_property,
        then_body,
        else_body,
    ):
        if mode == "top" and (then_header is not None or else_header is not None):
            return self._finalize_ifdef_rule_bodies(then_header, else_header)
        if mode in ("macro", "property") and (then_property is not None or else_property is not None):
            return self._finalize_ifdef_property_bodies(then_property, else_property)
        return then_body, else_body

    def _finalize_ifdef_rule_bodies(self, then_header, else_header):
        shared_body = self._parse_sequence(mode="rule", stop_symbols={"}"})
        self._expect(TT.SYMBOL, "}")
        then_body = []
        else_body = []
        if then_header is not None:
            then_body = [self._build_conditional_rule_block(then_header, shared_body)]
        if else_header is not None:
            else_body = [self._build_conditional_rule_block(else_header, shared_body)]
        return then_body, else_body

    def _build_conditional_rule_block(self, header, shared_body):
        return ast.RuleCheckBlock(
            name=header["name"],
            comments=header["comments"],
            body=copy.deepcopy(header["body"]) + copy.deepcopy(shared_body),
            **header["loc"],
        )

    def _finalize_ifdef_property_bodies(self, then_property, else_property):
        shared_body = self._parse_ifdef_shared_property_body()
        then_body = []
        else_body = []
        if then_property is not None:
            then_body = [self._build_conditional_property_block(then_property, shared_body)]
        if else_property is not None:
            else_body = [self._build_conditional_property_block(else_property, shared_body)]
        return then_body, else_body

    def _parse_ifdef_shared_property_body(self):
        next_idx = self._next_non_newline_index()
        immediate_property_body = not (
            next_idx < self.length
            and self.tokens[next_idx].type == TT.PREPROCESSOR
            and self.tokens[next_idx].value in {"#IFDEF", "#IFNDEF", "#ELSE", "#ENDIF"}
        )
        if not immediate_property_body:
            return []
        shared_body = self._parse_sequence(mode="property", stop_symbols={"]"})
        self._expect(TT.SYMBOL, "]", "Expected ']' to close property block")
        return shared_body

    def _build_conditional_property_block(self, header, shared_body):
        return ast.PropertyBlock(
            properties=header["properties"],
            body=copy.deepcopy(shared_body),
            **header["loc"],
        )

    def _try_parse_conditional_rule_header(self, stop_preprocessors):
        save = self.pos
        self._skip_newlines()
        header = self._segmenter.scan_rule_check_header(self.pos)
        if header is None:
            self.pos = save
            return None

        start = self._cur()
        try:
            name = header.name
            self.pos = header.body_start

            comments = []
            while self._cur().type == TT.RULE_COMMENT:
                comments.append(self._parse_rule_comment())
                self._skip_newlines()

            body = self._parse_sequence(mode="rule", stop_symbols={"}"}, stop_preprocessors=stop_preprocessors)
            if self._cur().type == TT.PREPROCESSOR and self._cur().value in stop_preprocessors:
                return {
                    "name": name,
                    "comments": comments or None,
                    "body": body,
                    "loc": self._loc(start),
                }
        except ParseError:
            pass

        self.pos = save
        return None

    def _try_parse_conditional_property_header(self, stop_preprocessors):
        save = self.pos
        self._skip_newlines()
        header = self._segmenter.scan_property_block_header(
            self.pos,
            stop_preprocessors=stop_preprocessors,
        )
        if header is None:
            self.pos = save
            return None

        start = self._cur()
        try:
            properties = list(header.properties)
            self.pos = header.body_start
            self._skip_newlines()
            if self._cur().type == TT.PREPROCESSOR and self._cur().value in stop_preprocessors:
                return {
                    "properties": properties,
                    "loc": self._loc(start),
                }
        except ParseError:
            pass

        self.pos = save
        return None

    def _parse_encrypted_block(self):
        start = self._expect(TT.PREPROCESSOR)
        self._match(TT.NEWLINE)
        content = ""
        content_token = None
        if self._at(TT.ENCRYPTED):
            content_token = self._advance()
            content = content_token.value
        else:
            parts = []
            while not self._at(TT.EOF):
                if self._at(TT.PREPROCESSOR, "#ENDCRYPT"):
                    break
                if self._at(TT.NEWLINE):
                    parts.append("\n")
                    self._advance()
                    continue
                parts.append(str(self._advance().raw))
                if self._cur().type not in (TT.NEWLINE, TT.EOF):
                    parts.append(" ")
            content = "".join(parts).strip()

        if self._at(TT.PREPROCESSOR, "#ENDCRYPT"):
            self._advance()
            self._collect_line_text()
        body, parse_status = self._try_parse_encrypted_plaintext(content, content_token)
        return ast.EncryptedBlock(
            content=content,
            body=body,
            parse_status=parse_status,
            directive=start.value,
            **self._loc(start),
        )

    def _try_parse_encrypted_plaintext(self, content, content_token):
        if not content or not content.strip():
            return [], "opaque"
        try:
            lexer = Lexer(content, filename=self.filename)
            parser = type(self)(
                lexer.tokens(),
                filename=self.filename,
                source_text=content,
                strict=False,
            )
            program = parser.parse()
        except Exception:
            return [], "opaque"
        statements = list(getattr(program, "statements", ()) or ())
        if not statements or parser.warnings:
            return [], "opaque"
        if any(isinstance(statement, ast.ErrorNode) for statement in statements):
            return [], "opaque"
        if count_svrf_constructs(statements) == 0:
            return [], "opaque"
        if content_token is not None:
            self._shift_encrypted_body_spans(
                statements,
                line_delta=content_token.line - 1,
                first_line_col_delta=content_token.col - 1,
                offset_delta=content_token.offset,
            )
        return statements, "plaintext"

    @staticmethod
    def _shift_encrypted_body_spans(statements, *, line_delta, first_line_col_delta, offset_delta):
        for statement in statements:
            for node in statement.walk():
                if node.line:
                    if node.line == 1:
                        node.col += first_line_col_delta
                    if node.end_line == 1:
                        node.end_col += first_line_col_delta
                    node.line += line_delta
                    node.end_line += line_delta
                if node.line:
                    node.start_offset += offset_delta
                    node.end_offset += offset_delta

    def _parse_property_block(self):
        return self._parse_statement_shape("property_block")

    def _parse_property_block_header(self):
        statement_cst = self._statement_cst_at_current()
        if statement_cst is None or statement_cst.property_block_header is None:
            token = self._cur()
            raise ParseError(
                "Missing property-block CST header metadata",
                token.line,
                token.col,
                token,
            )
        start = self._cur()
        self.pos = statement_cst.property_block_header.body_start
        return start, list(statement_cst.property_block_header.properties)

    def _parse_property_block_body(self):
        return self._parse_sequence(
            mode="property",
            stop_symbols={"]"},
            stop_preprocessors={"#ELSE", "#ENDIF"},
        )

    def _finish_property_block(self, start, properties, body):
        block = ast.PropertyBlock(properties=properties, body=body, **self._loc(start))
        return self._finish_property_block_node(block)

    def _finish_property_block_node(self, block):
        if self._at(TT.SYMBOL, "]"):
            self._advance()
            return block
        if self._at(TT.PREPROCESSOR) and self._cur().value in {"#ELSE", "#ENDIF"}:
            return block
        if self._at(TT.EOF) or self._at(TT.SYMBOL, "}"):
            return block
        self._expect(TT.SYMBOL, "]", "Expected ']' to close property block")
        return block

    def _parse_if_expr(self, mode):
        start, keywords = self._consume_head_from_statement_cst(("IF",))
        if keywords is None:
            start = self._expect(TT.IDENT, "IF")
        condition = self._parse_if_expr_condition()
        then_body = self._parse_if_expr_block(mode, "Expected '{' to start IF body")
        elseifs, else_body = self._parse_if_expr_tail(mode)

        return ast.IfExpr(
            condition=condition,
            then_body=then_body,
            elseifs=elseifs,
            else_body=else_body,
            **self._loc(start),
        )

    def _parse_if_expr_condition(self):
        self._skip_newlines()
        if self._match(TT.SYMBOL, "("):
            condition = self._parse_expression(stop_tokens={")"}, stop_on_newline=False)
            self._expect(TT.SYMBOL, ")")
            return condition
        return self._parse_expression(stop_on_newline=True)

    def _parse_if_expr_block(self, mode, message):
        self._skip_newlines()
        self._expect(TT.SYMBOL, "{", message)
        body = self._parse_sequence(mode=mode, stop_symbols={"}"})
        self._expect(TT.SYMBOL, "}")
        return body

    def _parse_if_expr_tail(self, mode):
        elseifs = []
        else_body = []
        self._skip_newlines()
        while self._match(TT.IDENT, "ELSE"):
            self._skip_newlines()
            if self._match(TT.IDENT, "IF"):
                elseifs.append(self._parse_else_if_expr_branch(mode))
                self._skip_newlines()
                continue
            else_body = self._parse_if_expr_block(mode, "Expected '{' to start ELSE body")
            break
        return elseifs, else_body

    def _parse_else_if_expr_branch(self, mode):
        self._skip_newlines()
        self._expect(TT.SYMBOL, "(")
        condition = self._parse_expression(stop_tokens={")"}, stop_on_newline=False)
        self._expect(TT.SYMBOL, ")")
        body = self._parse_if_expr_block(mode, "Expected '{' to start ELSE IF body")
        return condition, body

    def _parse_name(self, allow_missing=False, *, preserve_case=False):
        name = self._parse_name_part(allow_missing=allow_missing, preserve_case=preserve_case)
        if name is None:
            return None

        while True:
            save = self.pos
            self._skip_newlines()
            separator = None
            if self._at(TT.SYMBOL, ":") or self._at(TT.SYMBOL, "::"):
                separator = self._advance().value
            if separator is None:
                self.pos = save
                break
            self._skip_newlines()
            part = self._parse_name_part(preserve_case=preserve_case)
            name = f"{name}{separator}{part}"
        return name

    def _parse_name_part(self, allow_missing=False, *, preserve_case=False):
        token = self._cur()
        if token.type == TT.IDENT:
            token = self._advance()
            raw = token.raw if token.raw is not None else token.value
            return str(raw) if preserve_case else str(raw).upper()
        if token.type == TT.STRING:
            return self._advance().value
        if token.type == TT.NUMBER:
            return str(self._advance().raw)
        if allow_missing:
            return None
        raise ParseError("Expected a name", token.line, token.col, token)

    def _parse_scalar_argument(self):
        token = self._cur()
        if token.type == TT.STRING:
            return self._advance().value
        if token.type == TT.NUMBER:
            return self._advance().value
        if token.type == TT.IDENT:
            return self._advance().value
        if token.type == TT.SYMBOL and token.value == "[":
            return self._parse_bracketed_scalar_sequence()
        if token.type == TT.SYMBOL and token.value == "(":
            return self._parse_expression(stop_tokens={")"}, stop_on_newline=False)
        return self._advance().raw

    def _parse_bracketed_scalar_sequence(self):
        self._expect(TT.SYMBOL, "[")
        parts = ["["]
        depth = 1
        while not self._at(TT.EOF) and depth > 0:
            token = self._advance()
            if token.type == TT.SYMBOL and token.value == "[":
                depth += 1
            elif token.type == TT.SYMBOL and token.value == "]":
                depth -= 1
            parts.append("\n" if token.type == TT.NEWLINE else str(token.raw))
            if depth == 0:
                break
        return "".join(parts)

    def _consume_bracket_fallback_text(self):
        parts = ["["]
        depth = 1
        while not self._at(TT.EOF) and depth > 0:
            token = self._advance()
            if token.type == TT.SYMBOL and token.value == "[":
                depth += 1
            elif token.type == TT.SYMBOL and token.value == "]":
                depth -= 1
            parts.append("\n" if token.type == TT.NEWLINE else str(token.raw))
            if depth == 0:
                break
        return "".join(parts)

    def _collect_line_text(self):
        parts = []
        while self._cur().type not in (TT.EOF, TT.NEWLINE):
            parts.append(str(self._advance().raw))
        self._match(TT.NEWLINE)
        return " ".join(parts).strip()

    def _collect_line_arguments(self):
        args = []
        while self._cur().type not in (TT.EOF, TT.NEWLINE):
            args.append(self._parse_scalar_argument())
        self._match(TT.NEWLINE)
        return args

    def _parse_unknown(self, mode):
        token = self._cur()
        statement_cst = self._statement_cst_at_current(mode)
        if statement_cst is not None:
            statement_start = statement_cst.start
            statement_end = statement_cst.end
        else:
            statement_slice = self._segmenter.statement_slice(self.pos, mode)
            statement_start = statement_slice.start
            statement_end = statement_slice.end
        parts = []
        while self.pos < statement_end:
            parts.append(str(self._advance().raw))
        if statement_end == self.pos:
            self._match(TT.NEWLINE)
        skipped = " ".join(parts).strip()
        diagnostic = self._warn(
            "parser.unrecognized_statement",
            f"Skipped unrecognized content: {skipped[:80]}",
            token=token,
        )
        return ast.ErrorNode(
            message=str(diagnostic),
            skipped_text=skipped,
            **self._loc(token),
        )
