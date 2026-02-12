"""Coverage analysis: cross-reference SVRF docs with parser support.

Extracts construct names from the SVRF User Reference toc.json,
compares against parser-supported constructs, and outputs a
coverage matrix JSON.
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DOCS_TOC = None
MATRIX_PATH = Path(__file__).parent / "coverage_matrix.json"

# Constructs known to be supported by the parser, extracted from parser.py
PARSER_SUPPORTED = {
    # Binary/spatial ops (_BINARY_OPS + _LAYER_BP keys)
    "AND", "OR", "NOT", "INSIDE", "OUTSIDE", "INTERACT", "TOUCH",
    "ENCLOSE", "CUT", "BY",
    # Edge ops (multi-word binary/unary)
    "COINCIDENT EDGE", "COINCIDENT INSIDE EDGE", "COINCIDENT OUTSIDE EDGE",
    "COIN EDGE", "COIN INSIDE EDGE", "COIN OUTSIDE EDGE",
    "IN EDGE", "IN INSIDE EDGE", "IN OUTSIDE EDGE",
    "INSIDE EDGE", "OUTSIDE EDGE", "OR EDGE",
    "TOUCH EDGE", "TOUCH INSIDE EDGE", "TOUCH OUTSIDE EDGE",
    # Unary ops
    "COPY", "HOLES", "DONUT", "EXTENT", "MERGE", "PUSH",
    # DRC ops
    "INT", "EXT", "ENC", "DENSITY",
    "ENC RECTANGLE", "ENCLOSE RECTANGLE", "RECTANGLE ENCLOSURE",
    # Size/grow/shrink
    "SIZE", "SHIFT", "GROW", "SHRINK",
    # Measurement ops
    "AREA", "ANGLE", "LENGTH", "VERTEX",
    # Edge ops (prefix)
    "CONVEX EDGE", "EXPAND EDGE",
    # Rectangle/extents
    "RECTANGLE", "RECTANGLES", "EXTENTS",
    # Stamp
    "STAMP",
    # DFM/RET
    "DFM", "DFM PROPERTY", "DFM SPACE", "DFM COPY", "DFM DV",
    "DFM DP", "DFM TEXT", "RET",
    # NET operations
    "NET AREA", "NET AREA RATIO", "NET",
    # WITH operations
    "WITH", "WITH EDGE", "WITH WIDTH", "WITH LENGTH", "WITH AREA",
    "WITH TEXT", "WITH NEIGHBOR",
    # INSIDE/OUTSIDE CELL
    "INSIDE CELL", "OUTSIDE CELL",
    # Statements
    "LAYER", "LAYER MAP", "VARIABLE", "CONNECT", "SCONNECT",
    "DEVICE", "DMACRO", "ATTACH", "GROUP", "TRACE PROPERTY",
    # Preprocessor
    "#DEFINE", "#IFDEF", "#IFNDEF", "#ELSE", "#ENDIF",
    "#INCLUDE", "#ENCRYPT", "#ENDCRYPT", "#DECRYPT",
    # Directives (from _DIRECTIVE_HEADS)
    "LAYOUT", "SOURCE", "DRC", "LVS", "ERC", "PEX", "MASK",
    "FLAG", "UNIT", "TEXT", "PORT", "VIRTUAL", "SVRF", "PRECISION",
    "RESOLUTION", "LABEL", "TITLE", "PATHCHK", "DRAWN",
    "HCELL", "FILTER", "EXCLUDE", "FLATTEN", "ENVIRONMENT",
    "DRC RESULTS DATABASE", "LVS REPORT",
    "LAYOUT PATH", "LAYOUT PRIMARY",
    # Property blocks / IF
    "PROPERTY BLOCK", "IF", "ELSE", "ELSE IF",
    # Function calls
    "FUNCTION CALL",
}

# Category mapping for documented constructs
CATEGORY_KEYWORDS = {
    "layer_ops": {"AND", "OR", "NOT", "COPY", "INSIDE", "OUTSIDE",
                  "INTERACT", "TOUCH", "ENCLOSE", "CUT", "HOLES",
                  "DONUT", "MERGE", "PUSH"},
    "edge_ops": {"COINCIDENT EDGE", "COINCIDENT INSIDE EDGE",
                 "COINCIDENT OUTSIDE EDGE", "IN EDGE",
                 "INSIDE EDGE", "OUTSIDE EDGE", "OR EDGE",
                 "TOUCH EDGE", "TOUCH INSIDE EDGE",
                 "TOUCH OUTSIDE EDGE", "CONVEX EDGE", "EXPAND EDGE"},
    "drc_ops": {"INT", "EXT", "ENC", "DENSITY", "RECTANGLE ENCLOSURE",
                "ENCLOSE RECTANGLE", "ENC RECTANGLE"},
    "size_grow": {"SIZE", "SHIFT", "GROW", "SHRINK"},
    "measurement": {"AREA", "ANGLE", "LENGTH", "VERTEX", "PERIMETER"},
    "spatial": {"RECTANGLE", "RECTANGLES", "EXTENTS", "EXTENT", "STAMP"},
    "connectivity": {"CONNECT", "SCONNECT", "ATTACH", "GROUP",
                     "TRACE PROPERTY", "DEVICE", "DMACRO"},
    "preprocessor": {"#DEFINE", "#IFDEF", "#IFNDEF", "#ELSE", "#ENDIF",
                     "#INCLUDE", "#ENCRYPT", "#ENDCRYPT", "#DECRYPT",
                     "#UNDEFINE", "#PRAGMA"},
    "specification": {"LAYOUT", "SOURCE", "DRC", "LVS", "ERC", "PEX",
                      "PRECISION", "RESOLUTION", "TITLE", "UNIT",
                      "VARIABLE", "HCELL", "LAYER", "LAYER MAP"},
    "dfm_ret": {"DFM", "RET", "DFM PROPERTY", "DFM SPACE", "DFM COPY",
                "DFM DV", "DFM DP", "DFM TEXT"},
    "net_ops": {"NET", "NET AREA", "NET AREA RATIO"},
}


def extract_doc_constructs(toc_path):
    """Extract construct names from Reference Dictionary sections of toc.json."""
    with open(toc_path, 'r', encoding='utf-8') as f:
        toc = json.load(f)

    constructs = []
    for topic in toc.get("topics", []):
        title = topic.get("title", "")
        if "Reference Dictionary" in title:
            for child in topic.get("children", []):
                name = child.get("title", "").strip()
                if name:
                    constructs.append(name)
    return constructs


def normalize(name):
    """Normalize a construct name for comparison."""
    return name.upper().strip()


def classify_construct(name):
    """Classify a construct into a category."""
    upper = normalize(name)
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if upper in keywords:
            return cat
    return "other"


def match_construct(doc_name, supported_set):
    """Check if a documented construct is supported by the parser."""
    upper = normalize(doc_name)
    if upper in supported_set:
        return True
    # Try without spaces (e.g. "Coincident Edge" -> "COINCIDENT EDGE")
    if upper.replace(" ", " ") in supported_set:
        return True
    # Try first word only (e.g. "Density" matches "DENSITY")
    first_word = upper.split()[0] if upper.split() else ""
    if first_word in supported_set:
        return True
    return False


def main():
    if not DOCS_TOC.exists():
        print(f"toc.json not found: {DOCS_TOC}")
        return 1

    # Step 1: Extract from docs
    doc_constructs = extract_doc_constructs(DOCS_TOC)
    print(f"Documented constructs: {len(doc_constructs)}")

    # Normalize supported set for matching
    supported_upper = {normalize(s) for s in PARSER_SUPPORTED}

    # Step 2: Cross-reference
    supported = []
    not_supported = []
    for name in doc_constructs:
        if match_construct(name, supported_upper):
            supported.append(name)
        else:
            not_supported.append(name)

    total = len(doc_constructs)
    pct = len(supported) / total * 100 if total else 0
    print(f"Parser supported:     {len(supported)}")
    print(f"Not supported:        {len(not_supported)}")
    print(f"Coverage:             {pct:.1f}%")

    # Step 3: By-category breakdown
    by_category = {}
    for name in doc_constructs:
        cat = classify_construct(name)
        if cat not in by_category:
            by_category[cat] = {"total": 0, "supported": 0, "missing": []}
        by_category[cat]["total"] += 1
        if match_construct(name, supported_upper):
            by_category[cat]["supported"] += 1
        else:
            by_category[cat]["missing"].append(name)

    print(f"\nBy category:")
    for cat, info in sorted(by_category.items()):
        s = info["supported"]
        t = info["total"]
        print(f"  {cat:20s}: {s}/{t}")
        if info["missing"]:
            for m in info["missing"][:5]:
                print(f"    - {m}")

    if not_supported:
        print(f"\nMissing constructs:")
        for name in sorted(not_supported):
            print(f"  - {name}")

    # Write matrix JSON
    matrix = {
        "documented_constructs": sorted(doc_constructs),
        "parser_supported": sorted(supported),
        "not_supported": sorted(not_supported),
        "coverage_pct": round(pct, 1),
        "by_category": by_category,
    }
    MATRIX_PATH.write_text(
        json.dumps(matrix, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    print(f"\nMatrix written to {MATRIX_PATH}")
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python coverage_analysis.py <docs_toc_json>")
        sys.exit(1)
    DOCS_TOC = Path(sys.argv[1])
    sys.exit(main())
