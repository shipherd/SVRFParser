# Python and C corpus benchmark

## Reference-dictionary accuracy: 2026-11-25

The recovery parser returned a tree for all 189 inputs. Python, MSVC and GCC
agreed on all six per-file summary fields: 171 files were diagnostic-free,
16 reported unevaluated TVF, and two reported an unterminated property program.
The total was 867,395 rule checks. No source files were excluded by extension.

On the same 15-file detailed sample used below, Python and native C agreed on
**15/15 complete ASTs** (excluding positions), **126,748/126,748 rule bodies**,
**245,989/245,989 source-aligned top-level statements**, ordered rule names,
and all parse diagnostic codes and spans. Both matched all 22,000 independently
identified layer declarations. The previous run matched 11/15 complete ASTs
and had 42 differing rule bodies. The detailed check is a sample, not a
claim that every AST in the 189-file workload was compared. MSVC and GCC
also emitted identical per-statement JSON with spans and identical diagnostics
on each of the 15 files, after normalizing the output record line endings.

The external-reference run exercised 23 SVRF inputs from worked examples in
ten dictionary topics; Python and C parsed all 23 strictly and returned
identical ASTs. Report output and SPICE netlists were not used as decks.
Only HTML nonbreaking spaces were converted to ordinary spaces. To reproduce,
set `SVRF_MANUAL_ROOT` to the extracted reference, `SVRF_NATIVE_EXE` to the
built executable, and run `python -B -m unittest tests.test_reference_examples`.
The inputs themselves are not distributed.

The Python suite ran 804 tests with three optional corpus skips. All four
CTest targets passed under both MSVC and GCC. Each native reference suite
matched 1,731 ASTs, strict outcomes, diagnostic code/severity sets and
dialect profiles, and round-tripped 1,682 clean inputs. Source fingerprints using the method below: Python
`9b1d75c6ce5d2542` (92 files); C `9558a3976a717487` (33 files).
These results do not measure runtime or prove full SVRF grammar or signoff
conformance.

## Earlier post-fix accuracy: 2026-11-25

Python, MSVC Release, and GCC Release returned a tree for all **189** inputs
and agreed per file on status, diagnostics, rule count, and all three
protected-block counts. **171** inputs had no parse diagnostics. The other
18 diagnostics are accounted for:

- **16** mixed TVF files each have one `parser.tvf.opaque_tcl` diagnostic.
  Their literal `tvf::VERBATIM` prefixes contribute **713** rule blocks.
  Tcl-dependent rules are not counted; strict parsing rejects the incomplete
  result. The wrapper source is preserved, not executed.
- **2** macros have a property program without a final `]`. Both parsers
  retain the macro and protected payloads and report
  `parser.property.unterminated`. The other two files whose diagnostic counts
  originally differed now parse without warnings. All four original mismatch
  files now have matching full ASTs and diagnostic spans.

The totals are **867,395** rule blocks, **100,359** opaque protected blocks,
**192** plaintext protected blocks, and no partial protected blocks. TVF
wrappers are not included in the protected-block totals. The full Python
file-to-summary check used the interpreter's default recursion limit.

On the same 15-file detailed sample as the baseline, all 15 now produce trees
and match on ordered rule names and diagnostic codes and spans. Full ASTs
(excluding spans) match on **11/15** files. Of the **245,989** source-aligned
top-level statements, **245,983** match exactly; the remaining six are five
conditional blocks and one TVF wrapper with differences in their bodies.
**126,706/126,748** rule blocks match exactly, and both implementations
matched all **22,000** declarations recognized by the independent source
check. MSVC and GCC emitted identical statement and diagnostic JSON on all
15 files, including spans, after normalizing output record line endings.
The 42 differing Python/C rule bodies are not counted as fixed. This
selected sample is not a conformance score or a population estimate.

With the external manual enabled, the Python suite ran **786** tests with
three external-corpus skips and no failures. Both C Release presets passed
all four CTest targets. On public inputs, each C build matched Python on
**939/939** ASTs and strict parse outcomes and round-tripped **908/908**
diagnostic-free cases. Using the fingerprint method below, the post-fix
sources were Python `d35972d20e442f90` (88 package files) and C
`8ac37c1b50d8ae02` (30 files).

The fixes were checked against the SVRF User's Reference topics on command
parsing, DFM Copy, Net Area Ratio, Pathchk, Touch Inside Edge, device
annotation and macros, and `tvf::VERBATIM`. The DFM DP entry delegates its
detailed syntax to a separate manual: grouped arguments are preserved in
source order, not semantically validated. TVF extraction also respects the
difference between a [Tcl braced word and a substituted argument](https://www.tcl-lang.org/man/tcl8.6/TclCmd/Tcl.htm);
the parser does not interpret substitutions. These checks did not execute
Calibre or remeasure runtime.

## Pre-fix timings: 2026-11-25

The full workload comprised **189 files, 806,676,738 bytes (769.31 MiB)**.
All three parsers returned a tree for the same 173 files, including 169 with
no parse diagnostics, and rejected the same 16. Times include the rejected
inputs; throughput counts supplied bytes even if a lexer stops early. The
repeat workload was nine files, 26,233,601 bytes (25.02 MiB).

| Implementation | Full corpus (s) | Full MiB/s | Speed vs. Python | Repeat median (s) | Repeat runs (s) |
| --- | ---: | ---: | ---: | ---: | --- |
| CPython 3.14.3 | 1,051.567 | 0.732 | 1.0x | 46.237 | 45.388, 46.237, 46.576 |
| C, MSVC Release | 23.233 | 33.113 | 45.3x | 0.940 | 0.943, 0.940, 0.939 |
| C, GCC Release | 23.217 | 33.135 | 45.3x | 1.003 | 1.003, 1.178, 0.999 |

These are end-to-end batch times, not individual-file latency. The native
builds differed by only 0.016 s on a single full pass; that is not evidence
that either compiler produces a faster parser.

## Pre-fix accuracy

The MSVC and GCC summaries matched on **189/189** files. Python and C agreed
on parse status and rule count on **189/189**, and on all six summary fields
on **185/189**. Each counted 866,682 rule blocks across the successful files.
Diagnostic counts differed on four files. Opaque protected-block counts
differed on two (Python: 100,351; C: 100,353). Both counted 192 plaintext
protected blocks and no partial blocks. Equal counts do not prove equal trees.

- All 16 rejected inputs were `#!tvf` wrappers. Python raised a lexer error
  for an unexpected character; C reported `lexer.unexpected_character`.
  These wrappers were not excluded from the benchmark. The failure does not
  establish that the SVRF embedded in them is invalid.
- Among the 173 successful inputs, Python emitted six diagnostics and C
  emitted 14. Both emitted two `parser.parse_error` diagnostics; the other
  difference was four versus 12 `parser.unrecognized_statement` diagnostics.
  Ordered rule names matched on all four affected inputs.

### Detailed comparison

An untimed check covered 15 real files: nine size quantiles including both
extremes, plus a comment-only template, an include-only fragment, a TVF wrapper,
and all four files with differing summaries (overlaps counted once). Both
parsers rejected the same wrapper; the other 14 produced trees.

| Python vs. C (MSVC), on the detailed sample | Exact matches |
| --- | ---: |
| Files with identical ordered rule names | 14 / 14 |
| Files with identical complete ASTs, excluding spans | 8 / 14 |
| Files with identical diagnostic codes and spans | 10 / 14 |
| Source-aligned top-level statements with identical ASTs | 245,951 / 245,988 |
| Rule blocks with identical ASTs | 126,627 / 126,703 |
| Recognizable source `LAYER` / `LAYER MAP` declarations matched by each parser | 22,000 / 22,000 |

The 37 differing top-level statements were 25 rule blocks, 10 conditional
blocks (`IfDef`), and two macro definitions (`DMacro`). Independently, MSVC
and GCC emitted identical statement JSON including spans for all 14 parsed
files, and identical diagnostic JSON on all 15 inputs after normalizing
record line endings. The sample was selected for coverage and includes known
disagreements: **8/14 is not an estimate of the full corpus's AST match rate**.
These comparisons establish where implementations agree, not Calibre conformance.

## Method

This is a warm-cache, single-worker file-to-summary benchmark on Windows x64.
It measures reading a file, parsing with recovery, walking the resulting tree,
and emitting counts. It does not measure semantic validation, include expansion,
formatting, Calibre execution, or a cold filesystem.

- Use all regular files in the selected directory, recursively, without filtering
  extensions or deduplicating files. Sort by relative path with `/` separators.
  Give all implementations the same ordered manifest.
- Use the standard Python file API, `parse_file_with_diagnostics`, then walk
  `Program.walk()`. Count rule blocks, diagnostics, and protected blocks by
  parse status. The equivalent C command is `svrfparse --summary --files-from -`.
- Warm the file cache by reading every input before each timed pass and check
  that its contents do not change. Measure wall time from process launch to
  exit, including startup, file I/O, tree disposal, and summary output. Exclude
  manifest creation, cache warming, result comparison, and deep accuracy checks.
- Run the full corpus once per implementation. For repeat timings, sort by byte
  size (breaking ties by manifest order) and pick the middle file from each of
  nine equal-count bands (zero-based index `floor((2j + 1) * N / 18)` for
  `j = 0..8`). Run that same batch three times per implementation,
  rotating the order: MSVC/GCC/Python, GCC/Python/MSVC, Python/MSVC/GCC.
  Throughput is input bytes divided by wall seconds and by 1,048,576.

## Build and tests

The 2026-11-25 run used CPython 3.14.3, the MSVC 14.51 x64 Release toolset
(`/O2`), and GCC 15.2.0 under MSYS (Release, `-O3`). CMake 4.3.2 built the
native executables. The Python and C working trees included parser changes on
top of commits `b4595f12b0ce` and `995303ad115c`, respectively; these are
baseline commits, not exact identifiers of the tested working trees.

Tested source fingerprints (abbreviated SHA-256): Python `6e9c27f6744cedaa`
for all 86 package `.py` and `.json` files; C `1f5df39ca04c9117` for all 30
files in `src`, `include`, `cli`, and the two top-level CMake files. To
recalculate, sort repository-relative paths by ordinal value and hash the
concatenated UTF-8 records `path + NUL + lowercase_hex_file_digest + LF`.
File digests use SHA-256 over UTF-8 text with CRLF normalized to LF.

The Python unit suite ran 767 tests with four skips and no failures. Both C
Release presets passed all four CTest targets, including the Python-reference
table and parser comparisons. The external corpus and local benchmark driver
are not distributed.
