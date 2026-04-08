"""Statement-boundary helpers for SVRF token streams.

The parser historically embedded same-line statement and directive boundary
heuristics inline. This module centralizes that logic so statement segmentation
can evolve independently from expression parsing.
"""

from __future__ import annotations

from dataclasses import dataclass

from .statement_cst import PropertyBlockHeader, RuleCheckHeader, StatementCst, StatementHead
from .tokens import Token, TokenType

TT = TokenType


@dataclass(frozen=True, slots=True)
class SegmenterConfig:
    directive_heads: frozenset[str]
    directive_same_line_heads: frozenset[str]
    directive_secondary_words: frozenset[str]
    top_level_line_heads: frozenset[str]
    top_level_same_line_heads: frozenset[str]
    expression_like_directive_heads: frozenset[str]
    rule_body_same_line_starters: frozenset[str]
    comparison_symbols: frozenset[str]
    arithmetic_symbols: frozenset[str]
    expression_operator_words: frozenset[str]
    expression_prefix_words: frozenset[str]
    modifier_starters: frozenset[str]
    prefix_boolean_ops: frozenset[str]
    group_continuation_keywords: frozenset[str]


@dataclass(frozen=True, slots=True)
class StatementSlice:
    """Half-open token range [start, end); boundary tokens, including EOF, are excluded."""

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class StatementUnit:
    mode: str
    parse_kind: str
    start: int
    end: int
    head_kind: str
    head_value: str | None
    leading_delimiter: str | None
    boundary_kind: str
    boundary_value: str | None
    continued_across_newline: bool
    head_end: int | None = None
    head_words: tuple[str, ...] | None = None

    @property
    def slice(self):
        return StatementSlice(start=self.start, end=self.end)


class StatementSegmenter:
    """Centralized statement start/boundary logic over a token stream."""

    def __init__(self, tokens, config: SegmenterConfig):
        self.tokens = tokens
        self.length = len(tokens)
        self.config = config
        self._slice_cache = {}
        self._unit_cache = {}
        self._cst_cache = {}
        self._clause_cst_cache = {}

    @staticmethod
    def _cache_key(start_idx, mode, stop_symbols=None, stop_preprocessors=None):
        return (
            start_idx,
            mode,
            frozenset(stop_symbols or ()),
            frozenset(stop_preprocessors or ()),
        )

    def _token_at(self, idx):
        if 0 <= idx < self.length:
            return self.tokens[idx]
        return self.tokens[-1]

    def next_non_newline_index(self, idx):
        while idx < self.length and self.tokens[idx].type == TT.NEWLINE:
            idx += 1
        return idx

    def next_non_newline_token(self, idx):
        idx = self.next_non_newline_index(idx)
        if idx >= self.length:
            return None
        return self.tokens[idx]

    def previous_non_newline_index(self, idx):
        while idx >= 0 and self.tokens[idx].type == TT.NEWLINE:
            idx -= 1
        return idx

    def can_start_expression_token(self, token):
        if token.type in (TT.IDENT, TT.NUMBER, TT.STRING):
            return True
        return token.type == TT.SYMBOL and token.value in {"(", "[", "-", "+", "!", "~", "$"}

    def token_allows_group_continuation(self, token):
        if token is None:
            return False
        if token.type == TT.SYMBOL:
            return token.value in (
                {"(", "[", ",", "?", ":", "=", "+", "-", "*", "/", "^"}
                | self.config.comparison_symbols
            )
        if token.type != TT.IDENT:
            return False
        return token.value in self.config.group_continuation_keywords

    def continues_rhs_across_newline(self, newline_idx):
        next_idx = self.next_non_newline_index(newline_idx + 1)
        if next_idx >= self.length:
            return False
        nxt = self.tokens[next_idx]
        return self.can_start_expression_token(nxt) and not self.starts_line_statement_at(next_idx)

    def continues_indented_expression_across_newline(
        self,
        newline_idx,
        anchor_col,
        allow_parenthesized=False,
    ):
        next_idx = self.next_non_newline_index(newline_idx + 1)
        if next_idx >= self.length:
            return False
        nxt = self.tokens[next_idx]
        return (
            self.can_start_expression_token(nxt)
            and (allow_parenthesized or nxt.col > anchor_col)
            and not self.starts_line_statement_at(next_idx)
        )

    def continues_directive_across_newline(self, newline_idx):
        next_idx = self.next_non_newline_index(newline_idx + 1)
        if next_idx >= self.length:
            return False
        nxt = self.tokens[next_idx]
        return nxt.type == TT.SYMBOL and nxt.value == "["

    def continues_operation_across_newline(self, newline_idx):
        next_idx = self.next_non_newline_index(newline_idx + 1)
        if next_idx >= self.length:
            return False
        nxt = self.tokens[next_idx]
        if nxt.type == TT.SYMBOL and nxt.value == "[":
            return True
        if nxt.type == TT.SYMBOL and nxt.value in self.config.comparison_symbols:
            return True
        if nxt.type == TT.IDENT and nxt.value in self.config.modifier_starters:
            return True
        return False

    def continues_nonstatement_expression_across_newline(self, newline_idx, mode):
        next_idx = self.next_non_newline_index(newline_idx + 1)
        if next_idx >= self.length:
            return False
        nxt = self.tokens[next_idx]
        return self.can_start_expression_token(nxt) and not self.starts_statement_at(next_idx, mode)

    def property_header_newline_action(self, newline_idx, stop_preprocessors=None):
        stop_preprocessors = set(stop_preprocessors or ())
        next_idx = self.next_non_newline_index(newline_idx + 1)
        if next_idx >= self.length:
            return ("eof", next_idx)
        nxt = self.tokens[next_idx]
        if nxt.type == TT.PREPROCESSOR and nxt.value in stop_preprocessors:
            return ("stop_preprocessor", next_idx)
        if self.starts_assignment_at(next_idx):
            return ("body", next_idx)
        return ("continue", next_idx)

    def continues_across_newline(self, newline_idx):
        next_idx = self.next_non_newline_index(newline_idx + 1)
        if next_idx >= self.length:
            return False
        nxt = self.tokens[next_idx]
        prev_idx = self.previous_non_newline_index(newline_idx - 1)
        prev = self.tokens[prev_idx] if prev_idx >= 0 else None

        if nxt.type == TT.SYMBOL and nxt.value in {"?", ":"}:
            return True
        if nxt.type == TT.SYMBOL and nxt.value in {"[", "("}:
            return self.token_allows_group_continuation(prev)
        if prev is not None:
            if (
                prev.type == TT.SYMBOL
                and (
                    prev.value in {"?", ":", "=", "+", "-", "*", "/", "^"}
                    or prev.value in self.config.comparison_symbols
                )
                and self.continues_rhs_across_newline(newline_idx)
            ):
                return True
            if (
                prev.type == TT.IDENT
                and prev.value in self.config.prefix_boolean_ops
                and self.continues_rhs_across_newline(newline_idx)
            ):
                return True
        if nxt.type == TT.SYMBOL and (
            nxt.value in self.config.comparison_symbols
            or nxt.value in self.config.arithmetic_symbols
        ):
            return True
        if (
            nxt.type == TT.IDENT
            and nxt.value in self.config.modifier_starters
            and not self.starts_line_statement_at(next_idx)
        ):
            return True
        return False

    def scan_name_end(self, idx):
        scanned = self.scan_name(idx)
        if scanned is None:
            return None
        return scanned[1]

    def _name_part_value(self, token):
        if token.type == TT.IDENT:
            raw = token.raw if token.raw is not None else token.value
            return str(raw).upper()
        if token.type == TT.STRING:
            return token.value
        if token.type == TT.NUMBER:
            return str(token.raw)
        return None

    def scan_name(self, idx):
        if idx >= self.length:
            return None
        part = self._name_part_value(self.tokens[idx])
        if part is None:
            return None
        parts = [part]
        idx += 1
        while True:
            idx = self.next_non_newline_index(idx)
            if idx >= self.length:
                break
            token = self.tokens[idx]
            if token.type != TT.SYMBOL or token.value not in {":", "::"}:
                break
            parts.append(token.value)
            idx += 1
            idx = self.next_non_newline_index(idx)
            if idx >= self.length:
                return None
            part = self._name_part_value(self.tokens[idx])
            if part is None:
                return None
            parts.append(part)
            idx += 1
        return "".join(parts), idx

    def scan_rule_check_header(self, idx):
        scanned = self.scan_name(idx)
        if scanned is None:
            return None
        name, next_idx = scanned
        next_idx = self.next_non_newline_index(next_idx)
        token = self._token_at(next_idx)
        if token.type != TT.SYMBOL or token.value != "{":
            return None
        body_start = self.next_non_newline_index(next_idx + 1)
        return RuleCheckHeader(name=name, body_start=body_start)

    def scan_property_block_header(self, idx, stop_preprocessors=None):
        stop_preprocessors = set(stop_preprocessors or ())
        token = self._token_at(idx)
        if token.type != TT.SYMBOL or token.value != "[":
            return None
        prop_idx = self.next_non_newline_index(idx + 1)
        prop_token = self._token_at(prop_idx)
        if prop_token.type != TT.IDENT or prop_token.value != "PROPERTY":
            return None

        idx = prop_idx + 1
        properties = []
        expecting_name = True
        while idx < self.length:
            token = self._token_at(idx)
            if token.type == TT.NEWLINE:
                action, next_idx = self.property_header_newline_action(
                    idx,
                    stop_preprocessors=stop_preprocessors,
                )
                if action == "eof":
                    return PropertyBlockHeader(properties=tuple(properties), body_start=next_idx)
                if action in {"stop_preprocessor", "body"}:
                    return PropertyBlockHeader(properties=tuple(properties), body_start=next_idx)
                idx += 1
                continue
            if token.type == TT.PREPROCESSOR:
                if token.value in stop_preprocessors:
                    return PropertyBlockHeader(properties=tuple(properties), body_start=idx)
                idx += 1
                while idx < self.length and self.tokens[idx].type not in (TT.EOF, TT.NEWLINE):
                    idx += 1
                continue
            if token.type == TT.SYMBOL and token.value == ",":
                expecting_name = True
                idx += 1
                continue
            if expecting_name:
                part = self._name_part_value(token)
                if part is not None:
                    properties.append(part)
                    expecting_name = False
                    idx += 1
                    continue
            break
        if idx < self.length and self.tokens[idx].type == TT.NEWLINE:
            idx += 1
        return PropertyBlockHeader(properties=tuple(properties), body_start=idx)

    def starts_assignment_at(self, idx):
        end = self.scan_name_end(idx)
        if end is None:
            return False
        idx = self.next_non_newline_index(end)
        if idx >= self.length:
            return False
        token = self.tokens[idx]
        return token.type == TT.SYMBOL and token.value == "="

    def starts_rule_check_at(self, idx, mode):
        if mode != "top" or idx >= self.length:
            return False
        token = self.tokens[idx]
        if token.type not in (TT.IDENT, TT.STRING, TT.NUMBER):
            return False
        idx += 1
        idx = self.next_non_newline_index(idx)
        while idx + 1 < self.length:
            colon = self.tokens[idx]
            if colon.type != TT.SYMBOL or colon.value != ":":
                break
            idx += 1
            idx = self.next_non_newline_index(idx)
            if idx >= self.length or self.tokens[idx].type not in (TT.IDENT, TT.STRING, TT.NUMBER):
                return False
            idx += 1
            idx = self.next_non_newline_index(idx)
        if idx < self.length:
            nxt = self.tokens[idx]
            return nxt.type == TT.SYMBOL and nxt.value == "{"
        return False

    def starts_line_statement_at(self, idx):
        if idx >= self.length:
            return False
        token = self.tokens[idx]
        if token.type == TT.PREPROCESSOR:
            return True
        if token.type in (TT.STRING, TT.NUMBER):
            return self.starts_assignment_at(idx) or self.starts_rule_check_at(idx, "top")
        if token.type != TT.IDENT:
            return False
        if self.starts_assignment_at(idx) or self.starts_rule_check_at(idx, "top"):
            return True
        if token.value in self.config.top_level_line_heads:
            return True
        return (
            token.value in self.config.directive_heads
            and token.value not in self.config.expression_like_directive_heads
        )

    def looks_like_same_line_top_directive_at(self, idx):
        if idx >= self.length:
            return False
        token = self.tokens[idx]
        if token.type != TT.IDENT or token.value not in self.config.directive_same_line_heads:
            return False
        nxt = self.next_non_newline_token(idx + 1)
        return nxt is not None and nxt.type == TT.IDENT and nxt.value in self.config.directive_secondary_words

    def starts_same_line_statement_at(self, idx, mode):
        if idx >= self.length:
            return False
        token = self.tokens[idx]
        if token.type in (TT.EOF, TT.NEWLINE):
            return False
        if token.type == TT.PREPROCESSOR:
            return True
        if token.type == TT.SYMBOL:
            return False

        if mode == "top":
            if token.type != TT.IDENT:
                return False
            if self.starts_assignment_at(idx) or self.starts_rule_check_at(idx, "top"):
                return True
            if token.value in self.config.top_level_same_line_heads:
                return True
            if token.value == "TRACE":
                nxt = self.next_non_newline_token(idx + 1)
                return nxt is not None and nxt.type == TT.IDENT and nxt.value == "PROPERTY"
            return self.looks_like_same_line_top_directive_at(idx)

        if mode in {"rule", "macro", "property"}:
            if token.type != TT.IDENT:
                return False
            if self.starts_assignment_at(idx):
                return True
            if mode in {"macro", "property"} and token.value == "IF":
                return True
            return token.value in self.config.rule_body_same_line_starters

        return False

    def at_statement_boundary(self, idx, mode, allow_same_line_statement=False):
        token = self._token_at(idx)
        if token.type in (TT.EOF, TT.NEWLINE, TT.PREPROCESSOR):
            return True
        if token.type == TT.SYMBOL and token.value in {"}", "]", ")"}:
            return True
        if allow_same_line_statement and self.starts_same_line_statement_at(idx, mode):
            return True
        return False

    def at_directive_boundary(self, idx):
        token = self._token_at(idx)
        if token.type in (TT.EOF, TT.NEWLINE, TT.PREPROCESSOR):
            return True
        if token.type == TT.SYMBOL and token.value in {"}", "]", ")"}:
            return True
        if self.starts_assignment_at(idx) or self.starts_rule_check_at(idx, "top"):
            return True
        return self.looks_like_same_line_top_directive_at(idx)

    def statement_slice(self, start_idx, mode, stop_symbols=None, stop_preprocessors=None):
        cache_key = self._cache_key(start_idx, mode, stop_symbols, stop_preprocessors)
        cached = self._slice_cache.get(cache_key)
        if cached is not None:
            return cached
        stop_symbols = cache_key[2]
        stop_preprocessors = cache_key[3]
        idx = start_idx
        head_kind, _head_value = self._classify_head(start_idx, mode)
        consumed = False
        suppress_same_line_break = False
        paren_depth = 0
        bracket_depth = 0
        brace_depth = 0

        while idx < self.length:
            token = self.tokens[idx]
            depth_zero = paren_depth == 0 and bracket_depth == 0 and brace_depth == 0
            if token.type == TT.EOF:
                break

            if consumed and depth_zero:
                if token.type == TT.NEWLINE:
                    if head_kind == "directive" and self.continues_directive_across_newline(idx):
                        idx = self.next_non_newline_index(idx + 1)
                        suppress_same_line_break = True
                        continue
                    if self.continues_across_newline(idx):
                        idx = self.next_non_newline_index(idx + 1)
                        suppress_same_line_break = True
                        continue
                    idx = self.next_non_newline_index(idx + 1)
                    break
                if token.type == TT.PREPROCESSOR:
                    if not stop_preprocessors or token.value in stop_preprocessors:
                        break
                if token.type == TT.SYMBOL:
                    if token.value in stop_symbols or token.value in {"}", "]", ")"}:
                        break
                if not suppress_same_line_break and head_kind == "directive" and self.at_directive_boundary(idx):
                    break
                if (
                    not suppress_same_line_break
                    and head_kind != "directive"
                    and self.starts_same_line_statement_at(idx, mode)
                ):
                    prev_idx = self.previous_non_newline_index(idx - 1)
                    prev = self.tokens[prev_idx] if prev_idx >= 0 else None
                    if not self.token_allows_group_continuation(prev):
                        break

            if token.type == TT.SYMBOL:
                if token.value == "(":
                    paren_depth += 1
                elif token.value == "[":
                    bracket_depth += 1
                elif token.value == "{":
                    brace_depth += 1
                elif token.value == ")" and paren_depth > 0:
                    paren_depth -= 1
                elif token.value == "]" and bracket_depth > 0:
                    bracket_depth -= 1
                elif token.value == "}" and brace_depth > 0:
                    brace_depth -= 1

            idx += 1
            consumed = True
            suppress_same_line_break = False

        statement_slice = StatementSlice(start=start_idx, end=idx)
        self._slice_cache[cache_key] = statement_slice
        return statement_slice

    def _classify_head(self, idx, mode):
        token = self._token_at(idx)
        if token.type == TT.PREPROCESSOR:
            return ("preprocessor", token.value)
        if token.type == TT.SYMBOL:
            if token.value == "[":
                nxt = self.next_non_newline_token(idx + 1)
                if nxt is not None and nxt.type == TT.IDENT and nxt.value == "PROPERTY":
                    return ("property_block", "PROPERTY")
            if self.can_start_expression_token(token):
                return ("expression", token.value)
            return ("unknown", str(token.raw))
        if self.starts_assignment_at(idx):
            return ("assignment", token.value if token.type == TT.IDENT else str(token.raw))
        if self.starts_rule_check_at(idx, mode):
            return ("rule_check", token.value if token.type == TT.IDENT else str(token.raw))
        if token.type == TT.IDENT:
            if mode == "top" and token.value in self.config.top_level_line_heads:
                return ("statement_head", token.value)
            if mode in {"macro", "property"} and token.value == "IF":
                return ("statement_head", token.value)
            if mode in {"rule", "macro", "property"} and token.value in self.config.rule_body_same_line_starters:
                return ("statement_head", token.value)
            if token.value in self.config.directive_heads and token.value not in self.config.expression_like_directive_heads:
                return ("directive", token.value)
            return ("expression", token.value)
        if token.type in (TT.STRING, TT.NUMBER):
            if self.starts_assignment_at(idx):
                return ("assignment", str(token.raw))
            if self.starts_rule_check_at(idx, mode):
                return ("rule_check", str(token.raw))
            return ("expression", str(token.raw))
        return ("unknown", str(token.raw))

    def _looks_like_expression_slice(self, statement_slice):
        start = statement_slice.start
        end = statement_slice.end
        if start >= end:
            return False
        token = self.tokens[start]
        if not self.can_start_expression_token(token):
            return False
        if self.starts_assignment_at(start) or self.starts_rule_check_at(start, "top"):
            return False

        saw_operator = False
        idx = start
        while idx < end:
            token = self.tokens[idx]
            if token.type in (TT.EOF, TT.PREPROCESSOR, TT.RULE_COMMENT):
                break
            if token.type == TT.NEWLINE:
                idx += 1
                continue
            if token.type == TT.SYMBOL and token.value in {"}", "]"}:
                break
            if token.type == TT.SYMBOL and token.value in {"?", ":"}:
                saw_operator = True
            elif token.type == TT.SYMBOL and (
                token.value in self.config.comparison_symbols
                or token.value in self.config.arithmetic_symbols
                or token.value == "="
            ):
                saw_operator = True
            elif token.type == TT.IDENT and token.value in self.config.expression_operator_words:
                if idx != start or token.value in self.config.expression_prefix_words:
                    saw_operator = True
            idx += 1
        if saw_operator:
            return True
        if self.tokens[start].type not in (TT.IDENT, TT.NUMBER, TT.STRING):
            return False
        next_idx = self.next_non_newline_index(start + 1)
        return next_idx >= end

    def _classify_parse_kind(self, statement_slice, mode, head_kind):
        if head_kind in {"preprocessor", "property_block", "rule_check", "assignment", "directive"}:
            return head_kind
        if head_kind == "statement_head":
            return "statement_head"
        if head_kind == "expression":
            if mode in {"rule", "macro", "property"}:
                return "expression_statement"
            if mode == "top" and self._looks_like_expression_slice(statement_slice):
                return "expression_statement"
            return "unknown"
        return "unknown"

    def starts_statement_at(self, idx, mode):
        if idx >= self.length:
            return False
        token = self.tokens[idx]
        if token.type in (TT.EOF, TT.NEWLINE):
            return False
        if token.type == TT.SYMBOL and token.value in {"}", "]", ")"}:
            return False
        return self.statement_unit(idx, mode).parse_kind != "unknown"

    def looks_like_expression_statement_at(self, idx, mode):
        if idx >= self.length:
            return False
        token = self.tokens[idx]
        if token.type in (TT.EOF, TT.NEWLINE):
            return False
        return self.statement_unit(idx, mode).parse_kind == "expression_statement"

    def _leading_delimiter(self, start_idx):
        prev_idx = self.previous_non_newline_index(start_idx - 1)
        if prev_idx < 0:
            return None
        prev = self.tokens[prev_idx]
        if prev.type == TT.SYMBOL and prev.value in {"{", "[", "("}:
            return prev.value
        return None

    def _classify_head_span(self, idx, head_kind):
        token = self._token_at(idx)
        if token.type == TT.PREPROCESSOR:
            return idx + 1, (token.value,)
        if token.type == TT.SYMBOL and token.value == "[" and head_kind == "property_block":
            next_idx = self.next_non_newline_index(idx + 1)
            next_token = self._token_at(next_idx)
            if next_token.type == TT.IDENT:
                return next_idx + 1, ("[", next_token.value)
            return idx + 1, ("[",)
        if token.type != TT.IDENT:
            return idx + 1, None

        words = [token.value]
        end = idx + 1
        if head_kind in {"directive", "statement_head"}:
            next_idx = self.next_non_newline_index(end)
            while next_idx < self.length:
                next_token = self.tokens[next_idx]
                if next_token.type != TT.IDENT or next_token.value not in self.config.directive_secondary_words:
                    break
                words.append(next_token.value)
                end = next_idx + 1
                next_idx = self.next_non_newline_index(end)
        return end, tuple(words)

    def _classify_boundary(self, end_idx, mode, stop_symbols, stop_preprocessors):
        token = self._token_at(end_idx)
        if token.type == TT.EOF:
            return ("eof", None)
        if token.type == TT.PREPROCESSOR and token.value in stop_preprocessors:
            return ("stop_preprocessor", token.value)
        if token.type == TT.SYMBOL and token.value in stop_symbols:
            return ("stop_symbol", token.value)
        if token.type == TT.SYMBOL and token.value in {"}", "]", ")"}:
            return ("closing_delimiter", token.value)
        if self.starts_same_line_statement_at(end_idx, mode) or self.starts_line_statement_at(end_idx):
            value = token.value if token.type in (TT.IDENT, TT.PREPROCESSOR, TT.SYMBOL) else None
            return ("next_statement", value)
        return ("unknown", token.value if hasattr(token, "value") else None)

    def _continued_across_newline(self, statement_slice):
        for idx in range(statement_slice.start, statement_slice.end):
            token = self.tokens[idx]
            if token.type == TT.NEWLINE and self.continues_across_newline(idx):
                return True
        return False

    def statement_unit(self, start_idx, mode, stop_symbols=None, stop_preprocessors=None):
        cache_key = self._cache_key(start_idx, mode, stop_symbols, stop_preprocessors)
        cached = self._unit_cache.get(cache_key)
        if cached is not None:
            return cached
        stop_symbols = cache_key[2]
        stop_preprocessors = cache_key[3]
        statement_slice = self.statement_slice(
            start_idx,
            mode,
            stop_symbols=stop_symbols,
            stop_preprocessors=stop_preprocessors,
        )
        head_kind, head_value = self._classify_head(statement_slice.start, mode)
        parse_kind = self._classify_parse_kind(statement_slice, mode, head_kind)
        head_end, head_words = self._classify_head_span(statement_slice.start, head_kind)
        boundary_kind, boundary_value = self._classify_boundary(
            statement_slice.end,
            mode,
            stop_symbols,
            stop_preprocessors,
        )
        statement_unit = StatementUnit(
            mode=mode,
            parse_kind=parse_kind,
            start=statement_slice.start,
            end=statement_slice.end,
            head_kind=head_kind,
            head_value=head_value,
            head_end=head_end,
            head_words=head_words,
            leading_delimiter=self._leading_delimiter(statement_slice.start),
            boundary_kind=boundary_kind,
            boundary_value=boundary_value,
            continued_across_newline=self._continued_across_newline(statement_slice),
        )
        self._unit_cache[cache_key] = statement_unit
        return statement_unit

    def statement_cst_from_unit(self, statement_unit):
        head = None
        rule_check_header = None
        property_block_header = None
        if (
            statement_unit.head_kind in {"directive", "statement_head", "property_block", "preprocessor"}
            and statement_unit.head_words is not None
            and statement_unit.head_end is not None
        ):
            head = StatementHead(
                kind=statement_unit.head_kind,
                start=statement_unit.start,
                end=statement_unit.head_end,
                words=statement_unit.head_words,
            )
        if statement_unit.parse_kind == "rule_check":
            rule_check_header = self.scan_rule_check_header(statement_unit.start)
        if statement_unit.parse_kind == "property_block":
            property_block_header = self.scan_property_block_header(statement_unit.start)
        return StatementCst(
            mode=statement_unit.mode,
            parse_kind=statement_unit.parse_kind,
            start=statement_unit.start,
            end=statement_unit.end,
            head=head,
            rule_check_header=rule_check_header,
            property_block_header=property_block_header,
            leading_delimiter=statement_unit.leading_delimiter,
            boundary_kind=statement_unit.boundary_kind,
            boundary_value=statement_unit.boundary_value,
            continued_across_newline=statement_unit.continued_across_newline,
        )

    def statement_cst(self, start_idx, mode, stop_symbols=None, stop_preprocessors=None):
        cache_key = self._cache_key(start_idx, mode, stop_symbols, stop_preprocessors)
        cached = self._cst_cache.get(cache_key)
        if cached is not None:
            return cached
        statement_unit = self.statement_unit(
            start_idx,
            mode,
            stop_symbols=stop_symbols,
            stop_preprocessors=stop_preprocessors,
        )
        statement_cst = self.statement_cst_from_unit(statement_unit)
        self._cst_cache[cache_key] = statement_cst
        return statement_cst

    def next_statement_slice(self, idx, mode, stop_symbols=None, stop_preprocessors=None):
        stop_symbols = set(stop_symbols or ())
        stop_preprocessors = set(stop_preprocessors or ())
        idx = self.next_non_newline_index(idx)
        if idx >= self.length:
            return None
        token = self.tokens[idx]
        if token.type == TT.EOF:
            return None
        if token.type == TT.PREPROCESSOR and token.value in stop_preprocessors:
            return None
        if token.type == TT.SYMBOL and token.value in stop_symbols:
            return None
        return self.statement_slice(
            idx,
            mode,
            stop_symbols=stop_symbols,
            stop_preprocessors=stop_preprocessors,
        )

    def next_statement_unit(self, idx, mode, stop_symbols=None, stop_preprocessors=None):
        stop_symbols = set(stop_symbols or ())
        stop_preprocessors = set(stop_preprocessors or ())
        idx = self.next_non_newline_index(idx)
        if idx >= self.length:
            return None
        token = self.tokens[idx]
        if token.type == TT.EOF:
            return None
        if token.type == TT.PREPROCESSOR and token.value in stop_preprocessors:
            return None
        if token.type == TT.SYMBOL and token.value in stop_symbols:
            return None
        return self.statement_unit(
            idx,
            mode,
            stop_symbols=stop_symbols,
            stop_preprocessors=stop_preprocessors,
        )

    def next_statement_cst(self, idx, mode, stop_symbols=None, stop_preprocessors=None):
        statement_unit = self.next_statement_unit(
            idx,
            mode,
            stop_symbols=stop_symbols,
            stop_preprocessors=stop_preprocessors,
        )
        if statement_unit is None:
            return None
        return self.statement_cst_from_unit(statement_unit)

    def statement_clause_cst(self, start_idx, mode, stop_symbols=None, stop_preprocessors=None):
        from .cst_builder import build_statement_clause_cst

        cache_key = self._cache_key(start_idx, mode, stop_symbols, stop_preprocessors)
        cached = self._clause_cst_cache.get(cache_key)
        if cached is not None:
            return cached
        statement_cst = self.statement_cst(
            start_idx,
            mode,
            stop_symbols=stop_symbols,
            stop_preprocessors=stop_preprocessors,
        )
        if statement_cst is None:
            return None
        clause_cst = build_statement_clause_cst(self.tokens, statement_cst)
        self._clause_cst_cache[cache_key] = clause_cst
        return clause_cst

    def next_statement_clause_cst(self, idx, mode, stop_symbols=None, stop_preprocessors=None):
        from .cst_builder import build_statement_clause_cst

        statement_cst = self.next_statement_cst(
            idx,
            mode,
            stop_symbols=stop_symbols,
            stop_preprocessors=stop_preprocessors,
        )
        if statement_cst is None:
            return None
        return build_statement_clause_cst(self.tokens, statement_cst)
