"""PEX directive validators."""

from __future__ import annotations

from .semantic_directive_contracts import (
    PEX_NETLIST_CONNECTION_SECTION_CONTRACT as _PEX_NETLIST_CONNECTION_SECTION_CONTRACT,
    PEX_NETLIST_CREATE_SMASHED_DEVICE_NAMES_CONTRACT as _PEX_NETLIST_CREATE_SMASHED_DEVICE_NAMES_CONTRACT,
    PEX_NETLIST_EXPORT_PORTS_CONTRACT as _PEX_NETLIST_EXPORT_PORTS_CONTRACT,
    PEX_NETLIST_GROUNDNET_GLOBAL_CONTRACT as _PEX_NETLIST_GROUNDNET_GLOBAL_CONTRACT,
    PEX_NETLIST_LINEWRAP_CONTRACT as _PEX_NETLIST_LINEWRAP_CONTRACT,
    PEX_NETLIST_LPE_IGNORE_IDEALNET_CONTRACT as _PEX_NETLIST_LPE_IGNORE_IDEALNET_CONTRACT,
    PEX_NETLIST_MUTUAL_RESISTANCE_CONTRACT as _PEX_NETLIST_MUTUAL_RESISTANCE_CONTRACT,
    PEX_NETLIST_NOXREF_NET_NAMES_CONTRACT as _PEX_NETLIST_NOXREF_NET_NAMES_CONTRACT,
    PEX_NETLIST_UNSHORT_DEVICE_PINS_CONTRACT as _PEX_NETLIST_UNSHORT_DEVICE_PINS_CONTRACT,
    PEX_NETLIST_UPPERCASE_CONTRACT as _PEX_NETLIST_UPPERCASE_CONTRACT,
    PEX_NETLIST_VIRTUAL_CONNECT_CONTRACT as _PEX_NETLIST_VIRTUAL_CONNECT_CONTRACT,
    PEX_REPORT_NETSUMMARY_CONTRACT as _PEX_REPORT_NETSUMMARY_CONTRACT,
    PEX_REPORT_POINT2POINT_CONTRACT as _PEX_REPORT_POINT2POINT_CONTRACT,
)
from .semantic_symbols import _coerce_argument_number


class PexDirectiveValidationMixin:
    """Validation helpers for PEX directive families."""

    def _validate_pex_report_arguments(self, node, scope):
        normalized = self._normalized_argument_texts(node)
        if normalized is None or not normalized:
            return

        if normalized[0] == "NETSUMMARY":
            contract = _PEX_REPORT_NETSUMMARY_CONTRACT
            if len(normalized) < 2:
                self.error(
                    "semantic.directive.argument_shape",
                    "PEX REPORT NETSUMMARY requires a report filename",
                    node,
                )
                return
            idx = 2
            if idx < len(normalized) and normalized[idx] in contract.value_sets["scopes"]:
                idx += 1
            if idx < len(normalized) and normalized[idx] in contract.value_sets["details"]:
                idx += 1
            if idx < len(normalized):
                selection_clause_heads = {
                    words[0]
                    for words in contract.clause_sequences["selection_clauses"]
                    if words[0] != "NETFILE"
                }
                trailing_clause_heads = {
                    words[0] for words in contract.clause_sequences["trailing_clauses"]
                }
                if normalized[idx] in selection_clause_heads:
                    idx += 1
                    start = idx
                    while idx < len(normalized) and normalized[idx] not in (
                        {"NETFILE"} | trailing_clause_heads
                    ):
                        idx += 1
                    if idx == start:
                        self.error(
                            "semantic.directive.argument_shape",
                            "PEX REPORT NETSUMMARY requires at least one net after LAYOUT or SOURCE",
                            node,
                        )
                        return
                elif normalized[idx] == "NETFILE":
                    idx += 1
                    if idx >= len(normalized) or normalized[idx] in {
                        "NETFILE",
                        "LAYOUT",
                        "SOURCE",
                        "CELL",
                        "SCALE",
                        "COLUMNS",
                    }:
                        self.error(
                            "semantic.directive.argument_shape",
                            "PEX REPORT NETSUMMARY NETFILE requires a filename",
                            node,
                        )
                        return
                    idx += 1
            if idx < len(normalized) and normalized[idx] == "CELL":
                idx += 1
                if idx >= len(normalized):
                    self.error(
                        "semantic.directive.argument_shape",
                        "PEX REPORT NETSUMMARY CELL requires a cell name",
                        node,
                    )
                    return
                idx += 1
            if idx < len(normalized) and normalized[idx] == "SCALE":
                idx += 1
                if idx >= len(normalized):
                    self.error(
                        "semantic.directive.argument_shape",
                        "PEX REPORT NETSUMMARY SCALE requires a numeric value",
                        node,
                    )
                    return
                if not self._matches_numeric_text(normalized[idx], scope):
                    self.error(
                        "semantic.directive.invalid_value",
                        "PEX REPORT NETSUMMARY SCALE expects a numeric value or variable",
                        node,
                    )
                    return
                idx += 1
            if idx < len(normalized) and normalized[idx] == "COLUMNS":
                idx += 1
                if idx >= len(normalized) or normalized[idx] not in contract.value_sets["columns"]:
                    self.error(
                        "semantic.directive.invalid_value",
                        "PEX REPORT NETSUMMARY COLUMNS expects BASIC or ADVANCED",
                        node,
                    )
                    return
                idx += 1
            if idx != len(normalized):
                self.error(
                    "semantic.directive.invalid_value",
                    "PEX REPORT NETSUMMARY has an invalid option order or unsupported trailing arguments",
                    node,
                )
            return

        if normalized[0] == "POINT2POINT":
            contract = _PEX_REPORT_POINT2POINT_CONTRACT
            idx = 1
            if idx < len(normalized) and normalized[idx] in contract.value_sets["units"]:
                idx += 1
            if idx >= len(normalized):
                self.error(
                    "semantic.directive.argument_shape",
                    "PEX REPORT POINT2POINT requires an input file",
                    node,
                )
                return
            idx += 1
            if idx < len(normalized) and normalized[idx] not in (
                contract.value_sets["names"] | {"SAMEPORT"}
            ):
                idx += 1
            if idx < len(normalized) and normalized[idx] in contract.value_sets["names"]:
                naming = normalized[idx]
                idx += 1
                if idx < len(normalized) and normalized[idx] == "CALIBREVIEW":
                    if naming != "SOURCENAMES":
                        self.error(
                            "semantic.directive.invalid_value",
                            "PEX REPORT POINT2POINT only allows CALIBREVIEW after SOURCENAMES",
                            node,
                        )
                        return
                    idx += 1
            elif idx < len(normalized) and normalized[idx] == "CALIBREVIEW":
                self.error(
                    "semantic.directive.invalid_value",
                    "PEX REPORT POINT2POINT only allows CALIBREVIEW after SOURCENAMES",
                    node,
                )
                return
            if idx < len(normalized) and normalized[idx] == "SAMEPORT":
                idx += 1
                if idx >= len(normalized) or normalized[idx] not in contract.value_sets["sameport_values"]:
                    self.error(
                        "semantic.directive.invalid_value",
                        "PEX REPORT POINT2POINT SAMEPORT expects OPEN or SHORT",
                        node,
                    )
                    return
                idx += 1
            if idx != len(normalized):
                self.error(
                    "semantic.directive.invalid_value",
                    "PEX REPORT POINT2POINT has an invalid option order or unsupported trailing arguments",
                    node,
                )

    def _validate_pex_netlist_arguments(self, node, scope):
        normalized = self._normalized_argument_texts(node)
        if normalized is None or not normalized:
            return

        if normalized[:2] == ["MUTUAL", "RESISTANCE"]:
            self._validate_boolean_suffix_arguments(
                node,
                ("MUTUAL", "RESISTANCE"),
                _PEX_NETLIST_MUTUAL_RESISTANCE_CONTRACT.value_sets["values"],
                "PEX NETLIST MUTUAL RESISTANCE",
            )
            return

        if normalized[:2] == ["VIRTUAL", "CONNECT"]:
            self._validate_boolean_suffix_arguments(
                node,
                ("VIRTUAL", "CONNECT"),
                _PEX_NETLIST_VIRTUAL_CONNECT_CONTRACT.value_sets["values"],
                "PEX NETLIST VIRTUAL CONNECT",
            )
            return

        if normalized[:2] == ["GROUNDNET", "GLOBAL"]:
            self._validate_boolean_suffix_arguments(
                node,
                ("GROUNDNET", "GLOBAL"),
                _PEX_NETLIST_GROUNDNET_GLOBAL_CONTRACT.value_sets["values"],
                "PEX NETLIST GROUNDNET GLOBAL",
            )
            return

        if normalized[:3] == ["NOXREF", "NET", "NAMES"]:
            self._validate_boolean_suffix_arguments(
                node,
                ("NOXREF", "NET", "NAMES"),
                _PEX_NETLIST_NOXREF_NET_NAMES_CONTRACT.value_sets["values"],
                "PEX NETLIST NOXREF NET NAMES",
            )
            return

        if normalized[:3] == ["LPE", "IGNORE", "IDEALNET"]:
            self._validate_boolean_suffix_arguments(
                node,
                ("LPE", "IGNORE", "IDEALNET"),
                _PEX_NETLIST_LPE_IGNORE_IDEALNET_CONTRACT.value_sets["values"],
                "PEX NETLIST LPE IGNORE IDEALNET",
            )
            return

        if normalized[:4] == ["CREATE", "SMASHED", "DEVICE", "NAMES"]:
            self._validate_boolean_suffix_arguments(
                node,
                ("CREATE", "SMASHED", "DEVICE", "NAMES"),
                _PEX_NETLIST_CREATE_SMASHED_DEVICE_NAMES_CONTRACT.value_sets["values"],
                "PEX NETLIST CREATE SMASHED DEVICE NAMES",
            )
            return

        if normalized[:2] == ["EXPORT", "PORTS"]:
            self._validate_boolean_suffix_arguments(
                node,
                ("EXPORT", "PORTS"),
                _PEX_NETLIST_EXPORT_PORTS_CONTRACT.value_sets["values"],
                "PEX NETLIST EXPORT PORTS",
            )
            return

        if normalized[:1] == ["GROUNDLAYER"]:
            pairs = normalized[1:]
            if len(pairs) < 2 or len(pairs) % 2:
                self.error(
                    "semantic.directive.argument_shape",
                    "PEX NETLIST GROUNDLAYER requires one or more layer/net pairs",
                    node,
                )
            return

        if normalized[:3] == ["UNSHORT", "DEVICE", "PINS"]:
            if len(normalized) != 4:
                self.error(
                    "semantic.directive.argument_shape",
                    "PEX NETLIST UNSHORT DEVICE PINS expects exactly one value or NO",
                    node,
                )
                return
            if normalized[3] in _PEX_NETLIST_UNSHORT_DEVICE_PINS_CONTRACT.value_sets["disable_values"]:
                return
            if not self._matches_numeric_text(normalized[3], scope, positive=True):
                self.error(
                    "semantic.directive.invalid_value",
                    "PEX NETLIST UNSHORT DEVICE PINS expects a positive numeric value or NO",
                    node,
                )
            return

        if normalized[:1] == ["UPPERCASE"]:
            contract = _PEX_NETLIST_UPPERCASE_CONTRACT
            if len(normalized) < 3:
                self.error(
                    "semantic.directive.argument_shape",
                    "PEX NETLIST UPPERCASE requires one or more KEYWORDS/MODELNAMES/PARAMETERS YES/NO sets",
                    node,
                )
                return
            idx = 1
            seen = set()
            expected_index = 0
            ordered_fields = contract.ordered_values["fields"]
            while idx < len(normalized):
                field = normalized[idx]
                if field not in ordered_fields:
                    self.error(
                        "semantic.directive.invalid_value",
                        "PEX NETLIST UPPERCASE only allows KEYWORDS, MODELNAMES, and PARAMETERS",
                        node,
                    )
                    return
                if field in seen:
                    self.error(
                        "semantic.directive.invalid_value",
                        "PEX NETLIST UPPERCASE cannot repeat the same option",
                        node,
                    )
                    return
                while (
                    expected_index < len(ordered_fields)
                    and ordered_fields[expected_index] != field
                ):
                    expected_index += 1
                if expected_index >= len(ordered_fields):
                    self.error(
                        "semantic.directive.invalid_value",
                        "PEX NETLIST UPPERCASE options must appear in the order KEYWORDS, MODELNAMES, PARAMETERS",
                        node,
                    )
                    return
                if idx + 1 >= len(normalized) or normalized[idx + 1] not in contract.value_sets["values"]:
                    self.error(
                        "semantic.directive.invalid_value",
                        f"PEX NETLIST UPPERCASE {field} expects YES or NO",
                        node,
                    )
                    return
                seen.add(field)
                expected_index += 1
                idx += 2
            return

        if normalized[:2] == ["POSITION", "FILE"]:
            if len(normalized) != 3:
                self.error(
                    "semantic.directive.argument_shape",
                    "PEX NETLIST POSITION FILE expects exactly one value",
                    node,
                )
            return

        if normalized[:2] == ["CONNECTION", "SECTION"]:
            contract = _PEX_NETLIST_CONNECTION_SECTION_CONTRACT
            if len(normalized) not in {3, 4}:
                self.error(
                    "semantic.directive.argument_shape",
                    "PEX NETLIST CONNECTION SECTION expects YES [INST_LOC] or NO",
                    node,
                )
                return
            if normalized[2] == "NO":
                if len(normalized) != 3:
                    self.error(
                        "semantic.directive.invalid_value",
                        "PEX NETLIST CONNECTION SECTION NO cannot be combined with INST_LOC",
                        node,
                    )
                return
            if normalized[2] not in contract.value_sets["values"]:
                self.error(
                    "semantic.directive.invalid_value",
                    "PEX NETLIST CONNECTION SECTION expects YES or NO",
                    node,
                )
                return
            if len(normalized) == 4 and normalized[3] != "INST_LOC":
                self.error(
                    "semantic.directive.invalid_value",
                    "PEX NETLIST CONNECTION SECTION only allows INST_LOC after YES",
                    node,
                )
            return

        if normalized[:1] == ["LINEWRAP"]:
            if len(normalized) != 2:
                self.error(
                    "semantic.directive.argument_shape",
                    "PEX NETLIST LINEWRAP expects NO or one numeric value",
                    node,
                )
                return
            if normalized[1] in _PEX_NETLIST_LINEWRAP_CONTRACT.value_sets["disable_values"]:
                return
            if not self._matches_numeric_text(normalized[1], scope, integer=True):
                self.error(
                    "semantic.directive.invalid_value",
                    "PEX NETLIST LINEWRAP expects NO or an integer value >= 80",
                    node,
                )
                return
            value = _coerce_argument_number(node.arguments[1])
            if value is not None and value < 80:
                self.error(
                    "semantic.directive.invalid_value",
                    "PEX NETLIST LINEWRAP expects NO or an integer value >= 80",
                    node,
                )
            return
