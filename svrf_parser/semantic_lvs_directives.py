"""LVS directive validators."""

from __future__ import annotations

from .semantic_directive_contracts import (
    LVS_COMPARE_CASE_CONTRACT as _LVS_COMPARE_CASE_CONTRACT,
    LVS_RECOGNIZE_GATES_CONTRACT as _LVS_RECOGNIZE_GATES_CONTRACT,
    LVS_RECOGNIZE_GATES_TOLERANCE_CONTRACT as _LVS_RECOGNIZE_GATES_TOLERANCE_CONTRACT,
)
from .semantic_symbols import _normalized_directive_tail


class LvsDirectiveValidationMixin:
    """Validation helpers for LVS directive families."""

    def _validate_lvs_compare_case_arguments(self, node):
        normalized = self._normalized_argument_texts(node)
        if normalized is None:
            return
        if not normalized:
            return
        ordered_fields = _LVS_COMPARE_CASE_CONTRACT.ordered_values["fields"]
        seen = set()
        expected_index = 0
        for option in normalized:
            if option not in ordered_fields:
                self.error(
                    "semantic.directive.invalid_value",
                    "LVS COMPARE CASE only allows NAMES, TYPES, SUBTYPES, and VALUES",
                    node,
                )
                return
            if option in seen:
                self.error(
                    "semantic.directive.invalid_value",
                    "LVS COMPARE CASE cannot repeat the same option",
                    node,
                )
                return
            while (
                expected_index < len(ordered_fields)
                and ordered_fields[expected_index] != option
            ):
                expected_index += 1
            if expected_index >= len(ordered_fields):
                self.error(
                    "semantic.directive.invalid_value",
                    "LVS COMPARE CASE options must appear in the order NAMES TYPES SUBTYPES VALUES",
                    node,
                )
                return
            seen.add(option)
            expected_index += 1

    def _validate_lvs_recognize_gates_arguments(self, node):
        normalized = _normalized_directive_tail(node, 3)
        if normalized is None:
            return
        if not normalized:
            self.error(
                "semantic.directive.missing_argument",
                "LVS RECOGNIZE GATES requires one of ALL, SIMPLE, or NONE",
                node,
            )
            return
        if normalized[0] not in _LVS_RECOGNIZE_GATES_CONTRACT.value_sets["modes"]:
            self.error(
                "semantic.directive.invalid_value",
                "LVS RECOGNIZE GATES expects ALL, SIMPLE, or NONE as its mode",
                node,
            )
            return

        idx = 1
        for clause in _LVS_RECOGNIZE_GATES_CONTRACT.clause_sequences["optional_clauses"]:
            clause_length = len(clause)
            if tuple(normalized[idx : idx + clause_length]) == clause:
                idx += clause_length
        if idx < len(normalized):
            trailing_clause = _LVS_RECOGNIZE_GATES_CONTRACT.clause_sequences["trailing_clause"][0]
            trailing_length = len(trailing_clause)
            if tuple(normalized[idx : idx + trailing_length]) != trailing_clause:
                self.error(
                    "semantic.directive.invalid_value",
                    "LVS RECOGNIZE GATES expects options in the order MIX SUBTYPES, XALSO, WITHIN TOLERANCE, WITH SUBSTRATE, and final CELL LIST",
                    node,
                )
                return
            idx += trailing_length
            if idx >= len(normalized):
                self.error(
                    "semantic.directive.argument_shape",
                    "LVS RECOGNIZE GATES CELL LIST requires a list name",
                    node,
                )
                return
            idx += 1
        if idx != len(normalized):
            self.error(
                "semantic.directive.invalid_value",
                "LVS RECOGNIZE GATES only allows a final CELL LIST <name> after its optional flags",
                node,
            )

    def _validate_lvs_recognize_gates_tolerance_arguments(self, node, scope):
        normalized = _normalized_directive_tail(node, 3)
        if normalized is None or not normalized or normalized[0] != "TOLERANCE":
            return
        tolerance_contract = _LVS_RECOGNIZE_GATES_TOLERANCE_CONTRACT

        tail = normalized[1:]
        if len(tail) < 3:
            self.error(
                "semantic.directive.argument_shape",
                "LVS RECOGNIZE GATES TOLERANCE requires component, property, and a tolerance or STRING clause",
                node,
            )
            return

        scope_count = 0
        while tail and tail[-1] in tolerance_contract.value_sets["scope_keywords"]:
            scope_count += 1
            tail = tail[:-1]
        scope_order = list(tolerance_contract.ordered_values["scope_order"])
        if scope_count == 2 and normalized[-2:] != scope_order:
            self.error(
                "semantic.directive.invalid_value",
                "LVS RECOGNIZE GATES TOLERANCE only allows LAYOUT SOURCE in that order when both scopes are specified",
                node,
            )
            return

        clause_start = None
        for idx in range(2, len(tail)):
            token = tail[idx]
            if token == "STRING" or token in tolerance_contract.value_sets["series_parallel_keywords"]:
                clause_start = idx
                break
            if self._matches_numeric_text(token, scope, non_negative=True):
                clause_start = idx
                break
        if clause_start is None:
            self.error(
                "semantic.directive.argument_shape",
                "LVS RECOGNIZE GATES TOLERANCE is missing its tolerance or STRING clause",
                node,
            )
            return

        clause = tail[clause_start:]
        if not clause:
            self.error(
                "semantic.directive.argument_shape",
                "LVS RECOGNIZE GATES TOLERANCE is missing its tolerance or STRING clause",
                node,
            )
            return

        if clause[0] == "STRING":
            idx = 1
            seen = set()
            while idx < len(clause):
                token = clause[idx]
                if token not in tolerance_contract.value_sets["series_parallel_keywords"]:
                    self.error(
                        "semantic.directive.invalid_value",
                        "LVS RECOGNIZE GATES TOLERANCE STRING only allows optional SERIES and/or PARALLEL",
                        node,
                    )
                    return
                if token in seen:
                    self.error(
                        "semantic.directive.invalid_value",
                        "LVS RECOGNIZE GATES TOLERANCE STRING cannot repeat SERIES or PARALLEL",
                        node,
                    )
                    return
                seen.add(token)
                idx += 1
            return

        idx = 0
        seen = set()
        if self._matches_numeric_text(clause[0], scope, non_negative=True):
            if len(clause) != 1:
                self.error(
                    "semantic.directive.invalid_value",
                    "LVS RECOGNIZE GATES TOLERANCE numeric form only allows a single tolerance value or SERIES/PARALLEL clauses",
                    node,
                )
            return

        while idx < len(clause):
            keyword = clause[idx]
            if keyword not in tolerance_contract.value_sets["series_parallel_keywords"]:
                self.error(
                    "semantic.directive.invalid_value",
                    "LVS RECOGNIZE GATES TOLERANCE expects SERIES and/or PARALLEL tolerance clauses, or STRING",
                    node,
                )
                return
            if keyword in seen:
                self.error(
                    "semantic.directive.invalid_value",
                    "LVS RECOGNIZE GATES TOLERANCE cannot repeat SERIES or PARALLEL",
                    node,
                )
                return
            if idx + 1 >= len(clause) or not self._matches_numeric_text(
                clause[idx + 1], scope, non_negative=True
            ):
                self.error(
                    "semantic.directive.invalid_value",
                    f"LVS RECOGNIZE GATES TOLERANCE {keyword} expects a non-negative numeric value",
                    node,
                )
                return
            seen.add(keyword)
            idx += 2
