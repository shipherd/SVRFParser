"""Centralized keyword registry for the SVRF parser.

Each keyword is declared once with its roles.  The legacy frozenset
variables (_DIRECTIVE_HEADS, _BINARY_OPS, etc.) are derived automatically
so that all existing import sites continue to work unchanged.
"""

# Roles:
#   directive_head  – starts a multi-word directive
#   binary_op       – layer boolean/spatial binary operator
#   unary_op        – unary prefix operation in layer expressions
#   drc_op          – DRC check operation (prefix-style in rule check blocks)
#   drc_modifier    – modifier that can follow DRC operations
#   expr_starter    – can start a layer expression in _layer_nud()
#   svrf_keyword    – should NOT be treated as layer name in expression context

_KEYWORD_REGISTRY = {
    # --- directive heads ---
    'LAYOUT':      {'directive_head'},
    'SOURCE':      {'directive_head'},
    'DRC':         {'directive_head'},
    'LVS':         {'directive_head'},
    'ERC':         {'directive_head'},
    'PEX':         {'directive_head'},
    'MASK':        {'directive_head'},
    'FLAG':        {'directive_head'},
    'UNIT':        {'directive_head'},
    'TEXT':        {'directive_head'},
    'PORT':        {'directive_head'},
    'VIRTUAL':     {'directive_head'},
    'SVRF':        {'directive_head'},
    'PRECISION':   {'directive_head'},
    'RESOLUTION':  {'directive_head'},
    'LABEL':       {'directive_head'},
    'TITLE':       {'directive_head'},
    'NET':         {'directive_head'},
    'PATHCHK':     {'directive_head'},
    'SONR':        {'directive_head'},
    'TDDRC':       {'directive_head'},
    'PERC':        {'directive_head'},
    'LITHO':       {'directive_head'},
    'MDP':         {'directive_head'},
    'MDPMERGE':    {'directive_head'},
    'FRACTURE':    {'directive_head'},
    'HCELL':       {'directive_head'},
    'FILTER':      {'directive_head'},
    'EXCLUDE':     {'directive_head'},
    'FLATTEN':     {'directive_head'},
    'VARIABLE':    {'directive_head'},
    'ENVIRONMENT': {'directive_head'},

    # --- binary ops ---
    'AND':         {'binary_op'},
    'OR':          {'binary_op', 'expr_starter'},
    'XOR':         {'binary_op'},
    'BY':          {'binary_op', 'svrf_keyword'},

    # --- multi-role keywords ---
    'NOT':         {'binary_op', 'unary_op', 'expr_starter'},
    'INSIDE':      {'binary_op', 'drc_modifier'},
    'OUTSIDE':     {'binary_op', 'drc_modifier'},
    'OUT':         {'binary_op'},
    'INTERACT':    {'binary_op', 'expr_starter'},
    'TOUCH':       {'binary_op'},
    'ENCLOSE':     {'binary_op', 'drc_op', 'expr_starter'},
    'CUT':         {'binary_op', 'expr_starter'},

    # --- unary ops ---
    'COPY':        {'unary_op', 'expr_starter'},
    'HOLES':       {'unary_op', 'expr_starter'},
    'DONUT':       {'unary_op', 'expr_starter'},
    'EXTENT':      {'unary_op', 'expr_starter'},

    # --- DRC ops ---
    'INT':         {'drc_op', 'expr_starter'},
    'EXT':         {'drc_op', 'expr_starter'},
    'ENC':         {'drc_op', 'expr_starter'},
    'DENSITY':     {'drc_op', 'expr_starter'},

    # --- DRC modifiers ---
    'ABUT':        {'drc_modifier'},
    'SINGULAR':    {'drc_modifier'},
    'REGION':      {'drc_modifier'},
    'OPPOSITE':    {'drc_modifier'},
    'NOTCH':       {'drc_modifier'},
    'ORIGINAL':    {'drc_modifier'},
    'CONNECTED':   {'drc_modifier'},
    'WINDOW':      {'drc_modifier'},
    'BACKUP':      {'drc_modifier'},
    'RDB':         {'drc_modifier'},
    'PRINT':       {'drc_modifier'},
    'POLYGON':     {'drc_modifier'},
    'EMPTY':       {'drc_modifier'},
    'INNER':       {'drc_modifier'},
    'CORNER':      {'drc_modifier'},
    'ACUTE':       {'drc_modifier'},
    'OBTUSE':      {'drc_modifier'},
    'BEVEL':       {'drc_modifier'},
    'SQUARE':      {'drc_modifier'},
    'ORTHOGONAL':  {'drc_modifier'},
    'CENTERS':     {'drc_modifier'},
    'ALSO':        {'drc_modifier'},
    'ONLY':        {'drc_modifier'},
    'COUNT':       {'drc_modifier'},
    'PERIMETER':   {'drc_modifier', 'expr_starter'},
    'HIER':        {'drc_modifier'},
    'CELL':        {'drc_modifier'},
    'PROJECTING':  {'drc_modifier'},
    'PARALLEL':    {'drc_modifier'},
    'PERPENDICULAR': {'drc_modifier'},
    'LVSCAREFUL':  {'drc_modifier'},

    # --- keywords that are both drc_modifier and expr_starter ---
    'DRAWN':       {'directive_head', 'drc_modifier', 'expr_starter'},
    'STAMP':       {'directive_head', 'expr_starter'},
    'DFM':         {'directive_head', 'expr_starter'},
    'RET':         {'directive_head', 'expr_starter'},
    'RECTANGLE':   {'drc_modifier', 'expr_starter'},
    'CONVEX':      {'drc_modifier', 'expr_starter'},
    'LENGTH':      {'drc_modifier', 'expr_starter'},
    'WITH':        {'drc_modifier', 'expr_starter'},
    'EDGE':        {'drc_modifier'},
    'STEP':        {'drc_modifier', 'svrf_keyword'},

    # --- expr starters only ---
    'PUSH':        {'expr_starter'},
    'MERGE':       {'expr_starter'},
    'SIZE':        {'expr_starter'},
    'SHIFT':       {'expr_starter'},
    'GROW':        {'expr_starter'},
    'SHRINK':      {'expr_starter'},
    'RECTANGLES':  {'expr_starter'},
    'EXTENTS':     {'expr_starter'},
    'AREA':        {'expr_starter'},
    'VERTEX':      {'expr_starter'},
    'ANGLE':       {'expr_starter'},
    'EXPAND':      {'expr_starter'},
    'PATH':        {'expr_starter'},

    # --- svrf_keyword only (not in other sets) ---
    'OF':          {'svrf_keyword'},
    'TRUNCATE':    {'svrf_keyword'},
    'LAYER':       {'svrf_keyword'},
    'CONNECT':     {'svrf_keyword'},
    'SCONNECT':    {'svrf_keyword'},
    'DEVICE':      {'svrf_keyword'},
    'DMACRO':      {'svrf_keyword'},
    'ATTACH':      {'svrf_keyword'},
    'GROUP':       {'svrf_keyword'},
    'TRACE':       {'svrf_keyword'},
    'PROPERTY':    {'svrf_keyword'},
    'IF':          {'svrf_keyword'},
    'ELSE':        {'svrf_keyword'},
    'ENDIF':       {'svrf_keyword'},
    'CMACRO':      {'svrf_keyword'},
    'UNDEROVER':   {'svrf_keyword'},
    'OVERUNDER':   {'svrf_keyword'},
}

# ---------------------------------------------------------------------------
# Derived frozensets (backward-compatible with existing import sites)
# ---------------------------------------------------------------------------

_DIRECTIVE_HEADS = frozenset(
    k for k, roles in _KEYWORD_REGISTRY.items() if 'directive_head' in roles
)

_BINARY_OPS = frozenset(
    k for k, roles in _KEYWORD_REGISTRY.items() if 'binary_op' in roles
)

_UNARY_OPS = frozenset(
    k for k, roles in _KEYWORD_REGISTRY.items() if 'unary_op' in roles
)

_DRC_OPS = frozenset(
    k for k, roles in _KEYWORD_REGISTRY.items() if 'drc_op' in roles
)

_DRC_MODIFIERS = frozenset(
    k for k, roles in _KEYWORD_REGISTRY.items() if 'drc_modifier' in roles
)

_EXPR_STARTERS = frozenset(
    k for k, roles in _KEYWORD_REGISTRY.items() if 'expr_starter' in roles
)

# _SVRF_KEYWORDS is the union of all categorized keywords plus those
# tagged explicitly as 'svrf_keyword'.
_SVRF_KEYWORDS = (
    _DIRECTIVE_HEADS | _DRC_MODIFIERS | _EXPR_STARTERS
    | frozenset(k for k, roles in _KEYWORD_REGISTRY.items() if 'svrf_keyword' in roles)
)

# Binding powers for layer binary operators (not derived from registry
# because the values are numeric, not role tags).
_LAYER_BP = {
    'OR': 10,
    'XOR': 10,
    'AND': 20,
    'NOT': 20,
    'INSIDE': 30,
    'OUTSIDE': 30,
    'OUT': 30,
    'INTERACT': 30,
    'TOUCH': 30,
    'ENCLOSE': 30,
    'IN': 30,
    'COIN': 30,
    'COINCIDENT': 30,
    'CUT': 30,
    'BY': 35,
}
