# SVRFParser

SVRFParser is a pure-Python parser and validator for Calibre SVRF rule decks.
It targets DRC, LVS, ERC, PEX, antenna, encrypted, and companion deck formats
used in real rule-deck corpora, while keeping the implementation dependency
free and easy to run from a checkout.

The current parser path is:

```text
source text -> lexer -> segmenter -> statement/clause CST -> normalizer -> typed AST -> semantic validation
```

Validation expands standalone includes before the lexer and retains a source
map for diagnostics. The `parse*` APIs parse only the supplied source and do
not read included files.

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
- Scalar arithmetic follows the manual's left-to-right multiplicative
  precedence, including `^` and `%`; DFM property bracket expressions retain
  higher precedence for `^`.
- DFM fill, spacing, optimization, and MAT syntax retains ordered clauses,
  bracketed arguments, and conditional fragments instead of splitting them
  into unrelated layer operations.
- `PERC LOAD` retains case-sensitive procedure names, parallel groups, and
  conditional selections without executing Tcl.
- Quoted SVRF symbol names resolve case-insensitively without changing the
  original quoted text or external filenames.
- Conditional symbol resolution isolates mutually exclusive branches and
  distinguishes definite definitions from conditional availability.
- Shared operation contracts supply operand roles and semantic requirements.
  Typed modifier views retain compatibility with the existing AST fields.
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
`__pycache__` directories while running tests or tools. Set
`$env:PYTHONDONTWRITEBYTECODE = "1"` in PowerShell as well to prevent bytecode
from test subprocesses.

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
  dfm_spec_parser.py            Ordered DFM specifications and MAT clauses
  perc_parser.py                PERC LOAD procedure selections and groups
  operation_*.py                Rule-operation parsing and normalization
  statement_*.py                Statement shape and handler logic
  ast.py, ast_nodes.py          AST node model and compatibility exports
  visitor.py                    Visitor base class
  diagnostics.py                Structured diagnostics
  include_resolver.py           INCLUDE/#INCLUDE expansion
  include_syntax.py             Embedded filename-reference include syntax
  source_map.py                 Included-source locations and provenance
  semantic*.py                  Symbol and semantic validation passes
  symbol_availability.py        Guarded definitions and conditional availability
  modifiers.py                  Typed modifier views and compatibility adapters
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
report_privacy.py               Redacted corpus-report formatting
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

`validate_svrf` and `validate_svrf_file` expand includes when enabled, parse the
aggregate input, build symbol information, run conservative semantic checks, apply the
unresolved-symbol policy, and return a `ValidationResult`.

```python
from svrf_parser import validate_svrf_file

result = validate_svrf_file(
    "path/to/rules.drc",
    strict=True,
    follow_includes=True,
    run_directory="path/to/run-directory",
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
- `follow_includes`: expand standalone `INCLUDE` and `#INCLUDE` before parsing.
  Anonymous text requires an explicit `run_directory` to enable expansion.
- `run_directory`: base for all relative include paths, including nested
  includes. Defaults to the current working directory, not the directory of
  each included file.
- `unresolved_policy`: `"strict"` or `"practical"`.
- `symbol_manifest`: `None`, a mapping, a manifest path, or a
  `SymbolManifest` instance.

Standalone includes may supply partial syntax, including rule-body statements,
macro bodies, and pieces of expressions. Includes inside conditionals and
recognized plaintext encrypted blocks are expanded too. Expansion occurs
before block-comment removal but ignores line-commented include statements.
Both conditional branches remain in the AST; validation does not execute the
preprocessor or interpret TVF/Tcl.

Branch scopes are validated independently and joined only after all alternatives
have been checked. Definitions present in every alternative are definite;
definitions present in only some alternatives produce
`semantic.reference.conditional` findings when referenced without a sufficient
guard. A reference to a definition in a mutually exclusive branch produces
`semantic.reference.unavailable_branch`. These warnings become errors in strict
mode and are not suppressed by practical unresolved-symbol policies or manifests.
Practical mode groups repeated conditional notices by file, include stack,
symbol, code, and reference context; `metadata["occurrence_count"]` records the
number of references represented by a grouped notice. Strict mode retains
individual diagnostics. Corpus audits classify these notices separately from
confirmed semantic rule errors.
Analysis does not evaluate control-variable values or correlate separate
conditional statements, so conditional findings are not proof that a specific
Calibre run will fail.

Embedded includes used as filename or cell-list arguments are retained as
`Include(embedded=True)` nodes rather than parsed as rule files. Opaque
encrypted payloads are not expanded. Missing files and include cycles produce
diagnostics with the original file location and include stack.

With include expansion enabled, `ValidationResult.program` is the aggregate
AST, not just the root file's statements. Set `follow_includes=False` or use a
`parse*` API to retain standalone include nodes without opening their targets.

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
- `filename`, `include_stack`

Validation maps node locations back to the original files. A node spanning
multiple files is anchored to the file where it starts; its source span is
bounded by that file. Position/provenance fields are excluded from
`to_dict(include_position=False)` and semantic structural comparisons.

Common top-level nodes include:

- `Program`
- `Define`, `IfDef`, `Include`, `EncryptedBlock`
- `LayerDef`, `LayerMap`, `VariableDef`
- `Directive`, `LayerAssignment`, `RuleCheckBlock`
- `DfmSpec`, `DfmClause`, `PercLoad`, `PercGroup`
- `Connect`, `Device`, `DMacro`, `MacroCall`
- `Group`, `Attach`, `TraceProperty`

`EncryptedBlock` always preserves the raw payload in `content`. If the payload
between `#ENCRYPT` / `#DECRYPT` and `#ENDCRYPT` parses cleanly as plaintext
SVRF, `body` contains the parsed statements and `parse_status` is `"plaintext"`.
Otherwise `body` is empty and `parse_status` is `"opaque"`.
`directive` preserves whether the block started with `#ENCRYPT` or `#DECRYPT`.

Expression and rule-body nodes include:

- `BinaryOp`, `UnaryOp`, `LayerRef`
- `NumberLiteral`, `StringLiteral`, `FuncCall`
- `Constraint`, `ConstrainedExpr`, `DRCOp`
- `PropertyBlock`, `IfExpr`
- `BracketExpr`
- `VarRef`, `ErrorNode`

`DfmSpec` records the specification kind, variant, name, header arguments, and
ordered body. `DfmClause` records clause keywords and arguments; a clause with
no keywords represents a conditional argument fragment. Shared clauses after
conditional declarations stay at their original source level.
`BracketExpr.items` preserves bracket boundaries and spacing intervals.

`PercLoad.function` is an SVRF name; its ordered body retains selection
keywords, procedure names, parallel `PercGroup` boundaries, and conditionals.
Unquoted procedure names keep their original case as `StringLiteral` values.
Unquoted cell/text filter operands retain their case as `LayerRef` nodes so
printing does not turn possible string-variable references into quoted strings.

`DRCOp.modifiers` and `ConstrainedExpr.modifiers` retain their existing list
representation, including `("BY", expression)` tuples. The additive
`modifier_nodes` property provides immutable `NamedModifier` / `RawModifier`
views from `svrf_parser.modifiers`. It reflects changes to the legacy list and
does not add fields to AST serialization or duplicate nodes during traversal.
Modifier argument contexts are shared by annotation, validation, and printing;
unquoted `BY NET` is a literal mode rather than a scalar symbol reference.

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
Directory selection also includes support files, documentation, scripts, and
binary artifacts. A mixed folder is not expected to pass as an all-SVRF corpus;
classify findings by content rather than adding extension filters. Conversely,
parsing without warnings does not prove that an input contains meaningful SVRF.

Semantic corpus gate for a directory or one file:

```powershell
python -B audit_sample_corpus.py <path-to-svrf-samples-or-file> `
  --run-directory <path-to-run-directory> `
  --unresolved-policy practical `
  --summary-only `
  --fail-on-errors
```

The audit gate returns a non-zero exit code when audited files are invalid or
emit semantic errors. Warnings are summarized and bucketed so remaining external
or companion-symbol context can be reviewed without failing the gate.
Omit `--run-directory` to resolve relative includes from the current directory.
The practical policy does not suppress known declaration-order violations,
invalid connectivity shapes, or provably output-free rule bodies.

Directory targets are recursive and extension-neutral. Files named `a.15a`,
`b.13a`, `deck`, `rules.custom`, or any other regular filename are all passed
to the parser/validator.

Parser success is a structural check, not a full semantic audit or a comparison
with Calibre. Check recovered `ErrorNode` nodes, rule-name completeness, and
semantic diagnostics separately. Opaque encrypted payloads cannot be verified.
Private decks and their corpus inventories are not committed; regressions use
synthetic inputs under `tests/`.

## Privacy

The parser gate, semantic audit, and baseline metrics command redact source
details by default. Files receive run-local labels such as `file-0001`; unresolved
symbols receive labels such as `symbol-0001`. Exception output retains the
exception type rather than potentially sensitive text. Metrics retain counts,
sizes, and timings, but do not store the input root or filenames.

Use `--show-private-details` on these commands only for local debugging. This
option restores filenames, symbol names, and exception text; do not share its
output without reviewing it. Aggregate metrics can still describe a private
corpus, so review redacted reports before publishing them too.

Parser APIs preserve original source data for normal use. For a source-redacted
export, request it explicitly:

```python
ast_shape = tree.to_dict(redact_source=True)
diagnostic_data = diagnostic.to_dict(redact_source=True)
```

Redacted AST exports retain node types and container shape, replace scalar
payloads with `None`, and omit position/provenance fields. Redacted diagnostics
retain codes, severity, and numeric positions, but remove messages, filenames,
snippets, include stacks, and metadata. `to_dict(include_position=False)` alone
is not redaction: names, include targets, literal values, and encrypted content
can still appear in the AST.

Generated reports, bytecode, caches, and local-only `tools/` are ignored by Git.
Ignored files can still enter a folder archive. Prefer distributing a reviewed
`git archive`, and keep samples/manuals outside the checkout. Ignore rules do
not remove information already committed to Git history or published elsewhere.

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
  `#INCLUDE`, `#ENCRYPT`, `#DECRYPT`, `#ENDCRYPT`
- Include statements: `INCLUDE` and `#INCLUDE`
- Layer definitions and maps: `LAYER`, `LAYER MAP`, `DATATYPE`, `TEXTTYPE`
- Variables and layer assignments, scalar arithmetic including `%`, and
  context-specific DFM power precedence
- Boolean and spatial layer operators: `AND`, `OR`, `NOT`, `XOR`, `INSIDE`,
  `OUTSIDE`, `OUT`, `INTERACT`, `TOUCH`, `ENCLOSE`, `CUT`, `STAMP`, `IN`
- Prefix, infix, and postfix Boolean forms, including `(M1 M2 OR M3)`;
  single-layer Boolean operations retain their operation rather than becoming
  bare layer references
- Compound spatial forms such as `INSIDE EDGE`, `OUTSIDE EDGE`, `COIN EDGE`,
  `TOUCH INSIDE EDGE`, `TOUCH OUTSIDE EDGE`, `NOT TOUCH`, `NOT IN`,
  `NOT OUT`, `NOT INSIDE`, `NOT INTERACT`, `NOT ENCLOSE`, and
  `INSIDE OF LAYER`
- DRC operations such as `INT`, `EXT`, `ENC`, `DENSITY`, `OFFGRID`, `ROTATE`,
  `PATHCHK`, `NET AREA`, `NET INTERACT`, and `NET AREA RATIO`
- Geometry operations such as `SIZE`, `GROW`, `SHRINK`, `SHIFT`,
  `EXPAND EDGE`, `CONVEX EDGE`, `RECTANGLE`, `RECTANGLE ENCLOSURE`,
  `RECTANGLES`, `EXTENT`, `EXTENTS`, and `FLATTEN`
- Measurement and constraint forms such as `AREA`, `PERIMETER`, `LENGTH`,
  `ANGLE`, `VERTEX`, comparison constraints, and modifier chains
- DFM forms such as `DFM PROPERTY`, `DFM PROPERTY NET`, `DFM DP`, and
  `DFM RDB`; ordered `DFM SPEC FILL`, `DFM SPEC SPACE`, and
  `DFM SPEC OPTIMIZE` declarations, legacy REGION/WRAP/DATA variants,
  `DFM MAT` continuation clauses, and complete `DFM FILL REGION` / `WRAP` heads
- `WITH` sub-expressions including `WITH WIDTH`, `WITH EDGE`, `WITH TEXT`,
  and `WITH NEIGHBOR`
- Cell selections such as `INSIDE CELL` and `NOT INSIDE CELL`, and
  `WITH TEXT` / `NOT WITH TEXT` with unquoted `?` patterns and text layers
- `PERC LOAD` initialization, selections, parallel groups, `SELECTTYPE`, and
  conditional procedure lists
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

Whole TVF rule files beginning with `#!tvf` are not supported. The parser does
not run Tcl, expand dynamically generated SVRF, verify PERC procedure
implementations, or decrypt opaque payloads. Ordered DFM syntax is represented
structurally; detailed fill/optimizer clause contracts and their geometric
behavior are not fully validated.

The semantic validator adds conservative checks for includes, include cycles,
shared symbols across includes, duplicate definitions, macro parameters,
undefined references, quoted layer operands, variable declaration order,
rule-description variable references, assignment-only rule bodies, SCONNECT
syntax variants, selected directive contracts, operation operands, value
constraints, conditional availability, and the SVRF construct ratio. Macro variable-order checks are
deferred because bodies are expanded at invocation; this validator does not
execute macro calls.

`SvrfPrinter` preserves expression grouping, variable string lists and
`ENVIRONMENT`, quoted rule names and string escapes, SCONNECT `LINK`/`ABUT ALSO`,
FMACRO call syntax, and encrypted-block introducers. It is not a lossless
formatter for every supported or opaque construct.
It also preserves DFM clause order, brackets, conditional fragments, and PERC
procedure groups.

## Public API

| Function | Description |
| --- | --- |
| `parse(text, filename="<input>", strict=False)` | Parse SVRF text and return a `Program` node. |
| `parse_file(path, strict=False)` | Parse an SVRF file and return a `Program` node. |
| `parse_with_diagnostics(text, filename="<input>", strict=False)` | Parse text and return `(Program, warning_diagnostics)`. |
| `parse_file_with_diagnostics(path, strict=False)` | Parse a file and return `(Program, warning_diagnostics)`. |
| `validate_svrf(text, filename="<input>", strict=False, follow_includes=True, unresolved_policy="strict", symbol_manifest=None, run_directory=None)` | Validate text and return a `ValidationResult`. |
| `validate_svrf_file(path, strict=False, follow_includes=True, unresolved_policy="strict", symbol_manifest=None, run_directory=None)` | Validate a file and return a `ValidationResult`. |
| `is_valid_svrf(text, filename="<input>", strict=False, follow_includes=True, unresolved_policy="strict", symbol_manifest=None, run_directory=None)` | Validate text and return `bool`. |
| `is_valid_svrf_file(path, strict=False, follow_includes=True, unresolved_policy="strict", symbol_manifest=None, run_directory=None)` | Validate a file and return `bool`. |
| `AstVisitor` | Base class for AST visitors. Override `visit_NodeType` methods. |

## Notes For Contributors

- Keep reduced regression fixtures under `tests/fixtures` when changing parser
  or semantic behavior.
- Prefer structured diagnostics and `Diagnostic.metadata` over parsing rendered
  message text.
- Keep operation requirements and operand roles in the packaged operation
  contracts, and use the shared modifier adapters rather than interpreting
  modifier tuples independently in each pass.
- Prefer `AstNode.walk()` for full-tree traversal so tooling and tests use the
  same traversal semantics.
- Keep sample-corpus candidate selection in `sample_corpus.py` rather
  than duplicating traversal logic in tools.
- Keep generated spec data machine-neutral; do not commit local filesystem
  paths or generated bytecode/cache files.
