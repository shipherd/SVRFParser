"""AST Pretty-Printer: converts AST nodes back to SVRF text.

Used for round-trip testing: parse -> print -> re-parse -> compare.
Not intended to reproduce original formatting exactly, only semantic equivalence.
"""

import re

from . import ast_nodes as ast
from .modifiers import NamedModifier, as_modifier


class SvrfPrinter:
    """Emit SVRF text from AST nodes."""

    def emit(self, node):
        """Dispatch to the appropriate emit method."""
        method = '_emit_' + type(node).__name__
        fn = getattr(self, method, None)
        if fn:
            return fn(node)
        return f"/* unknown {type(node).__name__} */"

    @staticmethod
    def _quote(value):
        escaped = str(value).replace('\\', '\\\\').replace('"', '\\"')
        escaped = escaped.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        return '"' + escaped + '"'

    def _name(self, name):
        if name == name.upper() and re.fullmatch(r"[A-Z_][A-Z0-9_.]*", name):
            return name
        return self._quote(name)

    def _operand(self, node):
        text = self.emit(node)
        if isinstance(node, (ast.BinaryOp, ast.ConstrainedExpr, ast.DRCOp)):
            return f"({text})"
        return text

    # ---- Program ----

    def _emit_Program(self, node):
        lines = []
        for stmt in node.statements:
            lines.append(self.emit(stmt))
        return '\n'.join(lines)

    # ---- Preprocessor ----

    def _emit_Define(self, node):
        if node.value is not None:
            return f"#DEFINE {node.name} {node.value}"
        return f"#DEFINE {node.name}"

    def _emit_IfDef(self, node):
        if node.name.startswith("$"):
            env = node.name[1:]
            name = "$" + (env if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env) else self._quote(env))
        else:
            name = self._name(node.name)
        parts = [f"{node.directive} {name}"]
        if node.value:
            parts[0] += f" {node.value}"
        for s in node.then_body:
            parts.append(self.emit(s))
        if node.else_body:
            parts.append("#ELSE")
            for s in node.else_body:
                parts.append(self.emit(s))
        parts.append("#ENDIF")
        return '\n'.join(parts)

    _emit_IfDefExp = _emit_IfDef

    def _emit_Include(self, node):
        keyword = "#INCLUDE" if getattr(node, "preprocessor", False) else "INCLUDE"
        return f'{keyword} {self._quote(node.path)}'

    def _emit_EncryptedBlock(self, node):
        return f"{node.directive}\n{node.content}\n#ENDCRYPT"

    # ---- Layer Definitions ----

    def _emit_LayerDef(self, node):
        nums = ' '.join(str(n) for n in node.numbers)
        name = self._quote(node.name) if node.name in {"MAP", "RESOLUTION"} else self._name(node.name)
        return f"LAYER {name} {nums}"

    def _emit_LayerMap(self, node):
        def selector(value):
            return ' '.join(self.emit(c) for c in value) if isinstance(value, list) else str(value)
        text = f"LAYER MAP {selector(node.gds_num)} {node.map_type} {selector(node.type_num)} {node.internal_num}"
        return text if node.target_texttype is None else f"{text} {node.target_texttype}"

    def _emit_VariableDef(self, node):
        values = "ENVIRONMENT" if node.environment else ' '.join(self.emit(value) for value in node.values)
        return f"VARIABLE {self._name(node.name)} {values}".rstrip()

    # ---- Directive ----

    def _emit_DfmSpec(self, node):
        parts = ["DFM SPEC " + node.kind]
        if node.variant:
            parts.append(node.variant)
        parts.append(self._name(node.name))
        parts.extend(self.emit(argument) for argument in node.arguments)
        return '\n'.join([' '.join(parts)] + [self.emit(clause) for clause in node.body])

    def _emit_LocalSvrf(self, node):
        inputs = ' '.join(self._name(name) + ("(NODAL)" if nodal else "") for name, nodal in node.inputs)
        outputs = ' '.join(map(self._name, node.outputs))
        header = f"DFM SPEC SVRF {self._name(node.name)} ({inputs} : {outputs})"
        if node.variables:
            defaults = (self._name(key) + (" = " + self.emit(v) if v is not None else "") for key, v in node.variables)
            header += " VARIABLES [" + " ".join(defaults) + "]"
        return '\n'.join([header + (" [/*" if node.wrapped else " ["), *(self.emit(s) for s in node.body),
                          ("*/]" if node.wrapped else "]") + (" CENTER" if node.center else "")])

    def _emit_DfmClause(self, node):
        return ' '.join(list(node.keywords) + [self.emit(argument) for argument in node.arguments])

    def _emit_BracketExpr(self, node):
        return '[' + ' '.join(self.emit(item) for item in node.items) + ']'

    def _emit_PercLoad(self, node):
        return '\n'.join(['PERC LOAD ' + self._name(node.function)] + [self.emit(item) for item in node.body])

    def _emit_PercGroup(self, node):
        return '(' + ' '.join(self.emit(item) for item in node.items) + ')'

    def _emit_Directive(self, node):
        parts = list(node.keywords)
        if parts == ["TVF", "FUNCTION"] and node.arguments:
            name = node.arguments[-2]
            return " ".join([*parts, *node.arguments[:-2], self._quote(name) if name in {"EDGE", "ERROR"} else self._name(name),
                             node.arguments[-1]])
        if parts[:1] == ["#PRAGMA"]:
            return " ".join([*parts, *(self._quote(arg) for arg in node.arguments)])
        is_description = (node.keywords == ['@'])
        for a in node.arguments:
            if isinstance(a, ast.Include) and a.embedded:
                parts.append('\n' + self.emit(a))
                continue
            if isinstance(a, ast.AstNode):
                parts.append(self.emit(a))
            elif isinstance(a, str):
                if is_description:
                    # Description text is not quoted
                    parts.append(a)
                elif a != a.upper() or ' ' in a or '.' in a or '/' in a or '\\' in a:
                    parts.append(self._quote(a))
                else:
                    parts.append(a)
            else:
                parts.append(str(a))
        result = ' '.join(parts)
        if node.property_block:
            result += '\n' + self.emit(node.property_block)
        return result

    # ---- Layer Assignment ----

    def _emit_LayerAssignment(self, node):
        expr_str = self.emit(node.expression) if node.expression else ''
        return f"{self._name(node.name)} = {expr_str}"

    # ---- Rule Check Block ----

    def _emit_RuleCheckBlock(self, node):
        parts = [f"{self._name(node.name)} {{"]
        if node.description:
            for line_segs in node.description:
                parts.append(f"  @ {self._emit_desc_line(line_segs)}")
        for s in node.body:
            parts.append(f"  {self.emit(s)}")
        parts.append("}")
        return '\n'.join(parts)

    def _emit_desc_line(self, segments):
        """Emit a description line from a list of str/VarRef segments."""
        parts = []
        for seg in segments:
            if isinstance(seg, ast.VarRef):
                parts.append(f"^{seg.name}")
            else:
                parts.append(seg)
        return ' '.join(parts)

    # ---- Connectivity ----

    def _emit_Connect(self, node):
        keyword = "SCONNECT" if node.soft else "CONNECT"
        parts = [keyword] + [self._name(layer) for layer in node.layers]
        if node.via_layer:
            parts.extend(["BY", self._name(node.via_layer)])
        if node.link_name is not None:
            parts.extend(["LINK", self._quote(node.link_name)])
        if node.abut_also:
            parts.extend(["ABUT", "ALSO"])
        return ' '.join(parts)

    # ---- Device ----

    def _emit_Device(self, node):
        parts = ["DEVICE"]
        if node.device_type:
            if node.device_name:
                parts.append(f"{self._name(node.device_type)}({self._name(node.device_name)})")
            else:
                parts.append(self._name(node.device_type))
        elif node.device_name:
            parts.append(self._name(node.device_name))
        if node.seed_layer:
            parts.append(self._name(node.seed_layer))
        for pin in node.pins:
            if isinstance(pin, tuple) and len(pin) == 2:
                name = self._name(pin[0])
                parts.append(f"{name}({self._name(pin[1])})" if pin[1] is not None else name)
            else:
                parts.append(str(pin))
        aux = iter(node.aux_layers)
        tail = []
        for layer in aux:
            if layer.startswith("["):
                tail = [layer, *aux]
                break
            parts.append(f"<{self._name(layer)}>")
        for group in node.swap_lists:
            pins = ("[" + " ".join(map(self._name, g)) + "]" for g in group) if isinstance(group[0], list) else map(self._name, group)
            parts.append("(" + " ".join(pins) + ")")
        if node.connection_mode:
            parts.extend(("BY", node.connection_mode))
        if node.cmacro:
            parts.append("CMACRO")
            parts.append(node.cmacro)
            for a in node.cmacro_args:
                parts.append(self._operand(a) if isinstance(a, ast.AstNode) else str(a))
        for kind, name in node.netlist_options:
            parts.extend(("NETLIST", kind, self._name(name)))
        if node.text_model_layer:
            parts.extend(("TEXT MODEL LAYER", self._name(node.text_model_layer)))
        if node.text_property_layers:
            parts.append("TEXT PROPERTY LAYER")
            parts.extend(map(self._name, node.text_property_layers))
        if node.signature:
            key, layers = node.signature
            parts.extend(("SIGNATURE", "?" if key is None else self._quote(key), *map(self._name, layers)))
        if node.template:
            parts.extend(("TEMPLATE", self._name(node.template)))
        parts.extend(layer if layer.startswith("[") else f"<{self._name(layer)}>" for layer in tail)
        return ' '.join(parts)

    # ---- DMacro ----

    def _emit_DMacro(self, node):
        params = ' '.join(self._name(param) for param in node.params)
        if params:
            header = f"DMACRO {self._name(node.name)} {params} {{"
        else:
            header = f"DMACRO {self._name(node.name)} {{"
        parts = [header]
        for s in node.body:
            parts.append(f"  {self.emit(s)}")
        parts.append("}")
        return '\n'.join(parts)

    def _emit_MacroCall(self, node):
        args = ' '.join(self._operand(a) if isinstance(a, ast.AstNode) else str(a) for a in node.arguments)
        if node.kind == "FMACRO":
            return f"FMACRO {self._name(node.name)}({args})"
        return f"{node.kind} {self._name(node.name)} {args}".rstrip()

    # ---- Property Block ----

    def _emit_PropertyBlock(self, node):
        props = ', '.join(node.properties)
        parts = [f"[PROPERTY {props}"]
        for s in node.body:
            parts.append(f"  {self.emit(s)}")
        parts.append("]")
        return '\n'.join(parts)

    # ---- Misc Statements ----

    def _emit_Group(self, node):
        return f"GROUP {node.name} {node.pattern}".rstrip()

    def _emit_Attach(self, node):
        return f"ATTACH {node.layer} {node.net}"

    def _emit_TraceProperty(self, node):
        args = ' '.join(str(a) for a in node.args)
        return f"TRACE PROPERTY {node.device} {args}".rstrip()

    # ---- Expressions ----

    def _emit_BinaryOp(self, node):
        if node.op == "?:" and isinstance(node.right, ast.BinaryOp) and node.right.op == ":":
            return f"{self._operand(node.left)} ? {self.emit(node.right.left)} : {self._operand(node.right.right)}"
        left = self._operand(node.left) if node.left else ''
        right = self._operand(node.right) if node.right else ''
        return f"{left} {node.op} {right}"

    def _emit_UnaryOp(self, node):
        operand = self._operand(node.operand) if node.operand else ''
        return f"{node.op} {operand}"

    def _emit_LayerRef(self, node):
        return node.name

    def _emit_NumberLiteral(self, node):
        if isinstance(node.value, float) and node.value == int(node.value):
            # Preserve decimal form for values like 0.0
            return str(node.value)
        return str(node.value)

    def _emit_StringLiteral(self, node):
        return self._quote(node.value)

    def _emit_FuncCall(self, node):
        args = ', '.join(self.emit(a) for a in node.args)
        return f"{node.name}({args})"

    # ---- Constraints ----

    def _emit_Constraint(self, node):
        val = self._operand(node.value) if isinstance(node.value, ast.AstNode) else str(node.value)
        return f"{node.op} {val}"

    def _emit_ConstrainedExpr(self, node):
        expr_str = self.emit(node.expr) if node.expr else ''
        parts = [expr_str]
        for c in node.constraints:
            parts.append(self.emit(c))
        for m in node.modifier_nodes:
            parts.append(self._emit_modifier(m))
        return ' '.join(parts)

    # ---- DRC Op ----

    def _emit_DRCOp(self, node):
        parts = [node.op]
        for op in node.operands:
            if isinstance(op, str):
                parts.append(op)
            else:
                parts.append(self._operand(op))
        for c in node.constraints:
            parts.append(self.emit(c))
        for m in node.modifier_nodes:
            parts.append(self._emit_modifier(m))
        return ' '.join(parts)

    def _emit_modifier(self, m):
        """Render modifiers through the shared compatibility adapter."""
        modifier = as_modifier(m)
        value = modifier.value
        if isinstance(value, ast.AstNode):
            rendered = self._operand(value) if isinstance(modifier, NamedModifier) else self.emit(value)
        else:
            rendered = str(value)
        return f"{modifier.name} {rendered}" if isinstance(modifier, NamedModifier) else rendered

    # ---- IfExpr (inside DMACRO / PropertyBlock) ----

    def _emit_IfExpr(self, node):
        cond = self.emit(node.condition) if node.condition else ''
        parts = [f"IF ({cond}) {{"]
        for s in node.then_body:
            parts.append(f"  {self.emit(s)}")
        parts.append("}")
        for elseif_cond, elseif_body in (node.elseifs or []):
            ec = self.emit(elseif_cond) if elseif_cond else ''
            parts.append(f"ELSE IF ({ec}) {{")
            for s in elseif_body:
                parts.append(f"  {self.emit(s)}")
            parts.append("}")
        if node.else_body:
            parts.append("ELSE {")
            for s in node.else_body:
                parts.append(f"  {self.emit(s)}")
            parts.append("}")
        return '\n'.join(parts)

    # ---- VarRef ----

    def _emit_VarRef(self, node):
        return f"^{node.name}"

    def _emit_ErrorNode(self, node):
        return node.skipped_text or f"/* {node.message} */"
