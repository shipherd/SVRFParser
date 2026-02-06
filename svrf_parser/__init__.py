"""SVRFParser - A hand-written recursive descent + Pratt parsing SVRF parser."""

from .lexer import Lexer
from .parser import Parser


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
