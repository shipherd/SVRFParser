"""Public validation pipeline detached from the package facade."""

from __future__ import annotations

from pathlib import Path

from .diagnostics import SEVERITY_ERROR
from .diagnostic_postprocess import (
    apply_unresolved_symbol_policy,
    reclassify_unresolved_reference_diagnostics,
    summarize_conditional_references,
    warn_encrypted_blocks_may_define_symbols,
    warn_limited_support_features,
)
from .include_resolver import expand_includes, parse_document
from .semantic_passes import (
    build_validation_profile,
    run_semantic_validation_pass,
    run_symbol_table_pass,
)
from .svrf_constructs import count_svrf_constructs
from .unresolved_policy import (
    is_manifest_suppressible_code,
    load_symbol_manifest,
    new_policy_summary,
    normalize_unresolved_policy,
    unresolved_policy_summary,
)
from .validation_common import (
    ValidationResult,
    ParsedDocument,
    is_pathlike_filename,
    make_diagnostic,
    read_error_result,
    route_diagnostic,
)


_MIN_SVRF_NODE_RATIO = 0.2


def validate_svrf(
    text,
    filename="<input>",
    strict=False,
    follow_includes=True,
    unresolved_policy="strict",
    symbol_manifest=None,
    run_directory=None,
):
    """Validate whether *text* is a valid SVRF file."""

    try:
        unresolved_policy = normalize_unresolved_policy(unresolved_policy)
        symbol_manifest = load_symbol_manifest(symbol_manifest)
    except Exception as exc:
        return ValidationResult(
            False,
            [
                make_diagnostic(
                    SEVERITY_ERROR,
                    "validation.policy.invalid_manifest",
                    f"Invalid unresolved-symbol policy or manifest: {exc}",
                    filename=filename,
                )
            ],
            policy_summary=unresolved_policy_summary("strict"),
        )

    expansion = expand_includes(
        text or "", filename, run_directory=run_directory,
        follow_includes=follow_includes and (is_pathlike_filename(filename) or run_directory is not None),
    )
    source_map = expansion.source_map
    root_doc, parse_errors = parse_document(source_map.text, filename=filename, strict=strict)
    if root_doc is None:
        return ValidationResult(
            False,
            [*expansion.diagnostics, *(source_map.diagnostic(diag) for diag in parse_errors)],
            policy_summary=unresolved_policy_summary(
                unresolved_policy,
                manifest_source=getattr(symbol_manifest, "source", None),
            ),
        )

    warnings = [source_map.diagnostic(diag) for diag in root_doc.warnings]
    errors = list(expansion.diagnostics)
    source_map.remap_program(root_doc.program, expansion.sources[filename])
    documents = [ParsedDocument(source.filename, source.text, root_doc.program, [])
                 for source in expansion.sources.values()]

    symbol_pass = run_symbol_table_pass(
        root_doc.program.statements,
        filename=filename,
        strict=strict,
    )
    for diag in symbol_pass.diagnostics:
        route_diagnostic(
            diag,
            errors,
            warnings,
        )

    known_doc_paths = frozenset(
        str(Path(doc.filename).resolve())
        for doc in documents
        if is_pathlike_filename(doc.filename)
    )
    companion_file_cache = {}
    companion_pattern_cache = {}
    policy_summary = new_policy_summary(
        unresolved_policy,
        manifest_source=getattr(symbol_manifest, "source", None),
    )
    semantic_pass = run_semantic_validation_pass(
        root_doc.program, filename=filename, strict=strict,
        symbol_table=symbol_pass.symbol_table,
    )
    for doc in documents:
        semantic_diags = reclassify_unresolved_reference_diagnostics(
            doc,
            [diag for diag in semantic_pass.diagnostics if diag.filename == doc.filename],
            known_doc_paths,
            file_cache=companion_file_cache,
            pattern_cache=companion_pattern_cache,
        )
        semantic_diags = apply_unresolved_symbol_policy(
            semantic_diags,
            strict=strict,
            unresolved_policy=unresolved_policy,
            symbol_manifest=symbol_manifest,
            policy_summary=policy_summary,
            is_manifest_suppressible_code=is_manifest_suppressible_code,
        )
        if not strict and unresolved_policy == "practical":
            semantic_diags = summarize_conditional_references(semantic_diags)
        for diagnostic in semantic_diags:
            route_diagnostic(
                diagnostic,
                errors,
                warnings,
            )
        warn_encrypted_blocks_may_define_symbols(
            doc,
            semantic_diags,
            warnings,
        )
    warn_limited_support_features(root_doc, warnings)

    program = root_doc.program
    profile = build_validation_profile([root_doc])
    if not program.statements:
        errors.append(
            make_diagnostic(
                SEVERITY_ERROR,
                "validation.no_statements",
                "Parsed file contains no statements",
                filename=filename,
                snippet=text[:200],
            )
        )
        return ValidationResult(
            False,
            errors,
            warnings,
            program=program,
            profile=profile,
            policy_summary=policy_summary.freeze(),
        )

    total = len(program.statements)
    svrf_count = count_svrf_constructs(program.statements)

    if svrf_count == 0:
        errors.append(
            make_diagnostic(
                SEVERITY_ERROR,
                "validation.no_svrf_constructs",
                "Parsed file contains no recognizable SVRF constructs "
                "(e.g. LAYER, directive, rule check, CONNECT, DEVICE)",
                filename=filename,
                snippet=text[:200],
            )
        )
    else:
        ratio = svrf_count / total
        if ratio < _MIN_SVRF_NODE_RATIO:
            errors.append(
                make_diagnostic(
                    SEVERITY_ERROR,
                    "validation.low_svrf_ratio",
                    f"Only {svrf_count}/{total} ({ratio:.0%}) of top-level statements "
                    f"are SVRF constructs (need >= {_MIN_SVRF_NODE_RATIO:.0%})",
                    filename=filename,
                )
            )

    return ValidationResult(
        not errors,
        errors=errors,
        warnings=warnings,
        program=program,
        profile=profile,
        policy_summary=policy_summary.freeze(),
    )


def is_valid_svrf(
    text,
    filename="<input>",
    strict=False,
    follow_includes=True,
    unresolved_policy="strict",
    symbol_manifest=None,
    run_directory=None,
):
    """Return ``True`` if *text* is a valid SVRF file, ``False`` otherwise."""

    return validate_svrf(
        text,
        filename=filename,
        strict=strict,
        follow_includes=follow_includes,
        unresolved_policy=unresolved_policy,
        symbol_manifest=symbol_manifest,
        run_directory=run_directory,
    ).valid


def is_valid_svrf_file(
    path,
    strict=False,
    follow_includes=True,
    unresolved_policy="strict",
    symbol_manifest=None,
    run_directory=None,
):
    """Return ``True`` if the file at *path* is a valid SVRF file."""

    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return is_valid_svrf(
        text,
        filename=str(path),
        strict=strict,
        follow_includes=follow_includes,
        unresolved_policy=unresolved_policy,
        symbol_manifest=symbol_manifest,
        run_directory=run_directory,
    )


def validate_svrf_file(
    path,
    strict=False,
    follow_includes=True,
    unresolved_policy="strict",
    symbol_manifest=None,
    run_directory=None,
):
    """Validate the file at *path* and return a ``ValidationResult``."""

    path = Path(path)
    try:
        normalized_policy = normalize_unresolved_policy(unresolved_policy)
        symbol_manifest = load_symbol_manifest(symbol_manifest)
    except Exception as exc:
        return ValidationResult(
            False,
            [
                make_diagnostic(
                    SEVERITY_ERROR,
                    "validation.policy.invalid_manifest",
                    f"Invalid unresolved-symbol policy or manifest: {exc}",
                    filename=str(path),
                )
            ],
            policy_summary=unresolved_policy_summary("strict"),
        )
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return read_error_result(
            path,
            exc,
            policy=normalized_policy,
        )
    return validate_svrf(
        text,
        filename=str(path),
        strict=strict,
        follow_includes=follow_includes,
        unresolved_policy=normalized_policy,
        symbol_manifest=symbol_manifest,
        run_directory=run_directory,
    )
