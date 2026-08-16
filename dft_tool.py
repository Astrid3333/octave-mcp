"""
DFT / quimica computacional via PySCF, ejecutado en subprocess aislado
(.venv-pyscf) para evitar el conflicto de ABI numpy/h5py con el Python
del sistema que corre server.py. Ver _dft_worker.py para el contrato JSON.
"""
import subprocess
import json
import os

import tool_registry

_HERE = os.path.dirname(os.path.abspath(__file__))
_VENV_PYTHON = os.path.join(_HERE, ".venv-pyscf", "bin", "python3")
_WORKER = os.path.join(_HERE, "_dft_worker.py")

DFT_TOOL_SCHEMA = {
    "name": "dft_tool",
    "description": (
        "Quimica computacional: energia Hartree-Fock y DFT (funcionales "
        "LDA/GGA/hibridos como B3LYP/PBE) para moleculas pequenas, via "
        "PySCF en subprocess aislado. mode='validate' corre HF/STO-3G "
        "sobre H2 contra valor de referencia de libro de texto."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["hf_energy", "dft_energy", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "atom": {"type": "string", "description": "geometria en formato PySCF, ej. 'H 0 0 0; H 0 0 0.74'"},
                    "basis": {"type": "string", "default": "sto-3g", "description": "ej. sto-3g, 6-31g, cc-pvdz"},
                    "xc": {"type": "string", "default": "b3lyp", "description": "funcional de intercambio-correlacion (solo dft_energy)"},
                    "charge": {"type": "integer", "default": 0},
                    "spin": {"type": "integer", "default": 0, "description": "2S, numero de electrones desapareados"},
                    "unit": {"type": "string", "default": "Angstrom"},
                },
            },
        },
        "required": ["mode"],
    },
}


def compute_dft(mode, params=None, **kwargs):
    if not os.path.exists(_VENV_PYTHON):
        raise RuntimeError(
            f"No se encontro el venv de PySCF en {_VENV_PYTHON}. "
            "Crear con: python3 -m venv .venv-pyscf && .venv-pyscf/bin/pip install pyscf"
        )
    payload = json.dumps({"mode": mode, "params": params or {}})
    result = subprocess.run(
        [_VENV_PYTHON, _WORKER],
        input=payload, capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 and not result.stdout.strip():
        raise RuntimeError(f"dft worker fallo sin salida JSON: {result.stderr}")
    try:
        out = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        raise RuntimeError(f"dft worker devolvio salida no-JSON: {result.stdout!r} / stderr: {result.stderr}")
    if "error" in out:
        raise RuntimeError(f"dft worker error ({out.get('error_type')}): {out['error']}")
    return out


def _handler(args):
    return compute_dft(args.get("mode"), args.get("params"))


tool_registry.register_tool("dft_tool", DFT_TOOL_SCHEMA, _handler)
