"""Shared validation helpers and public validation result type."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .diagnostics import Diagnostic, SEVERITY_ERROR
from .unresolved_policy import unresolved_policy_summary


_ENV_VAR_RE = re.compile(r"\$(\w+)|\$\{([^}]+)\}")


class ValidationResult:
    """Result of SVRF validation, containing validity status and diagnostics."""

    __slots__ = ("valid", "errors", "warnings", "program", "profile", "policy_summary")

    def __init__(
        self,
        valid,
        errors=None,
        warnings=None,
        program=None,
        profile=None,
        policy_summary=None,
    ):
        self.valid = valid
        self.errors = errors or []
        self.warnings = warnings or []
        self.program = program
        self.profile = profile
        self.policy_summary = policy_summary or unresolved_policy_summary("strict")

    def __bool__(self):
        return self.valid

    @property
    def diagnostics(self):
        return [*self.errors, *self.warnings]

    @property
    def error_messages(self):
        return [str(diag) for diag in self.errors]

    @property
    def warning_messages(self):
        return [str(diag) for diag in self.warnings]

    @property
    def dialects(self):
        if self.profile is None:
            return ()
        return self.profile.dialects

    @property
    def feature_families(self):
        if self.profile is None:
            return ()
        return self.profile.families

    @property
    def profile_tags(self):
        if self.profile is None:
            return ()
        return self.profile.tags

    @property
    def limited_support_features(self):
        if self.profile is None:
            return ()
        return self.profile.limited_support_features

    @property
    def unresolved_policy(self):
        return self.policy_summary.policy

    def __repr__(self):
        if self.valid:
            return "ValidationResult(valid=True)"
        return f"ValidationResult(valid=False, errors={self.errors!r})"


@dataclass
class ParsedDocument:
    filename: str
    text: str
    program: object
    warnings: list


def line_snippet(text, line):
    if not text or line <= 0:
        return None
    lines = text.splitlines()
    if 1 <= line <= len(lines):
        return lines[line - 1]
    return None


def make_diagnostic(
    severity,
    code,
    message,
    filename="<input>",
    line=0,
    col=0,
    end_line=0,
    end_col=0,
    start_offset=0,
    end_offset=0,
    snippet=None,
    include_stack=(),
    metadata=None,
):
    return Diagnostic(
        severity=severity,
        code=code,
        message=message,
        filename=filename,
        line=line,
        col=col,
        end_line=end_line or line,
        end_col=end_col or col,
        start_offset=start_offset,
        end_offset=end_offset,
        snippet=snippet,
        include_stack=tuple(include_stack or ()),
        metadata=metadata,
    )


def route_diagnostic(diagnostic, errors, warnings):
    if diagnostic.is_error:
        errors.append(diagnostic)
    else:
        warnings.append(diagnostic)


def with_include_stack(diagnostic, include_stack):
    if not include_stack:
        return diagnostic
    return diagnostic.with_include_stack(include_stack)


def is_pathlike_filename(filename):
    if not filename:
        return False
    return not (filename.startswith("<") and filename.endswith(">"))


def expand_env_vars(value):
    def replace(match):
        name = match.group(1) or match.group(2)
        return os.environ.get(name, match.group(0))

    return _ENV_VAR_RE.sub(replace, value)


def read_error_result(path, exc, *, policy="strict"):
    return ValidationResult(
        False,
        [
            make_diagnostic(
                SEVERITY_ERROR,
                "validation.read_error",
                f"Cannot read file: {exc}",
                filename=str(path),
            )
        ],
        policy_summary=unresolved_policy_summary(policy),
    )
