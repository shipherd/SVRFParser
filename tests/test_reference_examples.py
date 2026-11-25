"""Optional conformance checks using locally installed reference examples."""
import json
import os
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

from svrf_parser import parse
from svrf_parser.exceptions import SVRFError
from svrf_parser.svrf_spec.dictionary_source import dictionary_leaves


# One-based worked-example blocks. Report output and SPICE netlists are not decks.
_DECKS = {
    "DFM DEFAULTS": (1, 2, 3, 4, 5, 6), "DFM PATTERN MATCH REPORT": (1, 2),
    "DFM SELECT BY NET": (1, 2), "DFM SPEC VIA REDUNDANCY": (1, 2),
    "DFM SPEC VIA REDUNDANCY COUNT": (1, 2, 3, 4), "EXPAND TEXT": (1,),
    "LAYER DIRECTORY": (1,), "LVS REPORT UNITS": (1, 5),
    "NET AREA RATIO PRINT": (1,), "NET INTERACT": (1, 2),
}


class _ExampleBlocks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks = []
        self.div_depth = 0
        self.in_code = False

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class", "").split()
        if tag == "div" and (self.div_depth or "Examples" in classes):
            self.div_depth += 1
        elif tag == "pre" and self.div_depth and "codeblock" in classes:
            self.blocks.append([])
            self.in_code = True

    def handle_endtag(self, tag):
        if tag == "div" and self.div_depth:
            self.div_depth -= 1
        elif tag == "pre":
            self.in_code = False

    def handle_data(self, data):
        if self.in_code:
            self.blocks[-1].append(data)


@unittest.skipUnless(os.environ.get("SVRF_MANUAL_ROOT"), "external reference not configured")
class WorkedExamplesTests(unittest.TestCase):
    def test_standalone_reference_examples(self):
        root = Path(os.environ["SVRF_MANUAL_ROOT"])
        native = os.environ.get("SVRF_NATIVE_EXE")
        toc = json.loads((root / "toc.json").read_text(encoding="utf-8-sig"))
        topics = {n["title"].upper(): n for n in dictionary_leaves(toc)}
        for title, indices in _DECKS.items():
            html = _ExampleBlocks()
            html.feed((root / topics[title]["href"].replace("\\", "/")).read_text(encoding="utf-8"))
            html.close()
            for index in indices:
                with self.subTest(topic=title, example=index):
                    self.assertGreaterEqual(len(html.blocks), index)
                    # HTML indentation in published code can use nonbreaking spaces.
                    source = "".join(html.blocks[index-1]).replace("\xa0", " ")
                    try:
                        tree = parse(source, strict=True)
                    except SVRFError:
                        tree = None
                    self.assertIsNotNone(tree, "Worked example did not parse strictly")
                    if native:
                        result = subprocess.run([native, "--strict", "--ast", "-"], input=source.encode("utf-8"),
                                                capture_output=True, timeout=30)
                        self.assertEqual(result.returncode, 0, "Native strict parse failed")
                        self.assertTrue(json.loads(result.stdout) == json.loads(json.dumps(tree.to_dict(False))),
                                        "Worked example ASTs differ")
