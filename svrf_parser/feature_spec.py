"""Unified runtime view over dialect, family, and support metadata."""

from __future__ import annotations

from dataclasses import dataclass

from .dialect_profile import (
    analyze_program_dialects,
    iter_program_profile_matches,
    merge_program_dialect_profiles,
)
from .support_notice import SUPPORT_NOTICE_REGISTRY


@dataclass(frozen=True, slots=True)
class LimitedSupportMatch:
    notice: object
    node: object


def analyze_program_profile(program):
    return analyze_program_dialects(program)


def merge_program_profiles(programs):
    return merge_program_dialect_profiles(analyze_program_profile(program) for program in programs)


def iter_limited_support_matches(program):
    seen = set()
    for entry, node in iter_program_profile_matches(program):
        notice = SUPPORT_NOTICE_REGISTRY.get(entry.name)
        if notice is None or not notice.emit_warning or notice.name in seen:
            continue
        seen.add(notice.name)
        yield LimitedSupportMatch(notice=notice, node=node)
