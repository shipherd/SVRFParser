"""Static prefix of a TVF script. Never evaluate or search through Tcl commands."""

import re


_HEADER = re.compile(r"#!tvf(?=[ \t\r\n]|\Z)", re.I | re.ASCII)
_VERBATIM = re.compile(r"(?:::)?tvf::VERBATIM[ \t]+\{")
_SPECIAL = re.compile(r"[{}\\]")
_COMMENT = re.compile(r"#[^\r\n]*")
_TRIVIA = re.compile(r"[ \t\r\n;]+")


def is_tvf_script(text):
    return _HEADER.match(text) is not None


def tvf_prefix(text):
    """Yield (kind, start, end): literal SVRF ranges or the first nonliteral command."""
    i = 0
    while i < len(text):
        trivia = _TRIVIA.match(text, i)
        if trivia:
            i = trivia.end()
            continue
        comment = _COMMENT.match(text, i)
        if comment:
            if comment.group().endswith("\\"):
                yield "tcl", i, len(text)
                return
            i = comment.end()
            continue
        word = _VERBATIM.match(text, i)
        if not word:
            yield "tcl", i, len(text)
            return
        start = j = word.end()
        depth = 1
        while depth:
            special = _SPECIAL.search(text, j)
            if not special:
                yield "unterminated", i, len(text)
                return
            j = special.end()
            if special[0] == "\\":
                if text[j:j+1] in ("\r", "\n"):
                    # Tcl substitutes this even inside braces. It is not verbatim SVRF.
                    yield "tcl", i, len(text)
                    return
                j += 1
            else:
                depth += 1 if special[0] == "{" else -1
        stop = j - 1
        while j < len(text) and text[j] in " \t":
            j += 1
        if j < len(text) and text[j] not in ";\r\n":
            yield "tcl", i, len(text)
            return
        yield "literal", start, stop
        i = j
