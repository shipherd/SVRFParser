"""DRC/ERC result directive validators."""

from __future__ import annotations

from .semantic_directive_contracts import (
    DRC_RESULTS_DATABASE_CONTRACT as _DRC_RESULTS_DATABASE_CONTRACT,
    ERC_RESULTS_DATABASE_CONTRACT as _ERC_RESULTS_DATABASE_CONTRACT,
)
from .semantic_symbols import _coerce_argument_number, _coerce_argument_text


class ResultDirectiveValidationMixin:
    """Validation helpers for DRC/ERC result directive families."""
    def _validate_summary_report_arguments(self, node, contract):
        if not node.arguments:
            return
        option_texts = []
        for argument in node.arguments[1:]:
            text = _coerce_argument_text(argument)
            if text is None:
                return
            option_texts.append(str(text).upper())

        idx = 0
        if idx < len(option_texts) and option_texts[idx] in contract.value_sets["modes"]:
            idx += 1

        for flag in contract.ordered_values["flags"]:
            if idx < len(option_texts) and option_texts[idx] == flag:
                idx += 1

        if idx != len(option_texts):
            allowed = ", ".join(["REPLACE/APPEND", *contract.ordered_values["flags"]])
            self.error(
                "semantic.directive.invalid_value",
                f"{' '.join(node.keywords)} expects trailing options in this order: {allowed}",
                node,
            )

    def _validate_erc_results_database_arguments(self, node):
        if not node.arguments:
            return
        contract = _ERC_RESULTS_DATABASE_CONTRACT

        option_texts = []
        for argument in node.arguments[1:]:
            text = _coerce_argument_text(argument)
            if text is None:
                return
            option_texts.append(str(text).upper())

        idx = 0
        if idx < len(option_texts) and option_texts[idx] in contract.value_sets["formats"]:
            idx += 1

        top_or_pseudo = None
        if idx < len(option_texts) and option_texts[idx] in contract.value_sets["final_modes"]:
            top_or_pseudo = option_texts[idx]
            idx += 1

        if idx != len(option_texts):
            self.error(
                "semantic.directive.invalid_value",
                "ERC RESULTS DATABASE only allows optional ASCII followed by one of PSEUDO or TOP",
                node,
            )
            return

        if top_or_pseudo not in {None, "PSEUDO", "TOP"}:
            self.error(
                "semantic.directive.invalid_value",
                "ERC RESULTS DATABASE may not combine TOP and PSEUDO",
                node,
            )

    def _validate_drc_results_database_arguments(self, node):
        normalized = self._normalized_argument_texts(node)
        if normalized is None or not normalized:
            return
        contract = _DRC_RESULTS_DATABASE_CONTRACT

        if normalized[0] == "LIBNAME":
            if len(normalized) != 2:
                self.error(
                    "semantic.directive.argument_shape",
                    "DRC RESULTS DATABASE LIBNAME expects exactly one name",
                    node,
                )
            return

        pipe_output = normalized[0].startswith("PIPE ")
        format_name = None
        index_seen = False
        noview_seen = False
        prefix_seen = False
        append_seen = False
        compression_seen = None
        strict_seen = None
        automap_seen = False
        snapreduce_seen = False
        final_mode_seen = None

        idx = 1
        while idx < len(normalized):
            token = normalized[idx]
            if token in contract.value_sets["formats"]:
                if format_name is not None:
                    self.error(
                        "semantic.directive.invalid_value",
                        "DRC RESULTS DATABASE only allows one output format",
                        node,
                    )
                    return
                format_name = token
                idx += 1
                continue
            if token == "INDEX":
                if format_name != "OASIS" or index_seen:
                    self.error(
                        "semantic.directive.invalid_value",
                        "DRC RESULTS DATABASE only allows INDEX with OASIS output",
                        node,
                    )
                    return
                index_seen = True
                idx += 1
                continue
            if token == "NOVIEW":
                if not index_seen or noview_seen:
                    self.error(
                        "semantic.directive.invalid_value",
                        "DRC RESULTS DATABASE only allows NOVIEW after OASIS INDEX",
                        node,
                    )
                    return
                noview_seen = True
                idx += 1
                continue
            if token == "PREFIX":
                if prefix_seen:
                    self.error(
                        "semantic.directive.invalid_value",
                        "DRC RESULTS DATABASE only allows one PREFIX clause",
                        node,
                    )
                    return
                if idx + 1 >= len(normalized):
                    self.error(
                        "semantic.directive.argument_shape",
                        "DRC RESULTS DATABASE PREFIX requires a string",
                        node,
                    )
                    return
                prefix_seen = True
                idx += 2
                continue
            if token == "APPEND":
                if append_seen:
                    self.error(
                        "semantic.directive.invalid_value",
                        "DRC RESULTS DATABASE only allows one APPEND clause",
                        node,
                    )
                    return
                if idx + 1 >= len(normalized):
                    self.error(
                        "semantic.directive.argument_shape",
                        "DRC RESULTS DATABASE APPEND requires a string",
                        node,
                    )
                    return
                append_seen = True
                idx += 2
                continue
            if token in contract.value_sets["oasis_compression"]:
                if compression_seen is not None:
                    self.error(
                        "semantic.directive.invalid_value",
                        "DRC RESULTS DATABASE only allows one CBLOCK or NOCBLOCK setting",
                        node,
                    )
                    return
                compression_seen = token
                idx += 1
                if token == "CBLOCK" and idx < len(normalized) and normalized[idx] in {
                    "BEST_SPEED",
                    "BEST_COMPRESSION",
                }:
                    idx += 1
                continue
            if token in contract.value_sets["strictness"]:
                if strict_seen is not None:
                    self.error(
                        "semantic.directive.invalid_value",
                        "DRC RESULTS DATABASE only allows one STRICT or NOSTRICT setting",
                        node,
                    )
                    return
                strict_seen = token
                idx += 1
                continue
            if token == "AUTOMAP":
                if automap_seen:
                    self.error(
                        "semantic.directive.invalid_value",
                        "DRC RESULTS DATABASE only allows AUTOMAP once",
                        node,
                    )
                    return
                automap_seen = True
                idx += 1
                continue
            if token == "SNAPREDUCE":
                if snapreduce_seen:
                    self.error(
                        "semantic.directive.invalid_value",
                        "DRC RESULTS DATABASE only allows SNAPREDUCE once",
                        node,
                    )
                    return
                snapreduce_seen = True
                idx += 1
                continue
            if token == "USER":
                if final_mode_seen is not None:
                    self.error(
                        "semantic.directive.invalid_value",
                        "DRC RESULTS DATABASE only allows one final result-selection mode",
                        node,
                    )
                    return
                final_mode_seen = "USER"
                idx += 1
                if idx < len(normalized) and normalized[idx] == "MERGED":
                    final_mode_seen = "USER MERGED"
                    idx += 1
                continue
            if token in contract.value_sets["final_modes"]:
                if final_mode_seen is not None:
                    self.error(
                        "semantic.directive.invalid_value",
                        "DRC RESULTS DATABASE only allows one final result-selection mode",
                        node,
                    )
                    return
                final_mode_seen = token
                idx += 1
                continue
            self.error(
                "semantic.directive.invalid_value",
                "DRC RESULTS DATABASE has an invalid option or unsupported option order",
                node,
            )
            return

        format_name = format_name or "ASCII"
        if compression_seen is not None and format_name != "OASIS":
            self.error(
                "semantic.directive.invalid_value",
                "DRC RESULTS DATABASE only allows CBLOCK or NOCBLOCK with OASIS output",
                node,
            )
        if strict_seen is not None and format_name != "OASIS":
            self.error(
                "semantic.directive.invalid_value",
                "DRC RESULTS DATABASE only allows STRICT or NOSTRICT with OASIS output",
                node,
            )
        if pipe_output and format_name == "ASCII":
            self.error(
                "semantic.directive.invalid_value",
                "DRC RESULTS DATABASE PIPE output may not be combined with ASCII",
                node,
            )
        if pipe_output and format_name == "OASIS" and (
            compression_seen == "CBLOCK" or strict_seen == "STRICT"
        ):
            self.error(
                "semantic.directive.invalid_value",
                "DRC RESULTS DATABASE PIPE output with OASIS may not explicitly specify CBLOCK or STRICT",
                node,
            )
        if (prefix_seen or append_seen) and format_name not in (
            contract.value_sets["gds_formats"] | {"OASIS"}
        ):
            self.error(
                "semantic.directive.invalid_value",
                "DRC RESULTS DATABASE PREFIX and APPEND are only valid with GDSII/GDS/GDS2 or OASIS output",
                node,
            )

    def _validate_drc_results_database_precision_arguments(self, node, scope):
        if len(node.arguments) not in {1, 2}:
            self.error(
                "semantic.directive.argument_shape",
                "DRC RESULTS DATABASE PRECISION expects one numeric value or two integer values",
                node,
            )
            return
        if len(node.arguments) == 1:
            if not self._matches_numeric_argument(node.arguments[0], scope, positive=True):
                self.error(
                    "semantic.directive.invalid_value",
                    "DRC RESULTS DATABASE PRECISION expects a positive numeric value or numeric variable",
                    node,
                )
            return
        for argument in node.arguments:
            if not self._matches_numeric_argument(argument, scope, positive=True, integer=True):
                self.error(
                    "semantic.directive.invalid_value",
                    "DRC RESULTS DATABASE PRECISION expects two positive integers or numeric variables",
                    node,
                )
                return

    def _validate_drc_magnify_results_arguments(self, node, scope):
        if not node.arguments:
            return
        args = node.arguments
        if _coerce_argument_text(args[0]) not in {"X", "Y"}:
            if len(args) > 2:
                self.error(
                    "semantic.directive.argument_shape",
                    "DRC MAGNIFY RESULTS expects VALUE [PLACE] or directional X/Y pairs",
                    node,
                )
                return
            if not self._matches_numeric_argument(args[0], scope, positive=True):
                self.error(
                    "semantic.directive.invalid_value",
                    "DRC MAGNIFY RESULTS expects a positive numeric value or numeric variable",
                    node,
                )
                return
            if len(args) == 2:
                place = _coerce_argument_text(args[1])
                if str(place).upper() != "PLACE":
                    self.error(
                        "semantic.directive.invalid_value",
                        "DRC MAGNIFY RESULTS only allows PLACE as the trailing keyword after a scalar value",
                        node,
                    )
            return

        idx = 0
        seen_axes = set()
        while idx < len(args):
            token = _coerce_argument_text(args[idx])
            token = None if token is None else str(token).upper()
            if token == "PLACE":
                self.error(
                    "semantic.directive.invalid_value",
                    "DRC MAGNIFY RESULTS cannot combine PLACE with X/Y directional magnification",
                    node,
                )
                return
            if token not in {"X", "Y"}:
                self.error(
                    "semantic.directive.invalid_value",
                    "DRC MAGNIFY RESULTS directional form expects X and/or Y keywords",
                    node,
                )
                return
            if token in seen_axes:
                self.error(
                    "semantic.directive.invalid_value",
                    "DRC MAGNIFY RESULTS cannot repeat the same directional axis",
                    node,
                )
                return
            seen_axes.add(token)
            if idx + 1 >= len(args) or not self._matches_numeric_argument(args[idx + 1], scope, positive=True):
                self.error(
                    "semantic.directive.invalid_value",
                    "DRC MAGNIFY RESULTS expects a positive numeric value after each X/Y keyword",
                    node,
                )
                return
            idx += 2

    def _validate_maximum_results_arguments(self, node, scope, *, allow_estimate):
        if not node.arguments:
            return

        args = node.arguments
        first_text = _coerce_argument_text(args[0])
        first_upper = None if first_text is None else str(first_text).upper()

        if allow_estimate and first_upper == "ESTIMATE":
            if len(args) != 2:
                self.error(
                    "semantic.directive.argument_shape",
                    f"{' '.join(node.keywords)} ESTIMATE expects exactly one trailing value",
                    node,
                )
                return
            second_text = _coerce_argument_text(args[1])
            second_upper = None if second_text is None else str(second_text).upper()
            if second_upper == "ALL":
                return
            if not self._matches_numeric_argument(args[1], scope, non_negative=True, integer=True):
                self.error(
                    "semantic.directive.invalid_value",
                    f"{' '.join(node.keywords)} ESTIMATE expects a non-negative integer or ALL",
                    node,
                )
            return

        if len(args) != 1:
            self.error(
                "semantic.directive.argument_shape",
                f"{' '.join(node.keywords)} expects exactly one value",
                node,
            )
            return

        if first_upper == "ALL":
            return

        if not self._matches_numeric_argument(args[0], scope, non_negative=True, integer=True):
            self.error(
                "semantic.directive.invalid_value",
                f"{' '.join(node.keywords)} expects a non-negative integer or ALL",
                node,
            )
