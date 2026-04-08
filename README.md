# SVRFParser

SVRFParser is a pure-Python parser and validator for Calibre SVRF rule decks.
It targets DRC, LVS, ERC, PEX, antenna, encrypted, and companion deck formats
used in real rule-deck corpora, while keeping the implementation dependency
free and easy to run from a checkout.

The current parser path is:

```text
source text -> lexer -> segmenter -> statement/clause CST -> normalizer -> typed AST -> semantic validation
```

## Current State

- No third-party runtime dependencies.
- The public facade exports `parse`, `parse_file`, `parse_with_diagnostics`,
  `parse_file_with_diagnostics`, `validate_svrf`, `validate_svrf_file`,
  `is_valid_svrf`, `is_valid_svrf_file`, `AstVisitor`, and
  `ValidationResult`.
- Real corpus selection is centralized in `sample_corpus.py`. A
  directory target means every regular file under that directory is treated as
  a potential SVRF file; a file target means that file is parsed or audited
  directly. Selection is not limited by extension.
- `test_samples.py --fail-on-warnings` is the strict parser-warning gate for a
  sample corpus.
- `audit_sample_corpus.py --summary-only --fail-on-errors` is the
  semantic corpus gate.
- Tier 1 tests are direct `unittest.TestCase` tests, so `pytest` is not
  required.
- Diagnostics carry structured location/provenance data, including
  `include_stack` and `metadata` for values such as unresolved symbol names.
- AST traversal uses the canonical iterative `AstNode.walk()` implementation.
- Packaged spec data lives under `svrf_parser/svrf_spec/data`. Generated spec
  payloads store the stable `$SVRF_MANUAL_ROOT` placeholder instead of a local
  manual path.

Semantic corpus audits can still report expected practical warnings for symbols
defined by external PDK context, companion files, encrypted content, or runtime
variables that are not present in the visible sample tree. Use the practical
unresolved-symbol policy and an optional symbol manifest to classify those
cases.

## Requirements

- Python 3.10+
- No third-party Python packages

Use `python -B` in the commands below when you want to keep the checkout free of
`__pycache__` directories while running tests or tools.

## Project Layout

```text
svrf_parser/
  __init__.py                  Public package facade
  lexer.py, tokens.py           Tokenization
  segmenter.py                  Statement and block segmentation
  *_cst.py, cst_builder.py      Concrete syntax tree helpers
  normalizer.py                 CST-to-AST normalization
  parser.py                     Main parser orchestration
  expression_parser.py          Pratt-style expression parsing
  operation_*.py                Rule-operation parsing and normalization
  statement_*.py                Statement shape and handler logic
  ast.py, ast_nodes.py          AST node model and compatibility exports
  visitor.py                    Visitor base class
  diagnostics.py                Structured diagnostics
  include_resolver.py           INCLUDE/#INCLUDE expansion
  semantic*.py                  Symbol and semantic validation passes
  validation_*.py               Public validation pipeline and helpers
  svrf_constructs.py            Shared SVRF construct classification
  svrf_spec/
    data/                       Packaged parser/spec JSON artifacts
    loader.py                   Spec data loading
    manual_sources.py           Manual-derived inventories
    manual_overrides.py         Reviewed manual/corpus overrides

tests/
  tier1/                        Construct-level parser tests
  tier2/                        Real sample corpus integration tests
  tier3/                        Parse/print/re-parse roundtrip tests
  fixtures/                     Reduced fixtures and golden snapshots
  test_*.py                     Parser, semantic, spec, tooling, and harness tests

examples/
  symbol_manifest.example.json  Optional unresolved-symbol manifest example

audit_sample_corpus.py          Semantic audit for real sample corpora
sample_corpus.py                Extension-neutral real-corpus file selection
test_samples.py                 Parser corpus harness
baseline.py                     Corpus metrics snapshot helper
coverage_analysis.py            Manual keyword coverage helper
```

## Quick Start

Run from the repository root, or put the checkout on `PYTHONPATH`.

```python
from svrf_parser import parse_file

tree = parse_file("path/to/rules.drc")
print(len(tree.statements))
```

Parse a string:

```python
from svrf_parser import parse

text = """\
LAYOUT PATH "design.gds"
LAYOUT PRIMARY "top"

LAYER M1 10
LAYER VIA1 11
LAYER M2 12

CONNECT M1 M2 BY VIA1

M1_WIDE = SIZE M1 BY 0.1

M1.W.1 {
  @ M1 minimum width
  INT M1 < 0.1
}
"""

tree = parse(text)
for stmt in tree.statements:
    print(type(stmt).__name__, stmt.line)
```

Parse with recoverable parser diagnostics:

```python
from svrf_parser import parse_with_diagnostics

tree, warnings = parse_with_diagnostics(text)
for warning in warnings:
    print(warning.code, warning.line, warning.col, warning.message)
```

Use strict parsing when parser recovery should become an exception:

```python
from svrf_parser import parse

tree = parse(text, strict=True)
```

## Validation

`validate_svrf` and `validate_svrf_file` parse input, follow includes when
possible, build symbol information, run conservative semantic checks, apply the
unresolved-symbol policy, and return a `ValidationResult`.

```python
from svrf_parser import validate_svrf_file

result = validate_svrf_file(
    "path/to/rules.drc",
    strict=True,
    follow_includes=True,
    unresolved_policy="practical",
)

if result:
    print("valid")
else:
    for diagnostic in result.errors:
        print(diagnostic.code, diagnostic.message)
```

The validation API accepts:

- `strict`: parser and semantic recovery should be treated more aggressively.
- `follow_includes`: follow `INCLUDE` and `#INCLUDE` when the filename is a
  real path.
- `unresolved_policy`: `"strict"` or `"practical"`.
- `symbol_manifest`: `None`, a mapping, a manifest path, or a
  `SymbolManifest` instance.

`ValidationResult` exposes:

- `valid`
- `errors`
- `warnings`
- `diagnostics`
- `program`
- `profile`
- `policy_summary`
- `error_messages`
- `warning_messages`
- profile convenience properties such as `dialects`, `feature_families`,
  `profile_tags`, and `limited_support_features`

## Unresolved Symbol Manifests

`examples/symbol_manifest.example.json` documents the optional manifest shape
used by the practical unresolved-symbol policy. It can mark known PDK/runtime
symbols as external, scalar, or layer-like symbols, either globally or for
matching files.

```json
{
  "external_symbols": ["EXTERNAL_NET"],
  "scalar_parameters": ["LAYER_THICKNESS_M0"],
  "layer_like_symbols": ["OUTPUT_LAYER_A"],
  "rules": [
    {
      "file_globs": ["*process/*.drc", "*process\\*.drc"],
      "scalar_parameters": ["LAYER_THICKNESS_M1"]
    }
  ]
}
```

Use a manifest from Python:

```python
from svrf_parser import validate_svrf_file

result = validate_svrf_file(
    "path/to/rules.drc",
    unresolved_policy="practical",
    symbol_manifest="examples/symbol_manifest.example.json",
)
print(result.policy_summary.to_dict())
```

Or from the corpus audit tool:

```powershell
python -B audit_sample_corpus.py <path-to-svrf-samples> `
  --unresolved-policy practical `
  --symbol-manifest examples\symbol_manifest.example.json
```

## Diagnostics

Diagnostics are structured records. They are used by parser recovery, include
resolution, semantic validation, audit bucketing, and public validation results.

Each diagnostic has:

- `severity`
- `code`
- `message`
- `filename`
- `line`, `col`, `end_line`, `end_col`
- `start_offset`, `end_offset`
- `snippet`
- `include_stack`
- `metadata`

Convert a diagnostic to data with:

```python
payload = diagnostic.to_dict()
```

Unresolved-symbol diagnostics populate `metadata["symbol"]` so tools do not
need to parse rendered diagnostic messages.

## AST Model

All AST nodes inherit from `AstNode` and carry source position metadata:

- `line`, `col`
- `end_line`, `end_col`
- `start_offset`, `end_offset`
- `source_text`

Common top-level nodes include:

- `Program`
- `Define`, `IfDef`, `Include`, `EncryptedBlock`
- `LayerDef`, `LayerMap`, `VariableDef`
- `Directive`, `LayerAssignment`, `RuleCheckBlock`
- `Connect`, `Device`, `DMacro`, `MacroCall`
- `Group`, `Attach`, `TraceProperty`

`EncryptedBlock` always preserves the raw payload in `content`. If the payload
between `#ENCRYPT` / `#DECRYPT` and `#ENDCRYPT` parses cleanly as plaintext
SVRF, `body` contains the parsed statements and `parse_status` is `"plaintext"`.
Otherwise `body` is empty and `parse_status` is `"opaque"`.

Expression and rule-body nodes include:

- `BinaryOp`, `UnaryOp`, `LayerRef`
- `NumberLiteral`, `StringLiteral`, `FuncCall`
- `Constraint`, `ConstrainedExpr`, `DRCOp`
- `PropertyBlock`, `IfExpr`
- `VarRef`, `ErrorNode`

Use the visitor API:

```python
from svrf_parser import AstVisitor, parse_file
from svrf_parser.ast_nodes import LayerDef

class LayerCounter(AstVisitor):
    def __init__(self):
        self.count = 0

    def visit_LayerDef(self, node):
        self.count += 1

tree = parse_file("path/to/rules.drc")
counter = LayerCounter()
tree.accept(counter)
print(counter.count)
```

Or use the canonical iterative walk:

```python
tree = parse_file("path/to/rules.drc")
for node in tree.walk():
    print(type(node).__name__, getattr(node, "line", 0))
```

Rule-check `@` descriptions preserve text and split `^VARNAME` references into
`VarRef` nodes:

```python
from svrf_parser import parse
from svrf_parser.ast_nodes import RuleCheckBlock, VarRef

tree = parse("""\
VARIABLE MIN_SPACE 0.042

M1.S.1 {
  @ Minimum M1 space >= ^MIN_SPACE
  INT M1 < MIN_SPACE
}
""")

rule = next(stmt for stmt in tree.statements if isinstance(stmt, RuleCheckBlock))
refs = [part for line in rule.description for part in line if isinstance(part, VarRef)]
print([ref.name for ref in refs])
```

## Running Tests

Run the dependency-free unit suite:

```powershell
python -B -m unittest discover -q
```

Run the construct-level tests directly:

```powershell
python -B -m unittest discover tests.tier1 -q
```

Run roundtrip tests:

```powershell
python -B -m unittest discover -s tests\tier3 -q
```

Run integration tests against a real sample corpus directory or direct file:

```powershell
$env:SVRF_SAMPLES_DIR = "<path-to-svrf-samples-or-file>"
python -B -m unittest discover -s tests\tier2 -q
```

If `SVRF_SAMPLES_DIR` is unset, the tier 2 integration tests skip cleanly.

## Real Corpus Gates

Parser corpus gate for a directory:

```powershell
python -B test_samples.py <path-to-svrf-samples> --fail-on-warnings
```

Parser corpus gate for one file:

```powershell
python -B test_samples.py <path-to-svrf-file> --fail-on-warnings
```

The parser gate returns a non-zero exit code if no candidate files are selected,
if parsing raises an exception, or if parser warnings are present when
`--fail-on-warnings` is used.

Semantic corpus gate for a directory or one file:

```powershell
python -B audit_sample_corpus.py <path-to-svrf-samples-or-file> `
  --unresolved-policy practical `
  --summary-only `
  --fail-on-errors
```

The audit gate returns a non-zero exit code when audited files are invalid or
emit semantic errors. Warnings are summarized and bucketed so remaining external
or companion-symbol context can be reviewed without failing the gate.

Directory targets are recursive and extension-neutral. Files named `a.15a`,
`b.13a`, `deck`, `rules.custom`, or any other regular filename are all passed
to the parser/validator.

## Tools

Corpus metrics:

```powershell
python -B baseline.py <path-to-svrf-samples-or-file>
```

Manual keyword coverage:

```powershell
python -B coverage_analysis.py <path-to-svrf-docs-toc-json>
```

Manual-backed extraction and packaged-spec rebuild scripts may exist locally
under an ignored `tools/` directory, but they are not part of the committed
project tree.

## Supported SVRF Coverage

The parser is intentionally tolerant: unsupported or malformed syntax should be
localized into diagnostics or `ErrorNode` output rather than aborting the whole
file when strict mode is off.

Current covered families include:

- Preprocessor: `#DEFINE`, `#IFDEF`, `#IFNDEF`, `#ELSE`, `#ENDIF`,
  `#INCLUDE`, `#ENCRYPT`, `#ENDCRYPT`
- Include statements: `INCLUDE` and `#INCLUDE`
- Layer definitions and maps: `LAYER`, `LAYER MAP`, `DATATYPE`, `TEXTTYPE`
- Variables and layer assignments
- Boolean and spatial layer operators: `AND`, `OR`, `NOT`, `XOR`, `INSIDE`,
  `OUTSIDE`, `OUT`, `INTERACT`, `TOUCH`, `ENCLOSE`, `CUT`, `STAMP`, `IN`
- Compound spatial forms such as `INSIDE EDGE`, `OUTSIDE EDGE`, `COIN EDGE`,
  `TOUCH INSIDE EDGE`, `TOUCH OUTSIDE EDGE`, `NOT TOUCH`, `NOT IN`,
  `NOT OUT`, `NOT INSIDE`, `NOT INTERACT`, `NOT ENCLOSE`, and
  `INSIDE OF LAYER`
- DRC operations such as `INT`, `EXT`, `ENC`, `DENSITY`, `OFFGRID`, `ROTATE`,
  `PATHCHK`, `NET AREA`, `NET INTERACT`, and `NET AREA RATIO`
- Geometry operations such as `SIZE`, `GROW`, `SHRINK`, `SHIFT`,
  `EXPAND EDGE`, `CONVEX EDGE`, `RECTANGLE`, `RECTANGLE ENCLOSURE`,
  `RECTANGLES`, `EXTENT`, and `EXTENTS`
- Measurement and constraint forms such as `AREA`, `PERIMETER`, `LENGTH`,
  `ANGLE`, `VERTEX`, comparison constraints, and modifier chains
- DFM forms such as `DFM PROPERTY`, `DFM PROPERTY NET`, `DFM DP`, and
  `DFM RDB`
- `WITH` sub-expressions including `WITH WIDTH`, `WITH EDGE`, `WITH TEXT`,
  and `WITH NEIGHBOR`
- Connectivity: `CONNECT`, `SCONNECT`, `ATTACH`, and `GROUP`
- Device constructs: `DEVICE`, `DEVICE LAYER`, `DMACRO`, `CMACRO`, `FMACRO`,
  and `TRACE PROPERTY`
- Common directive families: `LAYOUT`, `SOURCE`, `DRC`, `LVS`, `ERC`, `PEX`,
  `PRECISION`, `RESOLUTION`, `TITLE`, `TEXT`, `PORT`, `VIRTUAL`, `FLAG`,
  `UNIT`, `MASK`, `HCELL`, and `RDB`
- Property blocks and `IF` / `ELSE IF` / `ELSE` control flow inside rule or
  property bodies
- Rule-check blocks with same-line or next-line braces
- Multi-line `@` descriptions with `^VARNAME` variable references
- Comments: `//` and `/* ... */`
- Plaintext-capable handling for `#ENCRYPT` / `#DECRYPT` blocks: clean SVRF
  payloads are parsed and participate in validation; opaque payloads remain
  preserved as raw content
- Limited/opaque handling for `TVF`, `POLYGON`, and other forms that can define
  symbols outside visible SVRF text

The semantic validator adds conservative checks for includes, include cycles,
shared symbols across includes, duplicate definitions, macro parameters,
undefined references, rule-description variable references, selected directive
contracts, operation operands, value constraints, and the SVRF construct ratio.

## Public API

| Function | Description |
| --- | --- |
| `parse(text, filename="<input>", strict=False)` | Parse SVRF text and return a `Program` node. |
| `parse_file(path, strict=False)` | Parse an SVRF file and return a `Program` node. |
| `parse_with_diagnostics(text, filename="<input>", strict=False)` | Parse text and return `(Program, warning_diagnostics)`. |
| `parse_file_with_diagnostics(path, strict=False)` | Parse a file and return `(Program, warning_diagnostics)`. |
| `validate_svrf(text, filename="<input>", strict=False, follow_includes=True, unresolved_policy="strict", symbol_manifest=None)` | Validate text and return a `ValidationResult`. |
| `validate_svrf_file(path, strict=False, follow_includes=True, unresolved_policy="strict", symbol_manifest=None)` | Validate a file and return a `ValidationResult`. |
| `is_valid_svrf(text, filename="<input>", strict=False, follow_includes=True, unresolved_policy="strict", symbol_manifest=None)` | Validate text and return `bool`. |
| `is_valid_svrf_file(path, strict=False, follow_includes=True, unresolved_policy="strict", symbol_manifest=None)` | Validate a file and return `bool`. |
| `AstVisitor` | Base class for AST visitors. Override `visit_NodeType` methods. |

## Notes For Contributors

- Keep reduced regression fixtures under `tests/fixtures` when changing parser
  or semantic behavior.
- Prefer structured diagnostics and `Diagnostic.metadata` over parsing rendered
  message text.
- Prefer `AstNode.walk()` for full-tree traversal so tooling and tests use the
  same traversal semantics.
- Keep sample-corpus candidate selection in `sample_corpus.py` rather
  than duplicating traversal logic in tools.
- Keep generated spec data machine-neutral; do not commit local filesystem
  paths or generated bytecode/cache files.
