"""Build a redistributable command index from the local reference dictionary.

Only syntax identifiers and closed keyword alternatives are exported, never
manual prose, examples, filenames, or installation paths.
"""

import json
import re
from html.parser import HTMLParser
from pathlib import Path


def dictionary_leaves(toc):
    def leaves(node):
        if not node.get("children"):
            yield node
        else:
            for child in node["children"]:
                yield from leaves(child)

    for section in toc["topics"]:
        if section["title"].startswith("Reference Dictionary"):
            for node in section.get("children", ()):
                yield from leaves(node)


class _Usage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lines = []
        self.active = False
        self.roles = []

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class", "").split()
        if tag == "p" and "UsageLine" in classes:
            self.active = True
            self.lines.append([])
            self.roles = []
        if self.active and tag == "span":
            role = self.roles[-1] if self.roles else "syntax"
            if any("Replaceable" in c for c in classes):
                role = "required" if any(c.startswith("RequiredReplaceable") for c in classes) else "optional"
            self.roles.append(role)

    def handle_endtag(self, tag):
        if tag == "p":
            self.active = False
        elif self.active and tag == "span" and self.roles:
            self.roles.pop()

    def handle_data(self, data):
        if self.active and data.strip():
            self.lines[-1].append((self.roles[-1] if self.roles else "syntax", " ".join(data.split())))


_WORD = re.compile(r"(?=[0-9]*[A-Z])[A-Z0-9_]+\Z", re.ASCII)
_META = re.compile(r"[A-Za-z0-9_]+|[^\s]", re.ASCII)


def _head(title, lines):
    # Topic qualifiers can designate a variant selected later in a command.
    name = title.split(" ...")[0].split(" (")[0]
    if name == "DFM RDB GDS/OASIS":
        name = "DFM RDB"
    words = name.split()
    if not words or not all(_WORD.fullmatch(w) for w in words):
        return None
    best = 0
    for line in lines:
        initial = []
        for role, data in line:
            if role != "syntax":
                break
            initial.extend(_META.findall(data.upper()))
            if len(initial) >= len(words):
                break
        same = 0
        for actual, expected in zip(initial, words):
            if actual != expected:
                break
            same += 1
        best = max(best, same)
    return " ".join(words[:best]) or None


def _closed_forms(head, lines):
    """Only enforce complete, finite choices; metavariables are not keywords."""
    forms = set()
    for line in lines:
        if not line or any(role != "syntax" for role, _ in line):
            return None
        tokens = _META.findall(" ".join(text for _, text in line))
        words = head.split()
        if [w.upper() for w in tokens[:len(words)]] != words:
            return None
        tail = tokens[len(words):]
        if not tail:
            forms.add("")
            continue
        if tail[0] == "{" and tail[-1] == "}":
            tail = tail[1:-1]
        parts = " ".join(tail).split(" | ")
        if not all(part and all(_WORD.fullmatch(w) for w in part.split()) for part in parts):
            return None
        forms.update(parts)
    return sorted(forms) or None


def _minimum_arguments(head, lines):
    """Count only the initial mandatory positional slots common to every usage."""
    counts = []
    for line in lines:
        tokens = [(role, word) for role, text in line for word in _META.findall(text)]
        words = head.split()
        if [(r, w.upper()) for r, w in tokens[:len(words)]] != [("syntax", w) for w in words]:
            return 0
        tail = tokens[len(words):]
        # An ungrouped alternative can replace the apparent mandatory prefix.
        depth = 0
        for _, word in tail:
            if word in {"[", "{"}:
                depth += 1
            elif word in {"]", "}"}:
                depth -= 1
            elif word == "|" and depth <= 0:
                return 0
        count = 0
        for role, word in tail:
            if role != "required" or not word.isidentifier():
                break
            count += 1
        counts.append(count)
    return min(counts, default=0)


def build_dictionary(root):
    root = Path(root)
    toc = json.loads((root / "toc.json").read_text(encoding="utf-8-sig"))
    topics = json.loads((root / "topics.json").read_text(encoding="utf-8-sig"))
    by_id = {t["id"]: t for t in topics["topics"]}
    rows = []
    for n in dictionary_leaves(toc):
        title = " ".join(n["title"].upper().split())
        topic = by_id[n["id"]]
        parser = _Usage()
        parser.feed((root / n["href"].replace("\\", "/")).read_text(encoding="utf-8"))
        parser.close()
        lines = [line for line in parser.lines if line]
        head = _head(title, lines)
        intro = " ".join(topic.get("searchtext", "").casefold().split())
        description = intro.removeprefix(title.casefold()).strip().removeprefix(title.casefold()).strip()
        kind = ("operation" if description.startswith("layer operation") else "statement") if lines else "reference"
        forms = _closed_forms(head, lines) if kind == "statement" and head else None
        minimum = _minimum_arguments(head, lines) if head and kind == "statement" else 0
        rows.append([title, kind, head, forms, minimum])
    if len({r[0] for r in rows}) != len(rows):
        raise ValueError("Duplicate reference dictionary title")
    return sorted(rows)
