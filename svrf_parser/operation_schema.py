"""Packaged operation-head registry for generic DRC op parsing."""

from __future__ import annotations

from dataclasses import dataclass

from .svrf_spec import OPERATION_SCHEMA_SPEC, PARSER_SPEC
from .tokens import TokenType

TT = TokenType


@dataclass(frozen=True, slots=True)
class OperationSchema:
    name: str
    head_prefix: tuple[str, ...]
    family: str
    parse_strategy: str
    modifier_family: str
    allow_nonstatement_expression_newline: bool
    bracket_modifier_mode: str
    parenthesized_scalar_modifiers: bool


@dataclass(frozen=True, slots=True)
class ResolvedOperationSchema:
    name: str
    words: tuple[str, ...]
    end_idx: int
    parse_strategy: str
    modifier_family: str
    allow_nonstatement_expression_newline: bool
    bracket_modifier_mode: str
    parenthesized_scalar_modifiers: bool


class OperationSchemaRegistry:
    def __init__(self, schemas, contracts=()):
        self.contracts = {entry.name: entry for entry in contracts}
        self.schemas = tuple(
            sorted(
                schemas,
                key=lambda schema: (len(schema.head_prefix), schema.name),
                reverse=True,
            )
        )
        self._by_first_word = {}
        for schema in self.schemas:
            if schema.head_prefix:
                self._by_first_word.setdefault(schema.head_prefix[0], []).append(schema)

    def contract_for(self, name):
        return self.contracts.get(str(name).upper())

    def operand_role(self, name, index, count):
        contract = self.contract_for(name)
        if contract is None:
            return None
        if count == 1 and contract.single_operand_role:
            return contract.single_operand_role
        if index < len(contract.operand_roles):
            return contract.operand_roles[index]
        return contract.variadic_operand_role

    @staticmethod
    def modifier_starters_for(schema):
        starters = PARSER_SPEC.table("modifier_starters")
        if schema.modifier_family == "dfm_property":
            return starters | PARSER_SPEC.table("dfm_property_modifiers")
        if schema.modifier_family == "ret":
            return starters | PARSER_SPEC.table("ret_option_starters") | {"EMULATION"}
        return starters

    @staticmethod
    def _match_prefix(tokens, start_idx, head_prefix, next_non_newline_index):
        idx = start_idx
        words = []
        for offset, word in enumerate(head_prefix):
            if idx >= len(tokens):
                return None
            token = tokens[idx]
            if token.type != TT.IDENT or token.value != word:
                return None
            words.append(word)
            idx += 1
            if offset + 1 < len(head_prefix):
                idx = next_non_newline_index(idx)
        return idx, tuple(words)

    @staticmethod
    def _resolved(schema, words, end_idx, **updates):
        return ResolvedOperationSchema(
            name=updates.get("name", schema.name),
            words=tuple(words),
            end_idx=end_idx,
            parse_strategy=updates.get("parse_strategy", schema.parse_strategy),
            modifier_family=updates.get("modifier_family", schema.modifier_family),
            allow_nonstatement_expression_newline=updates.get(
                "allow_nonstatement_expression_newline",
                schema.allow_nonstatement_expression_newline,
            ),
            bracket_modifier_mode=updates.get(
                "bracket_modifier_mode",
                schema.bracket_modifier_mode,
            ),
            parenthesized_scalar_modifiers=updates.get(
                "parenthesized_scalar_modifiers",
                schema.parenthesized_scalar_modifiers,
            ),
        )

    def _resolve_ret(self, schema, tokens, end_idx, words, next_non_newline_index):
        idx = next_non_newline_index(end_idx)
        if idx < len(tokens) and tokens[idx].type == TT.IDENT:
            words = tuple(words) + (tokens[idx].value,)
            return self._resolved(schema, words, idx + 1, name=" ".join(words))
        return self._resolved(schema, words, end_idx, name=" ".join(words))

    def _resolve_dfm(self, schema, tokens, end_idx, words, next_non_newline_index):
        idx = next_non_newline_index(end_idx)
        if idx >= len(tokens) or tokens[idx].type != TT.IDENT:
            return self._resolved(schema, words, end_idx, name=" ".join(words))

        second = tokens[idx].value
        words = tuple(words) + (second,)
        idx += 1

        updates = {}
        if second == "PROPERTY":
            updates = {
                "modifier_family": "dfm_property",
                "allow_nonstatement_expression_newline": True,
                "bracket_modifier_mode": "expression",
            }
            net_idx = next_non_newline_index(idx)
            if net_idx < len(tokens) and tokens[net_idx].type == TT.IDENT and tokens[net_idx].value == "NET":
                words = tuple(words) + ("NET",)
                idx = net_idx + 1
        elif second == "RDB":
            updates = {
                "parse_strategy": "dfm_rdb",
                "parenthesized_scalar_modifiers": True,
            }
        elif second == "DP":
            updates = {"parenthesized_scalar_modifiers": True}
            third_idx = next_non_newline_index(idx)
            if third_idx < len(tokens) and tokens[third_idx].type == TT.IDENT:
                words = tuple(words) + (tokens[third_idx].value,)
                idx = third_idx + 1
        elif second == "RET":
            updates = {"modifier_family": "ret"}
            third_idx = next_non_newline_index(idx)
            if third_idx < len(tokens) and tokens[third_idx].type == TT.IDENT:
                words = tuple(words) + (tokens[third_idx].value,)
                idx = third_idx + 1

        return self._resolved(schema, words, idx, name=" ".join(words), **updates)

    def resolve(self, tokens, start_idx, next_non_newline_index):
        token = tokens[start_idx]
        if token.type == TT.IDENT:
            candidates = self._by_first_word.get(token.value, ())
        else:
            candidates = ()
        for schema in candidates:
            matched = self._match_prefix(tokens, start_idx, schema.head_prefix, next_non_newline_index)
            if matched is None:
                continue
            end_idx, words = matched
            if schema.family == "fixed":
                return self._resolved(schema, words, end_idx)
            if schema.family == "ret":
                return self._resolve_ret(schema, tokens, end_idx, words, next_non_newline_index)
            if schema.family == "dfm":
                return self._resolve_dfm(schema, tokens, end_idx, words, next_non_newline_index)
        raw = token.value if token.type == TT.IDENT else str(token.raw)
        return ResolvedOperationSchema(
            name=raw,
            words=(raw,),
            end_idx=start_idx + 1,
            parse_strategy="default",
            modifier_family="default",
            allow_nonstatement_expression_newline=False,
            bracket_modifier_mode="none",
            parenthesized_scalar_modifiers=False,
        )


OPERATION_SCHEMAS = tuple(
    OperationSchema(
        name=entry.name,
        head_prefix=entry.head_prefix,
        family=entry.family,
        parse_strategy=entry.parse_strategy,
        modifier_family=entry.modifier_family,
        allow_nonstatement_expression_newline=entry.allow_nonstatement_expression_newline,
        bracket_modifier_mode=entry.bracket_modifier_mode,
        parenthesized_scalar_modifiers=entry.parenthesized_scalar_modifiers,
    )
    for entry in OPERATION_SCHEMA_SPEC.entries
)


OPERATION_SCHEMA_REGISTRY = OperationSchemaRegistry(OPERATION_SCHEMAS, OPERATION_SCHEMA_SPEC.contracts)
