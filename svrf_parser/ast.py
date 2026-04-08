"""AST node classes for the reconstructed SVRF parser.

The module keeps the historic node names used by this repository while also
providing the clearer names proposed in ``instruct.md``.
"""


from functools import lru_cache


_POSITION_FIELDS = (
    "line",
    "col",
    "end_line",
    "end_col",
    "start_offset",
    "end_offset",
    "source_text",
)


@lru_cache(maxsize=None)
def _slot_names_for(cls):
    names = []
    for base in reversed(cls.__mro__):
        if base is object:
            continue
        for slot in getattr(base, "__slots__", ()):
            if isinstance(slot, str):
                names.append(slot)
    return tuple(names)


def _iter_slot_names(cls):
    return _slot_names_for(cls)


def _iter_direct_child_nodes(value):
    if isinstance(value, AstNode):
        yield value
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_direct_child_nodes(item)
        return
    if isinstance(value, tuple):
        for item in value:
            yield from _iter_direct_child_nodes(item)


def _value_to_dict(value, include_position):
    if isinstance(value, AstNode):
        return value.to_dict(include_position=include_position)
    if isinstance(value, list):
        return [_value_to_dict(item, include_position) for item in value]
    if isinstance(value, tuple):
        return tuple(_value_to_dict(item, include_position) for item in value)
    return value


class AstNode:
    """Base class for all AST nodes."""

    __slots__ = _POSITION_FIELDS

    def __init__(
        self,
        line=0,
        col=0,
        end_line=0,
        end_col=0,
        start_offset=0,
        end_offset=0,
        source_text=None,
    ):
        self.line = line
        self.col = col
        self.end_line = end_line or line
        self.end_col = end_col or col
        self.start_offset = start_offset
        self.end_offset = end_offset
        self.source_text = source_text

    def accept(self, visitor):
        method_name = "visit_" + type(self).__name__
        method = getattr(visitor, method_name, visitor.generic_visit)
        return method(self)

    @property
    def span(self):
        return ((self.line, self.col), (self.end_line, self.end_col))

    @property
    def has_span(self):
        return self.end_offset > self.start_offset or (
            self.line > 0 and self.col > 0 and self.end_line > 0 and self.end_col > 0
        )

    def set_span(
        self,
        line,
        col,
        end_line,
        end_col,
        start_offset=0,
        end_offset=0,
        source_text=None,
    ):
        self.line = line
        self.col = col
        self.end_line = end_line
        self.end_col = end_col
        self.start_offset = start_offset
        self.end_offset = end_offset
        self.source_text = source_text
        return self

    def iter_fields(self, include_position=False):
        for slot in _iter_slot_names(type(self)):
            if not include_position and slot in _POSITION_FIELDS:
                continue
            yield slot, getattr(self, slot, None)

    def to_dict(self, include_position=True):
        data = {"type": type(self).__name__}
        for name, value in self.iter_fields(include_position=include_position):
            data[name] = _value_to_dict(value, include_position)
        return data

    def structurally_equal(self, other, include_position=False):
        if type(self) is not type(other):
            return False
        return self.to_dict(include_position=include_position) == other.to_dict(
            include_position=include_position
        )

    def walk(self):
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            children = []
            for _, value in node.iter_fields(include_position=False):
                children.extend(_iter_direct_child_nodes(value))
            stack.extend(reversed(children))

    def __repr__(self):
        fields = []
        for name, value in self.iter_fields(include_position=False):
            fields.append(f"{name}={value!r}")
        joined = ", ".join(fields)
        return f"{type(self).__name__}({joined})"


class Program(AstNode):
    __slots__ = ("statements",)

    def __init__(self, statements=None, **kw):
        super().__init__(**kw)
        self.statements = statements or []


class Define(AstNode):
    __slots__ = ("name", "value")

    def __init__(self, name="", value=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.value = value


class IfDef(AstNode):
    __slots__ = ("name", "value", "negated", "then_body", "else_body")

    def __init__(self, name="", value=None, negated=False,
                 then_body=None, else_body=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.value = value
        self.negated = negated
        self.then_body = then_body or []
        self.else_body = else_body or []


class Include(AstNode):
    __slots__ = ("path", "embedded", "preprocessor")

    def __init__(self, path="", embedded=False, preprocessor=False, **kw):
        super().__init__(**kw)
        self.path = path
        self.embedded = embedded
        self.preprocessor = preprocessor


class EncryptedBlock(AstNode):
    __slots__ = ("content",)

    def __init__(self, content="", **kw):
        super().__init__(**kw)
        self.content = content


class LayerDef(AstNode):
    __slots__ = ("name", "numbers")

    def __init__(self, name="", numbers=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.numbers = numbers or []

    @property
    def originals(self):
        return self.numbers


class LayerMap(AstNode):
    __slots__ = ("gds_num", "map_type", "type_num", "internal_num")

    def __init__(self, gds_num=0, map_type="DATATYPE",
                 type_num=0, internal_num=0, **kw):
        super().__init__(**kw)
        self.gds_num = gds_num
        self.map_type = map_type
        self.type_num = type_num
        self.internal_num = internal_num


class VariableDef(AstNode):
    __slots__ = ("name", "values", "environment")

    def __init__(self, name="", values=None, environment=False, **kw):
        super().__init__(**kw)
        self.name = name
        self.values = values or []
        self.environment = environment

    @property
    def expr(self):
        if not self.values:
            return None
        if len(self.values) == 1:
            return self.values[0]
        if all(isinstance(value, StringLiteral) for value in self.values):
            joined = " ".join(value.value for value in self.values)
            return StringLiteral(value=joined, line=self.line, col=self.col)
        return self.values[0]


class Directive(AstNode):
    __slots__ = ("keywords", "arguments", "property_block")

    def __init__(self, keywords=None, arguments=None,
                 property_block=None, **kw):
        super().__init__(**kw)
        self.keywords = keywords or []
        self.arguments = arguments or []
        self.property_block = property_block


class LayerAssignment(AstNode):
    __slots__ = ("name", "expression")

    def __init__(self, name="", expression=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.expression = expression


class RuleCheckBlock(AstNode):
    __slots__ = ("name", "comments", "body")

    def __init__(self, name="", comments=None, body=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.comments = comments
        self.body = body or []

    @property
    def description(self):
        return self.comments


class Connect(AstNode):
    __slots__ = ("soft", "layers", "via_layer", "link_name", "abut_also")

    def __init__(self, soft=False, layers=None, via_layer=None,
                 link_name=None, abut_also=False, **kw):
        super().__init__(**kw)
        self.soft = soft
        self.layers = layers or []
        self.via_layer = via_layer
        self.link_name = link_name
        self.abut_also = abut_also

    @property
    def by_layer(self):
        return self.via_layer


class Device(AstNode):
    __slots__ = ("device_type", "device_name", "seed_layer",
                 "pins", "aux_layers", "cmacro", "cmacro_args")

    def __init__(self, device_type=None, device_name=None,
                 seed_layer="", pins=None, aux_layers=None,
                 cmacro=None, cmacro_args=None, **kw):
        super().__init__(**kw)
        self.device_type = device_type
        self.device_name = device_name
        self.seed_layer = seed_layer
        self.pins = pins or []
        self.aux_layers = aux_layers or []
        self.cmacro = cmacro
        self.cmacro_args = cmacro_args or []


class DMacro(AstNode):
    __slots__ = ("name", "params", "body")

    def __init__(self, name="", params=None, body=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.params = params or []
        self.body = body or []

    @property
    def parameters(self):
        return self.params


class MacroCall(AstNode):
    __slots__ = ("kind", "name", "arguments")

    def __init__(self, kind="CMACRO", name="", arguments=None, **kw):
        super().__init__(**kw)
        self.kind = kind
        self.name = name
        self.arguments = arguments or []


class PropertyBlock(AstNode):
    __slots__ = ("properties", "body")

    def __init__(self, properties=None, body=None, **kw):
        super().__init__(**kw)
        self.properties = properties or []
        self.body = body or []


class Group(AstNode):
    __slots__ = ("name", "members")

    def __init__(self, name="", members=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.members = members or []

    @property
    def pattern(self):
        return " ".join(str(member) for member in self.members)


class Attach(AstNode):
    __slots__ = ("layer", "net")

    def __init__(self, layer="", net="", **kw):
        super().__init__(**kw)
        self.layer = layer
        self.net = net


class TraceProperty(AstNode):
    __slots__ = ("device", "args")

    def __init__(self, device="", args=None, **kw):
        super().__init__(**kw)
        self.device = device
        self.args = args or []


class Expression(AstNode):
    """Base class for expression nodes."""


class BinaryOp(Expression):
    __slots__ = ("op", "left", "right")

    def __init__(self, op="", left=None, right=None, **kw):
        super().__init__(**kw)
        self.op = op
        self.left = left
        self.right = right


class UnaryOp(Expression):
    __slots__ = ("op", "operand")

    def __init__(self, op="", operand=None, **kw):
        super().__init__(**kw)
        self.op = op
        self.operand = operand


class LayerRef(Expression):
    __slots__ = ("name",)

    def __init__(self, name="", **kw):
        super().__init__(**kw)
        self.name = name


class NumberLiteral(Expression):
    __slots__ = ("value",)

    def __init__(self, value=0, **kw):
        super().__init__(**kw)
        self.value = value


class StringLiteral(Expression):
    __slots__ = ("value",)

    def __init__(self, value="", **kw):
        super().__init__(**kw)
        self.value = value


class FuncCall(Expression):
    __slots__ = ("name", "args")

    def __init__(self, name="", args=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.args = args or []


class Constraint(AstNode):
    __slots__ = ("op", "value")

    def __init__(self, op="", value=None, **kw):
        super().__init__(**kw)
        self.op = op
        self.value = value


class ConstrainedExpr(Expression):
    __slots__ = ("expr", "constraints", "modifiers")

    def __init__(self, expr=None, constraints=None, modifiers=None, **kw):
        super().__init__(**kw)
        self.expr = expr
        self.constraints = constraints or []
        self.modifiers = modifiers or []


class DRCOp(Expression):
    __slots__ = ("op", "operands", "constraints", "modifiers")

    def __init__(self, op="", operands=None,
                 constraints=None, modifiers=None, **kw):
        super().__init__(**kw)
        self.op = op
        self.operands = operands or []
        self.constraints = constraints or []
        self.modifiers = modifiers or []


class VarRef(AstNode):
    __slots__ = ("name",)

    def __init__(self, name="", **kw):
        super().__init__(**kw)
        self.name = name


class ErrorNode(AstNode):
    __slots__ = ("message", "skipped_text")

    def __init__(self, message="", skipped_text="", **kw):
        super().__init__(**kw)
        self.message = message
        self.skipped_text = skipped_text


class IfExpr(AstNode):
    __slots__ = ("condition", "then_body", "elseifs", "else_body")

    def __init__(self, condition=None, then_body=None,
                 elseifs=None, else_body=None, **kw):
        super().__init__(**kw)
        self.condition = condition
        self.then_body = then_body or []
        self.elseifs = elseifs or []
        self.else_body = else_body or []


# Canonical aliases requested in instruct.md.
SVRFDocument = Program
LayerDefinitionNode = LayerDef
LayerAssignmentNode = LayerAssignment
RuleCheckNode = RuleCheckBlock
VariableNode = VariableDef
IncludeNode = Include
DirectiveNode = Directive
ConnectNode = Connect
MacroDefinitionNode = DMacro
MacroCallNode = MacroCall
OperationNode = DRCOp
IdentifierNode = LayerRef
NumberNode = NumberLiteral
StringNode = StringLiteral
FunctionCallNode = FuncCall
UnaryOpNode = UnaryOp
BinaryOpNode = BinaryOp
ConstraintNode = Constraint
