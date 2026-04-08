"""Policy helpers for unresolved-symbol diagnostics."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path


SUPPORTED_UNRESOLVED_POLICIES = frozenset({"strict", "practical"})

UNRESOLVED_SYMBOL_CODES = frozenset(
    {
        "semantic.reference.undefined",
        "semantic.reference.companion_candidate",
        "semantic.reference.external_candidate",
        "semantic.reference.scalar_undefined",
        "semantic.reference.local_scope_only",
        "semantic.varref.undefined",
    }
)

MANIFEST_SUPPRESSIBLE_CODES = frozenset(
    {
        "semantic.reference.undefined",
        "semantic.reference.companion_candidate",
        "semantic.reference.external_candidate",
        "semantic.reference.scalar_undefined",
    }
)


def _normalize_symbol_values(values):
    return frozenset(str(value).upper() for value in (values or ()))


def _normalize_globs(values):
    return tuple(str(value) for value in (values or ()))


@dataclass(frozen=True, slots=True)
class SymbolManifestRule:
    file_globs: tuple[str, ...] = ()
    external_symbols: frozenset[str] = frozenset()
    scalar_parameters: frozenset[str] = frozenset()
    layer_like_symbols: frozenset[str] = frozenset()

    @classmethod
    def from_mapping(cls, payload):
        return cls(
            file_globs=_normalize_globs(payload.get("file_globs")),
            external_symbols=_normalize_symbol_values(payload.get("external_symbols")),
            scalar_parameters=_normalize_symbol_values(payload.get("scalar_parameters")),
            layer_like_symbols=_normalize_symbol_values(payload.get("layer_like_symbols")),
        )

    def matches_file(self, filename):
        if not self.file_globs:
            return True
        filename = str(filename or "")
        normalized = filename.replace("\\", "/")
        basename = Path(filename).name
        return any(
            fnmatch(normalized, pattern)
            or fnmatch(basename, pattern)
            for pattern in self.file_globs
        )

    def classes_for_symbol(self, filename, symbol):
        if not self.matches_file(filename):
            return frozenset()
        symbol = str(symbol or "").upper()
        classes = set()
        if symbol in self.external_symbols:
            classes.add("external_symbols")
        if symbol in self.scalar_parameters:
            classes.add("scalar_parameters")
        if symbol in self.layer_like_symbols:
            classes.add("layer_like_symbols")
        return frozenset(classes)


@dataclass(frozen=True, slots=True)
class SymbolManifest:
    rules: tuple[SymbolManifestRule, ...] = ()
    source: str | None = None

    def classes_for_symbol(self, filename, symbol):
        classes = set()
        for rule in self.rules:
            classes.update(rule.classes_for_symbol(filename, symbol))
        return frozenset(classes)

    def resolves_symbol(self, filename, symbol):
        return bool(self.classes_for_symbol(filename, symbol))

    @classmethod
    def from_mapping(cls, payload, *, source=None):
        rules = [SymbolManifestRule.from_mapping(payload)]
        for entry in payload.get("rules", ()):
            if isinstance(entry, dict):
                rules.append(SymbolManifestRule.from_mapping(entry))
        return cls(rules=tuple(rules), source=source)


@dataclass(frozen=True, slots=True)
class UnresolvedPolicySummary:
    policy: str
    raw_unresolved_count: int = 0
    deduped_unresolved_count: int = 0
    manifest_resolved_count: int = 0
    remaining_unresolved_count: int = 0
    manifest_source: str | None = None
    manifest_resolved_symbols: tuple[str, ...] = ()

    def to_dict(self):
        return {
            "policy": self.policy,
            "raw_unresolved_count": self.raw_unresolved_count,
            "deduped_unresolved_count": self.deduped_unresolved_count,
            "manifest_resolved_count": self.manifest_resolved_count,
            "remaining_unresolved_count": self.remaining_unresolved_count,
            "manifest_source": self.manifest_source,
            "manifest_resolved_symbols": self.manifest_resolved_symbols,
        }


@dataclass(slots=True)
class _MutablePolicySummary:
    policy: str
    raw_unresolved_count: int = 0
    deduped_unresolved_count: int = 0
    manifest_resolved_count: int = 0
    remaining_unresolved_count: int = 0
    manifest_source: str | None = None
    manifest_resolved_symbols: set[str] = field(default_factory=set)

    def freeze(self):
        return UnresolvedPolicySummary(
            policy=self.policy,
            raw_unresolved_count=self.raw_unresolved_count,
            deduped_unresolved_count=self.deduped_unresolved_count,
            manifest_resolved_count=self.manifest_resolved_count,
            remaining_unresolved_count=self.remaining_unresolved_count,
            manifest_source=self.manifest_source,
            manifest_resolved_symbols=tuple(sorted(self.manifest_resolved_symbols)),
        )


def new_policy_summary(policy, *, manifest_source=None):
    return _MutablePolicySummary(policy=policy, manifest_source=manifest_source)


def unresolved_policy_summary(policy, *, manifest_source=None):
    return UnresolvedPolicySummary(policy=policy, manifest_source=manifest_source)


def is_unresolved_symbol_code(code):
    return code in UNRESOLVED_SYMBOL_CODES


def is_manifest_suppressible_code(code):
    return code in MANIFEST_SUPPRESSIBLE_CODES


def normalize_unresolved_policy(policy):
    value = str(policy or "strict").lower()
    if value not in SUPPORTED_UNRESOLVED_POLICIES:
        raise ValueError(
            f"Unsupported unresolved_policy {policy!r}; expected one of: "
            f"{', '.join(sorted(SUPPORTED_UNRESOLVED_POLICIES))}"
        )
    return value


def load_symbol_manifest(symbol_manifest):
    if symbol_manifest is None:
        return None
    if isinstance(symbol_manifest, SymbolManifest):
        return symbol_manifest
    if isinstance(symbol_manifest, (str, Path)):
        path = Path(symbol_manifest)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return SymbolManifest.from_mapping(payload, source=str(path))
    if isinstance(symbol_manifest, dict):
        return SymbolManifest.from_mapping(symbol_manifest, source="<mapping>")
    raise TypeError(
        "symbol_manifest must be None, a mapping, a filesystem path, or SymbolManifest"
    )
