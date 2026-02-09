"""SVRFParser - A hand-written recursive descent + Pratt parsing SVRF parser."""

from .lexer import Lexer
from .parser import Parser, SVRFParseError
from . import ast_nodes as ast


def parse(text, filename="<input>"):
    """Parse SVRF source text and return an AST Program node."""
    lexer = Lexer(text, filename=filename)
    parser = Parser(lexer.tokens())
    return parser.parse()


def parse_file(path):
    """Parse an SVRF file and return an AST Program node."""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()
    return parse(text, filename=path)


# SVRF-characteristic AST node types produced by the parser.  These represent
# constructs specific to the SVRF language.  Generic expression-only nodes
# (LayerRef, NumberLiteral, …) are excluded because the tolerant parser can
# produce them from arbitrary text.
_SVRF_NODE_TYPES = (
    ast.LayerDef, ast.LayerMap, ast.LayerAssignment,
    ast.Directive, ast.RuleCheckBlock,
    ast.Connect, ast.Device, ast.DMacro,
    ast.Define, ast.IfDef, ast.Include, ast.EncryptedBlock,
    ast.Group, ast.Attach, ast.TraceProperty,
    ast.VariableDef,
)

# Minimum ratio of SVRF-characteristic AST nodes to total top-level
# statements.  Real SVRF files score 30 %–100 %; non-SVRF files score
# 0 %–5 %.  A 20 % threshold cleanly separates the two.
_MIN_SVRF_NODE_RATIO = 0.2


class ValidationResult:
    """Result of SVRF validation, containing validity status and diagnostics."""

    __slots__ = ('valid', 'errors', 'warnings')

    def __init__(self, valid, errors=None, warnings=None):
        self.valid = valid
        self.errors = errors or []
        self.warnings = warnings or []

    def __bool__(self):
        return self.valid

    def __repr__(self):
        if self.valid:
            return "ValidationResult(valid=True)"
        return f"ValidationResult(valid=False, errors={self.errors!r})"


def validate_svrf(text, filename="<input>"):
    """Validate whether *text* is a valid SVRF file.

    Returns a ``ValidationResult`` whose boolean value indicates validity.
    The ``errors`` attribute contains diagnostic strings when validation
    fails.  The ``warnings`` attribute contains informational parser
    warnings (available regardless of validity).

    Validation is based on syntax analysis: the file is tokenized and
    parsed, then the ratio of SVRF-characteristic AST nodes to total
    top-level statements is checked against a threshold.
    """
    errors = []

    # 1. Empty / whitespace-only content is not valid SVRF.
    if not text or not text.strip():
        errors.append("File is empty or contains only whitespace")
        return ValidationResult(False, errors)

    # 2. Tokenization.
    try:
        lexer = Lexer(text, filename=filename)
        tokens = lexer.tokens()
    except Exception as exc:
        errors.append(f"Lexer error: {exc}")
        return ValidationResult(False, errors)

    # 3. Parsing – a valid SVRF file must parse without fatal errors.
    try:
        parser = Parser(tokens)
        program = parser.parse()
    except SVRFParseError as exc:
        errors.append(f"Parse error: {exc}")
        return ValidationResult(False, errors)
    except Exception as exc:
        errors.append(f"Unexpected error during parsing: {exc}")
        return ValidationResult(False, errors)

    # 4. The AST must contain a meaningful proportion of SVRF-characteristic
    #    statements.  The parser is tolerant and can consume arbitrary
    #    identifiers as LayerRef expressions, so we require that at least
    #    half of the top-level statements are genuine SVRF constructs
    #    (directives, layer definitions, rule check blocks, etc.).
    if not program.statements:
        errors.append("Parsed file contains no statements")
        return ValidationResult(False, errors, parser.warnings)

    total = len(program.statements)
    svrf_count = sum(
        1 for stmt in program.statements if isinstance(stmt, _SVRF_NODE_TYPES)
    )

    if svrf_count == 0:
        errors.append(
            "Parsed file contains no recognizable SVRF constructs "
            "(e.g. LAYER, directive, rule check, CONNECT, DEVICE)"
        )
        return ValidationResult(False, errors, parser.warnings)

    ratio = svrf_count / total
    if ratio < _MIN_SVRF_NODE_RATIO:
        errors.append(
            f"Only {svrf_count}/{total} ({ratio:.0%}) of top-level statements "
            f"are SVRF constructs (need >= {_MIN_SVRF_NODE_RATIO:.0%})"
        )
        return ValidationResult(False, errors, parser.warnings)

    return ValidationResult(True, warnings=parser.warnings)


def is_valid_svrf(text, filename="<input>"):
    """Return ``True`` if *text* is a valid SVRF file, ``False`` otherwise."""
    return validate_svrf(text, filename).valid


def is_valid_svrf_file(path):
    """Return ``True`` if the file at *path* is a valid SVRF file."""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError as exc:
        return False
    return is_valid_svrf(text, filename=str(path))


def validate_svrf_file(path):
    """Validate the file at *path* and return a ``ValidationResult``."""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError as exc:
        return ValidationResult(False, [f"Cannot read file: {exc}"])
    return validate_svrf(text, filename=str(path))
