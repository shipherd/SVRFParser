"""Baseline metrics collector for SVRF parser.

Parses all sample files and produces a JSON report + console summary
with per-file statistics: size, parse time, statement count, warning count,
AST node type distribution, and SVRF node ratio.
"""

import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from svrf_parser import parse_with_diagnostics
from svrf_parser.ast_nodes import *

SAMPLES_DIR = Path(r"C:\Users\Boshe\Desktop\tmp\svrf_samples")
REPORT_PATH = Path(__file__).parent / "baseline_report.json"

_SVRF_NODE_TYPES = (
    LayerDef, LayerMap, LayerAssignment,
    Directive, RuleCheckBlock,
    Connect, Device, DMacro,
    Define, IfDef, Include, EncryptedBlock,
    Group, Attach, TraceProperty,
    VariableDef,
)

# Warning category patterns
_WARNING_CATEGORIES = {
    "parser_stuck": re.compile(r"Parser stuck"),
    "skipped_unknown": re.compile(r"Skipped unknown"),
    "unrecognized": re.compile(r"Unrecognized"),
}


def walk_ast(node):
    """Depth-first traversal of all AST nodes."""
    yield node
    if isinstance(node, Program):
        for s in node.statements:
            yield from walk_ast(s)
    elif isinstance(node, (IfDef,)):
        for s in node.then_body:
            yield from walk_ast(s)
        for s in node.else_body:
            yield from walk_ast(s)
    elif isinstance(node, RuleCheckBlock):
        for s in node.body:
            yield from walk_ast(s)
        if node.description:
            yield from walk_ast(node.description)
    elif isinstance(node, DMacro):
        for s in node.body:
            yield from walk_ast(s)
    elif isinstance(node, PropertyBlock):
        for s in node.body:
            yield from walk_ast(s)
    elif isinstance(node, IfExpr):
        if node.condition:
            yield from walk_ast(node.condition)
        for s in node.then_body:
            yield from walk_ast(s)
        for cond, body in node.elseifs:
            yield from walk_ast(cond)
            for s in body:
                yield from walk_ast(s)
        for s in node.else_body:
            yield from walk_ast(s)
    elif isinstance(node, BinaryOp):
        if node.left:
            yield from walk_ast(node.left)
        if node.right:
            yield from walk_ast(node.right)
    elif isinstance(node, UnaryOp):
        if node.operand:
            yield from walk_ast(node.operand)
    elif isinstance(node, ConstrainedExpr):
        if node.expr:
            yield from walk_ast(node.expr)
        for c in node.constraints:
            yield from walk_ast(c)
    elif isinstance(node, DRCOp):
        for o in node.operands:
            if isinstance(o, AstNode):
                yield from walk_ast(o)
        for c in node.constraints:
            yield from walk_ast(c)
    elif isinstance(node, LayerAssignment):
        if node.expression:
            yield from walk_ast(node.expression)
    elif isinstance(node, FuncCall):
        for a in node.args:
            if isinstance(a, AstNode):
                yield from walk_ast(a)
    elif isinstance(node, Directive):
        if node.property_block:
            yield from walk_ast(node.property_block)
    elif isinstance(node, VariableDef):
        if node.expr:
            yield from walk_ast(node.expr)


def categorize_warnings(warnings):
    """Group warnings by category."""
    cats = {k: [] for k in _WARNING_CATEGORIES}
    cats["other"] = []
    for w in warnings:
        matched = False
        for cat, pat in _WARNING_CATEGORIES.items():
            if pat.search(w):
                cats[cat].append(w)
                matched = True
                break
        if not matched:
            cats["other"].append(w)
    return {k: len(v) for k, v in cats.items()}


def analyze_file(path):
    """Analyze a single SVRF file and return metrics dict."""
    size = os.path.getsize(path)
    text = Path(path).read_text(encoding='utf-8', errors='replace')

    t0 = time.time()
    tree, warnings = parse_with_diagnostics(text, filename=str(path))
    elapsed = time.time() - t0

    n_stmts = len(tree.statements)
    svrf_count = sum(
        1 for s in tree.statements if isinstance(s, _SVRF_NODE_TYPES)
    )
    ratio = svrf_count / n_stmts if n_stmts else 0

    # Node type distribution
    type_counts = Counter()
    for node in walk_ast(tree):
        type_counts[type(node).__name__] += 1

    return {
        "file": str(path),
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
    """Find all sample files under SAMPLES_DIR."""
    files = []
    for dirpath, _, filenames in os.walk(SAMPLES_DIR):
        for fn in sorted(filenames):
            files.append(os.path.join(dirpath, fn))
    return files


def main():
    if not SAMPLES_DIR.is_dir():
        print(f"Samples directory not found: {SAMPLES_DIR}")
        return 1

    files = find_sample_files()
    print(f"Found {len(files)} sample files in {SAMPLES_DIR}\n")

    results = []
    total_warnings = 0
    total_stmts = 0

    for path in files:
        rel = os.path.relpath(path, SAMPLES_DIR)
        try:
            metrics = analyze_file(path)
            results.append(metrics)
            total_warnings += metrics["total_warnings"]
            total_stmts += metrics["statements"]
            print(f"  {rel:50s}  {metrics['statements']:5d} stmts  "
                  f"{metrics['total_warnings']:4d} warnings  "
                  f"{metrics['svrf_ratio']*100:5.1f}% SVRF  "
                  f"{metrics['parse_time_s']:.2f}s")
        except Exception as e:
            print(f"  {rel:50s}  ERROR: {e}")
            results.append({"file": str(path), "error": str(e)})

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
        "samples_dir": str(SAMPLES_DIR),
        "total_files": len(files),
        "total_statements": total_stmts,
        "total_warnings": total_warnings,
        "warning_category_totals": dict(cat_totals),
        "files": results,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str),
                           encoding='utf-8')
    print(f"\nReport written to {REPORT_PATH}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
