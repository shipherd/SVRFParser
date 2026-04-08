"""Shared sample-corpus file selection helpers for project tooling."""

from __future__ import annotations

from pathlib import Path


# Kept for compatibility with older callers. An empty set means corpus
# selection is intentionally not suffix-limited.
SUPPORTED_SAMPLE_SUFFIXES = frozenset()


def is_supported_sample_file(path):
    """Return True for any candidate file path.

    Real SVRF corpora use many extension schemes, including technology-specific
    suffixes. The parser harness therefore treats every regular file selected
    from a corpus root as a potential SVRF file and lets the parser/validator
    decide whether the content is meaningful.
    """

    return True


def iter_sample_files(root):
    """Yield candidate SVRF files for *root* in stable order.

    If *root* is a file, yield that file directly. If *root* is a directory,
    yield every regular file under it recursively, without filtering by suffix.
    """

    if isinstance(root, (str, bytes)):
        root = Path(root)
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and is_supported_sample_file(path):
            yield path
