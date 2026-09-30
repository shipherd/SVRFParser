"""Baseline metrics collector for SVRF parser.

Parses all candidate sample files and produces a JSON report + console summary
with per-file statistics: size, parse time, statement count, warning count,
AST node type distribution, and SVRF node ratio.
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from svrf_parser import parse_with_diagnostics
from sample_corpus import iter_sample_files
from report_privacy import ReportPrivacy
from svrf_parser.svrf_constructs import count_svrf_constructs

SAMPLES_DIR = None
REPORT_PATH = Path(__file__).parent / "baseline_report.json"

# Warning category patterns
_WARNING_CATEGORIES = {
    "parser_stuck": re.compile(r"Parser stuck"),
    "skipped_unknown": re.compile(r"Skipped unknown"),
    "unrecognized": re.compile(r"Unrecognized"),
}

_WARNING_CODE_CATEGORIES = {
    "parser.assignment.empty": "assignment_empty",
    "parser.connect.expected_also": "connect_expected_also",
    "parser.parse_error": "parse_error",
    "parser.stuck": "parser_stuck",
    "parser.unrecognized_statement": "unrecognized",
}


def walk_ast(node):
    """Yield AST nodes using the parser's canonical iterative traversal."""

    yield from node.walk()


def categorize_warnings(warnings):
    """Group warnings by category."""
    cats = {k: 0 for k in (*_WARNING_CATEGORIES, *_WARNING_CODE_CATEGORIES.values())}
    cats["parser_other"] = 0
    cats["other"] = 0
    for warning in warnings:
        code = getattr(warning, "code", "") or ""
        code_category = _WARNING_CODE_CATEGORIES.get(code)
        if code_category is not None:
            cats[code_category] += 1
            continue
        if code.startswith("parser."):
            cats["parser_other"] += 1
            continue

        text = str(warning)
        matched = False
        for cat, pat in _WARNING_CATEGORIES.items():
            if pat.search(text):
                cats[cat] += 1
                matched = True
                break
        if not matched:
            cats["other"] += 1
    return cats


def analyze_file(path, *, privacy=None):
    """Analyze a single SVRF file and return metrics dict."""
    privacy = privacy or ReportPrivacy()
    size = os.path.getsize(path)
    text = Path(path).read_text(encoding='utf-8', errors='replace')

    t0 = time.time()
    tree, warnings = parse_with_diagnostics(text, filename=str(path))
    elapsed = time.time() - t0

    n_stmts = len(tree.statements)
    svrf_count = count_svrf_constructs(tree.statements)
    ratio = svrf_count / n_stmts if n_stmts else 0

    # Node type distribution
    type_counts = Counter()
    for node in walk_ast(tree):
        type_counts[type(node).__name__] += 1

    return {
        "file": privacy.path(path),
        "size_bytes": size,
        "parse_time_s": round(elapsed, 3),
        "statements": n_stmts,
        "svrf_nodes": svrf_count,
        "svrf_ratio": round(ratio, 4),
        "total_warnings": len(warnings),
        "warning_categories": categorize_warnings(warnings),
        "node_type_distribution": dict(type_counts.most_common()),
    }


def find_sample_files():
    """Find candidate SVRF sample files from SAMPLES_DIR."""
    return [str(path) for path in iter_sample_files(SAMPLES_DIR)]


def main(argv=None):
    global SAMPLES_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Candidate file or recursive corpus directory.")
    parser.add_argument("--show-private-details", action="store_true",
                        help="Include source paths and exception text in output.")
    args = parser.parse_args(argv)
    SAMPLES_DIR = Path(args.root)
    privacy = ReportPrivacy(show_private_details=args.show_private_details)
    if not SAMPLES_DIR.exists() or not (SAMPLES_DIR.is_dir() or SAMPLES_DIR.is_file()):
        print("Sample file or directory not found at the requested location.")
        return 1

    try:
        files = find_sample_files()
    except Exception as error:
        print(f"Cannot select candidate files: {privacy.exception(error)}")
        return 1
    print(f"Found {len(files)} candidate files.\n")

    results = []
    total_warnings = 0
    total_stmts = 0

    for path in files:
        rel = privacy.path(path, root=SAMPLES_DIR)
        try:
            metrics = analyze_file(path, privacy=privacy)
            results.append(metrics)
            total_warnings += metrics["total_warnings"]
            total_stmts += metrics["statements"]
            print(f"  {rel:50s}  {metrics['statements']:5d} stmts  "
                  f"{metrics['total_warnings']:4d} warnings  "
                  f"{metrics['svrf_ratio']*100:5.1f}% SVRF  "
                  f"{metrics['parse_time_s']:.2f}s")
        except Exception as e:
            error = privacy.exception(e)
            print(f"  {rel:50s}  ERROR: {error}")
            results.append({"file": privacy.path(path), "error": error})

    # Summary
    print(f"\n{'='*70}")
    print(f"Total files:    {len(files)}")
    print(f"Total stmts:    {total_stmts}")
    print(f"Total warnings: {total_warnings}")

    # Warning category totals
    cat_totals = Counter()
    for r in results:
        if "warning_categories" in r:
            for cat, count in r["warning_categories"].items():
                cat_totals[cat] += count
    print(f"\nWarning breakdown:")
    for cat, count in cat_totals.most_common():
        print(f"  {cat:20s}: {count}")

    # Write JSON report
    report = {
        "samples_dir": str(SAMPLES_DIR) if args.show_private_details else "<redacted>",
        "source_details_redacted": not args.show_private_details,
        "total_files": len(files),
        "total_statements": total_stmts,
        "total_warnings": total_warnings,
        "warning_category_totals": dict(cat_totals),
        "files": results,
    }
    try:
        REPORT_PATH.write_text(json.dumps(report, indent=2, default=str),
                               encoding='utf-8')
    except Exception as error:
        print(f"Cannot write metrics report: {privacy.exception(error)}")
        return 1
    print("\nReport written." if not args.show_private_details else
          f"\nReport written to {REPORT_PATH}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
