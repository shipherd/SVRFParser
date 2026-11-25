# SVRFParser

A dependency-free Python 3.10+ parser, formatter, and static validator for Calibre Standard Verification Rule Format (SVRF) decks. Use it to extract rule checks, inspect layer expressions, or audit references across includes. It does not read layout geometry, execute Tcl or macros, decrypt data, or replace a Calibre signoff run.

This checkout contains the Python implementation. The C17 library and `svrfparse` CLI are distributed separately. Neither parser needs the other at runtime.

## Quick start

Run Python from this checkout, or add the checkout to `PYTHONPATH`. No package installation or Calibre installation is required.

```python
from svrf_parser import ast, parse_with_diagnostics
from svrf_parser.printer import SvrfPrinter

source = """LAYER METAL 10
METAL.W.1 {
    INTERNAL METAL < 0.1
}
"""
tree, diagnostics = parse_with_diagnostics(source, strict=True)
rule = next(n for n in tree.walk() if isinstance(n, ast.RuleCheckBlock))
print(rule.name, rule.body[0].op)  # METAL.W.1 INT
print(SvrfPrinter().emit(tree))
```

For a file, use `parse_file(path)` or `parse_file_with_diagnostics(path)`. No filename extension is required: `deck`, `a.15a`, and `b.13a` are equally valid inputs. Parse calls never open include targets.

## Parsing and validation

| Task | API | Result |
| --- | --- | --- |
| Build an AST from text or a file | `parse`, `parse_file` | `ast.Program` |
| Inspect parser recovery | `parse_with_diagnostics`, `parse_file_with_diagnostics` | `(Program, diagnostics)`; recoverable syntax can produce `ErrorNode` nodes |
| Check syntax, includes, symbols, and supported contracts | `validate_svrf`, `validate_svrf_file` | `ValidationResult` with `valid`, `errors`, `warnings`, `program`, `profile`, and `policy_summary` |
| Get a yes/no validation result | `is_valid_svrf`, `is_valid_svrf_file` | `bool` |
| Traverse, export, or format | `tree.walk()`, `AstVisitor`, `tree.to_dict()`, `SvrfPrinter().emit(tree)` | Preorder nodes, visitor dispatch, a dictionary, or canonical SVRF |

Parsing is tolerant by default. A recoverable syntax problem is not a successful strict parse, and a lexical error can still abort tolerant parsing. On a parse call, `strict=True` raises on syntax recovery. On a validation call, inspect the returned diagnostics; `strict=True` also promotes selected semantic warnings. A file can parse cleanly but fail validation, for example if a rule references an undefined layer.

This example uses a bundled synthetic fixture. The root file contains an `INCLUDE` and a `CONNECT`; validation sees the three layer definitions supplied by the include:

```python
from pathlib import Path
from svrf_parser import validate_svrf_file

run_dir = Path("tests/fixtures/includes")
result = validate_svrf_file(run_dir / "root_with_layer_include.svrf",
                            run_directory=run_dir, strict=True)
assert result.valid, [d.code for d in result.diagnostics]
print([s.name for s in result.program.statements if hasattr(s, "name")])
# ['M1', 'M2', 'VIA1']
```

### Includes and symbol policy

- Validation expands standalone `INCLUDE` and `#INCLUDE` **before parsing**. An include can supply part of an expression or a rule body. Relative paths, including nested ones, use `run_directory` or the process working directory, not the including file's directory. For anonymous text, provide `run_directory` to enable expansion. Use `follow_includes=False` to retain include nodes instead.
- Both preprocessor branches remain in the AST. `#PRAGMA ENV` supplies a default for an unset environment variable in include paths; `#PRAGMA DEFENV` also covers empty values. Defaults follow source order without changing the process environment. Missing files and cycles carry source locations and include stacks.
- By default, standalone include lines inside ordinary block comments can expand. Set `include_in_block_comments=False` to disable this. Line comments, TVF function scripts, embedded filename-list arguments, and opaque or partially parsed protected blocks do not trigger include reads.
- `unresolved_policy="strict"` is the default. With `strict=False` and `unresolved_policy="practical"`, repeated unresolved references can be grouped and a `symbol_manifest` can acknowledge known external, scalar, or layer-like names. The [example JSON manifest](examples/symbol_manifest.example.json) shows global entries and per-file rules; it is not a deck or a required input. Python can look for companion evidence in sibling files when a filename is available.
- Practical policy does not erase definite errors, variable-order violations, or conditional availability findings. `semantic.reference.conditional` means a name is defined on only some paths; `semantic.reference.unavailable_branch` means its definition is in a mutually exclusive branch. Separate conditionals are not evaluated as a simulation of one Calibre run.

## What the tree preserves

| SVRF construct | Representation and checks |
| --- | --- |
| Rule and layer names | Compact colons, numeric components, and quoted names remain part of the name. Rule descriptions retain text and `^VARIABLE` references. |
| `LAYER MAP` | Exact selectors are integers; ranged `gds_num` and `type_num` selectors are lists of `Constraint` nodes. `internal_num` is the target layer; `target_texttype` is `None` unless supplied. |
| DRC and geometry | `INTERNAL`, `EXTERNAL`, and `ENCLOSURE` normalize to `INT`, `EXT`, and `ENC`. Required constraints are checked. `EXPAND EDGE`, `GROW`, and `SHRINK` keep directional distances separate from a following parenthesized layer. `WITH EDGE` can place its count before the second layer. |
| Connectivity and devices | `CONNECT` has a 32-layer limit. `SCONNECT` keeps quoted `LINK` names and `ABUT ALSO`. `Device` separates pins and swap lists from `BY NET`/`BY SHAPE`, netlist options, text layers, signatures, and templates. |
| Preprocessor and macros | `#UNDEFINE` retires definitions on the relevant branch. Standalone and inline `CMACRO`/`FMACRO` calls are checked against reachable definitions, including arity and recursion. `FMACRO` requires `#USING KEYWORD FMACRO`. Device macro calls may have trailing device arguments. Calls are not expanded. |
| DFM specifications | `DfmSpec` and `DfmClause` retain ordered fill, spacing, optimization, and VIA clauses; `DFM SPEC VIA` keeps `VIASHAPE`, `ENC1`, and `ENC2` dimensions. `DFM MAT` retains its continuation clauses. `DFM DV ANALYZE` requires an input layer and an `RDB` filename. |
| Local SVRF | `DFM SPEC SVRF` produces `LocalSvrf` with input names and `NODAL` flags, outputs, numeric variable defaults, parsed body, and `wrapped`/`center` flags. Visible outer variables are inherited, but unrelated outer layers are not; names defined inside do not leak out. |
| TVF and PERC | The final argument of a `TVF FUNCTION` directive is the original bracketed Tcl script, including line endings. `PERC LOAD` retains case-sensitive procedure names and parallel groups. Neither executes Tcl. |
| Protected blocks | `EncryptedBlock` preserves its opener (`#ENCRYPT` or `#DECRYPT`) and payload. `parse_status` distinguishes `plaintext`, `partial` (recognizable declarations with recovery), and `opaque`. Only confidently parsed plaintext can contribute includes. |

Other supported forms include Boolean and spatial layer expressions, measurements, variables and scalar arithmetic, property blocks, and common layout, DRC, LVS, ERC, and PEX directives. `RESOLUTION` requires positive integers. `DRCOp.modifiers` retains the list representation; `modifier_nodes` provides typed views. Recognition of a keyword does not imply that every option combination or its geometric effect is validated. Whole `#!tvf` scripts and dynamically generated SVRF are outside scope.

## Source locations and privacy

File APIs preserve line endings. AST spans use one-based lines/columns and zero-based character offsets with an exclusive end. Validation maps locations back to their source file and include stack. Formatting is canonical: it is **not** a byte-for-byte rewrite of the deck or its comments.

ASTs and diagnostics normally contain source data. Omitting positions with `tree.to_dict(include_position=False)` still exposes identifiers, filenames, and payloads. Use `tree.to_dict(redact_source=True)` for structure without source values, and `diagnostic.to_dict(redact_source=True)` for diagnostic codes, severity, and numeric positions without messages or provenance. Corpus commands redact paths, symbols, and exception text by default; `--show-private-details` is for local debugging. Review even aggregate reports before sharing. Private decks, manuals, and local-only utilities are not required for the public tests and should stay outside a distribution.

## Running tests

```sh
python -B -m unittest discover -s tests -t . -q
```

The current suite discovers **761 tests**. Without external inputs, three corpus integration tests and one manual-inventory check skip. To enable them, point `SVRF_SAMPLES_DIR` at a deck or directory of valid decks, and `SVRF_MANUAL_ROOT` at the extracted SVRF User's Reference directory containing `topics.json` and `toc.json`. The manual and decks are not bundled. The C project provides an optional differential suite comparing ASTs, strict parse outcomes, round trips, diagnostics, and dialect profiles; it is not a Calibre execution test.

### Checking a deck or directory

```sh
python -B test_samples.py tests/fixtures/includes/root_with_layer_include.svrf --fail-on-warnings
python -B audit_sample_corpus.py tests/fixtures/includes/root_with_layer_include.svrf --run-directory tests/fixtures/includes --summary-only --fail-on-errors
```

Replace the file argument with a directory to try **every regular file recursively**, including extensionless and non-SVRF files. `test_samples.py` tests parsing, not include expansion; `--fail-on-warnings` makes recovery fail the gate. `audit_sample_corpus.py` runs validation; `--fail-on-errors` fails when a file is invalid or has errors. For an external-symbol manifest, add `--unresolved-policy practical --symbol-manifest examples/symbol_manifest.example.json` to the audit. A mixed directory is not expected to pass as an all-SVRF corpus.

## Project layout

| Location | Purpose |
| --- | --- |
| [svrf_parser/](svrf_parser/) | Parser and validation sources only: lexer, statement segmenter/CST, normalization, expression and domain parsers, AST, printer, includes, and semantic passes. |
| [Packaged specification tables](svrf_parser/svrf_spec/data/) | Keyword spellings, parser tables, operation contracts, and support profiles. Normal use does not read an external manual. |
| [tests/](tests/) | Unit, integration, and round-trip tests; [fixtures](tests/fixtures/) contain reduced synthetic inputs. |
| [test_samples.py](test_samples.py) and [audit_sample_corpus.py](audit_sample_corpus.py) | Parser and semantic corpus checks; both use [sample_corpus.py](sample_corpus.py) for file selection. |
| [baseline.py](baseline.py) and [coverage_analysis.py](coverage_analysis.py) | Optional corpus metrics and a manual keyword inventory. Keyword coverage is not grammar conformance. |

For parser changes, add a reduced regression under `tests/`. When a change affects a shared operation contract or the normalized AST, check the C port and its differential tests as well.
