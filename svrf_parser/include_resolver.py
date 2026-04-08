"""Parse documents and flatten include graphs for validation."""

from __future__ import annotations

from pathlib import Path

from . import ast
from .exceptions import ParseError
from .lexer import Lexer
from .parser import Parser, SVRFParseError
from .validation_common import (
    ParsedDocument,
    expand_env_vars,
    is_pathlike_filename,
    line_snippet,
    make_diagnostic,
    route_diagnostic,
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


def read_document(path, strict=False):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, [
            make_diagnostic(
                SEVERITY_ERROR,
                "validation.read_error",
                f"Cannot read file: {exc}",
                filename=str(path),
            )
        ]
    return parse_document(text, filename=str(path), strict=strict)


def resolve_include_path(include_node, current_filename):
    raw = (include_node.path or "").strip()
    if not raw or not is_pathlike_filename(current_filename):
        return None, []

    expanded = expand_env_vars(raw)
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

    base_dir = Path(current_filename).resolve().parent
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    resolved = candidate.resolve(strict=False)
    if not resolved.exists():
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


def flatten_with_includes(root_doc, strict=False, follow_includes=True):
    errors = []
    warnings = list(root_doc.warnings)
    parsed_cache = {}
    unique_docs = {root_doc.filename: root_doc}
    include_stacks = {root_doc.filename: ()}
    flattened = []

    initial_stack = (
        [str(Path(root_doc.filename).resolve())]
        if is_pathlike_filename(root_doc.filename)
        else [root_doc.filename]
    )
    pending = [{"doc": root_doc, "stack": initial_stack, "index": 0}]
    while pending:
        frame = pending[-1]
        doc = frame["doc"]
        statements = doc.program.statements
        if frame["index"] >= len(statements):
            pending.pop()
            continue

        stmt = statements[frame["index"]]
        frame["index"] += 1
        doc_include_stack = include_stacks.get(doc.filename, ())
        flattened.append((stmt, doc.filename))
        if not follow_includes:
            continue
        if not isinstance(stmt, ast.Include) or stmt.embedded:
            continue

        resolved_path, include_diags = resolve_include_path(stmt, doc.filename)
        for diag in include_diags:
            route_diagnostic(
                with_include_stack(diag, doc_include_stack),
                errors,
                warnings,
            )
        if not resolved_path:
            continue

        child_include_stack = (*doc_include_stack, doc.filename)
        stack = frame["stack"]
        if resolved_path in stack:
            errors.append(
                with_include_stack(
                    make_diagnostic(
                        SEVERITY_ERROR,
                        "validation.include.cycle",
                        f"Include cycle detected: {' -> '.join([*stack, resolved_path])}",
                        filename=doc.filename,
                        line=stmt.line,
                        col=stmt.col,
                        end_line=stmt.end_line,
                        end_col=stmt.end_col,
                        start_offset=stmt.start_offset,
                        end_offset=stmt.end_offset,
                        snippet=stmt.source_text,
                    ),
                    doc_include_stack,
                )
            )
            continue

        child_doc = parsed_cache.get(resolved_path)
        if child_doc is None:
            child_doc, child_errors = read_document(resolved_path, strict=strict)
            for diag in child_errors:
                route_diagnostic(
                    with_include_stack(diag, child_include_stack),
                    errors,
                    warnings,
                )
            if child_doc is None:
                continue
            parsed_cache[resolved_path] = child_doc
            unique_docs[resolved_path] = child_doc
            include_stacks.setdefault(resolved_path, child_include_stack)
        else:
            include_stacks.setdefault(resolved_path, child_include_stack)
        warnings.extend(
            with_include_stack(diag, include_stacks[resolved_path])
            for diag in child_doc.warnings
        )
        pending.append(
            {
                "doc": child_doc,
                "stack": [*stack, resolved_path],
                "index": 0,
            }
        )
    return flattened, list(unique_docs.values()), include_stacks, errors, warnings
