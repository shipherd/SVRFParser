"""Custom exceptions for the reconstructed SVRF parser."""


class SVRFError(Exception):
    """Base class for SVRF front-end errors."""


class LexerError(SVRFError):
    """Raised when tokenization fails."""

    def __init__(self, message, line=0, col=0):
        self.line = line
        self.col = col
        super().__init__(f"L{line}:{col}: {message}")


class ParseError(SVRFError):
    """Raised when parsing fails."""

    def __init__(self, message, line=0, col=0, token=None):
        self.line = line
        self.col = col
        self.token = token
        super().__init__(f"L{line}:{col}: {message}")


# Backward-compatible alias used by the package entrypoint.
SVRFParseError = ParseError
