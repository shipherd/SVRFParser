"""Directive contract validation rules for semantic validation."""

from __future__ import annotations

from .semantic_lvs_directives import LvsDirectiveValidationMixin
from .semantic_pex_directives import PexDirectiveValidationMixin
from .semantic_result_directives import ResultDirectiveValidationMixin
from .semantic_directive_contracts import (
    DIRECTIVE_ALLOWED_ARGUMENT_COUNTS as _DIRECTIVE_ALLOWED_ARGUMENT_COUNTS,
    DIRECTIVE_MIN_ARGUMENTS as _DIRECTIVE_MIN_ARGUMENTS,
    DRC_INCREMENTAL_CONNECT_CONTRACT as _DRC_INCREMENTAL_CONNECT_CONTRACT,
    DRC_SUMMARY_REPORT_CONTRACT as _DRC_SUMMARY_REPORT_CONTRACT,
    ERC_SUMMARY_REPORT_CONTRACT as _ERC_SUMMARY_REPORT_CONTRACT,
    LVS_IGNORE_PORTS_CONTRACT as _LVS_IGNORE_PORTS_CONTRACT,
    LVS_REPORT_OPTION_CONTRACT as _LVS_REPORT_OPTION_CONTRACT,
    LVS_SOFTCHK_CONTRACT as _LVS_SOFTCHK_CONTRACT,
    LVS_SPICE_STRICT_CONTRACT as _LVS_SPICE_STRICT_CONTRACT,
)
from .semantic_symbols import (
    _coerce_argument_number,
    _coerce_argument_text,
    _normalized_directive_tail,
)


class DirectiveValidationMixin(
    LvsDirectiveValidationMixin,
    PexDirectiveValidationMixin,
    ResultDirectiveValidationMixin,
):
    """Directive-specific validation helpers used by SemanticValidator."""

    def _normalized_argument_texts(self, node):
        normalized = []
        for argument in node.arguments:
            text = _coerce_argument_text(argument)
            if text is None:
                return None
            normalized.append(str(text).upper())
        return normalized

    def _matches_numeric_argument(
        self,
        argument,
        scope,
        *,
        positive=False,
        non_negative=False,
        integer=False,
    ):
        numeric = _coerce_argument_number(argument)
        if numeric is not None:
            if positive and numeric <= 0:
                return False
            if non_negative and numeric < 0:
                return False
            if integer and int(numeric) != numeric:
                return False
            return True
        text = _coerce_argument_text(argument)
        return self._matches_numeric_text(
            text,
            scope,
            positive=positive,
            non_negative=non_negative,
            integer=integer,
        )

    def _matches_numeric_text(
        self,
        text,
        scope,
        *,
        positive=False,
        non_negative=False,
        integer=False,
    ):
        if text is None or text == "":
            return False
        try:
            numeric = float(text)
        except (TypeError, ValueError):
            return scope.knows_variable(str(text).upper())
        if positive and numeric <= 0:
            return False
        if non_negative and numeric < 0:
            return False
        if integer and int(numeric) != numeric:
            return False
        return True


    def _validate_boolean_suffix_arguments(self, node, prefix, allowed_values, description):
        normalized = self._normalized_argument_texts(node)
        if normalized is None:
            return
        if len(normalized) < len(prefix):
            return
        if tuple(normalized[: len(prefix)]) != prefix:
            return
        if len(normalized) != len(prefix) + 1:
            self.error(
                "semantic.directive.argument_shape",
                f"{description} expects exactly one trailing value",
                node,
            )
            return
        if normalized[-1] not in allowed_values:
            allowed = ", ".join(sorted(allowed_values))
            self.error(
                "semantic.directive.invalid_value",
                f"{description} expects one of: {allowed}",
                node,
            )


    def _validate_directive_arguments(self, node, scope):
        keyword_tuple = tuple(node.keywords)

        if keyword_tuple == ("LVS", "COMPARE", "CASE"):
            self._validate_lvs_compare_case_arguments(node)
            return

        if keyword_tuple[:3] == ("LVS", "RECOGNIZE", "GATES"):
            normalized = _normalized_directive_tail(node, 3)
            if normalized and normalized[0] == "TOLERANCE":
                self._validate_lvs_recognize_gates_tolerance_arguments(node, scope)
                return
            self._validate_lvs_recognize_gates_arguments(node)
            return

        if keyword_tuple == ("LVS", "IGNORE", "PORTS"):
            normalized = self._normalized_argument_texts(node)
            if normalized is None:
                return
            if (
                len(normalized) != 1
                or normalized[0] not in _LVS_IGNORE_PORTS_CONTRACT.value_sets["values"]
            ):
                self.error(
                    "semantic.directive.invalid_value",
                    "LVS IGNORE PORTS expects YES or NO",
                    node,
                )
            return

        if keyword_tuple == ("LVS", "REPORT", "OPTION", "NONE"):
            if node.arguments:
                self.error(
                    "semantic.directive.invalid_value",
                    "LVS REPORT OPTION NONE cannot be combined with other options",
                    node,
                )
            return

        if keyword_tuple == ("LVS", "REPORT", "OPTION"):
            normalized = self._normalized_argument_texts(node)
            if normalized is None:
                return
            exclusive_options = _LVS_REPORT_OPTION_CONTRACT.value_sets["exclusive_options"]
            if len(normalized) == 1 and normalized[0] in exclusive_options:
                return
            if any(option in exclusive_options for option in normalized):
                self.error(
                    "semantic.directive.invalid_value",
                    "LVS REPORT OPTION NONE cannot be combined with other options",
                    node,
                )
                return
            invalid = [
                text
                for text in normalized
                if text not in _LVS_REPORT_OPTION_CONTRACT.value_sets["options"]
            ]
            if invalid:
                invalid_text = ", ".join(sorted(set(invalid)))
                self.error(
                    "semantic.directive.invalid_value",
                    f"LVS REPORT OPTION contains unknown option(s): {invalid_text}",
                    node,
                )
            return

        if keyword_tuple == ("LVS", "SOFTCHK"):
            normalized = self._normalized_argument_texts(node)
            if normalized is None:
                return
            if (
                len(normalized) >= 2
                and normalized[1] not in _LVS_SOFTCHK_CONTRACT.value_sets["second_arg_values"]
            ):
                self.error(
                    "semantic.directive.invalid_value",
                    "LVS SOFTCHK expects LOWER, CONTACT, or UPPER as the optional second argument",
                    node,
                )
                return
            if (
                len(normalized) == 3
                and normalized[2] not in _LVS_SOFTCHK_CONTRACT.value_sets["third_arg_values"]
            ):
                self.error(
                    "semantic.directive.invalid_value",
                    "LVS SOFTCHK only allows ALL as the optional third argument",
                    node,
                )
            return

        if keyword_tuple == ("LVS", "SPICE", "STRICT"):
            normalized = self._normalized_argument_texts(node)
            if normalized is None:
                return
            strict_contract = _LVS_SPICE_STRICT_CONTRACT
            if normalized and normalized[0] not in strict_contract.value_sets["fields"]:
                self.error(
                    "semantic.directive.invalid_value",
                    "LVS SPICE STRICT expects WL as its first argument",
                    node,
                )
                return
            if len(normalized) >= 2 and normalized[1] not in strict_contract.value_sets["values"]:
                self.error(
                    "semantic.directive.invalid_value",
                    "LVS SPICE STRICT expects NO, YES, or NONE as its second argument",
                    node,
                )
            return

        if keyword_tuple == ("DRC", "INCREMENTAL", "CONNECT"):
            normalized = self._normalized_argument_texts(node)
            if normalized is None:
                return
            if (
                len(normalized) != 2
                or tuple(normalized[:1])
                != _DRC_INCREMENTAL_CONNECT_CONTRACT.clause_sequences["warning_prefix"][0]
            ):
                self.error(
                    "semantic.directive.invalid_value",
                    "DRC INCREMENTAL CONNECT expects YES/NO or WARNING ENABLE/DISABLE",
                    node,
                )
                return
            if normalized[1] not in _DRC_INCREMENTAL_CONNECT_CONTRACT.value_sets["warning_values"]:
                self.error(
                    "semantic.directive.invalid_value",
                    "DRC INCREMENTAL CONNECT WARNING expects ENABLE or DISABLE",
                    node,
                )
            return

        if keyword_tuple == ("DRC", "SUMMARY", "REPORT"):
            self._validate_summary_report_arguments(node, _DRC_SUMMARY_REPORT_CONTRACT)
            return

        if keyword_tuple == ("DRC", "RESULTS", "DATABASE"):
            self._validate_drc_results_database_arguments(node)
            return

        if keyword_tuple == ("ERC", "SUMMARY", "REPORT"):
            self._validate_summary_report_arguments(node, _ERC_SUMMARY_REPORT_CONTRACT)
            return

        if keyword_tuple == ("ERC", "RESULTS", "DATABASE"):
            self._validate_erc_results_database_arguments(node)
            return

        if keyword_tuple == ("DRC", "RESULTS", "DATABASE", "PRECISION"):
            self._validate_drc_results_database_precision_arguments(node, scope)
            return

        if keyword_tuple == ("DRC", "MAGNIFY", "RESULTS"):
            self._validate_drc_magnify_results_arguments(node, scope)
            return

        if keyword_tuple == ("DRC", "MAGNIFY", "DENSITY") or keyword_tuple == ("DRC", "MAGNIFY", "NAR"):
            if node.arguments and not self._matches_numeric_argument(node.arguments[0], scope, positive=True):
                self.error(
                    "semantic.directive.invalid_value",
                    f"{' '.join(node.keywords)} expects a positive numeric value or numeric variable",
                    node,
                )
            return

        if keyword_tuple == ("DRC", "MAXIMUM", "RESULTS"):
            self._validate_maximum_results_arguments(node, scope, allow_estimate=True)
            return

        if keyword_tuple == ("DRC", "MAXIMUM", "RESULTS", "NAR"):
            self._validate_maximum_results_arguments(node, scope, allow_estimate=False)
            return

        if keyword_tuple == ("ERC", "MAXIMUM", "RESULTS"):
            self._validate_maximum_results_arguments(node, scope, allow_estimate=False)
            return

        if keyword_tuple == ("PEX", "NETLIST"):
            self._validate_pex_netlist_arguments(node, scope)
            return

        if keyword_tuple == ("PEX", "REPORT"):
            self._validate_pex_report_arguments(node, scope)
            return
