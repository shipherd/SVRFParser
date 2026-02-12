"""Test harness for SVRF parser - parses all sample files and reports results."""

import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from svrf_parser import parse_file_with_diagnostics, parse_file
from svrf_parser.ast_nodes import *

SAMPLES_DIR = None

def _get_samples_dir():
    global SAMPLES_DIR
    if SAMPLES_DIR:
        return SAMPLES_DIR
    if len(sys.argv) > 1:
        SAMPLES_DIR = sys.argv[1]
        return SAMPLES_DIR
    print("Usage: python test_samples.py <samples_dir> [single_file]")
    sys.exit(1)

# SVRF-characteristic AST node types
_SVRF_NODE_TYPES = (
    LayerDef, LayerMap, LayerAssignment,
    Directive, RuleCheckBlock,
    Connect, Device, DMacro,
    Define, IfDef, Include, EncryptedBlock,
    Group, Attach, TraceProperty,
    VariableDef,
)


def find_sample_files(root):
    """Walk samples directory and collect all files."""
    if not os.path.isdir(root):
        print(f"No samples directory found at {root}")
        return []
    files = []
    for dirpath, _, filenames in os.walk(root):
        for fn in sorted(filenames):
            files.append(os.path.join(dirpath, fn))
    return files


def run_tests():
    samples_dir = _get_samples_dir()
    files = find_sample_files(samples_dir)

    if not files:
        print("No sample files found.")
        return

    total = len(files)
    passed = 0
    failed = 0
    results = []

    print(f"Found {total} sample files.\n")
    print("-" * 80)

    for path in files:
        rel = os.path.relpath(path, samples_dir)
        size = os.path.getsize(path)
        size_str = f"{size / 1024:.1f}KB" if size < 1024 * 1024 else \
                   f"{size / (1024 * 1024):.1f}MB"
        t0 = 0
        try:
            t0 = time.time()
            tree, warnings = parse_file_with_diagnostics(path)
            elapsed = time.time() - t0
            n_stmts = len(tree.statements) if tree else 0
            n_warnings = len(warnings)

            # Calculate SVRF node ratio
            svrf_count = sum(
                1 for s in tree.statements if isinstance(s, _SVRF_NODE_TYPES)
            ) if tree else 0
            ratio = svrf_count / n_stmts * 100 if n_stmts else 0

            print(f"  PASS  {rel} ({size_str}, {n_stmts} stmts, "
                  f"{n_warnings} warnings, {ratio:.0f}% SVRF, {elapsed:.2f}s)")
            passed += 1
            results.append(('PASS', rel, None))
        except Exception as e:
            elapsed = time.time() - t0 if 't0' in dir() else 0
            err_msg = str(e)
            if len(err_msg) > 120:
                err_msg = err_msg[:120] + "..."
            print(f"  FAIL  {rel} ({size_str})")
            print(f"        Error: {err_msg}")
            failed += 1
            results.append(('FAIL', rel, err_msg))

    print("-" * 80)
    print(f"\nSummary: {passed}/{total} passed, {failed} failed\n")

    if failed:
        print("Failed files:")
        for status, rel, err in results:
            if status == 'FAIL':
                print(f"  {rel}: {err}")
        return 1
    return 0

def single_run(fn):
    tree = parse_file(fn)
    for stm in tree.statements:
        if isinstance(stm, LayerAssignment):
            print(f"{stm.name}")
if __name__ == '__main__':
    if len(sys.argv) > 2:
        sys.exit(single_run(sys.argv[2]))
    else:
        sys.exit(run_tests())
