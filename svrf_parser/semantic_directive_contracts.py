"""Directive validation contract handles and argument-count tables."""

from __future__ import annotations

from .directive_contract import DIRECTIVE_CONTRACT_REGISTRY

DIRECTIVE_MIN_ARGUMENTS = {
    ("DRC",): 1,
    ("DFM",): 1,
    ("ERC",): 1,
    ("DRC", "INCREMENTAL", "CONNECT"): 1,
    ("LAYOUT", "PATH"): 1,
    ("LAYOUT", "PRIMARY"): 1,
    ("LVS",): 1,
    ("LVS", "CHECK"): 1,
    ("LVS", "COMPARE", "CASE"): 1,
    ("LVS", "FILTER", "UNUSED", "OPTION"): 1,
    ("LVS", "GROUND", "NAME"): 1,
    ("LVS", "IGNORE", "PORTS"): 1,
    ("LVS", "POWER", "NAME"): 1,
    ("LVS", "PROPERTY"): 1,
    ("LVS", "REPORT"): 1,
    ("LVS", "REPORT", "OPTION"): 1,
    ("LVS", "SOFTCHK"): 1,
    ("LVS", "SPICE", "MULTIPLIER", "NAME"): 1,
    ("LVS", "SPICE", "STRICT"): 1,
    ("PEX",): 1,
    ("PEX", "NETLIST"): 1,
    ("SOURCE", "PATH"): 1,
    ("SOURCE", "PRIMARY"): 1,
    ("DRC", "RESULTS", "DATABASE"): 1,
    ("DRC", "RESULTS", "DATABASE", "PRECISION"): 1,
    ("DRC", "SUMMARY", "REPORT"): 1,
    ("DRC", "MAGNIFY", "RESULTS"): 1,
    ("DRC", "MAGNIFY", "DENSITY"): 1,
    ("DRC", "MAGNIFY", "NAR"): 1,
    ("ERC", "MAXIMUM", "RESULTS"): 1,
    ("ERC", "RESULTS", "DATABASE"): 1,
    ("ERC", "SUMMARY", "REPORT"): 1,
    ("TITLE",): 1,
    ("PRECISION",): 1,
    ("RESOLUTION",): 1,
}

DIRECTIVE_ALLOWED_ARGUMENT_COUNTS = {
    ("DRC", "INCREMENTAL", "CONNECT", "NO"): frozenset({0}),
    ("DRC", "INCREMENTAL", "CONNECT", "YES"): frozenset({0}),
    ("DRC", "KEEP", "EMPTY", "NO"): frozenset({0}),
    ("DRC", "KEEP", "EMPTY", "YES"): frozenset({0}),
    ("DRC", "MAGNIFY", "DENSITY"): frozenset({1}),
    ("DRC", "MAGNIFY", "NAR"): frozenset({1}),
    ("DRC", "MAXIMUM", "RESULTS", "ALL"): frozenset({0}),
    ("DRC", "MAXIMUM", "RESULTS", "NAR"): frozenset({1}),
    ("DRC", "MAXIMUM", "RESULTS", "NAR", "ALL"): frozenset({0}),
    ("ERC", "MAXIMUM", "RESULTS", "ALL"): frozenset({0}),
    ("DRC", "UNSELECT", "CHECK"): frozenset({1}),
    ("LVS", "COMPARE", "CASE", "NO"): frozenset({0}),
    ("LVS", "COMPARE", "CASE", "YES"): frozenset({0}),
    ("LVS", "IGNORE", "PORTS", "YES"): frozenset({0}),
    ("LVS", "IGNORE", "PORTS", "NO"): frozenset({0}),
    ("LVS", "RECOGNIZE", "GATES", "NONE"): frozenset({0}),
    ("LVS", "REPORT"): frozenset({1}),
    ("LVS", "REPORT", "OPTION", "NONE"): frozenset({0}),
    ("LVS", "SOFTCHK"): frozenset({1, 2, 3}),
    ("LVS", "SPICE", "PREFER", "PINS", "YES"): frozenset({0}),
    ("LVS", "SPICE", "REPLICATE", "DEVICES", "YES"): frozenset({0}),
    ("LVS", "SPICE", "STRICT"): frozenset({2}),
    ("PEX", "REPORT", "DISTRIBUTED", "NONE"): frozenset({0}),
    ("PEX", "REPORT", "LUMPED", "NONE"): frozenset({0}),
}


def _directive_contract(keywords):
    contract = DIRECTIVE_CONTRACT_REGISTRY.get(keywords)
    if contract is None:
        raise RuntimeError(f"Missing directive contract for {' '.join(keywords)}")
    return contract


LVS_COMPARE_CASE_CONTRACT = _directive_contract(("LVS", "COMPARE", "CASE"))
LVS_RECOGNIZE_GATES_CONTRACT = _directive_contract(("LVS", "RECOGNIZE", "GATES"))
LVS_RECOGNIZE_GATES_TOLERANCE_CONTRACT = _directive_contract(
    ("LVS", "RECOGNIZE", "GATES", "TOLERANCE")
)
LVS_IGNORE_PORTS_CONTRACT = _directive_contract(("LVS", "IGNORE", "PORTS"))
LVS_REPORT_OPTION_CONTRACT = _directive_contract(("LVS", "REPORT", "OPTION"))
LVS_SOFTCHK_CONTRACT = _directive_contract(("LVS", "SOFTCHK"))
LVS_SPICE_STRICT_CONTRACT = _directive_contract(("LVS", "SPICE", "STRICT"))
DRC_INCREMENTAL_CONNECT_CONTRACT = _directive_contract(("DRC", "INCREMENTAL", "CONNECT"))
DRC_SUMMARY_REPORT_CONTRACT = _directive_contract(("DRC", "SUMMARY", "REPORT"))
ERC_SUMMARY_REPORT_CONTRACT = _directive_contract(("ERC", "SUMMARY", "REPORT"))
ERC_RESULTS_DATABASE_CONTRACT = _directive_contract(("ERC", "RESULTS", "DATABASE"))
PEX_REPORT_NETSUMMARY_CONTRACT = _directive_contract(("PEX", "REPORT", "NETSUMMARY"))
PEX_REPORT_POINT2POINT_CONTRACT = _directive_contract(("PEX", "REPORT", "POINT2POINT"))
PEX_NETLIST_MUTUAL_RESISTANCE_CONTRACT = _directive_contract(
    ("PEX", "NETLIST", "MUTUAL", "RESISTANCE")
)
PEX_NETLIST_VIRTUAL_CONNECT_CONTRACT = _directive_contract(
    ("PEX", "NETLIST", "VIRTUAL", "CONNECT")
)
PEX_NETLIST_GROUNDNET_GLOBAL_CONTRACT = _directive_contract(
    ("PEX", "NETLIST", "GROUNDNET", "GLOBAL")
)
PEX_NETLIST_NOXREF_NET_NAMES_CONTRACT = _directive_contract(
    ("PEX", "NETLIST", "NOXREF", "NET", "NAMES")
)
PEX_NETLIST_LPE_IGNORE_IDEALNET_CONTRACT = _directive_contract(
    ("PEX", "NETLIST", "LPE", "IGNORE", "IDEALNET")
)
PEX_NETLIST_CREATE_SMASHED_DEVICE_NAMES_CONTRACT = _directive_contract(
    ("PEX", "NETLIST", "CREATE", "SMASHED", "DEVICE", "NAMES")
)
PEX_NETLIST_EXPORT_PORTS_CONTRACT = _directive_contract(("PEX", "NETLIST", "EXPORT", "PORTS"))
PEX_NETLIST_UPPERCASE_CONTRACT = _directive_contract(("PEX", "NETLIST", "UPPERCASE"))
PEX_NETLIST_CONNECTION_SECTION_CONTRACT = _directive_contract(
    ("PEX", "NETLIST", "CONNECTION", "SECTION")
)
PEX_NETLIST_UNSHORT_DEVICE_PINS_CONTRACT = _directive_contract(
    ("PEX", "NETLIST", "UNSHORT", "DEVICE", "PINS")
)
PEX_NETLIST_LINEWRAP_CONTRACT = _directive_contract(("PEX", "NETLIST", "LINEWRAP"))
DRC_RESULTS_DATABASE_CONTRACT = _directive_contract(("DRC", "RESULTS", "DATABASE"))
