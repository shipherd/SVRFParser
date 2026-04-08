"""Centralized keyword tables derived from packaged spec artifacts."""

from .svrf_spec import KEYWORD_SPEC


_KEYWORD_REGISTRY = dict(KEYWORD_SPEC.keyword_registry)
_KEYWORD_ALIASES = dict(KEYWORD_SPEC.keyword_aliases)
_LAYER_BP = dict(KEYWORD_SPEC.layer_bp)


_DIRECTIVE_HEADS = frozenset(
    k for k, roles in _KEYWORD_REGISTRY.items() if "directive_head" in roles
)

_BINARY_OPS = frozenset(
    k for k, roles in _KEYWORD_REGISTRY.items() if "binary_op" in roles
)

_UNARY_OPS = frozenset(
    k for k, roles in _KEYWORD_REGISTRY.items() if "unary_op" in roles
)

_DRC_OPS = frozenset(
    k for k, roles in _KEYWORD_REGISTRY.items() if "drc_op" in roles
)

_DRC_MODIFIERS = frozenset(
    k for k, roles in _KEYWORD_REGISTRY.items() if "drc_modifier" in roles
)

_EXPR_STARTERS = frozenset(
    k for k, roles in _KEYWORD_REGISTRY.items() if "expr_starter" in roles
)

_SVRF_KEYWORDS = (
    _DIRECTIVE_HEADS
    | _DRC_MODIFIERS
    | _EXPR_STARTERS
    | frozenset(
        k for k, roles in _KEYWORD_REGISTRY.items() if "svrf_keyword" in roles
    )
)
