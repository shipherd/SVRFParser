"""Manual-backed data extractors used for packaged SVRF spec generation."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .manual_overrides import (
    APPROVED_KEYWORD_ALIASES,
    CASE_SENSITIVITY_RULES,
    DOC_ALL_EXTRA_FUNCTION_NAMES,
    DOC_DFM_EXTRA_FUNCTION_NAMES,
    FUNCTION_LIKE_EXTRA_NAMES,
    MANUAL_EXCEPTION_ENTRIES,
    SUPPORT_MATRIX_ENTRIES,
    SYMBOL_CONVENTION_ENTRIES,
)


TOC_FILE = "toc.json"
TOPICS_FILE = "topics.json"

MIXED_CASE_PATTERN = re.compile(r"\b([A-Z]{2,}[a-z][A-Za-z]*)\b")
PREFIX_PATTERN = re.compile(r"[A-Z]+")

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_:]*$")
RETURN_VALUE_TITLE_PATTERN = re.compile(r"^(?:RETURN VALUES OF\s+)?([A-Za-z_][A-Za-z0-9_:]*)\s+RETURN VALUES?\b")
FUNCTION_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9_:]*)\s*\(")
XREF_NAME_PATTERN = re.compile(r'rel="[^"]+">([^<]+)</a>')

STRING_XREF_NAME_PATTERN = re.compile(r'rel="[^"]+">([A-Z][A-Z0-9_]+)</a>')
TITLE_PATTERN = re.compile(r'<h1 class="title topictitle1">([^<]+)</h1>')
MATH_FUNCTION_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9_]*)\s*\(")

FUNCTION_ROOT_PATTERNS = (
    re.compile(r"\bFUNCTION SUMMARY\b"),
    re.compile(r"\bFUNCTION REFERENCE\b"),
    re.compile(r"\bRETURN VALUES?\b"),
    re.compile(r"\bNUMERIC EXPRESSIONS\b"),
    re.compile(r"\bPERIMETER FUNCTIONS\b"),
    re.compile(r"\bTRIGONOMETRIC FUNCTIONS\b"),
    re.compile(r"\bHYPERBOLIC FUNCTIONS\b"),
    re.compile(r"\bROUNDING AND REMAINDER FUNCTIONS\b"),
    re.compile(r"\bSIGN, MAX, MIN FUNCTIONS\b"),
    re.compile(r"\bEXPONENTIAL AND LOGARITHMIC FUNCTIONS\b"),
    re.compile(r"\bBESSEL FUNCTIONS\b"),
    re.compile(r"\bERROR AND PROBABILITY FUNCTIONS\b"),
    re.compile(r"\bMEASUREMENT FUNCTIONS\b"),
    re.compile(r"\bBUILT-IN LANGUAGE FUNCTIONS\b"),
    re.compile(r"\bBUILT-IN FUNCTIONS\b"),
    re.compile(r"\bNUMERIC FUNCTIONS FOR BUILT-IN LANGUAGES\b"),
)

EXCLUDED_ROOT_PATTERNS = (
    re.compile(r"\bSUPPORT\b"),
    re.compile(r"\bEXAMPLE\b"),
    re.compile(r"\bEXAMPLES\b"),
    re.compile(r"\bRESULTS\b"),
    re.compile(r"\bIMPORT\b"),
    re.compile(r"\bCALL\b"),
    re.compile(r"\bRUNTIME\b"),
    re.compile(r"\bTVF\b"),
    re.compile(r"\bFUNCTIONALITY\b"),
)

NON_FUNCTION_IDENTIFIERS = {
    "ACCUMULATE",
    "EXAMPLES",
    "FORMAT",
    "PERIM",
    "SUM::FAILARG",
    "VARIABLE",
}

DEFAULT_MATH_RELATIVE_PAGES = (
    Path(r"luj1752242843309\id4e0e1792-abef-43fa-ae13-7061e19c8827.html"),
    Path(r"tsg1752242865753\id7c9c3927-fe30-43b0-ba09-c4caa4cbc19a.html"),
)

DEFAULT_STRING_SUMMARY_PAGE = Path(r"tsg1752242865753\id7b7971d8-4f58-41c5-b079-de95534e261e.html")
DEFAULT_STRING_REFERENCE_PAGES = (
    Path(r"hri1752242863124\id01f4fd8d-017f-409b-8d61-368786d9c877.html"),
    Path(r"hri1752242863124\id2e653a04-6b1c-403a-b3f4-e4f93b933b87.html"),
    Path(r"hri1752242863124\idea22e2de-46f3-44c0-8676-693f1a3be145.html"),
)

DEFAULT_DFM_RELATIVE_PAGES = (
    Path(r"tsg1752242865753\id9960b498-e68d-40d6-9ad3-e0abcfee00f5.html"),
    Path(r"tsg1752242865753\id2ead69c3-3636-4830-8e3c-ddb3a61bee43.html"),
    Path(r"tsg1752242865753\ide04c1ce6-8fb3-474a-919f-372f068424b1.html"),
    Path(r"tsg1752242865753\id42561dcb-784c-490b-8b56-73d11467cbfa.html"),
)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8", errors="ignore"))


def _iter_nodes(items):
    for item in items:
        yield item
        yield from _iter_nodes(item.get("children") or ())


def is_svrf_style_function_name(name: str):
    if "::" in name:
        return all(is_svrf_style_function_name(part) for part in name.split("::"))
    if len(name) == 1:
        return name.isupper()
    return name[1].isupper() or name[1].isdigit() or name[1] == "_"


def _looks_like_function_root(title: str):
    upper = title.upper()
    if any(pattern.search(upper) for pattern in EXCLUDED_ROOT_PATTERNS):
        return False
    return any(pattern.search(upper) for pattern in FUNCTION_ROOT_PATTERNS)


def _collect_titles_from_subtree(node):
    names = set()
    stack = [node]
    while stack:
        current = stack.pop()
        title = (current.get("title") or "").strip()
        if title:
            upper = title.upper()
            title_match = RETURN_VALUE_TITLE_PATTERN.match(upper)
            if title_match:
                names.add(title_match.group(1).upper())
            elif (
                IDENTIFIER_PATTERN.match(upper)
                and is_svrf_style_function_name(upper)
                and upper not in NON_FUNCTION_IDENTIFIERS
            ):
                names.add(upper)
        stack.extend(reversed(current.get("children") or ()))
    return names


def _extract_names_from_page_text(path: Path):
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8", errors="ignore")
    names = set()
    for match in FUNCTION_PATTERN.findall(text):
        upper = match.upper()
        if upper not in NON_FUNCTION_IDENTIFIERS and is_svrf_style_function_name(upper):
            names.add(upper)
    for raw in XREF_NAME_PATTERN.findall(text):
        name = " ".join(raw.split()).upper()
        if IDENTIFIER_PATTERN.match(name) and name not in NON_FUNCTION_IDENTIFIERS and is_svrf_style_function_name(name):
            names.add(name)
    return names


def discover_doc_all_function_names(doc_root: Path):
    toc_path = doc_root / TOC_FILE
    if toc_path.exists():
        data = _read_json(toc_path)
        roots = [
            node for node in _iter_nodes(data.get("topics", ()))
            if _looks_like_function_root(node.get("title") or "")
        ]
        names = set()
        for node in roots:
            names.update(_collect_titles_from_subtree(node))
            href = node.get("href")
            if href:
                names.update(_extract_names_from_page_text(doc_root / href))
        return names

    topics_path = doc_root / TOPICS_FILE
    if not topics_path.exists():
        return set()
    data = _read_json(topics_path)
    names = set()
    for record in data.get("topics", ()):
        title = (record.get("title") or "").strip()
        if not _looks_like_function_root(title):
            continue
        upper = title.upper()
        title_match = RETURN_VALUE_TITLE_PATTERN.match(upper)
        if title_match:
            names.add(title_match.group(1).upper())
        elif IDENTIFIER_PATTERN.match(upper) and is_svrf_style_function_name(upper):
            names.add(upper)
        href = record.get("href")
        if href:
            names.update(_extract_names_from_page_text(doc_root / href))
    return names


def discover_doc_math_function_names(doc_root: Path):
    names = set()
    for relative in DEFAULT_MATH_RELATIVE_PAGES:
        path = doc_root / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        names.update(
            match.upper()
            for match in MATH_FUNCTION_PATTERN.findall(text)
            if is_svrf_style_function_name(match)
        )
    return names


def discover_doc_string_function_names(doc_root: Path):
    names = set()
    summary_path = doc_root / DEFAULT_STRING_SUMMARY_PAGE
    if summary_path.exists():
        text = summary_path.read_text(encoding="utf-8", errors="ignore")
        names.update(STRING_XREF_NAME_PATTERN.findall(text))
    for relative in DEFAULT_STRING_REFERENCE_PAGES:
        path = doc_root / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        match = TITLE_PATTERN.search(text)
        if match:
            names.add(match.group(1).upper())
    return names


def discover_doc_dfm_function_names(doc_root: Path):
    names = set()
    for relative in DEFAULT_DFM_RELATIVE_PAGES:
        path = doc_root / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        names.update(STRING_XREF_NAME_PATTERN.findall(text))
    return names


def build_known_keyword_inventory(
    keyword_registry,
    *,
    directive_secondary_words=(),
    modifier_starters=(),
    generic_prefix_ops=(),
    measurement_ops=(),
    edge_binary_prefix_ops=(),
    not_compound_ops=(),
    with_secondary_ops=(),
    function_like_names=(),
):
    known = set(keyword_registry)
    known.update(directive_secondary_words)
    known.update(modifier_starters)
    known.update(generic_prefix_ops)
    known.update(measurement_ops)
    known.update(edge_binary_prefix_ops)
    known.update(not_compound_ops)
    known.update(with_secondary_ops)
    known.update(function_like_names)
    return frozenset(known)


def scan_keyword_alias_hits(doc_root: Path, known_keywords):
    hits = defaultdict(lambda: {"canon": None, "count": 0, "samples": set()})
    for path in doc_root.rglob("*.html"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in MIXED_CASE_PATTERN.finditer(text):
            word = match.group(1)
            canon = word.upper()
            if canon not in known_keywords:
                continue
            prefix_match = PREFIX_PATTERN.match(word)
            if prefix_match is None:
                continue
            prefix = prefix_match.group(0)
            if prefix == canon:
                continue
            entry = hits[prefix]
            entry["count"] += 1
            entry["samples"].add(str(path))
            if entry["canon"] is None:
                entry["canon"] = canon
            elif entry["canon"] != canon:
                entry["canon"] = f"{entry['canon']} | {canon}"
    return hits


def build_keyword_aliases(doc_root: Path, known_keywords):
    hits = scan_keyword_alias_hits(doc_root, known_keywords)
    aliases = dict(APPROVED_KEYWORD_ALIASES)
    review = []
    blocked = []
    for prefix in sorted(hits):
        canon = hits[prefix]["canon"]
        count = hits[prefix]["count"]
        sample = sorted(hits[prefix]["samples"])[0]
        if prefix in aliases and aliases[prefix] == canon:
            continue
        if "|" in canon:
            blocked.append((prefix, canon, count, sample, "ambiguous canonical targets"))
            continue
        if prefix in known_keywords:
            blocked.append((prefix, canon, count, sample, "prefix collides with supported token/function"))
            continue
        if len(prefix) <= 3:
            blocked.append((prefix, canon, count, sample, "short prefix; review manually before enabling globally"))
            continue
        review.append((prefix, canon, count, sample))
    return aliases, {"review": tuple(review), "blocked": tuple(blocked)}


def build_doc_math_function_names(doc_root: Path):
    return frozenset(discover_doc_math_function_names(doc_root))


def build_doc_string_function_names(doc_root: Path):
    return frozenset(discover_doc_string_function_names(doc_root))


def build_doc_dfm_function_names(doc_root: Path):
    return frozenset(discover_doc_dfm_function_names(doc_root)) | DOC_DFM_EXTRA_FUNCTION_NAMES


def build_doc_all_function_names(doc_root: Path):
    return (
        frozenset(discover_doc_all_function_names(doc_root))
        | build_doc_math_function_names(doc_root)
        | build_doc_string_function_names(doc_root)
        | build_doc_dfm_function_names(doc_root)
        | DOC_ALL_EXTRA_FUNCTION_NAMES
    )


def build_function_like_names(doc_root: Path):
    return build_doc_all_function_names(doc_root) | FUNCTION_LIKE_EXTRA_NAMES


def build_manual_exception_entries(doc_root: Path):
    del doc_root
    return tuple(MANUAL_EXCEPTION_ENTRIES)


def build_case_sensitivity_rules(doc_root: Path):
    del doc_root
    return tuple(CASE_SENSITIVITY_RULES)


def build_support_matrix_entries(doc_root: Path):
    del doc_root
    return tuple(SUPPORT_MATRIX_ENTRIES)


def build_symbol_convention_entries(doc_root: Path):
    del doc_root
    return tuple(SYMBOL_CONVENTION_ENTRIES)
