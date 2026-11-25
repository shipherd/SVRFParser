"""Source-ordered NET AREA RATIO clauses across compilation-control boundaries."""

from . import ast
from .tokens import TokenType as TT


_OPEN = {"#IFDEF", "#IFNDEF", "#IFDEF_EXP"}
_BRANCH_MARKERS = _OPEN | {"#ELSE", "#ENDIF"}
_OPTIONS = {"RDB", "ONLY", "MAG", "BY", "DETAILED", "MAXIMUM", "ACCUMULATE"}


class RatioClauseParserMixin:
    def _ratio_piece_end(self, start, allow_names):
        tokens = self.tokens
        head = tokens[start]
        if not ((head.type == TT.SYMBOL and head.value == "[")
                or (head.type == TT.IDENT and head.value in {"RDB", "ACCUMULATE", "BY", "INSIDE"})
                or (allow_names and head.type in (TT.IDENT, TT.STRING))):
            return start
        stack = []
        i = start
        while i < self.length:
            t = tokens[i]
            if t.type in (TT.EOF, TT.PREPROCESSOR, TT.RULE_COMMENT) or (not stack and t.type == TT.NEWLINE):
                break
            if t.type == TT.SYMBOL:
                if t.value in ("[", "("):
                    stack.append("]" if t.value == "[" else ")")
                elif t.value in ("]", ")"):
                    if not stack:
                        break
                    if t.value != stack.pop():
                        return start
                elif t.value in ("{", "}") or (not stack and t.value == "="):
                    break
            elif not stack and t.type == TT.IDENT:
                if self._segmenter.starts_assignment_at(i) or self._segmenter.starts_rule_check_at(i, "top"):
                    break
                prev = tokens[i-1].value if i > start and tokens[i-1].type == TT.IDENT else None
                option = (t.value in _OPTIONS or (t.value == "INSIDE" and i+2 < self.length
                          and tokens[i+1].value == "OF" and tokens[i+2].value == "LAYER")
                          or (t.value == "OF" and prev == "INSIDE") or (t.value == "NET" and prev == "BY")
                          or (t.value == "LAYER" and prev in {"BY", "OF"}))
                if not option and (t.value in {"NET", "INSIDE", "DVPARAMS"} or self._segmenter.starts_line_statement_at(i)
                                   or self._segmenter.starts_operation_at(i)):
                    break
                if not option and t.value in self._segmenter.config.expression_operator_words:
                    return start
            i += 1
        return start if stack else i

    def _is_ratio_conditional(self, start, allow_names):
        # Probe without emitting diagnostics or consuming an unrelated conditional.
        depth = 0
        seen = False
        i = start
        while i < self.length:
            t = self.tokens[i]
            if t.type == TT.PREPROCESSOR and t.value in _BRANCH_MARKERS:
                if t.value in _OPEN:
                    depth += 1
                elif t.value == "#ENDIF":
                    depth -= 1
                    if not depth:
                        return seen
                while self.tokens[i].type not in (TT.NEWLINE, TT.EOF):
                    i += 1
            else:
                end = self._ratio_piece_end(i, allow_names)
                if end == i:
                    return False
                seen = True
                i = end
            i = self._next_non_newline_index(i)
        return False

    def _parse_ratio_piece(self, end):
        start = self.pos
        self.pos = end
        return self._operation_clause(start, end)

    def _attach_ratio_tail(self, op):
        i = self._next_non_newline_index(self.pos)
        if self.tokens[i].type != TT.PREPROCESSOR or self.tokens[i].value not in _OPEN:
            return
        allow_names = any(isinstance(m, str) and m in {"RDB", "ACCUMULATE"} for m in op.modifiers)
        attached = False
        while True:
            i = self._next_non_newline_index(self.pos)
            t = self.tokens[i]
            if t.type == TT.PREPROCESSOR and t.value in _OPEN:
                if not self._is_ratio_conditional(i, allow_names):
                    break
                self.pos = i
                clause = self._finish_node(self._parse_ifdef("ratio_clause"), i)
            else:
                end = self._ratio_piece_end(i, allow_names)
                if end == i:
                    break
                self.pos = i
                clause = self._parse_ratio_piece(end)
                allow_names |= any(tok.value in {"ACCUMULATE", "RDB"} for tok in self.tokens[i:end])
            op.modifiers.append(clause)
            attached = True
        if attached:
            last = op.modifiers[-1]
            op.set_span(op.line, op.col, last.end_line, last.end_col, op.start_offset, last.end_offset,
                        self._slice(op.start_offset, last.end_offset))
