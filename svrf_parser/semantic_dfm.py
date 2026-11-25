"""Static checks on the primitive in an ordered DFM SPEC FILL SHAPE."""

from . import ast

_PRIMITIVES = {"RECTFILL": 4, "POLYFILL": 6, "ARRAYFILL": 4, "STRETCHFILL": 7, "STRIPE": 1}


def validate_fill_shape(validator, node):
    if (node.kind, node.variant) != ("FILL", "SHAPE"):
        return
    if node.arguments:
        validator.error("semantic.dfm.unexpected_shape_argument",
                        "Expected a fill primitive after the shape name", node.arguments[0])

    def counts(statements, incoming):
        possible = incoming
        for item in statements:
            if isinstance(item, ast.IfDef):
                possible = counts(item.then_body, possible) | counts(item.else_body, possible)
                continue
            if not isinstance(item, ast.DfmClause) or not item.keywords:
                continue
            head = item.keywords[0]
            if head not in _PRIMITIVES:
                continue
            possible = {min(n + 1, 2) for n in possible}
            size = len(item.arguments)
            if (size < _PRIMITIVES[head] or (head == "POLYFILL" and size % 2)
                    or (head == "STRETCHFILL" and size != 7)):
                validator.error("semantic.dfm.shape_arguments",
                                f"{head} has an invalid number of shape arguments", item)
            if head == "RECTFILL" and size > 4:
                extra = item.arguments[4]
                if not isinstance(extra, ast.LayerRef) or extra.name != "DISCRETEWIDTH":
                    validator.error("semantic.dfm.shape_arguments", "Unexpected argument after RECTFILL coordinates", extra)
            if head == "ARRAYFILL" and size >= 4:
                words = [arg.name if isinstance(arg, ast.LayerRef) else None for arg in item.arguments]
                if not (size in (10, 11) and words[4] == "ASTEP" and words[-4] == "NCOL" and words[-2] == "NROW"):
                    validator.error("semantic.dfm.shape_arguments",
                                    "ARRAYFILL requires ASTEP, NCOL and NROW after its coordinates", item)
        return possible

    if counts(node.body, {0}) != {1}:
        validator.error("semantic.dfm.shape_primitive",
                        "DFM SPEC FILL SHAPE requires exactly one fill primitive in each branch", node)
