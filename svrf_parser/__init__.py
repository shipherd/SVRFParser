"""SVRFParser - public package facade."""

from __future__ import annotations

from . import ast
from .lexer import Lexer
from .parser import Parser
from .validation_common import ValidationResult
from .validation_pipeline import (
    is_valid_svrf,
    is_valid_svrf_file,
    validate_svrf,
    validate_svrf_file,
)
from .visitor import AstVisitor


def parse(text, filename="<input>", strict=False):
    """Parse SVRF source text and return an AST Program node."""
    lexer = Lexer(text, filename=filename)
    parser = Parser(
        lexer.tokens(),
        filename=filename,
        source_text=text,
        strict=strict,
    )
    return parser.parse()


def parse_with_diagnostics(text, filename="<input>", strict=False):
    """Parse SVRF source text and return ``(Program, warnings)``."""
    lexer = Lexer(text, filename=filename)
    parser = Parser(
        lexer.tokens(),
        filename=filename,
        source_text=text,
        strict=strict,
    )
    tree = parser.parse()
    return tree, parser.warnings


def parse_file(path, strict=False):
    """Parse an SVRF file and return an AST Program node."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return parse(text, filename=str(path), strict=strict)


def parse_file_with_diagnostics(path, strict=False):
    """Parse an SVRF file and return ``(Program, warnings)``."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return parse_with_diagnostics(text, filename=str(path), strict=strict)


__all__ = [
    "AstVisitor",
    "ValidationResult",
    "ast",
    "is_valid_svrf",
    "is_valid_svrf_file",
    "parse",
    "parse_file",
    "parse_file_with_diagnostics",
    "parse_with_diagnostics",
    "validate_svrf",
    "validate_svrf_file",
]
