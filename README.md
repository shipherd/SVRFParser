# SVRFParser

A pure-Python parser for SVRF (Standard Verification Rule Format) files used by Calibre DRC, LVS, and antenna rule decks. Built with hand-written recursive descent and Pratt parsing. No third-party dependencies.

## Project Structure

```
svrf_parser/
  __init__.py        # Package entry point, exports parse / parse_file
  tokens.py          # TokenType enum and Token dataclass
  lexer.py           # Lexer: source text -> token stream
  ast_nodes.py       # AST node class hierarchy
  parser.py          # Recursive descent + Pratt parser
test_samples.py      # Batch test harness for sample files
samples/             # Sample SVRF files
```

## Usage

### Parse a File

```python
from svrf_parser import parse_file

tree = parse_file("path/to/calibre.drc")
print(f"{len(tree.statements)} statements parsed")
```

`parse_file` reads the file with UTF-8 encoding (replacing invalid bytes) and returns a `Program` AST node. The `Program.statements` list contains all top-level parsed statements.

### Parse a String

```python
from svrf_parser import parse

text = """\
LAYOUT PATH "design.gds"
LAYOUT PRIMARY "top_cell"

LAYER M1 10
LAYER VIA1 11
LAYER M2 12

CONNECT M1 M2 BY VIA1

VARIABLE WIDTH 0.1

M1_min = SIZE M1 BY 0.1

rule_check {
  @ M1 minimum width check
  INT M1 < 0.1
}
"""

tree = parse(text)
for stmt in tree.statements:
    print(type(stmt).__name__, getattr(stmt, 'line', ''))
```

Output:

```
Directive 1
Directive 2
LayerDef 4
LayerDef 5
LayerDef 6
Connect 8
VariableDef 10
LayerAssignment 12
RuleCheckBlock 14
```

The optional second argument `filename` is used in error messages:

```python
tree = parse(text, filename="my_rules.drc")
```

### Inspecting AST Nodes

Every AST node carries `line` and `col` attributes indicating its source location. Node-specific fields are accessed as regular attributes:

```python
from svrf_parser import parse_file
from svrf_parser.ast_nodes import LayerDef, LayerAssignment, RuleCheckBlock

tree = parse_file("path/to/rules.drc")

for stmt in tree.statements:
    if isinstance(stmt, LayerDef):
        print(f"Line {stmt.line}: LAYER {stmt.name} {stmt.numbers}")

    elif isinstance(stmt, LayerAssignment):
        print(f"Line {stmt.line}: {stmt.name} = <expr>")

    elif isinstance(stmt, RuleCheckBlock):
        print(f"Line {stmt.line}: Rule '{stmt.name}' "
              f"with {len(stmt.body)} operations")
```

### Extracting Layer Definitions

```python
from svrf_parser import parse_file
from svrf_parser.ast_nodes import LayerDef, LayerMap

tree = parse_file("path/to/rules.drc")

# Named layers: LAYER M1 10
layers = [s for s in tree.statements if isinstance(s, LayerDef)]
for layer in layers:
    print(f"LAYER {layer.name} {layer.numbers}")

# Layer mappings: LAYER MAP 62 DATATYPE 0 1062
maps = [s for s in tree.statements if isinstance(s, LayerMap)]
for m in maps:
    print(f"LAYER MAP {m.gds_num} {m.map_type} {m.type_num} {m.internal_num}")
```

### Extracting Connectivity

```python
from svrf_parser.ast_nodes import Connect

connects = [s for s in tree.statements if isinstance(s, Connect)]
for c in connects:
    kind = "SCONNECT" if c.soft else "CONNECT"
    via = f" BY {c.via_layer}" if c.via_layer else ""
    print(f"{kind} {' '.join(c.layers)}{via}")
```

### Extracting Device Definitions

```python
from svrf_parser.ast_nodes import Device

devices = [s for s in tree.statements if isinstance(s, Device)]
for d in devices:
    print(f"DEVICE {d.device_type}({d.device_name}) "
          f"seed={d.seed_layer} pins={d.pins}")
    if d.cmacro:
        print(f"  CMACRO {d.cmacro}")
```

### Extracting Derived Layers and Rule Checks

```python
from svrf_parser.ast_nodes import LayerAssignment, RuleCheckBlock, BinaryOp, DRCOp

# Derived layers
for s in tree.statements:
    if isinstance(s, LayerAssignment):
        expr = s.expression
        if isinstance(expr, BinaryOp):
            print(f"{s.name} = {expr.left} {expr.op} {expr.right}")

# Rule check blocks
for s in tree.statements:
    if isinstance(s, RuleCheckBlock):
        print(f"\nRule: {s.name}")
        if s.description:
            print(f"  Description: {s.description}")
        for op in s.body:
            if isinstance(op, DRCOp):
                print(f"  {op.op} with constraints {op.constraints}")
```

### Working with Preprocessor Directives

```python
from svrf_parser.ast_nodes import Define, IfDef, Include

for s in tree.statements:
    if isinstance(s, Define):
        print(f"#DEFINE {s.name} {s.value}")

    elif isinstance(s, IfDef):
        keyword = "#IFNDEF" if s.negated else "#IFDEF"
        print(f"{keyword} {s.name}")
        print(f"  then: {len(s.then_body)} statements")
        print(f"  else: {len(s.else_body)} statements")

    elif isinstance(s, Include):
        print(f"#INCLUDE {s.path}")
```

### Walking the Full AST Recursively

```python
from svrf_parser import ast_nodes as ast

def walk(node, depth=0):
    indent = "  " * depth
    name = type(node).__name__
    print(f"{indent}{name} (line {node.line})")

    # Visit child nodes based on node type
    if isinstance(node, ast.Program):
        for s in node.statements:
            walk(s, depth + 1)
    elif isinstance(node, ast.RuleCheckBlock):
        for s in node.body:
            walk(s, depth + 1)
    elif isinstance(node, ast.IfDef):
        for s in node.then_body:
            walk(s, depth + 1)
        for s in node.else_body:
            walk(s, depth + 1)
    elif isinstance(node, ast.BinaryOp):
        if node.left:
            walk(node.left, depth + 1)
        if node.right:
            walk(node.right, depth + 1)
    elif isinstance(node, ast.UnaryOp):
        if node.operand:
            walk(node.operand, depth + 1)
    elif isinstance(node, ast.LayerAssignment):
        if node.expression:
            walk(node.expression, depth + 1)
    elif isinstance(node, ast.DMacro):
        for s in node.body:
            walk(s, depth + 1)

tree = parse_file("path/to/rules.drc")
walk(tree)
```

### Running the Test Suite

The included `test_samples.py` parses all files under the `samples/` directory and reports results:

```bash
python test_samples.py
```

Sample output:

```
Found 16 sample files.

----------------------------------------------------------------------
  PASS  samples/calibre.drc (4.6MB, 11845 stmts, 2.56s)
  PASS  samples/design.lvs (5.4MB, 2049 stmts, 2.87s)
  ...
----------------------------------------------------------------------

Summary: 16/16 passed, 0 failed
```

## API Reference

### `parse(text, filename="<input>")`

Parse SVRF source text and return an AST.

- **text** (`str`) — SVRF source code string
- **filename** (`str`) — Optional filename used in error messages
- **Returns** — `Program` node with a `statements` list

### `parse_file(path)`

Read and parse an SVRF file, returning an AST.

- **path** (`str`) — Path to the SVRF file
- **Returns** — `Program` node with a `statements` list

## AST Node Types

All nodes inherit from `AstNode` and carry `line` and `col` source location attributes.

### Preprocessor

| Node | Fields | SVRF Syntax |
|------|--------|-------------|
| `Define` | `name`, `value` | `#DEFINE name value` |
| `IfDef` | `name`, `negated`, `then_body`, `else_body` | `#IFDEF` / `#IFNDEF ... #ELSE ... #ENDIF` |
| `Include` | `path` | `#INCLUDE "path"` |
| `EncryptedBlock` | `content` | Opaque content between `#ENCRYPT` and `#ENDCRYPT` |

### Layer Definitions

| Node | Fields | SVRF Syntax |
|------|--------|-------------|
| `LayerDef` | `name`, `numbers` | `LAYER M1 10` |
| `LayerMap` | `gds_num`, `map_type`, `type_num`, `internal_num` | `LAYER MAP 10 DATATYPE 0 1001` |

### Statements

| Node | Fields | SVRF Syntax |
|------|--------|-------------|
| `VariableDef` | `name`, `expr` | `VARIABLE name value` |
| `Directive` | `keywords`, `arguments`, `property_block` | Multi-keyword directives (e.g. `LAYOUT PATH "file"`) |
| `LayerAssignment` | `name`, `expression` | `derived = M1 AND M2` |
| `RuleCheckBlock` | `name`, `description`, `body` | `name { @desc ... }` |
| `Connect` | `soft`, `layers`, `via_layer` | `CONNECT M1 M2 BY VIA1` |
| `Device` | `device_type`, `device_name`, `seed_layer`, `pins`, `aux_layers`, `cmacro` | `DEVICE MOSFET ...` |
| `DMacro` | `name`, `params`, `body` | `DMACRO name param1 ... { body }` |
| `Group` | `name`, `pattern` | `GROUP name pattern` |
| `Attach` | `layer`, `net` | `ATTACH layer net` |
| `TraceProperty` | `device`, `args` | `TRACE PROPERTY device ...` |

### Expressions

| Node | Fields | Description |
|------|--------|-------------|
| `BinaryOp` | `op`, `left`, `right` | Binary operations: `AND`, `OR`, `NOT`, `INSIDE`, `OUTSIDE`, `INTERACT`, etc. |
| `UnaryOp` | `op`, `operand` | Unary operations: `NOT`, `COPY`, `HOLES`, etc. |
| `LayerRef` | `name` | Layer reference |
| `NumberLiteral` | `value` | Numeric literal |
| `StringLiteral` | `value` | String literal |
| `FuncCall` | `name`, `args` | Function call: `AREA()`, `PERIM_CO()`, etc. |
| `Constraint` | `op`, `value` | Constraint: `< 0.1`, `>= 2.0` |
| `ConstrainedExpr` | `expr`, `constraints` | Expression with constraints |
| `DRCOp` | `op`, `operands`, `constraints`, `modifiers` | DRC operations: `INT`, `EXT`, `ENC`, `DENSITY` |
| `IfExpr` | `condition`, `then_body`, `elseifs`, `else_body` | IF/ELSE expression inside property blocks |
| `PropertyBlock` | `properties`, `body` | `[ PROPERTY ... ]` property block |


## Supported SVRF Syntax

- **Preprocessor**: `#DEFINE`, `#IFDEF`, `#IFNDEF`, `#ELSE`, `#ENDIF`, `#INCLUDE`, `#ENCRYPT`/`#ENDCRYPT`
- **Layer operations**: `LAYER`, `LAYER MAP`, layer assignment (`=`)
- **Boolean / spatial operators**: `AND`, `OR`, `NOT`, `INSIDE`, `OUTSIDE`, `INTERACT`, `TOUCH`, `ENCLOSE`, `IN EDGE`, `COIN EDGE`, `WITH`
- **DRC operations**: `INT`, `EXT`, `ENC`, `DENSITY`, `SIZE`, `AREA`, `ANGLE`, `LENGTH`, `CONVEX EDGE`, `EXPAND EDGE`, `RECTANGLE`, `EXTENT`, `STAMP`
- **Connectivity**: `CONNECT`, `SCONNECT`
- **Devices**: `DEVICE` (MOSFET, DIODE, CAP, RES, etc.)
- **Macros**: `DMACRO` definitions with property blocks
- **Directives**: `LAYOUT`, `SOURCE`, `DRC`, `LVS`, `ERC`, `PEX`, `PRECISION`, `RESOLUTION`, `TITLE`, `TEXT`, `PORT`, `VIRTUAL`, `FLAG`, `UNIT`, `MASK`, etc.
- **Other**: `GROUP`, `ATTACH`, `TRACE PROPERTY`, rule check blocks, comments (`//`, `/* */`)

## Requirements

- Python 3.6+
- No third-party dependencies
