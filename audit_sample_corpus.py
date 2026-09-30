"""Audit an SVRF sample corpus and bucket residual diagnostics."""

from __future__ import annotations

import argparse
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


from svrf_parser import validate_svrf_file
from svrf_parser.diagnostic_postprocess import undefined_symbol_name
from sample_corpus import iter_sample_files
from report_privacy import ReportPrivacy
from svrf_parser.unresolved_policy import load_symbol_manifest


@dataclass(frozen=True, slots=True)
class FileAuditSummary:
    path: Path
    valid: bool
    error_count: int
    warning_count: int
    category_counts: dict[str, int]
    undefined_symbol_counts: dict[str, int]
    dialects: tuple[str, ...]
    feature_families: tuple[str, ...]
    limited_support_features: tuple[str, ...]
    profile_tags: tuple[str, ...]
    unresolved_policy: str
    raw_unresolved_count: int
    deduped_unresolved_count: int
    manifest_resolved_count: int
    remaining_unresolved_count: int


def classify_diagnostic(diagnostic):
    code = diagnostic.code or ""
    if code.startswith("parser.") or code in {
        "validation.lexer_error",
        "validation.parse_error",
        "validation.unexpected_parse_error",
    }:
        return "parser_related"
    if code.startswith("validation.include.") or code == "validation.read_error":
        return "sample_setup_issue"
    if code == "validation.encrypted_blocks.possible_hidden_definitions":
        return "encrypted_hidden_definition"
    if code in {"validation.support.limited_feature", "validation.support.opaque_content"}:
        return "limited_support_feature"
    if code in {
        "validation.no_statements",
        "validation.no_svrf_constructs",
        "validation.low_svrf_ratio",
    }:
        return "unsupported_or_non_svrf"
    if code == "semantic.reference.companion_candidate":
        return "semantic_companion_symbol"
    if code == "semantic.reference.external_candidate":
        return "semantic_external_symbol"
    if code in {"semantic.reference.undefined", "semantic.varref.undefined"}:
        return "semantic_unresolved_symbol"
    if code == "semantic.reference.scalar_undefined":
        return "semantic_scalar_symbol"
    if code == "semantic.reference.local_scope_only":
        return "semantic_local_scope_symbol"
    if code in {"semantic.reference.conditional", "semantic.reference.unavailable_branch"}:
        return "semantic_conditional_symbol"
    if code.startswith("semantic."):
        return "semantic_rule_issue"
    if code.startswith("validation."):
        return "validation_issue"
    return "other"


def extract_undefined_symbol_name(diagnostic):
    return undefined_symbol_name(diagnostic)


def audit_validation_result(path, result):
    category_counts = Counter()
    undefined_symbol_counts = Counter()
    policy_summary = getattr(result, "policy_summary", None)
    for diagnostic in [*result.errors, *result.warnings]:
        category_counts[classify_diagnostic(diagnostic)] += 1
        name = extract_undefined_symbol_name(diagnostic)
        if name:
            undefined_symbol_counts[name] += 1
    return FileAuditSummary(
        path=Path(path),
        valid=result.valid,
        error_count=len(result.errors),
        warning_count=len(result.warnings),
        category_counts=dict(category_counts),
        undefined_symbol_counts=dict(undefined_symbol_counts),
        dialects=tuple(getattr(result, "dialects", ()) or ()),
        feature_families=tuple(getattr(result, "feature_families", ()) or ()),
        limited_support_features=tuple(getattr(result, "limited_support_features", ()) or ()),
        profile_tags=tuple(getattr(result, "profile_tags", ()) or ()),
        unresolved_policy=getattr(policy_summary, "policy", "strict"),
        raw_unresolved_count=int(getattr(policy_summary, "raw_unresolved_count", 0) or 0),
        deduped_unresolved_count=int(getattr(policy_summary, "deduped_unresolved_count", 0) or 0),
        manifest_resolved_count=int(getattr(policy_summary, "manifest_resolved_count", 0) or 0),
        remaining_unresolved_count=int(getattr(policy_summary, "remaining_unresolved_count", 0) or 0),
    )


def audit_path(path, *, unresolved_policy="strict", symbol_manifest=None, run_directory=None):
    return audit_validation_result(
        path,
        validate_svrf_file(
            path,
            strict=False,
            unresolved_policy=unresolved_policy,
            symbol_manifest=symbol_manifest,
            run_directory=run_directory,
        ),
    )


def audit_corpus(root, *, unresolved_policy="strict", symbol_manifest=None, run_directory=None):
    files = list(iter_sample_files(Path(root)))
    return [
        audit_path(
            path,
            unresolved_policy=unresolved_policy,
            symbol_manifest=symbol_manifest,
            run_directory=run_directory,
        )
        for path in files
    ]


def _format_counter(counter_dict, *, top=None):
    items = sorted(counter_dict.items(), key=lambda item: (-item[1], item[0]))
    if top is not None:
        items = items[:top]
    return ", ".join(f"{key}={value}" for key, value in items) if items else "none"


def has_audit_failures(summaries):
    return any((not summary.valid) or summary.error_count for summary in summaries)


def _print_summary(summaries, *, top_symbols=10, include_files=True, privacy=None):
    privacy = privacy or ReportPrivacy()
    total_files = len(summaries)
    valid_files = sum(1 for summary in summaries if summary.valid)
    total_errors = sum(summary.error_count for summary in summaries)
    total_warnings = sum(summary.warning_count for summary in summaries)

    overall_categories = Counter()
    overall_symbols = Counter()
    overall_dialects = Counter()
    overall_families = Counter()
    overall_limited = Counter()
    overall_tags = Counter()
    raw_unresolved_total = 0
    deduped_unresolved_total = 0
    manifest_resolved_total = 0
    remaining_unresolved_total = 0
    for summary in summaries:
        overall_categories.update(summary.category_counts)
        overall_symbols.update(summary.undefined_symbol_counts)
        overall_dialects.update(summary.dialects)
        overall_families.update(summary.feature_families)
        overall_limited.update(summary.limited_support_features)
        overall_tags.update(summary.profile_tags)
        raw_unresolved_total += summary.raw_unresolved_count
        deduped_unresolved_total += summary.deduped_unresolved_count
        manifest_resolved_total += summary.manifest_resolved_count
        remaining_unresolved_total += summary.remaining_unresolved_count

    print(f"files={total_files} valid={valid_files}/{total_files} errors={total_errors} warnings={total_warnings}")
    print(f"categories: {_format_counter(dict(overall_categories))}")
    print(
        "unresolved policy: "
        f"{summaries[0].unresolved_policy if summaries else 'strict'} "
        f"(raw={raw_unresolved_total}, deduped={deduped_unresolved_total}, "
        f"manifest_resolved={manifest_resolved_total}, remaining={remaining_unresolved_total})"
    )
    print(f"dialects: {_format_counter(dict(overall_dialects))}")
    print(f"feature families: {_format_counter(dict(overall_families), top=top_symbols)}")
    print(f"profile tags: {_format_counter(dict(overall_tags), top=top_symbols)}")
    print(f"limited-support features: {_format_counter(dict(overall_limited), top=top_symbols)}")
    if overall_symbols:
        print(f"top unresolved symbols: {_format_counter(privacy.symbol_counts(overall_symbols), top=top_symbols)}")
    else:
        print("top unresolved symbols: none")
    print()

    if not include_files:
        return

    for summary in summaries:
        print(privacy.path(summary.path))
        print(
            f"  valid={summary.valid} errors={summary.error_count} warnings={summary.warning_count}"
        )
        print(f"  categories: {_format_counter(summary.category_counts)}")
        print(
            "  unresolved policy: "
            f"{summary.unresolved_policy} "
            f"(raw={summary.raw_unresolved_count}, deduped={summary.deduped_unresolved_count}, "
            f"manifest_resolved={summary.manifest_resolved_count}, remaining={summary.remaining_unresolved_count})"
        )
        print(f"  dialects: {_format_counter({dialect: 1 for dialect in summary.dialects})}")
        print(f"  families: {_format_counter({family: 1 for family in summary.feature_families}, top=top_symbols)}")
        print(
            f"  limited support: {_format_counter({name: 1 for name in summary.limited_support_features}, top=top_symbols)}"
        )
        if summary.undefined_symbol_counts:
            print(
                f"  top unresolved: {_format_counter(privacy.symbol_counts(summary.undefined_symbol_counts), top=top_symbols)}"
            )
        else:
            print("  top unresolved: none")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        default=os.environ.get("SVRF_SAMPLES_DIR", ""),
        help="Sample corpus directory or file. Defaults to SVRF_SAMPLES_DIR.",
    )
    parser.add_argument(
        "--top-symbols",
        type=int,
        default=10,
        help="How many unresolved symbols to show per summary.",
    )
    parser.add_argument(
        "--unresolved-policy",
        choices=("strict", "practical"),
        default="strict",
        help="Unresolved-symbol reporting policy.",
    )
    parser.add_argument(
        "--symbol-manifest",
        default="",
        help="Optional JSON manifest of known external/scalar symbols.",
    )
    parser.add_argument(
        "--run-directory",
        help="Resolve all relative INCLUDE paths from this directory (default: current directory).",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print only the corpus-level summary.",
    )
    parser.add_argument(
        "--fail-on-errors",
        action="store_true",
        help="Exit with status 1 if any audited file is invalid or has errors.",
    )
    parser.add_argument(
        "--show-private-details",
        action="store_true",
        help="Include source paths, symbol names, and exception text in output.",
    )
    args = parser.parse_args(argv)
    privacy = ReportPrivacy(show_private_details=args.show_private_details)

    if not args.root:
        raise SystemExit("Sample root not provided and SVRF_SAMPLES_DIR is not set.")

    root = Path(args.root)
    if not root.exists() or not (root.is_dir() or root.is_file()):
        raise SystemExit("Sample root does not exist or is not a file/directory.")

    try:
        symbol_manifest = load_symbol_manifest(args.symbol_manifest) if args.symbol_manifest else None
        summaries = audit_corpus(
            root,
            unresolved_policy=args.unresolved_policy,
            symbol_manifest=symbol_manifest,
            run_directory=args.run_directory,
        )
    except Exception as error:
        raise SystemExit(f"Cannot audit the requested input: {privacy.exception(error)}") from None
    if not summaries:
        raise SystemExit("No candidate files found at the requested location.")
    _print_summary(
        summaries,
        top_symbols=max(args.top_symbols, 1),
        include_files=not args.summary_only,
        privacy=privacy,
    )
    return 1 if args.fail_on_errors and has_audit_failures(summaries) else 0


if __name__ == "__main__":
    raise SystemExit(main())
