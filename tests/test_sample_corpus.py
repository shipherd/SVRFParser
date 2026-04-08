"""Tests for shared sample-corpus selection policy."""

from __future__ import annotations

import unittest
from pathlib import Path

from sample_corpus import (
    SUPPORTED_SAMPLE_SUFFIXES,
    is_supported_sample_file,
    iter_sample_files,
)


class _FakeSamplePath:
    def __init__(self, name, *, is_file=True):
        self.name = name
        self.suffix = Path(name).suffix
        self._is_file = is_file

    def is_file(self):
        return self._is_file

    def __lt__(self, other):
        return self.name < other.name


class _FakeSampleRoot:
    def __init__(self, names):
        self._paths = tuple(_FakeSamplePath(name) for name in names)
        self._paths += (_FakeSamplePath("ignored_dir", is_file=False),)

    def is_file(self):
        return False

    def rglob(self, pattern):
        self.pattern = pattern
        return self._paths


class SampleCorpusTests(unittest.TestCase):
    def test_supported_sample_suffixes_empty_means_no_suffix_filter(self):
        self.assertEqual(frozenset(), SUPPORTED_SAMPLE_SUFFIXES)

    def test_is_supported_sample_file_does_not_filter_by_suffix(self):
        self.assertTrue(is_supported_sample_file(Path("deck.DRC")))
        self.assertTrue(is_supported_sample_file(Path("deck.13_1a.encrypt")))
        self.assertTrue(is_supported_sample_file(Path("notes.txt")))
        self.assertTrue(is_supported_sample_file(Path("deck")))

    def test_iter_sample_files_includes_all_regular_files_and_skips_directories(self):
        sample_names = [
            "deck.drc",
            "deck.lvs",
            "deck.svrf",
            "antenna.ant",
            "antenna.13a",
            "antenna.15a",
            "antenna.13_1a",
            "antenna.13_1a.encrypt",
            "notes.txt",
            "deck_without_extension",
        ]
        root = _FakeSampleRoot(sample_names)

        selected = {path.name for path in iter_sample_files(root)}

        self.assertEqual(set(sample_names), selected)
        self.assertEqual("*", root.pattern)


if __name__ == "__main__":
    unittest.main()
