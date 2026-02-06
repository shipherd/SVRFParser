"""Test harness for SVRF parser - parses all sample files and reports results."""

import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from svrf_parser import parse_file


def find_sample_files(root):
    """Walk samples/ directory and collect all files."""
    samples_dir = os.path.join(root, 'samples')
    if not os.path.isdir(samples_dir):
        print(f"No samples/ directory found at {samples_dir}")
        return []
    files = []
    for dirpath, _, filenames in os.walk(samples_dir):
        for fn in sorted(filenames):
            files.append(os.path.join(dirpath, fn))
    return files


def run_tests():
    root = os.path.dirname(os.path.abspath(__file__))
    files = find_sample_files(root)

    if not files:
        print("No sample files found.")
        return

    total = len(files)
    passed = 0
    failed = 0
    results = []

    print(f"Found {total} sample files.\n")
    print("-" * 70)

    for path in files:
        rel = os.path.relpath(path, root)
        size = os.path.getsize(path)
        size_str = f"{size / 1024:.1f}KB" if size < 1024 * 1024 else \
                   f"{size / (1024 * 1024):.1f}MB"

        try:
            t0 = time.time()
            tree = parse_file(path)
            elapsed = time.time() - t0
            n_stmts = len(tree.statements) if tree else 0
            print(f"  PASS  {rel} ({size_str}, {n_stmts} stmts, "
                  f"{elapsed:.2f}s)")
            passed += 1
            results.append(('PASS', rel, None))
        except Exception as e:
            elapsed = time.time() - t0 if 't0' in dir() else 0
            err_msg = str(e)
            # Truncate long error messages
            if len(err_msg) > 120:
                err_msg = err_msg[:120] + "..."
            print(f"  FAIL  {rel} ({size_str})")
            print(f"        Error: {err_msg}")
            failed += 1
            results.append(('FAIL', rel, err_msg))

    print("-" * 70)
    print(f"\nSummary: {passed}/{total} passed, {failed} failed\n")

    if failed:
        print("Failed files:")
        for status, rel, err in results:
            if status == 'FAIL':
                print(f"  {rel}: {err}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(run_tests())
