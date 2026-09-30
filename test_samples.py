"""Test harness for SVRF parser - parses candidate SVRF files and reports results."""

import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from svrf_parser import parse_file_with_diagnostics
from sample_corpus import iter_sample_files
from report_privacy import ReportPrivacy
from svrf_parser.svrf_constructs import count_svrf_constructs

SAMPLES_DIR = None


def _usage():
    print("Usage: python test_samples.py <samples_dir_or_file> [single_file] "
          "[--fail-on-warnings] [--show-private-details]")


def _parse_cli_args(argv):
    fail_on_warnings = False
    show_private_details = False
    positional = []
    for arg in argv:
        if arg == "--fail-on-warnings":
            fail_on_warnings = True
        elif arg == "--show-private-details":
            show_private_details = True
        elif arg.startswith("--"):
            raise SystemExit("Unknown option.")
        else:
            positional.append(arg)

    if not positional:
        _usage()
        raise SystemExit(1)

    samples_dir = positional[0]
    single_file = positional[1] if len(positional) > 1 else None
    return samples_dir, single_file, fail_on_warnings, show_private_details


def _get_samples_dir():
    global SAMPLES_DIR
    if SAMPLES_DIR:
        return SAMPLES_DIR
    if len(sys.argv) > 1:
        SAMPLES_DIR = sys.argv[1]
        return SAMPLES_DIR
    _usage()
    sys.exit(1)


def _resolve_target(root, single_file=None):
    if not single_file:
        return Path(root)
    single_path = Path(single_file)
    if single_path.is_absolute():
        return single_path
    rooted = Path(root) / single_path
    return rooted if rooted.exists() else single_path


def find_sample_files(root):
    """Collect candidate SVRF files from a directory or direct file path."""
    root_path = Path(root)
    if root_path.is_file():
        return [str(root_path)]
    if not root_path.is_dir():
        print("No sample file or directory found at the requested location.")
        return []
    return [str(path) for path in iter_sample_files(root_path)]


def run_tests(samples_dir=None, *, fail_on_warnings=False, show_private_details=False):
    samples_dir = samples_dir or _get_samples_dir()
    privacy = ReportPrivacy(show_private_details=show_private_details)
    try:
        files = find_sample_files(samples_dir)
    except Exception as error:
        print(f"Cannot select candidate files: {privacy.exception(error)}")
        return 1

    if not files:
        print("No candidate files found.")
        return 1

    total = len(files)
    passed = 0
    failed = 0
    results = []

    print(f"Found {total} candidate files.\n")
    print("-" * 80)

    for path in files:
        rel = privacy.path(path, root=samples_dir)
        size_str = "size unknown"
        try:
            size = os.path.getsize(path)
            size_str = f"{size / 1024:.1f}KB" if size < 1024 * 1024 else \
                       f"{size / (1024 * 1024):.1f}MB"
            t0 = time.time()
            tree, warnings = parse_file_with_diagnostics(path)
            elapsed = time.time() - t0
            n_stmts = len(tree.statements) if tree else 0
            n_warnings = len(warnings)

            # Calculate SVRF node ratio
            svrf_count = count_svrf_constructs(tree.statements) if tree else 0
            ratio = svrf_count / n_stmts * 100 if n_stmts else 0

            warning_failure = fail_on_warnings and n_warnings
            status = "FAIL" if warning_failure else "PASS"
            print(f"  {status}  {rel} ({size_str}, {n_stmts} stmts, "
                  f"{n_warnings} warnings, {ratio:.0f}% SVRF, {elapsed:.2f}s)")
            if warning_failure:
                print(f"        Parser warnings: {n_warnings}")
                for warning in warnings[:3]:
                    print(f"        {privacy.diagnostic(warning)}")
                failed += 1
                results.append(('FAIL', rel, f"{n_warnings} parser warnings"))
                continue
            passed += 1
            results.append(('PASS', rel, None))
        except Exception as e:
            err_msg = privacy.exception(e)
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


if __name__ == '__main__':
    samples_dir, single_file, fail_on_warnings, show_private_details = _parse_cli_args(sys.argv[1:])
    SAMPLES_DIR = str(_resolve_target(samples_dir, single_file))
    sys.exit(run_tests(SAMPLES_DIR, fail_on_warnings=fail_on_warnings,
                       show_private_details=show_private_details))
