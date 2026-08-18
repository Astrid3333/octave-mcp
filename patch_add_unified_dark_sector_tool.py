"""
patch_add_unified_dark_sector_tool.py
======================================

Convierte unified_dark_sector_tool.py en una tool invocable vía MCP:

  1. En unified_dark_sector_tool.py:
     - agrega `from tool_registry import register_tool`
     - agrega el dispatcher compute_unified_dark_sector_tool(mode, params)
     - agrega UNIFIED_DARK_SECTOR_TOOL_SCHEMA
     - agrega la llamada register_tool(...) al final del archivo
  2. En server.py:
     - agrega `import unified_dark_sector_tool  # auto-registra via
       tool_registry, no requiere mas ediciones`

No toca la familia 'custom': requiere una q_fn (código Python arbitrario)
que no se puede transportar por JSON-RPC, así que queda excluida del tool
público a propósito — documentado en la descripción del schema.

Hace backup de ambos archivos (.bak) antes de escribir. No asume nada:
si algún anchor no aparece exactamente una vez, aborta sin tocar nada y
lo dice explícitamente.
"""
import shutil
import sys
from pathlib import Path

TOOL_FILE = Path("unified_dark_sector_tool.py")
SERVER_FILE = Path("server.py")

DISPATCHER_AND_REGISTER = '''

# ---------------------------------------------------------------------------
# 7. Registro como tool MCP
# ---------------------------------------------------------------------------
#
# Nota de alcance: solo se exponen las familias con parámetros puramente
# numéricos (lcdm, wang_meng, signswitch, ide_h3). La familia 'custom' pide
# una q_fn (callable Python) que no se puede transportar por JSON-RPC, así
# que queda fuera del tool público; sigue disponible llamando a compute_Hz()
# directamente desde Python.

from tool_registry import register_tool

_EXPOSED_FAMILIES = ("lcdm", "wang_meng", "signswitch", "ide_h3")


def compute_unified_dark_sector_tool(mode: str, params: dict | None = None):
    params = dict(params or {})

    if mode == "self_test":
        ok = self_test(verbose=False)
        return {"mode": "self_test", "all_pass": ok}

    if mode == "compute_Hz":
        family = params.get("family", "lcdm")
        if family not in _EXPOSED_FAMILIES:
            raise ValueError(
                f"family debe ser una de {_EXPOSED_FAMILIES} "
                f"('custom' no esta expuesta via MCP: requiere una funcion "
                f"Python arbitraria, usar compute_Hz() directamente)"
            )
        z = params.get("z")
        if z is None:
            raise ValueError("falta 'z' (lista de redshifts)")
        z_arr = np.atleast_1d(np.asarray(z, dtype=float))

        cosmo = Cosmology(
            H0=params.get("H0", 70.0),
            Om0=params.get("Om0", 0.3),
            Or0=params.get("Or0", 8.24e-5),
        )

        family_kwargs = {}
        if family == "wang_meng":
            family_kwargs["xi"] = params.get("xi", 0.01)
        elif family == "signswitch":
            family_kwargs["z_dagger"] = params.get("z_dagger", 2.0)
            family_kwargs["k"] = params.get("k", 5.0)
        elif family == "ide_h3":
            family_kwargs["beta"] = params.get("beta", 0.0)
            family_kwargs["w"] = params.get("w", -1.0)

        out = compute_Hz(z_arr, cosmo, family, **family_kwargs)
        return {
            "mode": "compute_Hz",
            "family": family,
            "z": out["z"].tolist(),
            "H_km_s_Mpc": out["H"].tolist(),
            "E": out["E"].tolist(),
            "Omega_m": out["Om"].tolist(),
            "Omega_de": out["Ode"].tolist(),
        }

    raise ValueError(f"mode desconocido: {mode!r} (usar 'compute_Hz' o 'self_test')")


UNIFIED_DARK_SECTOR_TOOL_SCHEMA = {
    "name": "unified_dark_sector_tool",
    "description": (
        "Calcula H(z) y Omega_m(z)/Omega_de(z) bajo un formalismo Friedmann+"
        "continuidad unificado, para cuatro familias de sector oscuro "
        "comparables entre si: lcdm (control), wang_meng (rho_de~a^-xi, "
        "Ozer&Taha 1987/Wang&Meng 2005), signswitch (Lambda_s tanh, ansatz "
        "tipo Akarsu et al. motivado por DESI BAO 2024), ide_h3 (acoplamiento "
        "Q~beta*H^3). Ninguna familia esta ajustada a datos observacionales "
        "reales, ver docstring del modulo. mode='self_test' corre las "
        "verificaciones internas (regresion a LCDM, conservacion de energia, "
        "cuadratura vs ODE)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["compute_Hz", "self_test"],
                "description": "compute_Hz: evalua H(z) para una familia. self_test: corre self_test() interno.",
            },
            "params": {
                "type": "object",
                "properties": {
                    "family": {
                        "type": "string",
                        "enum": list(_EXPOSED_FAMILIES),
                        "description": "Familia de sector oscuro (default lcdm). 'custom' no esta expuesta via MCP.",
                    },
                    "z": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Redshifts donde evaluar H(z) (requerido para compute_Hz)",
                    },
                    "H0": {"type": "number", "description": "H0 en km/s/Mpc (default 70.0)"},
                    "Om0": {"type": "number", "description": "Omega_m hoy (default 0.3)"},
                    "Or0": {"type": "number", "description": "Omega_r hoy (default 8.24e-5)"},
                    "xi": {"type": "number", "description": "Solo wang_meng: exponente rho_de~a^-xi (default 0.01)"},
                    "z_dagger": {"type": "number", "description": "Solo signswitch: redshift de cambio de signo (default 2.0)"},
                    "k": {"type": "number", "description": "Solo signswitch: agudeza de la transicion tanh (default 5.0)"},
                    "beta": {"type": "number", "description": "Solo ide_h3: intensidad de acoplamiento Q~beta*H^3 (default 0.0)"},
                    "w": {"type": "number", "description": "Solo ide_h3: ecuacion de estado del fluido oscuro (default -1.0)"},
                },
            },
        },
        "required": ["mode"],
    },
}


register_tool(
    name="unified_dark_sector_tool",
    schema=UNIFIED_DARK_SECTOR_TOOL_SCHEMA,
    handler=lambda args: compute_unified_dark_sector_tool(
        args.get("mode"), args.get("params")
    ),
)
'''

MAIN_BLOCK_OLD = '''if __name__ == "__main__":
    self_test(verbose=True)
'''

MAIN_BLOCK_NEW = '''if __name__ == "__main__":
    import json
    print(json.dumps(compute_unified_dark_sector_tool("self_test"), indent=2))
'''

SERVER_ANCHOR = "import vacuum_energy_density_tool  # auto-registra via tool_registry, no requiere mas ediciones\n"
SERVER_NEW_IMPORT = "import unified_dark_sector_tool  # auto-registra via tool_registry, no requiere mas ediciones\n"


def report(item, ok, detail=""):
    status = "[ok]" if ok else "[FALLA]"
    print(f"{status} {item}" + (f" -- {detail}" if detail else ""))
    return ok


def main():
    if not TOOL_FILE.exists():
        return report(f"{TOOL_FILE} existe", False, "corre este script desde la raiz del repo")
    if not SERVER_FILE.exists():
        return report(f"{SERVER_FILE} existe", False, "corre este script desde la raiz del repo")

    tool_src = TOOL_FILE.read_text(encoding="utf-8")
    server_src = SERVER_FILE.read_text(encoding="utf-8")

    all_ok = True

    # --- checks de idempotencia: si ya esta parcheado, no tocar nada ---
    if "register_tool(" in tool_src and "unified_dark_sector_tool" in tool_src.split("register_tool(", 1)[1][:200]:
        print(f"[skip] {TOOL_FILE} ya tiene register_tool() -- no se modifica")
        already_tool = True
    else:
        already_tool = False

    if SERVER_NEW_IMPORT.strip() in server_src:
        print(f"[skip] {SERVER_FILE} ya tiene el import -- no se modifica")
        already_server = True
    else:
        already_server = False

    if already_tool and already_server:
        print("Nada que hacer, ambos archivos ya estan parcheados.")
        return True

    # --- validar anchors antes de escribir nada ---
    if not already_tool:
        n_main = tool_src.count(MAIN_BLOCK_OLD)
        all_ok &= report(
            f"anchor del bloque __main__ aparece 1 vez en {TOOL_FILE}",
            n_main == 1, f"aparece {n_main} veces"
        )

    if not already_server:
        n_anchor = server_src.count(SERVER_ANCHOR)
        all_ok &= report(
            f"anchor de import (vacuum_energy_density_tool) aparece 1 vez en {SERVER_FILE}",
            n_anchor == 1, f"aparece {n_anchor} veces"
        )

    if not all_ok:
        print("\nAbortado: algun anchor no matcheo como se esperaba. Nada fue escrito.")
        print("Revisa a mano el archivo y ajusta este script antes de reintentar.")
        return False

    # --- escribir, con backup ---
    if not already_tool:
        shutil.copy2(TOOL_FILE, TOOL_FILE.with_suffix(".py.bak"))
        new_tool_src = tool_src.replace(MAIN_BLOCK_OLD, DISPATCHER_AND_REGISTER + "\n\n" + MAIN_BLOCK_NEW)
        TOOL_FILE.write_text(new_tool_src, encoding="utf-8")
        report(f"{TOOL_FILE} parchado (dispatcher + schema + register_tool agregados)", True)
        report(f"backup guardado en {TOOL_FILE.with_suffix('.py.bak')}", True)

    if not already_server:
        shutil.copy2(SERVER_FILE, SERVER_FILE.with_suffix(".py.bak"))
        new_server_src = server_src.replace(SERVER_ANCHOR, SERVER_ANCHOR + SERVER_NEW_IMPORT)
        SERVER_FILE.write_text(new_server_src, encoding="utf-8")
        report(f"{SERVER_FILE} parchado (1 linea de import agregada)", True)
        report(f"backup guardado en {SERVER_FILE.with_suffix('.py.bak')}", True)

    print("\nListo. Revisa con: git diff")
    print("Y corre esto para confirmar que el dispatcher funciona antes de commitear:")
    print(f"  python3 {TOOL_FILE}")
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
