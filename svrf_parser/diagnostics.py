"""Structured diagnostics for lexer, parser, and semantic validation."""

from __future__ import annotations

from dataclasses import dataclass, replace


SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Structured diagnostic record with stable string rendering."""

    severity: str
    code: str
    message: str
    filename: str = "<input>"
    line: int = 0
    col: int = 0
    end_line: int = 0
    end_col: int = 0
    start_offset: int = 0
    end_offset: int = 0
    snippet: str | None = None
    include_stack: tuple[str, ...] = ()
    metadata: dict | None = None

    @property
    def is_error(self):
        return self.severity == SEVERITY_ERROR

    @property
    def is_warning(self):
        return self.severity == SEVERITY_WARNING

    @property
    def has_location(self):
        return self.line > 0 and self.col > 0

    def to_dict(self, *, redact_source=False):
        """Serialize with optional removal of source-derived text and metadata."""
        return {
            "severity": self.severity,
            "code": self.code,
            "message": "<redacted>" if redact_source else self.message,
            "filename": "<redacted>" if redact_source else self.filename,
            "line": self.line,
            "col": self.col,
            "end_line": self.end_line,
            "end_col": self.end_col,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "snippet": None if redact_source else self.snippet,
            "include_stack": () if redact_source else self.include_stack,
            "metadata": {} if redact_source else self.metadata or {},
        }

    def with_include_stack(self, include_stack):
        include_stack = tuple(include_stack or ())
        if include_stack == self.include_stack:
            return self
        return replace(self, include_stack=include_stack)

    def __str__(self):
        if self.has_location:
            text = f"L{self.line}:{self.col}: {self.message}"
        else:
            text = self.message
        if self.include_stack:
            return f"{text} [via {' -> '.join(self.include_stack)}]"
        return text
