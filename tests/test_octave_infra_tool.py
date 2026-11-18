"""Pruebas de regresion para la tool de infraestructura octave_run_script."""

import tempfile
import unittest
from pathlib import Path

import octave_infra_tool


class OctaveRunScriptTests(unittest.TestCase):
    def test_missing_script_reports_error(self):
        out = octave_infra_tool.octave_run_script("/no/existe/archivo_inventado_xyz.m")
        self.assertTrue(out.startswith("Error: no existe"))

    def test_script_runs_with_mfilename_and_relative_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "datos.txt").write_text("7\n")
            script = base / "demo.m"
            script.write_text(
                "base = fileparts(mfilename('fullpath'));\n"
                "v = str2double(strtrim(fileread(fullfile(base, 'datos.txt'))));\n"
                "printf('BASE=%s\\nVAL=%d\\n', base, v);\n"
            )
            out = octave_infra_tool.octave_run_script(str(script), timeout=120)
        self.assertIn("VAL=7", out)
        self.assertIn(str(base), out)

    def test_script_output_is_returned(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "hola.m"
            script.write_text("disp(42)\n")
            out = octave_infra_tool.octave_run_script(str(script), timeout=120)
        self.assertIn("42", out)


if __name__ == "__main__":
    unittest.main()
