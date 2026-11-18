"""Pruebas de regresion para las herramientas de combinatoria avanzada."""

import json
import unittest

import block_designs_tool
import generating_functions_tool
import graph_combinatorics_tool
import matroid_tool
import polya_burnside_tool
import poset_lattice_tool
import ramsey_extremal_tool
import young_tableaux_tool
from tool_registry import REGISTRY


ADVANCED_TOOL_NAMES = {
    "polya_burnside_tool",
    "generating_functions_tool",
    "block_designs_tool",
    "ramsey_extremal_tool",
    "poset_lattice_tool",
    "young_tableaux_tool",
    "matroid_tool",
    "graph_combinatorics_tool",
}


class AdvancedCombinatoricsTests(unittest.TestCase):
    def test_tools_are_registered(self):
        self.assertTrue(ADVANCED_TOOL_NAMES.issubset(REGISTRY))

    def test_all_validations_pass(self):
        results = [
            polya_burnside_tool.compute_polya_burnside({"mode": "validate"}),
            generating_functions_tool.compute_generating_functions({"mode": "validate"}),
            block_designs_tool.compute_block_designs({"mode": "validate"}),
            ramsey_extremal_tool.compute_ramsey_extremal({"mode": "validate"}),
            poset_lattice_tool.compute_poset_lattice({"mode": "validate"}),
            young_tableaux_tool.compute_young_tableaux({"mode": "validate"}),
            matroid_tool.compute_matroid({"mode": "validate"}),
            graph_combinatorics_tool.compute_graph_combinatorics({"mode": "validate"}),
        ]
        for result in results:
            self.assertTrue(result["validation_passed"])
            self.assertTrue(result["checks"])

    def test_polya_burnside_counts_orbits(self):
        result = polya_burnside_tool.compute_polya_burnside(
            {"mode": "count_colorings", "n": 4, "group": "dihedral", "colors": 3}
        )
        self.assertEqual(result["orbits"], 21)

    def test_generating_functions_extracts_coefficient(self):
        result = generating_functions_tool.compute_generating_functions(
            {"mode": "coefficient", "expression": "1/(1-x-x**2)", "n": 10}
        )
        self.assertEqual(result["coefficient"], 89)

    def test_projective_plane_order_four(self):
        result = block_designs_tool.compute_block_designs(
            {"mode": "projective_plane", "q": 4}
        )
        self.assertEqual(result["v"], 21)
        self.assertEqual(result["b"], 21)
        self.assertTrue(result["is_projective_plane"])

    def test_ramsey_unknown_value_is_not_asserted(self):
        result = ramsey_extremal_tool.compute_ramsey_extremal(
            {"mode": "ramsey_number", "s": 5, "t": 5}
        )
        self.assertFalse(result["exact_known"])
        self.assertIsNone(result["exact"])
        self.assertLessEqual(result["lower_bound"], result["upper_bound"])

    def test_mobius_and_whitney_numbers(self):
        arguments = {
            "elements": [0, 1, 2, 3],
            "relations": [[0, 1], [0, 2], [1, 3], [2, 3]],
        }
        mobius = poset_lattice_tool.compute_poset_lattice(
            {"mode": "mobius", **arguments}
        )
        values = {(item["x"], item["y"]): item["mu"] for item in mobius["mobius"]}
        self.assertEqual(values[(0, 3)], 1)
        whitney = poset_lattice_tool.compute_poset_lattice(
            {"mode": "whitney", **arguments}
        )
        self.assertEqual(whitney["whitney_numbers"], [1, 2, 1])

    def test_young_tableaux_and_kostka(self):
        hooks = young_tableaux_tool.compute_young_tableaux(
            {"mode": "hook_length", "shape": [3, 2]}
        )
        self.assertEqual(hooks["number_of_standard_young_tableaux"], 5)
        kostka = young_tableaux_tool.compute_young_tableaux(
            {"mode": "kostka", "shape": [2, 1], "content": [2, 1]}
        )
        self.assertEqual(kostka["kostka"], 1)

    def test_rsk_recording_tableau_is_standard(self):
        result = young_tableaux_tool.compute_young_tableaux(
            {"mode": "rsk", "word": list("mississippi")}
        )
        self.assertEqual(result["shape"], [5, 5, 1])
        self.assertEqual(
            result["recording_tableau"],
            [[1, 3, 4, 6, 7], [2, 5, 8, 9, 10], [11]],
        )
        self.assertTrue(result["recording_is_standard"])
        self.assertTrue(result["roundtrip"])

    def test_rsk_roundtrip_on_many_words(self):
        words = ("abc", "cba", "aabbcc", "zyxwvu", "banana", "mississippi")
        for word in words:
            result = young_tableaux_tool.compute_young_tableaux(
                {"mode": "rsk", "word": list(word)}
            )
            self.assertTrue(result["roundtrip"], word)
            entries = [
                value
                for row in result["recording_tableau"]
                for value in row
            ]
            self.assertEqual(sorted(entries), list(range(1, len(word) + 1)), word)

    def test_fano_matroid_and_base_polytope(self):
        matrix = [
            [1, 0, 0, 1, 1, 0, 1],
            [0, 1, 0, 1, 0, 1, 1],
            [0, 0, 1, 0, 1, 1, 1],
        ]
        result = matroid_tool.compute_matroid(
            {"mode": "representable", "matrix": matrix}
        )
        self.assertEqual(result["rank"], 3)
        self.assertEqual(len(result["bases"]), 28)
        polytope = matroid_tool.compute_matroid(
            {"mode": "polytope", "uniform": True, "r": 2, "n": 4}
        )
        self.assertEqual(len(polytope["vertices"]), 6)

    def test_graph_polynomials_and_matchings(self):
        triangle = graph_combinatorics_tool.compute_graph_combinatorics(
            {
                "mode": "chromatic_polynomial",
                "vertices": [0, 1, 2],
                "edges": [[0, 1], [1, 2], [0, 2]],
            }
        )
        self.assertEqual(triangle["chromatic_polynomial"], "x^3 - 3*x^2 + 2*x")
        tutte = graph_combinatorics_tool.compute_graph_combinatorics(
            {
                "mode": "tutte_polynomial",
                "vertices": [0, 1, 2],
                "edges": [[0, 1], [1, 2], [0, 2]],
            }
        )
        self.assertEqual(tutte["tutte_polynomial"], "x^2 + x + y")
        matchings = graph_combinatorics_tool.compute_graph_combinatorics(
            {
                "mode": "matchings",
                "vertices": [0, 1, 2, 3],
                "edges": [[0, 1], [1, 2], [2, 3]],
            }
        )
        self.assertEqual(matchings["perfect_matchings"], 1)

    def test_results_are_json_serializable(self):
        results = [
            polya_burnside_tool.compute_polya_burnside({"mode": "validate"}),
            generating_functions_tool.compute_generating_functions({"mode": "validate"}),
            block_designs_tool.compute_block_designs({"mode": "validate"}),
            ramsey_extremal_tool.compute_ramsey_extremal({"mode": "validate"}),
            poset_lattice_tool.compute_poset_lattice({"mode": "validate"}),
            young_tableaux_tool.compute_young_tableaux({"mode": "validate"}),
            matroid_tool.compute_matroid({"mode": "validate"}),
            graph_combinatorics_tool.compute_graph_combinatorics({"mode": "validate"}),
        ]
        for result in results:
            json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
