"""Declarative expression-operator registries for Pratt parser dispatch."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PrefixExpressionSchema:
    name: str
    priority: int
    tags: frozenset[str]
    parser_method: str

    def matches(self, active_tags):
        return bool(self.tags & active_tags)


class PrefixExpressionSchemaRegistry:
    def __init__(self, schemas):
        self.schemas = tuple(
            sorted(
                schemas,
                key=lambda schema: (schema.priority, len(schema.tags), schema.name),
                reverse=True,
            )
        )
        self._schema_order = {schema: idx for idx, schema in enumerate(self.schemas)}
        self._by_tag = {}
        for schema in self.schemas:
            for tag in schema.tags:
                self._by_tag.setdefault(tag, []).append(schema)

    def match(self, active_tags):
        active_tags = frozenset(active_tags)
        best_schema = None
        best_order = len(self.schemas)
        for tag in active_tags:
            for schema in self._by_tag.get(tag, ()):
                order = self._schema_order[schema]
                if order < best_order:
                    best_order = order
                    best_schema = schema
        return best_schema


@dataclass(frozen=True, slots=True)
class LedExpressionSchema:
    name: str
    priority: int
    tags: frozenset[str]
    parser_method: str
    binding_power: int | None = None
    binding_power_source: str = "static"

    def matches(self, active_tags):
        return bool(self.tags & active_tags)


class LedExpressionSchemaRegistry:
    def __init__(self, schemas):
        self.schemas = tuple(
            sorted(
                schemas,
                key=lambda schema: (schema.priority, len(schema.tags), schema.binding_power or 0, schema.name),
                reverse=True,
            )
        )
        self._schema_order = {schema: idx for idx, schema in enumerate(self.schemas)}
        self._by_tag = {}
        for schema in self.schemas:
            for tag in schema.tags:
                self._by_tag.setdefault(tag, []).append(schema)

    def match(self, active_tags):
        active_tags = frozenset(active_tags)
        best_schema = None
        best_order = len(self.schemas)
        for tag in active_tags:
            for schema in self._by_tag.get(tag, ()):
                order = self._schema_order[schema]
                if order < best_order:
                    best_order = order
                    best_schema = schema
        return best_schema


PREFIX_EXPRESSION_SCHEMAS = (
    PrefixExpressionSchema("assignment_reference", 110, frozenset({"assignment_reference"}), "_parse_ident_layer_ref"),
    PrefixExpressionSchema("measurement", 100, frozenset({"measurement"}), "_parse_ident_measurement_nud"),
    PrefixExpressionSchema("text_selection", 98, frozenset({"text_selection"}), "_parse_text_selection_nud"),
    PrefixExpressionSchema("inside_outside_cell", 95, frozenset({"inside_outside_cell"}), "_parse_inside_outside_cell_nud"),
    PrefixExpressionSchema("edge_binary_prefix", 90, frozenset({"edge_binary_prefix"}), "_parse_prefix_edge_binary_nud"),
    PrefixExpressionSchema("prefix_boolean", 85, frozenset({"prefix_boolean"}), "_parse_prefix_boolean_nud"),
    PrefixExpressionSchema("unary_ident", 80, frozenset({"unary_ident"}), "_parse_ident_unary_nud"),
    PrefixExpressionSchema(
        "function_call",
        70,
        frozenset({"callable_name", "plain_function_call"}),
        "_parse_function_call_nud",
    ),
    PrefixExpressionSchema("spaced_operand", 60, frozenset({"spaced_operand_before_paren"}), "_parse_ident_layer_ref"),
    PrefixExpressionSchema("stamp", 50, frozenset({"stamp"}), "_parse_stamp_nud"),
    PrefixExpressionSchema("generic_prefix_operation", 40, frozenset({"generic_prefix_op"}), "_parse_generic_operation_nud"),
    PrefixExpressionSchema("layer_ref", 0, frozenset({"layer_ref"}), "_parse_ident_layer_ref"),
)


LED_EXPRESSION_SCHEMAS = (
    LedExpressionSchema("comparison_constraint", 110, frozenset({"comparison_symbol"}), "_parse_constraint_led_from_schema", 5),
    LedExpressionSchema("ternary", 100, frozenset({"ternary_question"}), "_parse_ternary_led", 1),
    LedExpressionSchema("equals_symbol", 95, frozenset({"equals_symbol"}), "_parse_symbol_binary_led", 4),
    LedExpressionSchema("arithmetic_symbol", 90, frozenset({"arithmetic_symbol"}), "_parse_symbol_binary_led", binding_power_source="arithmetic_symbol"),
    LedExpressionSchema("text_selection", 84, frozenset({"text_selection"}), "_parse_text_selection_led", 35),
    LedExpressionSchema("cell_selection", 82, frozenset({"inside_outside_cell"}), "_parse_cell_selection_led", 30),
    LedExpressionSchema("with", 80, frozenset({"with"}), "_parse_with_led_from_schema", 35),
    LedExpressionSchema("measurement", 75, frozenset({"measurement"}), "_parse_measurement_led", 35),
    LedExpressionSchema("holes_or_donut", 70, frozenset({"holes_or_donut"}), "_parse_holes_or_donut_led_from_schema", 35),
    LedExpressionSchema("size", 65, frozenset({"size"}), "_parse_size_led_from_schema", 35),
    LedExpressionSchema("rectangle", 60, frozenset({"rectangle"}), "_parse_rectangle_led_from_schema", 35),
    LedExpressionSchema("expand_or_convex_edge", 55, frozenset({"expand_or_convex_edge"}), "_parse_expand_or_convex_edge_led_from_schema", 35),
    LedExpressionSchema("edge_binary", 50, frozenset({"edge_binary"}), "_parse_edge_binary_led", binding_power_source="edge_binary"),
    LedExpressionSchema("not_compound", 45, frozenset({"not_compound"}), "_parse_not_compound_led_from_schema", 30),
    LedExpressionSchema("generic_ident", 0, frozenset({"generic_ident"}), "_parse_generic_infix_led_from_schema", binding_power_source="infix_ident"),
)


PREFIX_EXPRESSION_SCHEMA_REGISTRY = PrefixExpressionSchemaRegistry(PREFIX_EXPRESSION_SCHEMAS)
LED_EXPRESSION_SCHEMA_REGISTRY = LedExpressionSchemaRegistry(LED_EXPRESSION_SCHEMAS)
