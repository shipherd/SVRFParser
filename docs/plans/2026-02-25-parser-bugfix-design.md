# SVRF Parser Bug Fixes + Test Improvements Design

Date: 2026-02-25

## Bugs

### Bug 1: Compound NOT operators (Critical)
`A NOT INTERACT B` parses as `BinaryOp('NOT', A, UnaryOp('INTERACT', B))` instead of `BinaryOp('NOT INTERACT', A, B)`.
Fix: In `expression_parser.py` `_led_binary_op`, extend the NOT follow-up keyword set to include INSIDE, INTERACT, ENCLOSE, CUT.

### Bug 2: ABUT<angle> syntax (Critical)
`ABUT<90> SINGULAR` is mis-tokenized — `<90>` eats the next modifier.
Fix: In `drc_op_parser.py` `_parse_drc_modifiers`, detect ABUT + < + number + > and consume as single modifier string.

### Bug 3: PERIMETER not a measurement op (Medium)
`PERIMETER A > 5.0` splits into two statements instead of parsing as a unary constrained op.
Fix: Add `expr_starter` role to PERIMETER in `keywords.py`, add NUD dispatch entry in `expression_parser.py`.

### Bug 4: SIZE BY modifier type inconsistency (Medium)
BY value stored as raw AST node in modifier list alongside strings.
Fix: Store as structured tuple `('BY', value)` in the modifiers list.

### Bug 5: HOLES/DONUT AST inconsistency (Low)
HOLES → DRCOp, DONUT → UnaryOp for equivalent operations.
Fix: Change `_nud_holes` to return UnaryOp like `_nud_donut`.

## Test Improvements

- Compound NOT forms: NOT INTERACT, NOT ENCLOSE, NOT CUT, NOT INSIDE
- ABUT angle syntax: ABUT<90>, ABUT>0<90>, ABUT<180>
- PERIMETER as measurement op with constraints
- SIZE BY modifier type
- HOLES/DONUT consistency
- Deeply nested expressions
- Negative/malformed input tests
- Fix tier2 integration test Windows path bug

## Verification

All 9 sample files must parse with 0 errors/0 warnings after changes.
All existing 154 tests must continue to pass.
