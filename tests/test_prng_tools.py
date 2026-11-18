"""Pruebas de regresion de las tools de PRNG (hybrid_prng, lcg_lehmer,
middle_square_weyl).

Los vectores de referencia estan calculados con una implementacion
independiente en Python con aritmetica entera exacta (no con el codigo de
Octave de las tools), de modo que un cambio que rompa el generador hace
fallar los tests en vez de "validarse contra si mismo".
"""

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hybrid_prng_tool  # noqa: E402
import lcg_lehmer_tool  # noqa: E402
import middle_square_weyl_tool  # noqa: E402

pytestmark = pytest.mark.integration


def _nums(value):
    """Convierte '[1 2 3]' (así lo imprime Octave) en lista de floats."""
    if isinstance(value, (list, tuple)):
        return [float(v) for v in value]
    return [float(part) for part in str(value).strip().strip("[]").split()]


class HybridPrngTests(unittest.TestCase):
    def test_validate_mode_passes_all_checks(self):
        result = hybrid_prng_tool.hybrid_prng(mode="validate")
        self.assertTrue(result["validation_passed"], result["checks"])
        self.assertEqual(result["total_passed"], result["total_checks"])

    def test_first_values_match_python_reference(self):
        result = hybrid_prng_tool.hybrid_prng(mode="validate")
        first = [c for c in result["checks"] if "primeros 3 valores" in c["name"]][0]
        self.assertTrue(first["passed"])
        self.assertEqual(first["want"][0], 2416814197255316608)

    def test_compute_mode_reports_exact_tcr_modulus(self):
        result = hybrid_prng_tool.hybrid_prng()
        self.assertEqual(result["tcr_modulus_M"], 99400891)
        self.assertEqual(result["middle_square_cycles"], 8)


class LcgLehmerTests(unittest.TestCase):
    def test_validate_mode_passes_all_checks(self):
        result = lcg_lehmer_tool.lcg_lehmer(mode="validate")
        self.assertTrue(result["validation_passed"], result["checks"])
        self.assertEqual(result["total_passed"], result["total_checks"])

    def test_randu_first_values_match_reference(self):
        result = lcg_lehmer_tool.lcg_lehmer()
        self.assertEqual(_nums(result["first_values"])[:3], [65539, 393225, 1769499])

    def test_randu_falls_in_15_planes_3d(self):
        result = lcg_lehmer_tool.lcg_lehmer()
        self.assertEqual(result["planes_3d"], 15)

    def test_minstd_has_764_planes_3d(self):
        result = lcg_lehmer_tool.lcg_lehmer(
            a=16807, c=0, m=2 ** 31 - 1, dim=3, x0=1, max_iter=1000
        )
        self.assertEqual(result["planes_3d"], 764)

    def test_small_lcg_period_measured_with_floyd(self):
        result = lcg_lehmer_tool.lcg_lehmer(
            a=4, c=1, m=7, dim=3, x0=1, max_iter=1000, n_samples=100
        )
        self.assertEqual(result["period"], 3)
        self.assertEqual(result["period_found"], 1)


class MiddleSquareWeylTests(unittest.TestCase):
    def test_validate_mode_passes_all_checks(self):
        result = middle_square_weyl_tool.middle_square_weyl(mode="validate")
        self.assertTrue(result["validation_passed"], result["checks"])
        self.assertEqual(result["total_passed"], result["total_checks"])

    def test_compute_mode_reports_exact_tcr_modulus(self):
        result = middle_square_weyl_tool.middle_square_weyl()
        self.assertEqual(result["tcr_modulus_M"], 99400891)

    def test_middle_square_is_biased(self):
        result = middle_square_weyl_tool.middle_square_weyl()
        self.assertGreater(result["chi2_middle_square"], 1000)
        self.assertLess(result["chi2_msws64"], 21.666)

    def test_params_override_compute_arguments(self):
        result = middle_square_weyl_tool.middle_square_weyl(
            params={"chi2_bins": 5, "chi2_samples": 1000}
        )
        self.assertEqual(result["chi2_bins"], 5)
        self.assertEqual(result["chi2_samples"], 1000)


if __name__ == "__main__":
    unittest.main()
