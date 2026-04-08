"""Public validation pipeline detached from the package facade."""

from __future__ import annotations

from pathlib import Path

from .diagnostics import SEVERITY_ERROR
from .diagnostic_postprocess import (
    apply_unresolved_symbol_policy,
    reclassify_unresolved_reference_diagnostics,
    warn_encrypted_blocks_may_define_symbols,
    warn_limited_support_features,
)
from .include_resolver import flatten_with_includes, parse_document
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
    is_pathlike_filename,
    make_diagnostic,
    read_error_result,
    route_diagnostic,
    with_include_stack,
)


_MIN_SVRF_NODE_RATIO = 0.2


def validate_svrf(
    text,
    filename="<input>",
    strict=False,
    follow_includes=True,
    unresolved_policy="strict",
    symbol_manifest=None,
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

    root_doc, parse_errors = parse_document(text, filename=filename, strict=strict)
    if root_doc is None:
        return ValidationResult(
            False,
            parse_errors,
            policy_summary=unresolved_policy_summary(
                unresolved_policy,
                manifest_source=getattr(symbol_manifest, "source", None),
            ),
        )

    flattened, documents, include_stacks, errors, warnings = flatten_with_includes(
        root_doc,
        strict=strict,
        follow_includes=follow_includes and is_pathlike_filename(filename),
    )

    symbol_pass = run_symbol_table_pass(
        flattened,
        filename=filename,
        strict=strict,
    )
    for diag in symbol_pass.diagnostics:
        route_diagnostic(
            with_include_stack(diag, include_stacks.get(diag.filename, ())),
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
    for doc in documents:
        semantic_pass = run_semantic_validation_pass(
            doc.program,
            filename=doc.filename,
            strict=strict,
            symbol_table=symbol_pass.symbol_table,
        )
        semantic_diags = reclassify_unresolved_reference_diagnostics(
            doc,
            list(semantic_pass.diagnostics),
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
        for diagnostic in semantic_diags:
            route_diagnostic(
                with_include_stack(
                    diagnostic,
                    include_stacks.get(doc.filename, ()),
                ),
                errors,
                warnings,
            )
        warn_encrypted_blocks_may_define_symbols(
            doc,
            semantic_diags,
            warnings,
            include_stack=include_stacks.get(doc.filename, ()),
        )
        warn_limited_support_features(
            doc,
            warnings,
            include_stack=include_stacks.get(doc.filename, ()),
        )

    program = root_doc.program
    profile = build_validation_profile(documents)
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
):
    """Return ``True`` if *text* is a valid SVRF file, ``False`` otherwise."""

    return validate_svrf(
        text,
        filename=filename,
        strict=strict,
        follow_includes=follow_includes,
        unresolved_policy=unresolved_policy,
        symbol_manifest=symbol_manifest,
    ).valid


def is_valid_svrf_file(
    path,
    strict=False,
    follow_includes=True,
    unresolved_policy="strict",
    symbol_manifest=None,
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
    )


def validate_svrf_file(
    path,
    strict=False,
    follow_includes=True,
    unresolved_policy="strict",
    symbol_manifest=None,
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
    )
