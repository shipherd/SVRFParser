"""Reviewable support notices for recognized but limited-support features."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupportNotice:
    name: str
    feature_name: str
    warning_code: str
    message: str
    category: str
    emit_warning: bool
    tags: frozenset[str]


class SupportNoticeRegistry:
    def __init__(self, notices):
        self.notices = tuple(notices)
        self._by_feature_name = {
            notice.feature_name: notice
            for notice in self.notices
        }

    def get(self, feature_name):
        return self._by_feature_name.get(feature_name)


SUPPORT_NOTICES = (
    SupportNotice(
        name="polygon_directive",
        feature_name="polygon_directive",
        warning_code="validation.support.limited_feature",
        message=(
            "POLYGON directives are recognized, but only generic parsing and limited "
            "semantic handling are implemented"
        ),
        category="generic_semantics",
        emit_warning=True,
        tags=frozenset({"generic_semantics", "manual_review"}),
    ),
    SupportNotice(
        name="rdb_directive",
        feature_name="rdb_directive",
        warning_code="validation.support.limited_feature",
        message=(
            "Top-level RDB directives are recognized, but only generic parsing and "
            "limited semantic handling are implemented"
        ),
        category="generic_semantics",
        emit_warning=True,
        tags=frozenset({"generic_semantics", "manual_review"}),
    ),
    SupportNotice(
        name="tvf_directive",
        feature_name="tvf_directive",
        warning_code="validation.support.limited_feature",
        message=(
            "TVF built-in language constructs are recognized, but TVF bodies are not "
            "semantically interpreted beyond generic directive parsing"
        ),
        category="embedded_language",
        emit_warning=True,
        tags=frozenset({"embedded_language", "manual_review"}),
    ),
    SupportNotice(
        name="encrypted_block",
        feature_name="encrypted_block",
        warning_code="validation.support.opaque_content",
        message=(
            "Encrypted SVRF blocks are treated as opaque content; definitions inside "
            "them are not available to semantic validation"
        ),
        category="opaque_content",
        emit_warning=False,
        tags=frozenset({"opaque_content", "manual_review"}),
    ),
)


SUPPORT_NOTICE_REGISTRY = SupportNoticeRegistry(SUPPORT_NOTICES)
