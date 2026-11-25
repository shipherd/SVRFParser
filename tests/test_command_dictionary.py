import os
import unittest
from pathlib import Path

from coverage_analysis import inventory
from svrf_parser import ast, parse, validate_svrf
from svrf_parser.command_dictionary import COMMANDS, TOPICS
from svrf_parser.printer import SvrfPrinter
from svrf_parser.svrf_spec.dictionary_source import build_dictionary, dictionary_leaves


class CommandDictionaryTests(unittest.TestCase):
    def checked(self, text):
        tree = parse(text, strict=True)
        again = parse(SvrfPrinter().emit(tree), strict=True)
        self.assertEqual(tree.to_dict(False), again.to_dict(False))
        return tree.statements

    def test_all_closed_keyword_forms(self):
        for cmd in COMMANDS.values():
            if cmd.forms is None:
                continue
            for form in cmd.forms:
                source = " ".join((cmd.name, *form))
                with self.subTest(source=source):
                    self.assertEqual(len(parse(source, strict=True).statements), 1)
                    self.assertTrue(validate_svrf(source, follow_includes=False).valid)
            with self.subTest(invalid=cmd.name):
                report = validate_svrf(cmd.name + " INVALID_OPTION", follow_includes=False)
                self.assertFalse(report.valid)

    def test_documented_required_positionals_reject_empty_input(self):
        for cmd in COMMANDS.values():
            if cmd.min_args:
                with self.subTest(primary=cmd.name):
                    self.assertFalse(validate_svrf(cmd.name, strict=True, follow_includes=False).valid)

    def test_longest_head_and_argument_boundaries(self):
        a, b, c, rule = self.checked('lvs report trivial ports yes LVS REPORT UNITS no\n'
                                     'DFM PATTERN MATCH REPORT\n"LAYER"\n"DRC"\nR { COPY M }')
        self.assertEqual((a.keywords + a.arguments, b.keywords + b.arguments),
                         (["LVS", "REPORT", "TRIVIAL", "PORTS", "YES"], ["LVS", "REPORT", "UNITS", "NO"]))
        self.assertEqual((c.keywords, c.arguments, c.line), (["DFM", "PATTERN", "MATCH", "REPORT"], ["LAYER", "DRC"], 2))
        self.assertEqual(rule.name, "R")
        a, b = self.checked("LVS REPORT\nUNITS = 3")
        self.assertEqual((a.keywords, a.arguments, b.name), (["LVS", "REPORT"], [], "UNITS"))
        a, b = self.checked("LVS REPORT\nUNITS { COPY M }")
        self.assertIsInstance(b, ast.RuleCheckBlock)
        a, = self.checked('LVS REPORT "UNITS"')
        self.assertEqual(a.arguments, ["UNITS"])
        self.assertTrue(validate_svrf('LVS REPORT "UNITS"', follow_includes=False).valid)

    def test_declarations_with_embedded_primary_words(self):
        text = ('LAYER DIRECTORY "DRC"\nLVS GLOBAL LAYOUT NAME global_name\n'
                'PERC LDL LAYOUT REDUCE TOP LAYERS M1 M2\nLVS WRITE LAYOUT NETLIST "port.sp"')
        self.assertEqual([n.keywords for n in self.checked(text)],
                         [s.split() for s in ("LAYER DIRECTORY", "LVS GLOBAL LAYOUT NAME",
                                               "PERC LDL LAYOUT REDUCE TOP LAYERS", "LVS WRITE LAYOUT NETLIST")])

    def test_balanced_groups_and_missing_arguments(self):
        a, b = self.checked("RESISTANCE SHEET M [2 (3 4)]\nR { COPY M }")
        self.assertEqual((a.arguments[1].text, b.name), ("[2 (3 4)]", "R"))
        report = validate_svrf("DFM PATTERN MATCH REPORT A\nNEXT = 2", follow_includes=False)
        self.assertEqual([d.code for d in report.errors], ["semantic.directive.missing_argument"])
        self.assertEqual(report.program.statements[1].name, "NEXT")

    def test_dfm_defaults_keeps_its_selector_and_options(self):
        for tail in ("RDB MAXIMUM 10", "RDB NODAL ALL CELLS NULL", 'RDB GDS FILE "one" TOP',
                     'RDB OASIS PREFIX "tag" FILLONLY', "FILL COMPRESS VERSION 3",
                     "DV\nEXCLUDE SHIELDED RESTRICTED"):
            source = "DFM DEFAULTS " + tail + "\nNEXT = 2"
            directive, following = self.checked(source)
            self.assertEqual((directive.keywords, following.name), (["DFM", "DEFAULTS"], "NEXT"))
            self.assertTrue(validate_svrf(source, follow_includes=False).valid)
        for tail in ("RDB", "RDB MAXIMUM", "RDB OASIS NOFILE", "DV EXCLUDE SHIELDED WRONG"):
            self.assertFalse(validate_svrf("DFM DEFAULTS " + tail, follow_includes=False).valid)

    def test_modifiers_stop_before_new_assignments_and_layer_checks(self):
        rule, = self.checked("R {\n A = SIZE (OR M N) BY P OVERUNDER\n EMPTY = SIZE (M NOT A) BY P UNDEROVER\n"
                             " EMPTY INTERACT N\n NOT DONUT A\n CONVEX EDGE A ANGLE1 <= 1\n"
                             " (A INSIDE B) INTERACT C > 1 BY NET\n (A INSIDE B) INTERACT D > 1 BY NET\n}")
        self.assertEqual([getattr(n, "name", None) for n in rule.body[:2]], ["A", "EMPTY"])
        self.assertEqual(len(rule.body), 7)
        self.assertEqual(rule.body[2].op, "INTERACT")

    def test_prefix_boolean_continuations_are_relative_to_assignment(self):
        rule, = self.checked("R {\n X = OR\n   (COPY A)\n   (COPY B)\n   (B OR C) INTERACT D\n}")
        assign, check = rule.body
        self.assertEqual((assign.expression.op, check.op), ("OR", "INTERACT"))
        out, = self.checked("OUT = OR A\n            B\n            C")
        self.assertEqual((out.expression.left.right.name, out.expression.right.name), ("B", "C"))

    def test_property_ternaries_distinguish_names_from_branch_separators(self):
        out, = self.checked("X = DFM PROPERTY A [ -= (P > 0) ? F(P) - Q :\n (P > 1) ? Q - R : S ] > 0")
        self.assertEqual(out.expression.modifiers[0].expr.op, "?:")
        out, = self.checked("X = N ? GROUP:VALUE : OTHER")
        self.assertEqual(out.expression.right.left.name, "GROUP:VALUE")

    def test_lvs_bracket_after_parenthesized_argument_does_not_lose_tokens(self):
        a, = self.checked("LVS REDUCE PART (model) PARALLEL YES [\n TOLERANCE w 0\n value = fn(w)\n]")
        self.assertEqual(a.arguments[-1], "[ TOLERANCE W 0 VALUE = FN ( W ) ]")

    def test_operation_and_similarly_named_statement(self):
        a, b, rule = self.checked('X = DFM PATTERN MATCH A B\nDFM PATTERN MATCH REPORT A "out.rdb"\n'
                                  'R { DFM SELECT BY NET A B }')
        self.assertEqual((a.expression.op, b.keywords[-1], rule.body[0].op),
                         ("DFM PATTERN MATCH", "REPORT", "DFM SELECT BY NET"))
        self.assertEqual([v.name for v in rule.body[0].operands], ["A", "B"])
        for op in ("DFM SELECT BY NET", "NET AREA RATIO PRINT"):
            with self.subTest(op=op):
                ds = validate_svrf(f"LAYER A 1\nR {{ {op} A }}", follow_includes=False).errors
                self.assertEqual([d.code for d in ds], ["semantic.drc.missing_operand"])

    def test_qualified_macro_and_operand_names_are_not_split(self):
        call, = self.checked("CMACRO catalogue:compare LIB::INPUTS RESULT")
        self.assertEqual((call.name, [arg.name for arg in call.arguments]),
                         ("CATALOGUE:COMPARE", ["LIB::INPUTS", "RESULT"]))

    def test_net_interact_has_two_layer_roles_and_a_constraint(self):
        expected, = self.checked("X = NET INTERACT A B >= 2")
        for source in ("X = A NET INTERACT B >= 2", "X = A NET\nINTERACT B >= 2"):
            actual, = self.checked(source)
            self.assertTrue(expected.structurally_equal(actual))
        rule, = self.checked("R {\n DFM PROPERTY A [ p = 1 ]\n A NET INTERACT B >= 2\n}")
        self.assertEqual([n.op for n in rule.body], ["DFM PROPERTY", "NET INTERACT"])
        for expression, code in (("NET INTERACT A >= 2", "semantic.drc.missing_operand"),
                                 ("A NET INTERACT A", "semantic.drc.missing_constraint"),
                                 ("A NET INTERACT UNDECLARED > 0", "semantic.reference.undefined")):
            result = validate_svrf("LAYER A 1\nR { " + expression + " }", strict=True, follow_includes=False)
            self.assertEqual([d.code for d in result.errors], [code])

    def test_expand_text_uses_wildcards_not_ternary_expressions(self):
        for pattern in ("?", "pad?1?", '"pad?1?"'):
            source = (f"X = EXPAND TEXT {pattern} MARKERS BY 2*STEP\n"
                      "PRIMARY ONLY CASE SENSITIVE\nR { COPY X }")
            assign, rule = self.checked(source)
            op = assign.expression
            self.assertEqual((op.op, op.operands[0].value, op.operands[1].name), ("EXPAND TEXT", pattern.strip('"'), "MARKERS"))
            self.assertEqual((op.modifiers[0][0], op.modifiers[0][1].op, op.modifiers[1:]),
                             ("BY", "*", ["PRIMARY ONLY", "CASE SENSITIVE"]))
            self.assertEqual(rule.name, "R")
        result = validate_svrf('X = EXPAND TEXT "pattern" BY 0', follow_includes=False)
        self.assertEqual([d.code for d in result.errors], ["semantic.drc.geometry_value"])
        self.assertFalse(validate_svrf("X = EXPAND TEXT ?", strict=True, follow_includes=False).valid)

    def test_inventory_is_recursive_and_never_guesses_from_first_word(self):
        toc = {"topics": [{"title": "Reference Dictionary A-Z", "children": [
            {"title": "LVS", "children": [{"title": "LVS Report Units"}, {"title": "LVS Unlisted Secret"}]}]}]}
        matrix = inventory(n["title"] for n in dictionary_leaves(toc))
        self.assertEqual(matrix["counts"], {"closed_keyword_contract": 1, "unindexed": 1})
        self.assertIsNone(matrix["entries"][1]["topic"])

    def test_via_redundancy_models(self):
        spec, following = self.checked(
            "DFM SPEC VIA REDUNDANCY VSET\nCONNECTIVITY\n A V ; V B ;\nEND CONNECTIVITY\n"
            "TREAT AS REDUNDANT\nV WITH ASPECT > 2 ;\nV WITH AREA > 3 ;\nEND\nNEXT = 2")
        self.assertEqual((spec.kind, spec.variant, following.name), ("VIA", "REDUNDANCY", "NEXT"))
        self.assertEqual([f.text for f in spec.body[0].arguments], ["A V ;", "V B ;"])
        self.assertEqual(spec.body[2].keywords, ["TREAT", "AS", "REDUNDANT"])
        for stack in ("A _TARGET_ B", "A V B _TARGET_ C ;",
                      "[ A B BY V ] [ B _TARGET1_ ]\n[ _TARGET2_ C ]"):
            text = 'DFM SPEC VIA REDUNDANCY COUNT "via set"\nTARGET V\nCONNECTIVITY\n' + stack + '\nEND CONNECTIVITY'
            spec, = self.checked(text)
            self.assertEqual((spec.variant, spec.name, spec.body[0].arguments[0].text), ("REDUNDANCY COUNT", "via set", "V"))
        for stack in ("A B C", "_TARGET_ A B", "[ A _TARGET1_ ]", "[ A B BY ] [ _TARGET2_ C ]"):
            result = validate_svrf('DFM SPEC VIA REDUNDANCY COUNT "S" TARGET V CONNECTIVITY ' +
                                   stack + " END CONNECTIVITY", strict=True, follow_includes=False)
            self.assertFalse(result.valid)
        for rows in ("A ;", "A B;", "A B", "A B ; END"):
            self.assertFalse(validate_svrf("DFM SPEC VIA REDUNDANCY S CONNECTIVITY " + rows +
                                           " END CONNECTIVITY", strict=True, follow_includes=False).valid)

    @unittest.skipUnless(os.environ.get("SVRF_MANUAL_ROOT"), "external reference not configured")
    def test_packaged_inventory_matches_the_reference(self):
        rows = build_dictionary(Path(os.environ["SVRF_MANUAL_ROOT"]))
        self.assertEqual(tuple(map(tuple, rows)), TOPICS)
