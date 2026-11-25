"""Audit the reference dictionary against the packaged syntax inventory."""

import argparse
import json
from collections import Counter
from pathlib import Path

from svrf_parser.command_dictionary import COMMANDS, TOPICS
from svrf_parser.svrf_spec.dictionary_source import build_dictionary, dictionary_leaves

DOCS_TOC = None
MATRIX_PATH = Path(__file__).parent / "coverage_matrix.json"


def extract_doc_constructs(toc_path):
    toc = json.loads(Path(toc_path).read_text(encoding="utf-8-sig"))
    return [n["title"] for n in dictionary_leaves(toc)]


def inventory(names):
    rows = {title: (kind, head) for title, kind, head, _, _ in TOPICS}
    counts = Counter()
    entries = []
    for name in names:
        title = " ".join(name.upper().split())
        kind, head = rows.get(title, ("unindexed", None))
        if kind == "unindexed":
            level = "unindexed"
        elif kind == "reference":
            level = "no_local_usage"
        elif head is None:
            level = "usage_without_primary"
        elif COMMANDS[head].forms is not None:
            level = "closed_keyword_contract"
        elif COMMANDS[head].min_args:
            level = "required_positional_prefix"
        else:
            level = "documented_primary"
        counts[level] += 1
        # Do not publish arbitrary titles from an unrelated/private inventory.
        entries.append({"topic": title if title in rows else None,
                        "kind": kind, "primary": head, "level": level})
    return {"dictionary_entries": len(entries), "counts": dict(sorted(counts.items())),
            "entries": entries}


def main(*, check_manual=False, write=True):
    try:
        if DOCS_TOC is None or not DOCS_TOC.is_file():
            print("toc.json not found at the requested location.")
            return 1
        matrix = inventory(extract_doc_constructs(DOCS_TOC))
        if check_manual and tuple(map(tuple, build_dictionary(DOCS_TOC.parent))) != TOPICS:
            print("The local reference and packaged command dictionary differ.")
            return 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Cannot read the requested manual inventory: {type(error).__name__}")
        return 1
    print(f"Reference dictionary entries: {matrix['dictionary_entries']}")
    for level, count in matrix["counts"].items():
        print(f"  {level}: {count}")
    print("A documented primary keyword does not imply full grammar validation.")
    if write:
        try:
            MATRIX_PATH.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
        except OSError as error:
            print(f"Cannot write coverage matrix: {type(error).__name__}")
            return 1
        print("Coverage matrix written.")
    return 0


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("toc", type=Path)
    cli.add_argument("--check-manual", action="store_true", help="Verify the index against local usage lines")
    cli.add_argument("--no-write", action="store_true", help="Print counts without writing a matrix")
    args = cli.parse_args()
    DOCS_TOC = args.toc
    raise SystemExit(main(check_manual=args.check_manual, write=not args.no_write))
