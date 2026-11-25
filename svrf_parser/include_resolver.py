"""Expand INCLUDE text before parsing aggregate validation input."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import ast
from .exceptions import LexerError, ParseError
from .lexer import Lexer, encrypted_payload_end, tvf_body_span
from .include_syntax import EMBEDDED_INCLUDE_HEADS
from .parser import Parser, SVRFParseError
from .preprocessor_schema import CONDITIONAL_OPENERS, pragma_arguments
from .source_map import SourceFile, SourceMap, read_source_text
from .tokens import TokenType
from .validation_common import (
    ParsedDocument,
    expand_env_vars,
    is_pathlike_filename,
    line_snippet,
    make_diagnostic,
    with_include_stack,
)
from .diagnostics import SEVERITY_ERROR


def parse_document(text, filename, strict=False):
    if not text or not text.strip():
        return None, [
            make_diagnostic(
                SEVERITY_ERROR,
                "validation.empty_input",
                "File is empty or contains only whitespace",
                filename=filename,
            )
        ]

    try:
        lexer = Lexer(text, filename=filename)
        tokens = lexer.tokens()
    except Exception as exc:  # pragma: no cover - defensive
        return None, [
            make_diagnostic(
                SEVERITY_ERROR,
                "validation.lexer_error",
                f"Lexer error: {exc}",
                filename=filename,
                line=getattr(exc, "line", 0),
                col=getattr(exc, "col", 0),
                snippet=line_snippet(text, getattr(exc, "line", 0)),
            )
        ]

    try:
        parser = Parser(
            tokens,
            filename=filename,
            source_text=text,
            strict=strict,
        )
        program = parser.parse()
    except SVRFParseError as exc:
        return None, [
            make_diagnostic(
                SEVERITY_ERROR,
                "validation.parse_error",
                f"Parse error: {exc}",
                filename=filename,
                line=getattr(exc, "line", 0),
                col=getattr(exc, "col", 0),
                snippet=line_snippet(text, getattr(exc, "line", 0)),
            )
        ]
    except ParseError as exc:
        return None, [
            make_diagnostic(
                SEVERITY_ERROR,
                "validation.parse_error",
                f"Parse error: {exc}",
                filename=filename,
                line=getattr(exc, "line", 0),
                col=getattr(exc, "col", 0),
                snippet=line_snippet(text, getattr(exc, "line", 0)),
            )
        ]
    except Exception as exc:  # pragma: no cover - defensive
        return None, [
            make_diagnostic(
                SEVERITY_ERROR,
                "validation.unexpected_parse_error",
                f"Unexpected error during parsing: {exc}",
                filename=filename,
            )
        ]

    return (
        ParsedDocument(
            filename=filename,
            text=text,
            program=program,
            warnings=parser.warnings,
        ),
        [],
    )


def resolve_include_path(include_node, current_filename, run_directory=None, defaults=None):
    raw = (include_node.path or "").strip()
    if not raw:
        return None, []

    expanded = expand_env_vars(raw, defaults)
    if "$" in expanded:
        return None, [
            make_diagnostic(
                SEVERITY_ERROR,
                "validation.include.unresolved_variable",
                f"Could not resolve include path variable in {raw}",
                filename=current_filename,
                line=include_node.line,
                col=include_node.col,
                end_line=include_node.end_line,
                end_col=include_node.end_col,
                start_offset=include_node.start_offset,
                end_offset=include_node.end_offset,
                snippet=include_node.source_text,
            )
        ]

    base_dir = Path(run_directory) if run_directory is not None else Path.cwd()
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    try:
        resolved = candidate.resolve(strict=False)
        exists = resolved.is_file()
    except (OSError, ValueError) as exc:
        return None, [make_diagnostic(
            SEVERITY_ERROR, "validation.include.invalid_path", f"Invalid include path: {exc}",
            filename=current_filename, line=include_node.line, col=include_node.col,
            start_offset=include_node.start_offset, end_offset=include_node.end_offset,
            snippet=include_node.source_text,
        )]
    if not exists:
        return None, [
            make_diagnostic(
                SEVERITY_ERROR,
                "validation.include.missing_file",
                f"Included file not found: {resolved}",
                filename=current_filename,
                line=include_node.line,
                col=include_node.col,
                end_line=include_node.end_line,
                end_col=include_node.end_col,
                start_offset=include_node.start_offset,
                end_offset=include_node.end_offset,
                snippet=include_node.source_text,
            )
        ]
    return str(resolved), []


_LINE_START = r"(?:^|(?<=\r))[ \t]*"
_EVENT = _LINE_START + r"(?P<head>#?INCLUDE|#PRAGMA|#IFDEF_EXP|#IFN?DEF|#ELSE|#ENDIF)\b"
_FLAGS = re.IGNORECASE | re.MULTILINE | re.ASCII
_POSSIBLE_EVENT = re.compile(_EVENT, _FLAGS)
_INCLUDE_OR_PRAGMA = re.compile(_LINE_START + r"(?:#?INCLUDE|#PRAGMA)\b", _FLAGS)
_INCLUDE_LINE = re.compile(_LINE_START + r"(?P<head>#?INCLUDE)\b(?P<args>[^\r\n]*)(?:\r\n|[\r\n]|$)", _FLAGS)
_SOURCE_EVENT = re.compile(
    _EVENT + r"(?P<args>[^\r\n]*)(?:\r\n|[\r\n]|$)"
    + r"|(?P<crypt>#(?:ENCRYPT|DECRYPT))\b"
    + r"|(?P<tvf>\bTVF\b)"
    + r"""|//[^\r\n]*|@[^\r\n]*|(?P<comment>/\*[\s\S]*?(?:\*/|\Z))"""
    + r"""|"(?:[^"\\\r\n]|\\(?:\r\n|[\s\S]))*"?|'(?:[^'\\\r\n]|\\(?:\r\n|[\s\S]))*'?""",
    _FLAGS,
)


def _source_events(source, start, end, include_in_block_comments):
    text = source.text
    if not _POSSIBLE_EVENT.search(text, start, end):
        return
    while match := _SOURCE_EVENT.search(text, start, end):
        start = match.end()
        if match.group("tvf"):
            span = tvf_body_span(text, match.start(), end)
            if span:
                start = span[1] or end
        elif match.group("crypt"):
            close = min(end, encrypted_payload_end(text, start))
            if (_INCLUDE_OR_PRAGMA.search(text, start, close)
                    and Parser.parse_plaintext_payload(text[start:close], source.filename)):
                yield from _source_events(source, start, close, include_in_block_comments)
            start = close
        elif match.start("comment") >= 0 and include_in_block_comments:
            # Calibre expands standalone INCLUDE lines before removing block comments.
            for include in _INCLUDE_LINE.finditer(text, match.start(), match.end()):
                yield include, True
        elif match.group("head"):
            yield match, False
            start = match.end("head")


class _IncludeEnvironment:
    """Defaults live in expanded source order, never in the process environment."""

    def __init__(self):
        self.defaults = {}
        self.branches = []

    def observe(self, head, args):
        if head in CONDITIONAL_OPENERS:
            self.branches.append((self.defaults.copy(), None))
        elif head == "#ELSE" and self.branches:
            original, _ = self.branches[-1]
            self.branches[-1] = (original, self.defaults)
            self.defaults = original.copy()
        elif head == "#ENDIF" and self.branches:
            original, other = self.branches.pop()
            other = original if other is None else other
            self.defaults = {k: v for k, v in self.defaults.items() if other.get(k) == v}
        elif head == "#PRAGMA":
            try:
                parts = pragma_arguments(Lexer(args).tokens())
            except LexerError:
                return
            if len(parts) == 3 and parts[0].upper() in {"ENV", "DEFENV"} and "$" not in parts[2]:
                kind, name, value = parts
                actual = os.environ.get(name)
                if actual is None or (kind.upper() == "DEFENV" and not actual):
                    self.defaults[name] = value


def _is_embedded_include(source, match):
    if match.group("head").startswith("#"):
        return False
    line_no, _ = source.position(match.start())
    for index in range(line_no - 2, -1, -1):
        line = source.text[source.line_starts[index]:source.line_starts[index + 1]].strip()
        if not line or line.startswith("//"):
            continue
        try:
            tokens = [token for token in Lexer(line).tokens() if token.type != TokenType.EOF]
        except Exception:
            return False
        if not tokens:
            continue
        if len(tokens) == 2 and tokens[0].value == "VARIABLE":
            return True
        return tuple(token.value for token in tokens) in EMBEDDED_INCLUDE_HEADS
    return False


def _include_events(source, environment, include_in_block_comments, commented):
    for match, in_comment in _source_events(source, 0, len(source.text), include_in_block_comments):
        head = match.group("head").upper()
        if head not in {"INCLUDE", "#INCLUDE"}:
            if not commented:
                environment.observe(head, match.group("args"))
        elif not _is_embedded_include(source, match):
            yield match, commented or in_comment


def _include_node(source, match):
    argument = match.group("args").strip()
    if argument.startswith(('"', "'")):
        tokens = Lexer(argument).tokens()
        if len(tokens) != 2 or tokens[0].type != TokenType.STRING or not tokens[0].raw.endswith(argument[0]):
            raise ValueError("INCLUDE requires one quoted filename")
        path = tokens[0].value
    else:
        path = argument.split("//", 1)[0].strip()
        if not path or any(character.isspace() for character in path):
            raise ValueError("INCLUDE requires one filename on its own line")
    if not path:
        raise ValueError("INCLUDE path is empty")
    start = match.start("head")
    line, col = source.position(start)
    end_line, end_col = source.position(match.end())
    return ast.Include(
        path=path, preprocessor=match.group("head").startswith("#"),
        filename=source.filename, line=line, col=col, end_line=end_line, end_col=end_col,
        start_offset=start, end_offset=match.end(), source_text=match.group(),
    )


@dataclass
class IncludeExpansion:
    source_map: SourceMap
    sources: dict
    diagnostics: list


def expand_includes(text, filename, *, run_directory=None, follow_includes=True, include_in_block_comments=True):
    """Insert standalone includes iteratively, including syntax fragments."""
    run_directory = Path(run_directory).resolve() if run_directory is not None else Path.cwd()
    root = SourceFile(filename, text)
    sources = {filename: root}
    source_map = SourceMap()
    diagnostics = []
    occurrence = 0
    environment = _IncludeEnvironment()
    if follow_includes and not _INCLUDE_LINE.search(text):
        follow_includes = False

    def frame(source, include_stack, paths, commented=False):
        nonlocal occurrence
        occurrence += 1
        return {
            "source": source,
            "events": iter(_include_events(source, environment, include_in_block_comments, commented) if follow_includes else ()),
            "cursor": 0, "include_stack": include_stack, "paths": paths,
            "occurrence": occurrence,
        }

    root_paths = (Path(filename).resolve(),) if is_pathlike_filename(filename) else ()
    pending = [frame(root, (), root_paths)]
    while pending:
        current = pending[-1]
        source = current["source"]
        match, commented = next(current["events"], (None, False))
        end = match.start() if match is not None else len(source.text)
        source_map.append(
            source.text[current["cursor"]:end], source, current["cursor"],
            current["include_stack"], current["occurrence"],
        )
        if match is None:
            if len(pending) > 1 and not source.text.endswith(("\r", "\n")):
                source_map.append("\n", source, len(source.text), current["include_stack"], current["occurrence"])
            pending.pop()
            continue
        current["cursor"] = match.end()
        try:
            include = _include_node(source, match)
        except (ValueError, LexerError, ParseError) as exc:
            line, col = source.position(match.start())
            diagnostics.append(make_diagnostic(
                SEVERITY_ERROR, "validation.include.invalid_syntax", str(exc), filename=source.filename,
                line=line, col=col, start_offset=match.start(), end_offset=match.end(),
                snippet=match.group(), include_stack=current["include_stack"],
            ))
            continue
        resolved, include_diags = resolve_include_path(include, source.filename, run_directory, environment.defaults)
        diagnostics.extend(with_include_stack(diag, current["include_stack"]) for diag in include_diags)
        if not resolved:
            continue
        if Path(resolved) in current["paths"]:
            diagnostics.append(make_diagnostic(
                SEVERITY_ERROR, "validation.include.cycle", f"Include cycle detected for {resolved}",
                filename=source.filename, line=include.line, col=include.col,
                start_offset=include.start_offset, end_offset=include.end_offset,
                snippet=include.source_text, include_stack=current["include_stack"],
            ))
            continue
        child_stack = (*current["include_stack"], source.filename)
        child = sources.get(resolved)
        if child is None:
            try:
                child = SourceFile(resolved, read_source_text(resolved))
            except OSError as exc:
                diagnostics.append(make_diagnostic(
                    SEVERITY_ERROR, "validation.read_error", f"Cannot read file: {exc}",
                    filename=resolved, include_stack=child_stack,
                ))
                continue
            sources[resolved] = child
        pending.append(frame(child, child_stack, (*current["paths"], Path(resolved)), commented))
    source_map.finish()
    return IncludeExpansion(source_map, sources, diagnostics)
