"""Shared syntax for includes used as filename or cell-list references."""

EMBEDDED_INCLUDE_HEADS = frozenset({
    ("DRC", "RESULTS", "DATABASE"), ("DRC", "SUMMARY", "REPORT"),
    ("LAYOUT", "PATH"), ("LAYOUT", "PRIMARY"), ("SOURCE", "PATH"), ("SOURCE", "PRIMARY"),
})
