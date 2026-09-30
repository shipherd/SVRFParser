"""Source provenance for text assembled from INCLUDE files."""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field, replace

from . import ast
from .lexer import Lexer
from .tokens import TokenType


def _line_starts(text):
    return [0, *(match.end() for match in re.finditer(r"\r\n|\r|\n", text))]


@dataclass
class SourceFile:
    filename: str
    text: str
    line_starts: list = field(init=False)

    def __post_init__(self):
        self.line_starts = _line_starts(self.text)

    def position(self, offset):
        offset = min(max(0, offset), len(self.text))
        line_index = bisect_right(self.line_starts, offset) - 1
        return line_index + 1, offset - self.line_starts[line_index] + 1


@dataclass(frozen=True)
class SourceSegment:
    start: int
    end: int
    source: SourceFile
    source_start: int
    include_stack: tuple
    occurrence: int


class SourceMap:
    def __init__(self):
        self.segments = []
        self._starts = []
        self._pieces = []
        self._length = 0
        self.text = ""
        self._line_starts = [0]

    def append(self, text, source, source_start, include_stack, occurrence):
        if not text:
            return
        self.segments.append(SourceSegment(
            self._length, self._length + len(text), source,
            source_start, include_stack, occurrence,
        ))
        self._starts.append(self._length)
        self._pieces.append(text)
        self._length += len(text)

    def finish(self):
        self.text = "".join(self._pieces)
        self._pieces.clear()
        self._line_starts = _line_starts(self.text)

    def _locate(self, offset, *, endpoint=False):
        probe = offset - 1 if endpoint and offset > 0 else offset
        index = max(0, bisect_right(self._starts, probe) - 1)
        segment = self.segments[index]
        local_offset = segment.source_start + min(max(0, offset - segment.start), segment.end - segment.start)
        return segment, min(local_offset, len(segment.source.text))

    def _span(self, start, end):
        segment, source_start = self._locate(start)
        if end <= start:
            last_segment, source_end = segment, source_start
        else:
            last_segment, source_end = self._locate(end, endpoint=True)
        if segment.occurrence != last_segment.occurrence:
            source_end = len(segment.source.text)
        source_end = max(source_start, source_end)
        line, col = segment.source.position(source_start)
        end_line, end_col = segment.source.position(source_end)
        return {
            "filename": segment.source.filename,
            "line": line, "col": col, "end_line": end_line, "end_col": end_col,
            "start_offset": source_start, "end_offset": source_end,
            "include_stack": segment.include_stack,
            "snippet": segment.source.text[source_start:source_end],
        }

    def diagnostic(self, diagnostic):
        if not self.segments or diagnostic.line <= 0:
            return diagnostic
        start = diagnostic.start_offset
        end = diagnostic.end_offset
        if start == 0 and (diagnostic.line, diagnostic.col) != (1, 1):
            index = min(diagnostic.line - 1, len(self._line_starts) - 1)
            start = self._line_starts[index] + max(0, diagnostic.col - 1)
            end = max(start, end)
        span = self._span(start, end)
        if not span["snippet"]:
            segment, offset = self._locate(start)
            if offset < len(segment.source.text):
                span["snippet"] = segment.source.text.splitlines()[span["line"] - 1]
        return replace(diagnostic, **span)

    def remap_program(self, program, root_source):
        for node in program.walk():
            if node is program or not node.line or not self.segments:
                continue
            span = self._span(node.start_offset, node.end_offset)
            node.filename = span.pop("filename")
            node.include_stack = span.pop("include_stack")
            source_text = span.pop("snippet")
            node.set_span(**span, source_text=source_text)
            if isinstance(node, ast.EncryptedBlock):
                # Keep the original payload while its body reflects textual includes.
                tokens = Lexer(source_text, filename=node.filename).tokens()
                payload = next((token for token in tokens if token.type == TokenType.ENCRYPTED), None)
                if payload is not None:
                    node.content = payload.value
        end_line, end_col = root_source.position(len(root_source.text))
        program.set_span(1, 1, end_line, end_col, 0, len(root_source.text), root_source.text)
        program.filename = root_source.filename
