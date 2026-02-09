"""SVRFParser - A hand-written recursive descent + Pratt parsing SVRF parser."""

from .lexer import Lexer
from .parser import Parser, SVRFParseError
from .tokens import TokenType
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


# SVRF-characteristic AST node types. A valid SVRF file should contain
# at least one of these after successful parsing.
_SVRF_NODE_TYPES = (
    ast.LayerDef, ast.LayerMap, ast.LayerAssignment,
    ast.Directive, ast.RuleCheckBlock,
    ast.Connect, ast.Device, ast.DMacro,
    ast.Define, ast.IfDef, ast.Include, ast.EncryptedBlock,
    ast.Group, ast.Attach, ast.TraceProperty,
    ast.VariableDef,
)

# Well-known SVRF keywords that may appear as identifiers in the token stream.
_SVRF_KEYWORDS = frozenset({
    'LAYER', 'LAYOUT', 'SOURCE', 'DRC', 'LVS', 'ERC', 'PEX',
    'MASK', 'FLAG', 'UNIT', 'TEXT', 'PORT', 'VIRTUAL', 'SVRF',
    'PRECISION', 'RESOLUTION', 'LABEL', 'TITLE', 'NET', 'PATHCHK',
    'CONNECT', 'SCONNECT', 'DEVICE', 'DMACRO',
    'AND', 'OR', 'NOT', 'INSIDE', 'OUTSIDE', 'INTERACT',
    'TOUCH', 'ENCLOSE', 'BY',
    'GROUP', 'ATTACH', 'TRACE',
    'DRAWN', 'STAMP',
    'EXT', 'INT', 'AREA', 'DENSITY', 'SHRINK', 'EXPAND', 'SIZE',
    'COPY', 'MERGE', 'HOLES', 'EXTENT', 'RECTANGLE', 'POLYGON',
    'ANGLE', 'OFFGRID', 'WITH', 'EDGE', 'LENGTH', 'WIDTH',
})


class ValidationResult:
    """Result of SVRF validation, containing validity status and diagnostics."""

    __slots__ = ('valid', 'errors')

    def __init__(self, valid, errors=None):
        self.valid = valid
        self.errors = errors or []

    def __bool__(self):
        return self.valid

    def __repr__(self):
        if self.valid:
            return "ValidationResult(valid=True)"
        return f"ValidationResult(valid=False, errors={self.errors!r})"


def validate_svrf(text, filename="<input>"):
    """Validate whether *text* is a valid SVRF file.

    Returns a ``ValidationResult`` whose boolean value indicates validity.
    The ``errors`` attribute contains a list of diagnostic strings when
    validation fails.
    """
    errors = []

    # 1. Empty / whitespace-only content is not valid SVRF.
    if not text or not text.strip():
        errors.append("File is empty or contains only whitespace")
        return ValidationResult(False, errors)

    # 2. Tokenization check – also look for SVRF keywords in the token stream.
    try:
        lexer = Lexer(text, filename=filename)
        tokens = lexer.tokens()
    except Exception as exc:
        errors.append(f"Lexer error: {exc}")
        return ValidationResult(False, errors)

    has_svrf_keyword = any(
        tok.type == TokenType.IDENT and tok.value.upper() in _SVRF_KEYWORDS
        for tok in tokens
    )
    has_pp_directive = any(
        tok.type.name.startswith('PP_') for tok in tokens
    )

    if not has_svrf_keyword and not has_pp_directive:
        errors.append(
            "No recognizable SVRF keywords or preprocessor directives found"
        )
        return ValidationResult(False, errors)

    # 3. Parsing check.
    try:
        parser = Parser(tokens)
        program = parser.parse()
    except SVRFParseError as exc:
        errors.append(f"Parse error: {exc}")
        return ValidationResult(False, errors)
    except Exception as exc:
        errors.append(f"Unexpected error during parsing: {exc}")
        return ValidationResult(False, errors)

    # 4. The AST must contain at least one SVRF-characteristic statement.
    if not program.statements:
        errors.append("Parsed file contains no statements")
        return ValidationResult(False, errors)

    has_svrf_node = any(
        isinstance(stmt, _SVRF_NODE_TYPES) for stmt in program.statements
    )
    if not has_svrf_node:
        errors.append(
            "Parsed file contains no recognizable SVRF constructs "
            "(e.g. LAYER, directive, rule check, CONNECT, DEVICE)"
        )
        return ValidationResult(False, errors)

    return ValidationResult(True)


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
