"""Visitor pattern for SVRF AST nodes.

Provides ``AstVisitor`` with a ``visit_<NodeType>`` method for every AST
node class.  The default implementation of each method calls
``generic_visit``, which recurses into child nodes.
"""

from . import ast_nodes as ast


class AstVisitor:
    """Base visitor with double-dispatch via ``AstNode.accept(visitor)``.

    Subclass and override ``visit_XXX`` methods for the node types you
    care about.  Unhandled nodes fall through to ``generic_visit``.
    """

    def generic_visit(self, node):
        """Default handler: recurse into child nodes."""
        for child in _iter_children(node):
            if isinstance(child, ast.AstNode):
                child.accept(self)
            elif isinstance(child, list):
                for item in child:
                    if isinstance(item, ast.AstNode):
                        item.accept(self)

    # -- Top-level --
    def visit_Program(self, node):
        return self.generic_visit(node)

    # -- Statements --
    def visit_LayerDef(self, node):
        return self.generic_visit(node)

    def visit_LayerMap(self, node):
        return self.generic_visit(node)

    def visit_LayerAssignment(self, node):
        return self.generic_visit(node)

    def visit_Directive(self, node):
        return self.generic_visit(node)

    def visit_RuleCheckBlock(self, node):
        return self.generic_visit(node)

    def visit_Connect(self, node):
        return self.generic_visit(node)

    def visit_Device(self, node):
        return self.generic_visit(node)

    def visit_DMacro(self, node):
        return self.generic_visit(node)

    def visit_Define(self, node):
        return self.generic_visit(node)

    def visit_IfDef(self, node):
        return self.generic_visit(node)

    def visit_Include(self, node):
        return self.generic_visit(node)

    def visit_EncryptedBlock(self, node):
        return self.generic_visit(node)

    def visit_Group(self, node):
        return self.generic_visit(node)

    def visit_Attach(self, node):
        return self.generic_visit(node)

    def visit_TraceProperty(self, node):
        return self.generic_visit(node)

    def visit_VariableDef(self, node):
        return self.generic_visit(node)

    def visit_PropertyBlock(self, node):
        return self.generic_visit(node)

    def visit_IfExpr(self, node):
        return self.generic_visit(node)

    # -- Expressions --
    def visit_BinaryOp(self, node):
        return self.generic_visit(node)

    def visit_UnaryOp(self, node):
        return self.generic_visit(node)

    def visit_LayerRef(self, node):
        return self.generic_visit(node)

    def visit_NumberLiteral(self, node):
        return self.generic_visit(node)

    def visit_StringLiteral(self, node):
        return self.generic_visit(node)

    def visit_FuncCall(self, node):
        return self.generic_visit(node)

    def visit_Constraint(self, node):
        return self.generic_visit(node)

    def visit_ConstrainedExpr(self, node):
        return self.generic_visit(node)

    def visit_DRCOp(self, node):
        return self.generic_visit(node)

    # -- Error --
    def visit_ErrorNode(self, node):
        return self.generic_visit(node)


def _iter_children(node):
    """Yield all child attributes of an AST node that may contain sub-nodes."""
    for slot in getattr(node, '__slots__', ()):
        val = getattr(node, slot, None)
        if val is not None:
            yield val


class WalkVisitor(AstVisitor):
    """Example visitor that collects all visited nodes into a flat list."""

    def __init__(self):
        self.nodes = []

    def generic_visit(self, node):
        self.nodes.append(node)
        super().generic_visit(node)
