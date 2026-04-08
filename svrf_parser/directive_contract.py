"""Declarative manual-backed directive contracts for semantic validation."""

from __future__ import annotations

from dataclasses import dataclass


_YES_NO = frozenset({"YES", "NO"})


@dataclass(frozen=True, slots=True)
class DirectiveContract:
    name: str
    keywords: tuple[str, ...]
    dialect: str
    family: str
    value_sets: dict[str, frozenset[str]]
    ordered_values: dict[str, tuple[str, ...]]
    clause_sequences: dict[str, tuple[tuple[str, ...], ...]]


class DirectiveContractRegistry:
    def __init__(self, contracts):
        self.contracts = tuple(sorted(contracts, key=lambda contract: (len(contract.keywords), contract.name)))
        self._by_keywords = {contract.keywords: contract for contract in self.contracts}

    def get(self, keywords):
        return self._by_keywords.get(tuple(keywords))


def _boolean_suffix(name, keywords, dialect):
    return DirectiveContract(
        name,
        keywords,
        dialect,
        "boolean_suffix",
        {"values": _YES_NO},
        {},
        {},
    )


DIRECTIVE_CONTRACTS = (
    DirectiveContract(
        "LVS COMPARE CASE",
        ("LVS", "COMPARE", "CASE"),
        "LVS",
        "ordered_options",
        {},
        {"fields": ("NAMES", "TYPES", "SUBTYPES", "VALUES")},
        {},
    ),
    DirectiveContract(
        "LVS RECOGNIZE GATES",
        ("LVS", "RECOGNIZE", "GATES"),
        "LVS",
        "ordered_optional_clauses",
        {"modes": frozenset({"ALL", "SIMPLE", "NONE"})},
        {},
        {
            "optional_clauses": (
                ("MIX", "SUBTYPES"),
                ("XALSO",),
                ("WITHIN", "TOLERANCE"),
                ("WITH", "SUBSTRATE"),
            ),
            "trailing_clause": (("CELL", "LIST"),),
        },
    ),
    DirectiveContract(
        "LVS RECOGNIZE GATES TOLERANCE",
        ("LVS", "RECOGNIZE", "GATES", "TOLERANCE"),
        "LVS",
        "tolerance",
        {
            "scope_keywords": frozenset({"LAYOUT", "SOURCE"}),
            "series_parallel_keywords": frozenset({"SERIES", "PARALLEL"}),
        },
        {"scope_order": ("LAYOUT", "SOURCE")},
        {},
    ),
    DirectiveContract(
        "LVS SPICE STRICT",
        ("LVS", "SPICE", "STRICT"),
        "LVS",
        "strict_pair",
        {
            "fields": frozenset({"WL"}),
            "values": frozenset({"NO", "YES", "NONE"}),
        },
        {},
        {},
    ),
    _boolean_suffix("LVS IGNORE PORTS", ("LVS", "IGNORE", "PORTS"), "LVS"),
    DirectiveContract(
        "LVS REPORT OPTION",
        ("LVS", "REPORT", "OPTION"),
        "LVS",
        "option_list",
        {
            "options": frozenset(
                {
                    "A",
                    "AV",
                    "B",
                    "BPE",
                    "BPW",
                    "BV",
                    "BX",
                    "C",
                    "CV",
                    "D",
                    "E",
                    "E1",
                    "EB",
                    "EC",
                    "EERC",
                    "EO",
                    "ES",
                    "F",
                    "FX",
                    "G",
                    "H",
                    "I",
                    "IM",
                    "LPE",
                    "LPW",
                    "MC",
                    "N",
                    "NCA",
                    "NE",
                    "NOK",
                    "NP",
                    "NSC",
                    "NONE",
                    "O",
                    "P",
                    "PG",
                    "PMV",
                    "R",
                    "RA",
                    "RD",
                    "S",
                    "SP",
                    "SPE",
                    "UP",
                    "V",
                    "W",
                    "X",
                    "XC",
                    "XR",
                    "Y",
                }
            ),
            "exclusive_options": frozenset({"NONE"}),
        },
        {},
        {},
    ),
    DirectiveContract(
        "LVS SOFTCHK",
        ("LVS", "SOFTCHK"),
        "LVS",
        "softchk",
        {
            "second_arg_values": frozenset({"LOWER", "CONTACT", "UPPER"}),
            "third_arg_values": frozenset({"ALL"}),
        },
        {},
        {},
    ),
    DirectiveContract(
        "DRC INCREMENTAL CONNECT",
        ("DRC", "INCREMENTAL", "CONNECT"),
        "DRC",
        "incremental_connect",
        {
            "warning_values": frozenset({"ENABLE", "DISABLE"}),
        },
        {},
        {"warning_prefix": (("WARNING",),)},
    ),
    DirectiveContract(
        "DRC SUMMARY REPORT",
        ("DRC", "SUMMARY", "REPORT"),
        "DRC",
        "summary_report",
        {
            "modes": frozenset({"REPLACE", "APPEND"}),
        },
        {"flags": ("HIER", "EXECUTED")},
        {},
    ),
    DirectiveContract(
        "ERC SUMMARY REPORT",
        ("ERC", "SUMMARY", "REPORT"),
        "ERC",
        "summary_report",
        {
            "modes": frozenset({"REPLACE", "APPEND"}),
        },
        {"flags": ("HIER",)},
        {},
    ),
    DirectiveContract(
        "ERC RESULTS DATABASE",
        ("ERC", "RESULTS", "DATABASE"),
        "ERC",
        "results_database",
        {
            "formats": frozenset({"ASCII"}),
            "final_modes": frozenset({"PSEUDO", "TOP"}),
        },
        {},
        {},
    ),
    DirectiveContract(
        "PEX REPORT NETSUMMARY",
        ("PEX", "REPORT", "NETSUMMARY"),
        "PEX",
        "report_netsummary",
        {
            "scopes": frozenset({"FULL", "LOCAL", "ALL"}),
            "details": frozenset({"DETAIL", "SUMMARY"}),
            "columns": frozenset({"BASIC", "ADVANCED"}),
        },
        {},
        {
            "selection_clauses": (("LAYOUT",), ("SOURCE",), ("NETFILE",)),
            "trailing_clauses": (("CELL",), ("SCALE",), ("COLUMNS",)),
        },
    ),
    DirectiveContract(
        "PEX REPORT POINT2POINT",
        ("PEX", "REPORT", "POINT2POINT"),
        "PEX",
        "report_point2point",
        {
            "units": frozenset({"UNIT_LENGTH", "DBU"}),
            "names": frozenset({"LAYOUTNAMES", "SOURCENAMES"}),
            "sameport_values": frozenset({"OPEN", "SHORT"}),
        },
        {},
        {},
    ),
    _boolean_suffix(
        "PEX NETLIST MUTUAL RESISTANCE",
        ("PEX", "NETLIST", "MUTUAL", "RESISTANCE"),
        "PEX",
    ),
    _boolean_suffix(
        "PEX NETLIST VIRTUAL CONNECT",
        ("PEX", "NETLIST", "VIRTUAL", "CONNECT"),
        "PEX",
    ),
    _boolean_suffix(
        "PEX NETLIST GROUNDNET GLOBAL",
        ("PEX", "NETLIST", "GROUNDNET", "GLOBAL"),
        "PEX",
    ),
    _boolean_suffix(
        "PEX NETLIST NOXREF NET NAMES",
        ("PEX", "NETLIST", "NOXREF", "NET", "NAMES"),
        "PEX",
    ),
    _boolean_suffix(
        "PEX NETLIST LPE IGNORE IDEALNET",
        ("PEX", "NETLIST", "LPE", "IGNORE", "IDEALNET"),
        "PEX",
    ),
    _boolean_suffix(
        "PEX NETLIST CREATE SMASHED DEVICE NAMES",
        ("PEX", "NETLIST", "CREATE", "SMASHED", "DEVICE", "NAMES"),
        "PEX",
    ),
    _boolean_suffix(
        "PEX NETLIST EXPORT PORTS",
        ("PEX", "NETLIST", "EXPORT", "PORTS"),
        "PEX",
    ),
    DirectiveContract(
        "PEX NETLIST UPPERCASE",
        ("PEX", "NETLIST", "UPPERCASE"),
        "PEX",
        "ordered_boolean_pairs",
        {"values": _YES_NO},
        {"fields": ("KEYWORDS", "MODELNAMES", "PARAMETERS")},
        {},
    ),
    DirectiveContract(
        "PEX NETLIST CONNECTION SECTION",
        ("PEX", "NETLIST", "CONNECTION", "SECTION"),
        "PEX",
        "connection_section",
        {
            "values": _YES_NO,
            "yes_trailing_values": frozenset({"INST_LOC"}),
        },
        {},
        {},
    ),
    DirectiveContract(
        "PEX NETLIST UNSHORT DEVICE PINS",
        ("PEX", "NETLIST", "UNSHORT", "DEVICE", "PINS"),
        "PEX",
        "numeric_or_disable",
        {
            "disable_values": frozenset({"NO"}),
        },
        {},
        {},
    ),
    DirectiveContract(
        "PEX NETLIST LINEWRAP",
        ("PEX", "NETLIST", "LINEWRAP"),
        "PEX",
        "numeric_or_disable",
        {
            "disable_values": frozenset({"NO"}),
        },
        {},
        {},
    ),
    DirectiveContract(
        "DRC RESULTS DATABASE",
        ("DRC", "RESULTS", "DATABASE"),
        "DRC",
        "results_database",
        {
            "gds_formats": frozenset({"GDSII", "GDS", "GDS2"}),
            "formats": frozenset({"ASCII", "OASIS", "GDSII", "GDS", "GDS2"}),
            "oasis_compression": frozenset({"CBLOCK", "NOCBLOCK"}),
            "strictness": frozenset({"STRICT", "NOSTRICT"}),
            "final_modes": frozenset({"PSEUDO", "TOP", "COMBINE"}),
        },
        {},
        {"compression_modes": (("CBLOCK",), ("NOCBLOCK",))},
    ),
)


DIRECTIVE_CONTRACT_REGISTRY = DirectiveContractRegistry(DIRECTIVE_CONTRACTS)
