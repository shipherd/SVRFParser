"""SVRFParser - A hand-written recursive descent + Pratt parsing SVRF parser."""

from .lexer import Lexer
from .parser import Parser, SVRFParseError


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


# Maximum ratio of parser warnings to total statements allowed for a file
# to be considered valid SVRF.  A high warning ratio means the parser had
# to fall back to bare-expression / skip-token handling too often, which
# indicates the content is not genuine SVRF.
_MAX_WARNING_RATIO = 0.3


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

    Validation is based entirely on syntax analysis: the parser records
    warnings whenever it encounters constructs it cannot recognise as
    valid SVRF.  If the warning-to-statement ratio exceeds the threshold,
    the file is considered invalid.
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

    # 4. Check parser warnings.  The parser records a warning every time it
    #    falls back to bare-expression parsing or skips an unknown token.
    #    A genuine SVRF file should produce very few (if any) warnings.
    if not program.statements:
        errors.append("Parsed file contains no statements")
        return ValidationResult(False, errors)

    total = len(program.statements)
    warn_count = len(parser.warnings)

    if total > 0 and warn_count / total > _MAX_WARNING_RATIO:
        errors.append(
            f"Too many syntax warnings: {warn_count}/{total} statements "
            f"({warn_count/total:.0%}) were not recognized as valid SVRF "
            f"(threshold {_MAX_WARNING_RATIO:.0%})"
        )
        errors.extend(parser.warnings[:10])
        if warn_count > 10:
            errors.append(f"... and {warn_count - 10} more warnings")
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
