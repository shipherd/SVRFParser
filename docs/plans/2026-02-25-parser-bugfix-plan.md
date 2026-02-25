# SVRF Parser Bug Fixes + Test Improvements — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 parser bugs and improve test coverage for compound NOT operators, ABUT angle syntax, PERIMETER measurement, SIZE BY modifier types, HOLES/DONUT consistency, and the tier2 Windows path issue.

**Architecture:** Pratt parser with mixin classes and dispatch tables. Fixes target `expression_parser.py`, `drc_op_parser.py`, and `keywords.py`. Tests use `pytest` with helpers in `tests/helpers.py`.

**Tech Stack:** Python 3.14, pytest

---

### Task 1: Fix compound NOT operators (Bug 1)

**Files:**
- Modify: `svrf_parser/expression_parser.py:1257-1286`
- Test: `tests/tier1/test_spatial_ops.py`

**Step 1: Write failing tests**

Add to `tests/tier1/test_spatial_ops.py` in the `TestNotCompound` class:

```python
def test_not_inside(self):
    node = parse_expr("M1 NOT INSIDE M2")
    assert_node_type(node, BinaryOp, op="NOT INSIDE")

def test_not_interact(self):
    node = parse_expr("M1 NOT INTERACT M2")
    assert_node_type(node, BinaryOp, op="NOT INTERACT")

def test_not_enclose(self):
    node = parse_expr("M1 NOT ENCLOSE M2")
    assert_node_type(node, BinaryOp, op="NOT ENCLOSE")

def test_not_cut(self):
    node = parse_expr("M1 NOT CUT M2")
    assert_node_type(node, BinaryOp, op="NOT CUT")

def test_not_inside_edge(self):
    node = parse_expr("M1 NOT INSIDE EDGE M2")
    assert_node_type(node, BinaryOp, op="NOT INSIDE EDGE")

def test_not_outside_edge(self):
    node = parse_expr("M1 NOT OUTSIDE EDGE M2")
    assert_node_type(node, BinaryOp, op="NOT OUTSIDE EDGE")
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/tier1/test_spatial_ops.py::TestNotCompound -v`
Expected: 4 new tests FAIL (NOT INSIDE, NOT INTERACT, NOT ENCLOSE, NOT CUT produce `BinaryOp(op='NOT')` instead of compound ops). NOT INSIDE EDGE and NOT OUTSIDE EDGE may also fail.

**Step 3: Fix `_led_binary_op` in `expression_parser.py`**

At line 1271, after the `NOT IN / NOT OUT / NOT OUTSIDE` block, add a new block before the generic fallthrough at line 1318:

```python
# NOT INSIDE / NOT INTERACT / NOT ENCLOSE / NOT CUT [EDGE] as compound binary ops
if upper == 'NOT' and self._at(TT.IDENT) and self._cur().value.upper() in (
        'INSIDE', 'INTERACT', 'ENCLOSE', 'CUT'):
    not_rhs = self._advance().value.upper()
    op_name = 'NOT ' + not_rhs
    # NOT INSIDE EDGE / NOT ENCLOSE EDGE etc.
    if self._at(TT.IDENT) and self._cur().value.upper() == 'EDGE':
        self._advance()
        op_name += ' EDGE'
    if self._at_eol() and self._block_depth > 0:
        self._consume_eol()
        self._skip_newlines()
    right = self._parse_layer_expr(bp)
    result = ast.BinaryOp(op=op_name, left=left, right=right, **loc)
    return self._maybe_trailing_modifiers(result, loc)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/tier1/test_spatial_ops.py::TestNotCompound -v`
Expected: All PASS

**Step 5: Run full test suite + sample files**

Run: `pytest tests/tier1/ tests/tier3/ -v`
Expected: All 154+ tests PASS

Run sample file validation:
```python
python -c "
import sys; sys.path.insert(0,'.')
from svrf_parser import parse_file_with_diagnostics
import os
for root, dirs, files in os.walk(r'C:\Users\Boshe\Desktop\tmp\svrf_samples'):
    for f in files:
        if f.endswith(('.drc','.lvs','.ant')):
            path = os.path.join(root, f)
            prog, w = parse_file_with_diagnostics(path)
            errs = sum(1 for s in prog.statements if type(s).__name__=='ErrorNode')
            print(f'{f}: {len(prog.statements)} stmts, {errs} errors, {len(w)} warnings')
"
```
Expected: 0 errors, 0 warnings for all files

**Step 6: Commit**

```bash
git add svrf_parser/expression_parser.py tests/tier1/test_spatial_ops.py
git commit -m "fix: compound NOT operators (NOT INSIDE/INTERACT/ENCLOSE/CUT)"
```

---

### Task 2: Fix ABUT<angle> modifier parsing (Bug 2)

**Files:**
- Modify: `svrf_parser/drc_op_parser.py:18-50`
- Test: `tests/tier1/test_drc_ops.py`

**Step 1: Write failing tests**

Add to `tests/tier1/test_drc_ops.py`:

```python
class TestAbutAngle:
    def test_abut_90(self):
        node = parse_expr("INT M1 < 0.12 ABUT<90> SINGULAR REGION")
        assert isinstance(node, DRCOp)
        assert 'ABUT<90>' in node.modifiers
        assert 'SINGULAR' in node.modifiers
        assert 'REGION' in node.modifiers

    def test_abut_range(self):
        node = parse_expr("INT M1 < 0.12 ABUT>0<90>")
        assert isinstance(node, DRCOp)
        assert 'ABUT>0<90>' in node.modifiers

    def test_abut_180(self):
        node = parse_expr("INT M1 < 0.12 ABUT<180>")
        assert isinstance(node, DRCOp)
        assert 'ABUT<180>' in node.modifiers
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/tier1/test_drc_ops.py::TestAbutAngle -v`
Expected: FAIL — modifiers contain `['ABUT', '<90', '>SINGULAR', 'REGION']` instead of `['ABUT<90>', 'SINGULAR', 'REGION']`

**Step 3: Fix `_parse_drc_modifiers` in `drc_op_parser.py`**

In `_parse_drc_modifiers` (line 18), add ABUT angle detection before the generic IDENT handler at line 22. Replace the block starting at line 20:

```python
while not self._at_eol():
    t = self._cur()
    # ABUT<angle> or ABUT>angle<angle> — consume as single modifier
    if t.type == TT.IDENT and t.value.upper() == 'ABUT':
        abut_str = self._advance().value.upper()
        # Check for <angle> or >angle<angle>
        if not self._at_eol() and self._cur().type in (TT.LT, TT.GT_OP):
            while not self._at_eol() and self._cur().type in (
                    TT.LT, TT.GT_OP, TT.INTEGER, TT.FLOAT):
                abut_str += str(self._advance().value)
            modifiers.append(abut_str)
        else:
            modifiers.append(abut_str)
        continue
    if t.type == TT.IDENT:
```

(The rest of the method stays the same from the original `if t.type == TT.IDENT:` onward.)

**Step 4: Run tests to verify they pass**

Run: `pytest tests/tier1/test_drc_ops.py::TestAbutAngle -v`
Expected: All PASS

**Step 5: Run full suite + samples**

Run: `pytest tests/tier1/ tests/tier3/ -v && python -c "...sample validation..."`
Expected: All pass, 0 errors/warnings on samples

**Step 6: Commit**

```bash
git add svrf_parser/drc_op_parser.py tests/tier1/test_drc_ops.py
git commit -m "fix: ABUT<angle> parsed as single modifier token"
```

---

### Task 3: Add PERIMETER as measurement op (Bug 3)

**Files:**
- Modify: `svrf_parser/keywords.py:105`
- Modify: `svrf_parser/expression_parser.py:228` (NUD dispatch table)
- Test: `tests/tier1/test_drc_ops.py`

**Step 1: Write failing tests**

Add to `tests/tier1/test_drc_ops.py`:

```python
class TestPerimeter:
    def test_perimeter_prefix(self):
        node = parse_expr("PERIMETER M1 > 5.0")
        assert isinstance(node, ConstrainedExpr)
        assert isinstance(node.expr, UnaryOp)
        assert node.expr.op == "PERIMETER"
        assert len(node.constraints) == 1

    def test_perimeter_no_constraint(self):
        node = parse_expr("PERIMETER M1")
        assert isinstance(node, UnaryOp)
        assert node.op == "PERIMETER"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/tier1/test_drc_ops.py::TestPerimeter -v`
Expected: FAIL — PERIMETER not recognized as expr_starter, parsed as LayerRef

**Step 3: Add PERIMETER as expr_starter and NUD entry**

In `keywords.py` line 105, change:
```python
'PERIMETER':   {'drc_modifier'},
```
to:
```python
'PERIMETER':   {'drc_modifier', 'expr_starter'},
```

In `expression_parser.py` NUD dispatch table (around line 238), add:
```python
'PERIMETER': '_nud_area',
```

(Reuses `_nud_area` which calls `_parse_area_op` — same pattern: `OP operand [constraints]`. The `_parse_area_op` method at `drc_op_parser.py:395` uses `self._advance().value.upper()` for the op name, so it will correctly produce `PERIMETER` instead of `AREA`.)

**Step 4: Run tests to verify they pass**

Run: `pytest tests/tier1/test_drc_ops.py::TestPerimeter -v`
Expected: All PASS

**Step 5: Run full suite + samples**

Expected: All pass, 0 errors/warnings

**Step 6: Commit**

```bash
git add svrf_parser/keywords.py svrf_parser/expression_parser.py tests/tier1/test_drc_ops.py
git commit -m "fix: PERIMETER recognized as prefix measurement op"
```

---

### Task 4: Fix SIZE BY modifier type inconsistency (Bug 4)

**Files:**
- Modify: `svrf_parser/drc_op_parser.py:354-359`
- Modify: `svrf_parser/expression_parser.py:1193-1196`
- Test: `tests/tier1/test_size_grow.py`

**Step 1: Write failing tests**

Add to `tests/tier1/test_size_grow.py`:

```python
class TestSizeByType:
    def test_size_by_modifier_is_tuple(self):
        """SIZE BY value should store ('BY', expr) tuple, not raw AST node."""
        node = parse_expr("SIZE M1 BY 0.5")
        assert isinstance(node, DRCOp)
        assert node.op == "SIZE"
        by_items = [m for m in node.modifiers if isinstance(m, tuple) and m[0] == 'BY']
        assert len(by_items) == 1
        assert isinstance(by_items[0][1], (NumberLiteral, int, float))

    def test_size_by_with_overunder(self):
        node = parse_expr("SIZE M1 BY 0.5 OVERUNDER")
        assert isinstance(node, DRCOp)
        by_items = [m for m in node.modifiers if isinstance(m, tuple) and m[0] == 'BY']
        assert len(by_items) == 1
        assert 'OVERUNDER' in [m for m in node.modifiers if isinstance(m, str)]
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/tier1/test_size_grow.py::TestSizeByType -v`
Expected: FAIL — BY value is raw AST node, not tuple

**Step 3: Fix both SIZE BY locations**

In `drc_op_parser.py` line 359, change:
```python
modifiers.append(by_expr)
```
to:
```python
modifiers.append(('BY', by_expr))
```

In `expression_parser.py` line 1196, change:
```python
modifiers.append(by_expr)
```
to:
```python
modifiers.append(('BY', by_expr))
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/tier1/test_size_grow.py::TestSizeByType -v`
Expected: All PASS

**Step 5: Run full suite + samples**

Expected: All pass, 0 errors/warnings

**Step 6: Commit**

```bash
git add svrf_parser/drc_op_parser.py svrf_parser/expression_parser.py tests/tier1/test_size_grow.py
git commit -m "fix: SIZE BY stores ('BY', expr) tuple for type consistency"
```

---

### Task 5: Fix HOLES/DONUT AST inconsistency (Bug 5)

**Files:**
- Modify: `svrf_parser/expression_parser.py:425-436`
- Test: `tests/tier1/test_size_grow.py`

**Step 1: Write failing test**

Add to `tests/tier1/test_size_grow.py`:

```python
class TestHolesDonutConsistency:
    def test_holes_returns_unary_op(self):
        """HOLES should return UnaryOp like DONUT does."""
        node = parse_expr("HOLES M1")
        assert isinstance(node, UnaryOp)
        assert node.op == "HOLES"

    def test_donut_returns_unary_op(self):
        node = parse_expr("DONUT M1")
        assert isinstance(node, UnaryOp)
        assert node.op == "DONUT"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/tier1/test_size_grow.py::TestHolesDonutConsistency -v`
Expected: `test_holes_returns_unary_op` FAILS — HOLES returns DRCOp, not UnaryOp

**Step 3: Fix `_nud_holes`**

In `expression_parser.py` lines 425-436, replace:
```python
def _nud_holes(self, t, loc):
    self._advance()
    operand = self._parse_layer_expr(50)
    modifiers = []
    while not self._at_eol() and self._at(TT.IDENT):
        mod_u = self._cur().value.upper()
        if mod_u in _DRC_MODIFIERS:
            modifiers.append(self._advance().value)
        else:
            break
    return ast.DRCOp(op='HOLES', operands=[operand],
                     constraints=[], modifiers=modifiers, **self._loc())
```
with:
```python
def _nud_holes(self, t, loc):
    self._advance()
    operand = self._parse_layer_expr(50)
    return ast.UnaryOp(op='HOLES', operand=operand, **loc)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/tier1/test_size_grow.py::TestHolesDonutConsistency -v`
Expected: All PASS

**Step 5: Run full suite + samples**

Expected: All pass, 0 errors/warnings

**Step 6: Commit**

```bash
git add svrf_parser/expression_parser.py tests/tier1/test_size_grow.py
git commit -m "fix: HOLES returns UnaryOp consistent with DONUT"
```

---

### Task 6: Fix tier2 integration test Windows path bug

**Files:**
- Modify: `tests/tier2/test_integration.py:37-41`

**Step 1: Fix the path computation**

The bug is at line 38-41: when `SAMPLES_DIR` is empty (default `""`), `Path("")` resolves to the current directory, and `os.path.relpath` fails on Windows when comparing paths on different mounts.

Replace lines 37-41:
```python
_ALL_SAMPLES = _collect_samples()
_SAMPLE_IDS = [
    os.path.relpath(str(f), str(SAMPLES_DIR)).replace("\\", "/")
    for f in _ALL_SAMPLES
]
```
with:
```python
_ALL_SAMPLES = _collect_samples()
_SAMPLE_IDS = [
    f.name for f in _ALL_SAMPLES
] if _ALL_SAMPLES else []
```

**Step 2: Run tier2 tests**

Run: `SVRF_SAMPLES_DIR="C:\Users\Boshe\Desktop\tmp\svrf_samples" pytest tests/tier2/ -v`
Expected: All PASS (or skip if env var not set)

Also verify collection works without env var:
Run: `pytest tests/tier2/ --collect-only`
Expected: No collection error

**Step 3: Commit**

```bash
git add tests/tier2/test_integration.py
git commit -m "fix: tier2 integration test Windows path handling"
```

---

### Task 7: Add deeper test coverage

**Files:**
- Create: `tests/tier1/test_compound_expressions.py`

**Step 1: Write tests for complex/nested expressions and edge cases**

```python
"""Tier 1 unit tests: Complex compound expressions and edge cases."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import parse_expr, parse_one, assert_node_type, collect_warnings
from svrf_parser.ast_nodes import *


class TestDeepNesting:
    def test_triple_nested_boolean(self):
        node = parse_expr("((A AND B) OR C) NOT D")
        assert isinstance(node, BinaryOp)
        assert node.op == "NOT"

    def test_chained_spatial(self):
        node = parse_expr("(A NOT B) NOT INTERACT C")
        assert isinstance(node, BinaryOp)
        assert node.op == "NOT INTERACT"

    def test_not_interact_in_parens(self):
        node = parse_expr("(A NOT INTERACT B) AND C")
        assert isinstance(node, BinaryOp)
        assert node.op == "AND"
        assert isinstance(node.left, BinaryOp)
        assert node.left.op == "NOT INTERACT"


class TestSamplePatterns:
    """Patterns extracted from real SVRF sample files."""

    def test_complex_not_chain(self):
        """From 7nm calibre.drc: X = (GT NOT FTGT) NOT INTERACT HRP"""
        node = parse_expr("(GT NOT FTGT) NOT INTERACT HRP")
        assert isinstance(node, BinaryOp)
        assert node.op == "NOT INTERACT"

    def test_int_abut_singular_region(self):
        """From 14nm DRC: INT MOS12 < 0.12 ABUT<90> SINGULAR REGION"""
        node = parse_expr("INT MOS12 < 0.12 ABUT<90> SINGULAR REGION")
        assert isinstance(node, DRCOp)
        assert 'ABUT<90>' in node.modifiers
        assert 'SINGULAR' in node.modifiers
        assert 'REGION' in node.modifiers

    def test_size_by_overunder(self):
        node = parse_expr("SIZE M1 BY 0.5 OVERUNDER")
        assert isinstance(node, DRCOp)
        assert node.op == "SIZE"
        by_items = [m for m in node.modifiers if isinstance(m, tuple) and m[0] == 'BY']
        assert len(by_items) == 1


class TestNegativeCases:
    def test_unclosed_paren_no_crash(self):
        """Parser should not crash on unclosed parens."""
        warnings = collect_warnings("X = (A AND B")
        # Should parse without exception (may produce warnings)

    def test_empty_assignment(self):
        warnings = collect_warnings("X =")
        # Should not crash
```

**Step 2: Run tests**

Run: `pytest tests/tier1/test_compound_expressions.py -v`
Expected: All PASS (these test the fixes from Tasks 1-5)

**Step 3: Commit**

```bash
git add tests/tier1/test_compound_expressions.py
git commit -m "test: add compound expression, sample pattern, and negative tests"
```

---

### Task 8: Final validation

**Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS, no collection errors

**Step 2: Run sample file validation**

Verify all 9 sample files parse with 0 errors and 0 warnings.

**Step 3: Final commit (if any fixups needed)**
