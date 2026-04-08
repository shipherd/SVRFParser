"""Diagnostic reclassification and policy helpers for validation."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from . import ast
from .diagnostics import SEVERITY_WARNING
from .feature_spec import iter_limited_support_matches
from .unresolved_policy import is_unresolved_symbol_code
from .validation_common import (
    is_pathlike_filename,
    make_diagnostic,
    with_include_stack,
)

_UNDEFINED_SYMBOL_CODES = frozenset(
    {
        "semantic.reference.undefined",
        "semantic.reference.companion_candidate",
        "semantic.reference.external_candidate",
        "semantic.reference.scalar_undefined",
        "semantic.reference.local_scope_only",
        "semantic.varref.undefined",
    }
)


def first_encrypted_block(program, *, opaque_only=False):
    if program is None:
        return None
    for node in program.walk():
        if isinstance(node, ast.EncryptedBlock) and (
            not opaque_only or getattr(node, "parse_status", "opaque") == "opaque"
        ):
            return node
    return None


def undefined_symbol_name(diagnostic):
    if diagnostic.code not in _UNDEFINED_SYMBOL_CODES:
        return None
    metadata = getattr(diagnostic, "metadata", None) or {}
    symbol = metadata.get("symbol")
    if symbol:
        return str(symbol)
    if diagnostic.code in {
        "semantic.reference.undefined",
        "semantic.reference.companion_candidate",
        "semantic.reference.external_candidate",
        "semantic.reference.scalar_undefined",
        "semantic.reference.local_scope_only",
    }:
        prefixes = (
            "Unknown layer or variable reference ",
            "Unresolved scalar parameter-like identifier ",
            "Reference ",
        )
        for prefix in prefixes:
            if diagnostic.message.startswith(prefix):
                tail = diagnostic.message[len(prefix) :]
                return tail.split(" ", 1)[0]
        return None
    if diagnostic.code == "semantic.varref.undefined":
        prefix = "Description variable reference ^"
        suffix = " has no matching VARIABLE"
        if diagnostic.message.startswith(prefix) and diagnostic.message.endswith(suffix):
            return diagnostic.message[len(prefix) : -len(suffix)]
    return None


def _external_context_preview():
    from .symbol_convention import SYMBOL_CONVENTION_REGISTRY

    contexts = tuple(
        value.replace("_", " ")
        for value in SYMBOL_CONVENTION_REGISTRY.external_unresolved_contexts
        if value != "companion_deck"
    )
    return ", ".join(contexts)


def _companion_symbol_pattern(name, pattern_cache):
    pattern = pattern_cache.get(name)
    if pattern is None:
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])",
            re.IGNORECASE,
        )
        pattern_cache[name] = pattern
    return pattern


def _candidate_companion_files(filename, known_doc_paths, file_cache):
    current_path = str(Path(filename).resolve())
    cached = file_cache.get(current_path)
    if cached is not None:
        return cached

    path = Path(current_path)
    candidates = []
    try:
        siblings = sorted(path.parent.iterdir())
    except OSError:
        siblings = ()
    for sibling in siblings:
        if not sibling.is_file():
            continue
        try:
            resolved = str(sibling.resolve())
        except OSError:
            continue
        if resolved == current_path or resolved in known_doc_paths:
            continue
        try:
            text = sibling.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        candidates.append((resolved, text))
    file_cache[current_path] = tuple(candidates)
    return file_cache[current_path]


def _find_companion_symbol_hits(filename, name, known_doc_paths, file_cache, pattern_cache):
    if not is_pathlike_filename(filename):
        return ()
    pattern = _companion_symbol_pattern(name, pattern_cache)
    hits = []
    for candidate_path, candidate_text in _candidate_companion_files(
        filename,
        known_doc_paths,
        file_cache,
    ):
        if pattern.search(candidate_text):
            hits.append(candidate_path)
    return tuple(hits)


def reclassify_unresolved_reference_diagnostics(
    doc,
    diagnostics,
    known_doc_paths,
    *,
    file_cache,
    pattern_cache,
):
    if not is_pathlike_filename(doc.filename):
        return diagnostics

    rewritten = []
    external_contexts = _external_context_preview()
    for diagnostic in diagnostics:
        if diagnostic.code != "semantic.reference.undefined":
            rewritten.append(diagnostic)
            continue
        name = undefined_symbol_name(diagnostic)
        if not name:
            rewritten.append(diagnostic)
            continue
        hits = _find_companion_symbol_hits(
            doc.filename,
            name,
            known_doc_paths,
            file_cache,
            pattern_cache,
        )
        if hits:
            preview = ", ".join(Path(path).name for path in hits[:3])
            if len(hits) > 3:
                preview = f"{preview}, ..."
            rewritten.append(
                replace(
                    diagnostic,
                    code="semantic.reference.companion_candidate",
                    message=(
                        f"Reference {name} has no visible plaintext definition in this file "
                        f"but appears in sibling companion SVRF files ({preview})"
                    ),
                )
            )
            continue
        rewritten.append(
            replace(
                diagnostic,
                code="semantic.reference.external_candidate",
                message=(
                    f"Reference {name} has no visible plaintext definition in this file or sibling "
                    f"companion decks; it may come from {external_contexts}"
                ),
            )
        )
    return rewritten


def warn_encrypted_blocks_may_define_symbols(doc, diagnostics, warnings, include_stack=()):
    encrypted = first_encrypted_block(doc.program, opaque_only=True)
    if encrypted is None:
        return

    names = []
    seen = set()
    for diagnostic in diagnostics:
        name = undefined_symbol_name(diagnostic)
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)

    if not names:
        return

    preview = ", ".join(names[:5])
    if len(names) > 5:
        preview = f"{preview}, ..."
    warnings.append(
        with_include_stack(
            make_diagnostic(
                SEVERITY_WARNING,
                "validation.encrypted_blocks.possible_hidden_definitions",
                "This file contains encrypted SVRF blocks; some unresolved symbols may be defined there"
                f" ({preview})",
                filename=doc.filename,
                line=encrypted.line,
                col=encrypted.col,
                end_line=encrypted.end_line,
                end_col=encrypted.end_col,
                start_offset=encrypted.start_offset,
                end_offset=encrypted.end_offset,
                snippet=encrypted.source_text,
            ),
            include_stack,
        )
    )


def warn_limited_support_features(doc, warnings, include_stack=()):
    for match in iter_limited_support_matches(doc.program):
        notice = match.notice
        node = match.node
        warnings.append(
            with_include_stack(
                make_diagnostic(
                    SEVERITY_WARNING,
                    notice.warning_code,
                    notice.message,
                    filename=doc.filename,
                    line=node.line,
                    col=node.col,
                    end_line=node.end_line,
                    end_col=node.end_col,
                    start_offset=node.start_offset,
                    end_offset=node.end_offset,
                    snippet=node.source_text,
                ),
                include_stack,
            )
        )


def unresolved_diagnostic_key(diagnostic):
    name = undefined_symbol_name(diagnostic)
    if not name:
        return None
    return (diagnostic.filename, name.upper(), diagnostic.code)


def apply_unresolved_symbol_policy(
    diagnostics,
    *,
    strict,
    unresolved_policy,
    symbol_manifest,
    policy_summary,
    is_manifest_suppressible_code,
):
    unresolved = [diag for diag in diagnostics if is_unresolved_symbol_code(diag.code)]
    policy_summary.raw_unresolved_count += len(unresolved)
    if strict or unresolved_policy == "strict":
        policy_summary.deduped_unresolved_count += len(unresolved)
        policy_summary.remaining_unresolved_count += len(unresolved)
        return diagnostics

    kept = []
    seen = set()
    deduped_unresolved = 0
    remaining_unresolved = 0
    manifest_resolved = 0
    for diagnostic in diagnostics:
        if not is_unresolved_symbol_code(diagnostic.code):
            kept.append(diagnostic)
            continue
        key = unresolved_diagnostic_key(diagnostic)
        if key is not None and key in seen:
            continue
        if key is not None:
            seen.add(key)
        deduped_unresolved += 1
        name = undefined_symbol_name(diagnostic)
        if (
            name
            and symbol_manifest is not None
            and is_manifest_suppressible_code(diagnostic.code)
            and symbol_manifest.resolves_symbol(diagnostic.filename, name)
        ):
            manifest_resolved += 1
            policy_summary.manifest_resolved_symbols.add(name.upper())
            continue
        remaining_unresolved += 1
        kept.append(diagnostic)
    policy_summary.deduped_unresolved_count += deduped_unresolved
    policy_summary.manifest_resolved_count += manifest_resolved
    policy_summary.remaining_unresolved_count += remaining_unresolved
    return kept
