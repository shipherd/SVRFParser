"""Source redaction shared by the local corpus-report commands."""

from __future__ import annotations

import os
from pathlib import Path


class ReportPrivacy:
    """Use run-local aliases unless private details are explicitly requested."""

    def __init__(self, *, show_private_details=False):
        self.show_private_details = show_private_details
        self._files = {}
        self._symbols = {}

    def path(self, path, *, root=None):
        if self.show_private_details:
            if root is not None and Path(root).is_dir():
                return os.path.relpath(path, root)
            return str(path)
        key = os.path.normcase(os.path.abspath(path))
        if key not in self._files:
            self._files[key] = f"file-{len(self._files) + 1:04d}"
        return self._files[key]

    def symbol_counts(self, counts):
        if self.show_private_details:
            return dict(counts)
        redacted = {}
        for name, count in counts.items():
            if name not in self._symbols:
                self._symbols[name] = f"symbol-{len(self._symbols) + 1:04d}"
            redacted[self._symbols[name]] = count
        return redacted

    def exception(self, error):
        return str(error) if self.show_private_details else type(error).__name__

    def diagnostic(self, diagnostic):
        if self.show_private_details:
            return str(diagnostic)
        return getattr(diagnostic, "code", "") or "parser.warning"
