"""AST Pretty-Printer: converts AST nodes back to SVRF text.

Used for round-trip testing: parse -> print -> re-parse -> compare.
Not intended to reproduce original formatting exactly, only semantic equivalence.
"""

from . import ast_nodes as ast


class SvrfPrinter:
    """Emit SVRF text from AST nodes."""

    def emit(self, node):
        """Dispatch to the appropriate emit method."""
        method = '_emit_' + type(node).__name__
        fn = getattr(self, method, None)
        if fn:
            return fn(node)
        return f"/* unknown {type(node).__name__} */"

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
        tag = "#IFNDEF" if node.negated else "#IFDEF"
        parts = [f"{tag} {node.name}"]
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

    def _emit_Include(self, node):
        return f'#INCLUDE "{node.path}"'

    def _emit_EncryptedBlock(self, node):
        return f"#ENCRYPT\n{node.content}\n#ENDCRYPT"

    # ---- Layer Definitions ----

    def _emit_LayerDef(self, node):
        nums = ' '.join(str(n) for n in node.numbers)
        return f"LAYER {node.name} {nums}"

    def _emit_LayerMap(self, node):
        return (f"LAYER MAP {node.gds_num} {node.map_type} "
                f"{node.type_num} {node.internal_num}")

    def _emit_VariableDef(self, node):
        expr_str = self.emit(node.expr) if node.expr else ''
        return f"VARIABLE {node.name} {expr_str}".rstrip()

    # ---- Directive ----

    def _emit_Directive(self, node):
        parts = list(node.keywords)
        is_description = (node.keywords == ['@'])
        for a in node.arguments:
            if isinstance(a, ast.AstNode):
                parts.append(self.emit(a))
            elif isinstance(a, str):
                if is_description:
                    # Description text is not quoted
                    parts.append(a)
                elif ' ' in a or '.' in a or '/' in a or '\\' in a:
                    parts.append(f'"{a}"')
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
        return f"{node.name} = {expr_str}"

    # ---- Rule Check Block ----

    def _emit_RuleCheckBlock(self, node):
        parts = [f"{node.name} {{"]
        if node.description:
            if isinstance(node.description, ast.AstNode):
                # Description is a Directive with keywords=['@'], emit it directly
                parts.append(f"  {self.emit(node.description)}")
            else:
                parts.append(f"  @ {node.description}")
        for s in node.body:
            parts.append(f"  {self.emit(s)}")
        parts.append("}")
        return '\n'.join(parts)

    # ---- Connectivity ----

    def _emit_Connect(self, node):
        keyword = "SCONNECT" if node.soft else "CONNECT"
        parts = [keyword] + list(node.layers)
        if node.via_layer:
            parts.extend(["BY", node.via_layer])
        return ' '.join(parts)

    # ---- Device ----

    def _emit_Device(self, node):
        parts = ["DEVICE"]
        if node.device_type:
            if node.device_name:
                parts.append(f"{node.device_type}({node.device_name})")
            else:
                parts.append(node.device_type)
        if node.seed_layer:
            parts.append(node.seed_layer)
        for pin in node.pins:
            if isinstance(pin, tuple) and len(pin) == 2:
                parts.append(f"{pin[0]}({pin[1]})")
            else:
                parts.append(str(pin))
        for aux in node.aux_layers:
            parts.append(str(aux))
        if node.cmacro:
            parts.append("CMACRO")
            parts.append(node.cmacro)
            for a in node.cmacro_args:
                parts.append(str(a))
        return ' '.join(parts)

    # ---- DMacro ----

    def _emit_DMacro(self, node):
        params = ' '.join(node.params)
        if params:
            header = f"DMACRO {node.name} {params} {{"
        else:
            header = f"DMACRO {node.name} {{"
        parts = [header]
        for s in node.body:
            parts.append(f"  {self.emit(s)}")
        parts.append("}")
        return '\n'.join(parts)

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
        left = self.emit(node.left) if node.left else ''
        right = self.emit(node.right) if node.right else ''
        return f"{left} {node.op} {right}"

    def _emit_UnaryOp(self, node):
        operand = self.emit(node.operand) if node.operand else ''
        return f"{node.op} {operand}"

    def _emit_LayerRef(self, node):
        return node.name

    def _emit_NumberLiteral(self, node):
        if isinstance(node.value, float) and node.value == int(node.value):
            # Preserve decimal form for values like 0.0
            return str(node.value)
        return str(node.value)

    def _emit_StringLiteral(self, node):
        return f'"{node.value}"'

    def _emit_FuncCall(self, node):
        args = ', '.join(self.emit(a) for a in node.args)
        return f"{node.name}({args})"

    # ---- Constraints ----

    def _emit_Constraint(self, node):
        val = self.emit(node.value) if hasattr(node.value, 'line') else str(node.value)
        return f"{node.op} {val}"

    def _emit_ConstrainedExpr(self, node):
        expr_str = self.emit(node.expr) if node.expr else ''
        parts = [expr_str]
        for c in node.constraints:
            parts.append(self.emit(c))
        for m in (node.modifiers or []):
            parts.append(self._emit_modifier(m))
        return ' '.join(parts)

    # ---- DRC Op ----

    def _emit_DRCOp(self, node):
        parts = [node.op]
        for op in node.operands:
            if isinstance(op, str):
                parts.append(op)
            else:
                parts.append(self.emit(op))
        for c in node.constraints:
            parts.append(self.emit(c))
        for m in (node.modifiers or []):
            parts.append(self._emit_modifier(m))
        return ' '.join(parts)

    def _emit_modifier(self, m):
        """Emit a modifier which can be a string, AST node, or ('BY', expr) tuple."""
        if isinstance(m, tuple) and len(m) == 2 and m[0] == 'BY':
            return 'BY ' + self.emit(m[1]) if isinstance(m[1], ast.AstNode) else f'BY {m[1]}'
        if isinstance(m, ast.AstNode):
            return self.emit(m)
        return str(m)

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
