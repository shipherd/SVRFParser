"""Recursive descent + Pratt parser for SVRF source files."""

from .parser_base import ParserBase, SVRFParseError
from .statement_parser import StatementMixin
from .expression_parser import ExpressionMixin
from .drc_op_parser import DRCOpMixin
from .property_block_parser import PropertyBlockMixin


class Parser(StatementMixin, PropertyBlockMixin, DRCOpMixin,
             ExpressionMixin, ParserBase):
    """SVRF parser using recursive descent + Pratt parsing."""
    pass
