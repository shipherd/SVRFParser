# SVRFParser

A pure-Python parser for SVRF (Standard Verification Rule Format) files used by Calibre DRC, LVS, and antenna rule decks. Built with hand-written recursive descent + Pratt parsing and two-pass symbol table disambiguation. No third-party dependencies.

## Project Structure

```
svrf_parser/
  __init__.py        # Package entry, exports parse / parse_file / validate_svrf
  tokens.py          # TokenType enum and Token dataclass
  lexer.py           # Lexer: source text -> token stream
  ast_nodes.py       # AST node class hierarchy
  parser.py          # Two-pass recursive descent + Pratt parser
  printer.py         # AST -> SVRF text (for round-trip testing)
tests/
  helpers.py         # Shared test utilities (parse_one, parse_expr, etc.)
  conftest.py        # pytest fixtures
  tier1/             # Unit tests by construct category (110 tests)
  tier2/             # Integration tests on real sample files
  tier3/             # Round-trip tests (AST -> text -> AST)
baseline.py          # Baseline metrics collector
coverage_analysis.py # Grammar coverage analysis vs SVRF docs
test_samples.py      # Batch test harness for sample files
```

## Usage

### Parse a File

```python
from svrf_parser import parse_file

tree = parse_file("path/to/calibre.drc")
print(f"{len(tree.statements)} statements parsed")
```

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

### Parse with Diagnostics

```python
from svrf_parser import parse_with_diagnostics

tree, warnings = parse_with_diagnostics(text)
print(f"{len(warnings)} parser warnings")
```

### Validate SVRF

```python
from svrf_parser import validate_svrf, is_valid_svrf_file

result = validate_svrf(text)
if result:
    print("Valid SVRF")
else:
    print(result.errors)

# Or simply:
is_valid_svrf_file("path/to/rules.drc")  # -> bool
```

### Inspecting AST Nodes

Every AST node carries `line` and `col` attributes. Node-specific fields are accessed as regular attributes:

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
        print(f"Line {stmt.line}: Rule '{stmt.name}' with {len(stmt.body)} operations")
```

### Walking the Full AST

```python
from svrf_parser import ast_nodes as ast

def walk(node, depth=0):
    indent = "  " * depth
    print(f"{indent}{type(node).__name__} (line {node.line})")

    if isinstance(node, ast.Program):
        for s in node.statements: walk(s, depth + 1)
    elif isinstance(node, ast.RuleCheckBlock):
        for s in node.body: walk(s, depth + 1)
    elif isinstance(node, ast.BinaryOp):
        if node.left: walk(node.left, depth + 1)
        if node.right: walk(node.right, depth + 1)
    elif isinstance(node, ast.UnaryOp):
        if node.operand: walk(node.operand, depth + 1)
    elif isinstance(node, ast.LayerAssignment):
        if node.expression: walk(node.expression, depth + 1)
    elif isinstance(node, ast.DMacro):
        for s in node.body: walk(s, depth + 1)
    elif isinstance(node, ast.IfDef):
        for s in node.then_body: walk(s, depth + 1)
        for s in node.else_body: walk(s, depth + 1)

tree = parse_file("path/to/rules.drc")
walk(tree)
```

## Running Tests

### Unit tests (no sample files needed)

```bash
pytest tests/tier1/ -v
```

### Integration tests (requires sample files)

```bash
pytest tests/tier2/ -v --samples-dir /path/to/svrf_samples
# or
SVRF_SAMPLES_DIR=/path/to/svrf_samples pytest tests/tier2/ -v
```

### Batch test harness

```bash
python test_samples.py /path/to/svrf_samples
python test_samples.py /path/to/svrf_samples /path/to/single_file.drc
```

### Baseline metrics

```bash
python baseline.py /path/to/svrf_samples
```

### Coverage analysis

```bash
python coverage_analysis.py /path/to/svrf_docs/toc.json
```

## API Reference

| Function | Description |
|----------|-------------|
| `parse(text, filename)` | Parse SVRF text, return `Program` node |
| `parse_file(path)` | Parse SVRF file, return `Program` node |
| `parse_with_diagnostics(text, filename)` | Parse text, return `(Program, warnings)` |
| `parse_file_with_diagnostics(path)` | Parse file, return `(Program, warnings)` |
| `validate_svrf(text, filename)` | Validate text, return `ValidationResult` |
| `validate_svrf_file(path)` | Validate file, return `ValidationResult` |
| `is_valid_svrf(text, filename)` | Validate text, return `bool` |
| `is_valid_svrf_file(path)` | Validate file, return `bool` |

## AST Node Types

All nodes inherit from `AstNode` and carry `line` and `col` source location attributes.

### Preprocessor

| Node | Fields | SVRF Syntax |
|------|--------|-------------|
| `Define` | `name`, `value` | `#DEFINE name value` |
| `IfDef` | `name`, `negated`, `then_body`, `else_body` | `#IFDEF` / `#IFNDEF ... #ELSE ... #ENDIF` |
| `Include` | `path` | `#INCLUDE "path"` |
| `EncryptedBlock` | `content` | `#ENCRYPT ... #ENDCRYPT` |

### Layer Definitions

| Node | Fields | SVRF Syntax |
|------|--------|-------------|
| `LayerDef` | `name`, `numbers` | `LAYER M1 10` |
| `LayerMap` | `gds_num`, `map_type`, `type_num`, `internal_num` | `LAYER MAP 10 DATATYPE 0 1001` |

### Statements

| Node | Fields | SVRF Syntax |
|------|--------|-------------|
| `VariableDef` | `name`, `expr` | `VARIABLE name value` |
| `Directive` | `keywords`, `arguments`, `property_block` | `LAYOUT PATH "file"`, `DRC RESULTS DATABASE "out.db"` |
| `LayerAssignment` | `name`, `expression` | `derived = M1 AND M2` |
| `RuleCheckBlock` | `name`, `description`, `body` | `name { @desc ... }` |
| `Connect` | `soft`, `layers`, `via_layer` | `CONNECT M1 M2 BY VIA1` |
| `Device` | `device_type`, `device_name`, `seed_layer`, `pins`, `aux_layers`, `cmacro` | `DEVICE MOSFET(nmos) ...` |
| `DMacro` | `name`, `params`, `body` | `DMACRO name p1 p2 { ... }` |
| `Group` | `name`, `pattern` | `GROUP name pattern` |
| `Attach` | `layer`, `net` | `ATTACH layer net` |
| `TraceProperty` | `device`, `args` | `TRACE PROPERTY device ...` |

### Expressions

| Node | Fields | Description |
|------|--------|-------------|
| `BinaryOp` | `op`, `left`, `right` | `AND`, `OR`, `NOT`, `XOR`, `INSIDE`, `OUTSIDE`, `OUT`, `INTERACT`, `TOUCH`, `ENCLOSE`, `CUT`, `STAMP`, compound ops (`INSIDE EDGE`, `TOUCH OUTSIDE EDGE`, `NOT IN`, etc.) |
| `UnaryOp` | `op`, `operand` | `NOT`, `COPY`, `HOLES`, `DONUT`, `MERGE`, `PUSH` |
| `LayerRef` | `name` | Layer name reference |
| `NumberLiteral` | `value` | Numeric literal |
| `StringLiteral` | `value` | String literal |
| `FuncCall` | `name`, `args` | `AREA()`, `PERIM_CO()`, `MIN()`, `MAX()` |
| `Constraint` | `op`, `value` | `< 0.1`, `>= 2.0`, `!= 0` |
| `ConstrainedExpr` | `expr`, `constraints`, `modifiers` | Expression with constraints and trailing modifiers |
| `DRCOp` | `op`, `operands`, `constraints`, `modifiers` | `INT`, `EXT`, `ENC`, `DENSITY`, `SIZE`, `RECTANGLE`, `RECTANGLE ENCLOSURE`, `EXPAND EDGE`, `OFFGRID`, `ROTATE`, `DFM PROPERTY`, `NET AREA RATIO`, etc. |
| `IfExpr` | `condition`, `then_body`, `elseifs`, `else_body` | IF/ELSE inside property blocks |
| `PropertyBlock` | `properties`, `body` | `[ PROPERTY ... ]` |

## Supported SVRF Syntax

- **Preprocessor**: `#DEFINE`, `#IFDEF`, `#IFNDEF`, `#ELSE`, `#ENDIF`, `#INCLUDE`, `#ENCRYPT`/`#ENDCRYPT`
- **Layer operations**: `LAYER`, `LAYER MAP` (DATATYPE/TEXTTYPE), layer assignment (`=`)
- **Boolean operators**: `AND`, `OR`, `NOT`, `XOR` (infix and prefix forms)
- **Spatial operators**: `INSIDE`, `OUTSIDE`, `OUT`, `INTERACT`, `TOUCH`, `ENCLOSE`, `CUT`, `STAMP`, `IN`
- **Compound operators**: `INSIDE EDGE`, `OUTSIDE EDGE`, `COIN EDGE`, `IN EDGE`, `OR EDGE`, `TOUCH EDGE`, `TOUCH INSIDE EDGE`, `TOUCH OUTSIDE EDGE`, `NOT TOUCH`, `NOT IN`, `NOT OUT`, `INSIDE OF LAYER`
- **DRC operations**: `INT`, `EXT`, `ENC`, `DENSITY`, `OFFGRID`, `ROTATE`
- **Geometry operations**: `SIZE`, `GROW`, `SHRINK`, `SHIFT`, `EXPAND EDGE`, `CONVEX EDGE`, `RECTANGLE`, `RECTANGLE ENCLOSURE`, `RECTANGLES`, `EXTENT`, `EXTENTS`
- **Measurement**: `AREA`, `LENGTH`, `ANGLE`, `VERTEX`, `NET AREA RATIO`
- **DFM**: `DFM PROPERTY`, `DFM PROPERTY NET`, `DFM DP`, `DFM RDB`
- **WITH sub-expressions**: `WITH WIDTH`, `WITH EDGE`, `WITH TEXT`, `WITH NEIGHBOR`
- **Connectivity**: `CONNECT`, `SCONNECT`
- **Devices**: `DEVICE` (MOSFET, DIODE, CAP, RES, BJT, etc.), `DEVICE LAYER`
- **Macros**: `DMACRO` definitions with property blocks
- **Directives**: `LAYOUT`, `SOURCE`, `DRC`, `LVS`, `ERC`, `PEX`, `PRECISION`, `RESOLUTION`, `TITLE`, `TEXT`, `PORT`, `VIRTUAL`, `FLAG`, `UNIT`, `MASK`, `HCELL`, `RDB`, etc.
- **Control flow**: `IF`/`ELSE`/`ELSE IF` in property blocks and rule check blocks
- **Other**: `GROUP`, `ATTACH`, `TRACE PROPERTY`, rule check blocks (with `{` on same or next line), comments (`//`, `/* */`)

## Architecture

The parser uses a two-pass approach:

1. **Prescan** (`_prescan`): Scans the token stream to build a symbol table of known layer names (from `LAYER` definitions, layer assignments, rule check block names). This resolves the fundamental SVRF ambiguity where any identifier could be either a keyword or a layer name.

2. **Parse**: Recursive descent for statements, Pratt parsing for expressions. The symbol table from pass 1 guides disambiguation — identifiers in the symbol table are treated as layer references even when they match SVRF keywords.

## Requirements

- Python 3.6+
- No third-party dependencies
- pytest (for running tests)
