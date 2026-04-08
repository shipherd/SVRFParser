"""Build clause-level CST from pre-classified statement spans."""

from __future__ import annotations

from .clause_cst import (
    DelimitedGroupClause,
    KeywordRunClause,
    ModifierClause,
    OpaqueEmbeddedLanguageChunk,
    OperandClause,
    ScalarClause,
    StatementClauseCst,
)
from .statement_cst import StatementCst
from .tokens import TokenType

TT = TokenType

_OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}"}
_SCALAR_SYMBOLS = frozenset({"+", "-", "*", "/", "%", "?", ":", ",", "."})
_GENERIC_MODIFIER_STARTERS = frozenset(
    {
        "BY",
        "CMACRO",
        "ELEMENT",
        "GOOD",
        "LAYER",
        "MASK",
        "NETLIST",
        "OPPOSITE",
        "PIN",
        "PORT",
        "PROPERTY",
        "WITH",
    }
)
_PARSE_KIND_MODIFIER_STARTERS = {
    "connect": frozenset({"BY", "LINK", "ABUT"}),
    "sconnect": frozenset({"BY", "LINK", "ABUT"}),
    "device": frozenset({"CMACRO", "ELEMENT", "LAYER", "NETLIST", "PIN", "PORT", "PROPERTY"}),
    "trace_property": frozenset({"PROPERTY"}),
}


class ClauseCstBuilder:
    def __init__(self, tokens):
        self.tokens = tokens
        self.length = len(tokens)

    def build(self, statement_cst: StatementCst) -> StatementClauseCst:
        header_clauses = list(self._build_header_clauses(statement_cst))
        body_start = self._body_start(statement_cst)
        body_end = self._body_end(statement_cst, body_start)

        parse_kind = self._parse_kind(statement_cst)
        if parse_kind in {"rule_check", "property_block"}:
            body_clauses = self._build_block_body_clauses(
                parse_kind,
                body_start,
                body_end,
            )
        else:
            body_clauses = tuple(
                self._build_clause_list(
                    body_start,
                    body_end,
                    modifier_starters=self._modifier_starters(statement_cst),
                )
            )

        return StatementClauseCst(
            statement=statement_cst,
            header_clauses=tuple(header_clauses),
            body_clauses=tuple(body_clauses),
        )

    def _build_header_clauses(self, statement_cst):
        if statement_cst.head is not None:
            yield KeywordRunClause(
                start=statement_cst.head.start,
                end=statement_cst.head.end,
                words=statement_cst.head.words,
            )
        if statement_cst.rule_check_header is not None:
            yield OperandClause(
                start=statement_cst.start,
                end=statement_cst.rule_check_header.body_start,
                values=(statement_cst.rule_check_header.name,),
            )
        if statement_cst.property_block_header is not None:
            for name in statement_cst.property_block_header.properties:
                yield OperandClause(
                    start=statement_cst.start,
                    end=statement_cst.property_block_header.body_start,
                    values=(name,),
                )

    def _body_start(self, statement_cst):
        if statement_cst.rule_check_header is not None:
            return statement_cst.rule_check_header.body_start
        if statement_cst.property_block_header is not None:
            return statement_cst.property_block_header.body_start
        return statement_cst.body_start

    def _body_end(self, statement_cst, body_start):
        parse_kind = self._parse_kind(statement_cst)
        end = self._prev_non_newline_index(statement_cst.end - 1)
        if end < body_start:
            return body_start
        token = self.tokens[end]
        if (
            parse_kind in {"rule_check", "property_block"}
            and token.type == TT.SYMBOL
            and token.value in {"}", "]"}
        ):
            return end
        if parse_kind == "device":
            return self._extend_device_tail(statement_cst.end)
        return statement_cst.end

    def _extend_device_tail(self, end):
        idx = self._next_non_newline_index(end)
        if idx >= self.length:
            return end
        token = self.tokens[idx]
        if token.type not in {TT.IDENT, TT.PREPROCESSOR}:
            return end
        if token.value not in {"CMACRO", "ELEMENT", "LAYER", "NETLIST", "PIN", "PORT", "PROPERTY"}:
            return end
        line = token.line
        while idx < self.length:
            token = self.tokens[idx]
            if token.type in {TT.EOF, TT.NEWLINE}:
                break
            if token.line != line:
                break
            idx += 1
        return idx

    def _build_block_body_clauses(self, parse_kind, body_start, body_end):
        delimiter = "{" if parse_kind == "rule_check" else "["
        closing = _OPEN_TO_CLOSE[delimiter]
        inner = tuple(self._build_clause_list(body_start, body_end, modifier_starters=frozenset()))
        if not inner:
            return ()
        return (
            DelimitedGroupClause(
                start=body_start,
                end=body_end,
                open_symbol=delimiter,
                close_symbol=closing,
                clauses=inner,
            ),
        )

    def _modifier_starters(self, statement_cst):
        starters = set(_GENERIC_MODIFIER_STARTERS)
        head_value = statement_cst.head_value or ""
        starters.update(_PARSE_KIND_MODIFIER_STARTERS.get(self._parse_kind(statement_cst), ()))
        if head_value == "GROUP":
            return frozenset()
        if head_value in {"CMACRO", "FMACRO"}:
            return frozenset()
        return frozenset(starters)

    def _parse_kind(self, statement_cst):
        return StatementClauseCst(statement_cst, (), ()).parse_kind

    def _build_clause_list(self, start, end, modifier_starters):
        clauses = []
        idx = self._next_non_newline_index(start)
        while idx < end:
            token = self.tokens[idx]
            if token.type == TT.NEWLINE:
                idx += 1
                continue
            if token.type in {TT.RULE_COMMENT, TT.ENCRYPTED}:
                clauses.append(
                    OpaqueEmbeddedLanguageChunk(
                        start=idx,
                        end=idx + 1,
                        values=(token.value,),
                        reason="embedded" if token.type == TT.ENCRYPTED else "comment",
                    )
                )
                idx += 1
                continue
            if token.type == TT.SYMBOL and token.value in _OPEN_TO_CLOSE:
                clause, idx = self._build_delimited_group(idx, end)
                clauses.append(clause)
                continue
            if token.type in {TT.NUMBER, TT.STRING}:
                clause, idx = self._build_scalar_clause(idx, end)
                clauses.append(clause)
                continue
            clause, idx = self._build_run_clause(idx, end, modifier_starters)
            clauses.append(clause)
        return tuple(clauses)

    def _build_delimited_group(self, start, end):
        open_token = self.tokens[start]
        close_symbol = _OPEN_TO_CLOSE.get(open_token.value)
        idx = start + 1
        depth = 1
        while idx < end:
            token = self.tokens[idx]
            if token.type == TT.SYMBOL:
                if token.value == open_token.value:
                    depth += 1
                elif token.value == close_symbol:
                    depth -= 1
                    if depth == 0:
                        inner = tuple(self._build_clause_list(start + 1, idx, modifier_starters=frozenset()))
                        return (
                            DelimitedGroupClause(
                                start=start,
                                end=idx + 1,
                                open_symbol=open_token.value,
                                close_symbol=close_symbol,
                                clauses=inner,
                            ),
                            idx + 1,
                        )
            idx += 1
        inner = tuple(self._build_clause_list(start + 1, end, modifier_starters=frozenset()))
        return (
            DelimitedGroupClause(
                start=start,
                end=end,
                open_symbol=open_token.value,
                close_symbol=None,
                clauses=inner,
            ),
            end,
        )

    def _build_scalar_clause(self, start, end):
        values = []
        idx = start
        while idx < end:
            token = self.tokens[idx]
            if token.type == TT.NEWLINE:
                idx += 1
                continue
            if token.type in {TT.NUMBER, TT.STRING}:
                values.append(token.value)
                idx += 1
                continue
            if token.type == TT.SYMBOL and token.value in _SCALAR_SYMBOLS:
                values.append(token.value)
                idx += 1
                continue
            break
        return ScalarClause(start=start, end=idx, values=tuple(values)), idx

    def _build_run_clause(self, start, end, modifier_starters):
        values = []
        idx = start
        first_token = self.tokens[start]
        is_modifier = first_token.type in {TT.IDENT, TT.PREPROCESSOR} and first_token.value in modifier_starters
        while idx < end:
            token = self.tokens[idx]
            if token.type == TT.NEWLINE:
                idx += 1
                continue
            if token.type in {TT.RULE_COMMENT, TT.ENCRYPTED}:
                break
            if token.type == TT.SYMBOL and token.value in _OPEN_TO_CLOSE:
                break
            if token.type in {TT.NUMBER, TT.STRING}:
                if values:
                    break
                return self._build_scalar_clause(idx, end)
            if (
                values
                and token.type in {TT.IDENT, TT.PREPROCESSOR}
                and token.value in modifier_starters
            ):
                break
            values.append(token.value)
            idx += 1
        clause_type = ModifierClause if is_modifier else OperandClause
        return clause_type(start=start, end=idx, values=tuple(values)), idx

    def _next_non_newline_index(self, idx):
        while idx < self.length and self.tokens[idx].type == TT.NEWLINE:
            idx += 1
        return idx

    def _prev_non_newline_index(self, idx):
        while idx >= 0 and self.tokens[idx].type == TT.NEWLINE:
            idx -= 1
        return idx


def build_statement_clause_cst(tokens, statement_cst):
    return ClauseCstBuilder(tokens).build(statement_cst)
