"""AST node classes for the SVRF parse tree."""


class AstNode:
    """Base class for all AST nodes."""
    __slots__ = ('line', 'col')

    def __init__(self, line=0, col=0):
        self.line = line
        self.col = col

    def accept(self, visitor):
        """Double-dispatch: calls visitor.visit_<NodeType>(self)."""
        method_name = 'visit_' + type(self).__name__
        method = getattr(visitor, method_name, visitor.generic_visit)
        return method(self)


class Program(AstNode):
    __slots__ = ('statements',)

    def __init__(self, statements=None, **kw):
        super().__init__(**kw)
        self.statements = statements or []


# ---- Preprocessor ----

class Define(AstNode):
    __slots__ = ('name', 'value')

    def __init__(self, name='', value=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.value = value


class IfDef(AstNode):
    __slots__ = ('name', 'value', 'negated', 'then_body', 'else_body')

    def __init__(self, name='', value=None, negated=False,
                 then_body=None, else_body=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.value = value
        self.negated = negated
        self.then_body = then_body or []
        self.else_body = else_body or []


class Include(AstNode):
    __slots__ = ('path',)

    def __init__(self, path='', **kw):
        super().__init__(**kw)
        self.path = path


class EncryptedBlock(AstNode):
    __slots__ = ('content',)

    def __init__(self, content='', **kw):
        super().__init__(**kw)
        self.content = content


# ---- Layer Definitions ----

class LayerDef(AstNode):
    __slots__ = ('name', 'numbers')

    def __init__(self, name='', numbers=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.numbers = numbers or []


class LayerMap(AstNode):
    __slots__ = ('gds_num', 'map_type', 'type_num', 'internal_num')

    def __init__(self, gds_num=0, map_type='DATATYPE',
                 type_num=0, internal_num=0, **kw):
        super().__init__(**kw)
        self.gds_num = gds_num
        self.map_type = map_type
        self.type_num = type_num
        self.internal_num = internal_num


# ---- Variable ----

class VariableDef(AstNode):
    __slots__ = ('name', 'expr')

    def __init__(self, name='', expr=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.expr = expr


# ---- Directive (catch-all for multi-word statements) ----

class Directive(AstNode):
    __slots__ = ('keywords', 'arguments', 'property_block')

    def __init__(self, keywords=None, arguments=None,
                 property_block=None, **kw):
        super().__init__(**kw)
        self.keywords = keywords or []
        self.arguments = arguments or []
        self.property_block = property_block


# ---- Layer Assignment / Derivation ----

class LayerAssignment(AstNode):
    __slots__ = ('name', 'expression')

    def __init__(self, name='', expression=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.expression = expression


# ---- Rule Check Block ----

class RuleCheckBlock(AstNode):
    __slots__ = ('name', 'description', 'body')

    def __init__(self, name='', description=None, body=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.description = description
        self.body = body or []


# ---- CONNECT / SCONNECT ----

class Connect(AstNode):
    __slots__ = ('soft', 'layers', 'via_layer')

    def __init__(self, soft=False, layers=None, via_layer=None, **kw):
        super().__init__(**kw)
        self.soft = soft
        self.layers = layers or []
        self.via_layer = via_layer


# ---- DEVICE ----

class Device(AstNode):
    __slots__ = ('device_type', 'device_name', 'seed_layer',
                 'pins', 'aux_layers', 'cmacro', 'cmacro_args')

    def __init__(self, device_type=None, device_name=None,
                 seed_layer='', pins=None, aux_layers=None,
                 cmacro=None, cmacro_args=None, **kw):
        super().__init__(**kw)
        self.device_type = device_type
        self.device_name = device_name
        self.seed_layer = seed_layer
        self.pins = pins or []
        self.aux_layers = aux_layers or []
        self.cmacro = cmacro
        self.cmacro_args = cmacro_args or []


# ---- DMACRO ----

class DMacro(AstNode):
    __slots__ = ('name', 'params', 'body')

    def __init__(self, name='', params=None, body=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.params = params or []
        self.body = body or []


class PropertyBlock(AstNode):
    __slots__ = ('properties', 'body')

    def __init__(self, properties=None, body=None, **kw):
        super().__init__(**kw)
        self.properties = properties or []
        self.body = body or []


# ---- Miscellaneous Statements ----

class Group(AstNode):
    __slots__ = ('name', 'pattern')

    def __init__(self, name='', pattern='', **kw):
        super().__init__(**kw)
        self.name = name
        self.pattern = pattern


class Attach(AstNode):
    __slots__ = ('layer', 'net')

    def __init__(self, layer='', net='', **kw):
        super().__init__(**kw)
        self.layer = layer
        self.net = net


class TraceProperty(AstNode):
    __slots__ = ('device', 'args')

    def __init__(self, device='', args=None, **kw):
        super().__init__(**kw)
        self.device = device
        self.args = args or []


# ---- Expression Nodes ----

class Expression(AstNode):
    """Base class for expression nodes."""
    pass


class BinaryOp(Expression):
    __slots__ = ('op', 'left', 'right')

    def __init__(self, op='', left=None, right=None, **kw):
        super().__init__(**kw)
        self.op = op
        self.left = left
        self.right = right


class UnaryOp(Expression):
    __slots__ = ('op', 'operand')

    def __init__(self, op='', operand=None, **kw):
        super().__init__(**kw)
        self.op = op
        self.operand = operand


class LayerRef(Expression):
    __slots__ = ('name',)

    def __init__(self, name='', **kw):
        super().__init__(**kw)
        self.name = name


class NumberLiteral(Expression):
    __slots__ = ('value',)

    def __init__(self, value=0, **kw):
        super().__init__(**kw)
        self.value = value


class StringLiteral(Expression):
    __slots__ = ('value',)

    def __init__(self, value='', **kw):
        super().__init__(**kw)
        self.value = value


class FuncCall(Expression):
    __slots__ = ('name', 'args')

    def __init__(self, name='', args=None, **kw):
        super().__init__(**kw)
        self.name = name
        self.args = args or []


class Constraint(AstNode):
    __slots__ = ('op', 'value')

    def __init__(self, op='', value=None, **kw):
        super().__init__(**kw)
        self.op = op
        self.value = value


class ConstrainedExpr(Expression):
    __slots__ = ('expr', 'constraints', 'modifiers')

    def __init__(self, expr=None, constraints=None, modifiers=None, **kw):
        super().__init__(**kw)
        self.expr = expr
        self.constraints = constraints or []
        self.modifiers = modifiers or []


class DRCOp(Expression):
    __slots__ = ('op', 'operands', 'constraints', 'modifiers')

    def __init__(self, op='', operands=None,
                 constraints=None, modifiers=None, **kw):
        super().__init__(**kw)
        self.op = op
        self.operands = operands or []
        self.constraints = constraints or []
        self.modifiers = modifiers or []


class VarRef(AstNode):
    """Variable reference in description text: ^VARNAME."""
    __slots__ = ('name',)

    def __init__(self, name='', **kw):
        super().__init__(**kw)
        self.name = name


class ErrorNode(AstNode):
    """Represents an unrecognized or erroneous construct in the source."""
    __slots__ = ('message', 'skipped_text')

    def __init__(self, message='', skipped_text='', **kw):
        super().__init__(**kw)
        self.message = message
        self.skipped_text = skipped_text


class IfExpr(AstNode):
    __slots__ = ('condition', 'then_body', 'elseifs', 'else_body')

    def __init__(self, condition=None, then_body=None,
                 elseifs=None, else_body=None, **kw):
        super().__init__(**kw)
        self.condition = condition
        self.then_body = then_body or []
        self.elseifs = elseifs or []
        self.else_body = else_body or []
