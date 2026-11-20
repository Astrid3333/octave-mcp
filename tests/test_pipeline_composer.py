"""Pruebas de regresion del tool pipeline_composer (encadenado de tools)."""

import subprocess
import sys
import types
import unittest


def _install_fake_server():
    """Sustituye el modulo server por uno con run_octave real via octave-cli.

    pipeline_composer_tool importa run_octave de server de forma perezosa para
    evitar el ciclo de imports; en las pruebas no queremos arrancar el
    servidor MCP completo.
    """
    fake = types.ModuleType("server")

    def run_octave(code, timeout=30):
        proc = subprocess.run(
            ["octave", "--no-gui", "--quiet", "--eval", code],
            capture_output=True, text=True, timeout=timeout,
        )
        return proc.stdout + proc.stderr

    fake.run_octave = run_octave
    return fake


class PipelineComposerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_server = sys.modules.get("server")
        sys.modules["server"] = _install_fake_server()
        import ancestral_octave_tool  # noqa: F401
        import goertzel_tool  # noqa: F401
        import middle_square_weyl_tool  # noqa: F401
        import pipeline_composer_tool  # noqa: F401

        cls.pipeline_composer = staticmethod(pipeline_composer_tool.pipeline_composer)

    @classmethod
    def tearDownClass(cls):
        if cls._previous_server is None:
            sys.modules.pop("server", None)
        else:
            sys.modules["server"] = cls._previous_server

    def test_pipeline_chains_three_tools(self):
        result = self.pipeline_composer(
            steps=[
                {"tool": "ancestral_octave",
                 "arguments": {"preset": "liu_hui_pi", "params": {"iterations": 8, "levels": 2}},
                 "as": "pi_paso"},
                {"tool": "goertzel",
                 "arguments": {"signal": [1.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0],
                               "w": "${pi_paso.pi_liu_hui}", "form": "K"},
                 "as": "goertzel_paso"},
                {"tool": "middle_square_weyl", "arguments": {}, "as": "msw_paso"},
            ],
            stop_on_error=True,
        )
        self.assertEqual(result["pasos_totales"], 3)
        self.assertEqual(result["pasos_ejecutados"], 3)
        self.assertFalse(result["detenido_temprano"])
        self.assertEqual(set(result["resultados"]), {"pi_paso", "goertzel_paso", "msw_paso"})
        self.assertAlmostEqual(result["resultados"]["pi_paso"]["pi_liu_hui"], 3.14159, places=4)
        self.assertLess(abs(result["resultados"]["goertzel_paso"]["magnitude"]), 1e-6)
        self.assertIn("middle_square_cycles", result["resultados"]["msw_paso"])

    def test_missing_tool_stops_pipeline(self):
        result = self.pipeline_composer(
            steps=[
                {"tool": "ancestral_octave",
                 "arguments": {"preset": "liu_hui_pi", "params": {"iterations": 4, "levels": 1}},
                 "as": "pi_paso"},
                {"tool": "tool_que_no_existe_xyz", "arguments": {}, "as": "roto"},
            ],
            stop_on_error=True,
        )
        self.assertTrue(result["detenido_temprano"])
        self.assertIn("error", result["resultados"]["roto"])
        self.assertEqual(result["pasos_totales"], 2)


if __name__ == "__main__":
    unittest.main()
