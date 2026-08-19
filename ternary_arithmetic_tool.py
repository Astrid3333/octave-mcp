"""
ternary_arithmetic_tool.py

Reune los 4 motores que se usaron para verificar el modelo de energia
oscura interactuante ide_h3 (interaccion Q = 3*H*beta*rho_m) en un solo
tool de octave-mcp:

  1. Python / scipy  -- integrador adaptativo (solve_ivp)
  2. Rust             -- RK4 de paso fijo, cero dependencias (compilado on-demand)
  3. C++               -- RK4 de paso fijo, cero dependencias (compilado on-demand)
  4. Ternario balanceado -- RK4 en trits {-1,0,1}, aritmetica propia (ver ternary_bt.py)

Ademas expone la aritmetica ternaria balanceada de forma generica
(add/sub/mul/div) para uso fuera del contexto de ide_h3.

Modos:
  - "verify_ide_h3": corre los 4 motores para varios beta y compara
    contra la forma cerrada y contra LambdaCDM (beta=0).
  - "add" | "sub" | "mul" | "div": operacion ternaria generica sobre
    dos numeros (parametros a, b).
  - "validate": auto-validacion (casos con resultado conocido), para
    el pre-push hook run_all_validations.py.

Requiere en PATH (o instala on-demand via apt si estan permitidos los
dominos de red): rustc, g++. Si no estan disponibles, verify_ide_h3
degrada agraciadamente a 2 motores (Python + Ternario) y lo reporta
en el campo "motores_disponibles".
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from scipy.integrate import solve_ivp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ternary_bt import to_bt, from_bt, bt_add, bt_sub, bt_mul, bt_div  # noqa: E402

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass  # standalone (fuera de octave-mcp): no-op

# ---------------------------------------------------------------------------
# Constantes del modelo ide_h3 (Q = 3 H beta rho_m)
# ---------------------------------------------------------------------------
RHO_M0 = 0.3
RHO_DE0 = 0.7
DEFAULT_BETAS = (0.0, 0.02, 0.05, -0.10)
DEFAULT_Z_FINAL = 2.0
DEFAULT_N_STEPS = 2000

_ENGINES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engines")
_BUILD_DIR = os.path.join(tempfile.gettempdir(), "octave_mcp_ternary_engines")


def closed_form(beta, z, rho_m0=RHO_M0, rho_de0=RHO_DE0):
    if beta == 0.0:
        rho_m = rho_m0 * (1 + z) ** 3
        rho_de = rho_de0
    else:
        rho_m = rho_m0 * (1 + z) ** (3 * (1 - beta))
        rho_de = rho_de0 + (beta / (1 - beta)) * rho_m0 * ((1 + z) ** (3 * (1 - beta)) - 1)
    return rho_m, rho_de


# ---------------------------------------------------------------------------
# Motor 1: Python / scipy (integrador adaptativo)
# ---------------------------------------------------------------------------
def run_python(beta, z_final, rho_m0=RHO_M0, rho_de0=RHO_DE0):
    c_m = 3 * (1 - beta)
    c_de = 3 * beta

    def rhs(z, y):
        rho_m, _ = y
        inv = 1.0 / (1 + z)
        return [c_m * rho_m * inv, c_de * rho_m * inv]

    sol = solve_ivp(rhs, [0, z_final], [rho_m0, rho_de0], rtol=1e-10, atol=1e-12)
    return float(sol.y[0, -1]), float(sol.y[1, -1])


# ---------------------------------------------------------------------------
# Motores 2 y 3: Rust y C++ (binarios externos, compilados on-demand)
# ---------------------------------------------------------------------------
def _ensure_compiled():
    os.makedirs(_BUILD_DIR, exist_ok=True)
    status = {}

    rust_bin = os.path.join(_BUILD_DIR, "rk4_verify_rust")
    if not os.path.exists(rust_bin):
        rustc = shutil.which("rustc")
        if rustc:
            src = os.path.join(_ENGINES_DIR, "rk4_verify.rs")
            r = subprocess.run([rustc, "-O", src, "-o", rust_bin], capture_output=True, text=True)
            status["rust"] = r.returncode == 0
        else:
            status["rust"] = False
    else:
        status["rust"] = True

    cpp_bin = os.path.join(_BUILD_DIR, "rk4_verify_cpp")
    if not os.path.exists(cpp_bin):
        gpp = shutil.which("g++")
        if gpp:
            src = os.path.join(_ENGINES_DIR, "rk4_verify.cpp")
            r = subprocess.run([gpp, "-O2", "-std=c++17", src, "-o", cpp_bin], capture_output=True, text=True)
            status["cpp"] = r.returncode == 0
        else:
            status["cpp"] = False
    else:
        status["cpp"] = True

    return rust_bin, cpp_bin, status


def run_binary(binary_path, beta, z_final, n_steps):
    r = subprocess.run(
        [binary_path, str(beta), str(z_final), str(n_steps)],
        capture_output=True, text=True, timeout=60,
    )
    data = json.loads(r.stdout.strip())
    return data["rho_m"], data["rho_de"]


# ---------------------------------------------------------------------------
# Motor 4: Ternario balanceado (RK4 en trits, ver ternary_bt.py)
# ---------------------------------------------------------------------------
def run_ternary(beta, z_final, n_steps, rho_m0=RHO_M0, rho_de0=RHO_DE0):
    ONE, THREE = to_bt(1.0), to_bt(3.0)
    beta_bt = to_bt(beta)
    c_m = bt_mul(THREE, bt_sub(ONE, beta_bt))
    c_de = bt_mul(THREE, beta_bt)
    dz = to_bt(z_final / n_steps)
    half_dz = to_bt(z_final / n_steps / 2.0)

    def deriv(z, rho_m):
        inv = bt_div(ONE, bt_add(ONE, z))
        return bt_mul(c_m, bt_mul(rho_m, inv)), bt_mul(c_de, bt_mul(rho_m, inv))

    z = to_bt(0.0)
    rho_m, rho_de = to_bt(rho_m0), to_bt(rho_de0)
    for _ in range(n_steps):
        k1m, k1d = deriv(z, rho_m)
        z2 = bt_add(z, half_dz)
        k2m, k2d = deriv(z2, bt_add(rho_m, bt_mul(half_dz, k1m)))
        k3m, k3d = deriv(z2, bt_add(rho_m, bt_mul(half_dz, k2m)))
        z4 = bt_add(z, dz)
        k4m, k4d = deriv(z4, bt_add(rho_m, bt_mul(dz, k3m)))
        sm = bt_add(bt_add(k1m, k4m), bt_mul(to_bt(2.0), bt_add(k2m, k3m)))
        sd = bt_add(bt_add(k1d, k4d), bt_mul(to_bt(2.0), bt_add(k2d, k3d)))
        rho_m = bt_add(rho_m, bt_mul(bt_div(dz, to_bt(6.0)), sm))
        rho_de = bt_add(rho_de, bt_mul(bt_div(dz, to_bt(6.0)), sd))
        z = z4
    return from_bt(rho_m), from_bt(rho_de)


# ---------------------------------------------------------------------------
# mode="verify_ide_h3"
# ---------------------------------------------------------------------------
def verify_ide_h3(betas=DEFAULT_BETAS, z_final=DEFAULT_Z_FINAL, n_steps=DEFAULT_N_STEPS):
    rust_bin, cpp_bin, compiled = _ensure_compiled()
    motores_disponibles = ["python", "ternario"] + \
        (["rust"] if compiled.get("rust") else []) + \
        (["cpp"] if compiled.get("cpp") else [])

    resultados = []
    for beta in betas:
        rho_m_cf, rho_de_cf = closed_form(beta, z_final)
        fila = {"beta": beta}

        rho_m, rho_de = run_python(beta, z_final)
        fila["python"] = {"rho_m": rho_m, "rho_de": rho_de,
                           "error_rel": max(abs(rho_m - rho_m_cf) / rho_m_cf,
                                             abs(rho_de - rho_de_cf) / rho_de_cf)}

        rho_m, rho_de = run_ternary(beta, z_final, n_steps)
        fila["ternario"] = {"rho_m": rho_m, "rho_de": rho_de,
                             "error_rel": max(abs(rho_m - rho_m_cf) / rho_m_cf,
                                               abs(rho_de - rho_de_cf) / rho_de_cf)}

        if compiled.get("rust"):
            rho_m, rho_de = run_binary(rust_bin, beta, z_final, n_steps)
            fila["rust"] = {"rho_m": rho_m, "rho_de": rho_de,
                             "error_rel": max(abs(rho_m - rho_m_cf) / rho_m_cf,
                                               abs(rho_de - rho_de_cf) / rho_de_cf)}

        if compiled.get("cpp"):
            rho_m, rho_de = run_binary(cpp_bin, beta, z_final, n_steps)
            fila["cpp"] = {"rho_m": rho_m, "rho_de": rho_de,
                            "error_rel": max(abs(rho_m - rho_m_cf) / rho_m_cf,
                                              abs(rho_de - rho_de_cf) / rho_de_cf)}

        resultados.append(fila)

    todos_pasaron = all(
        motor_data["error_rel"] < 1e-6
        for fila in resultados
        for motor, motor_data in fila.items()
        if motor != "beta"
    )

    return {
        "modelo": "ide_h3 (Q = 3 H beta rho_m)",
        "motores_disponibles": motores_disponibles,
        "z_final": z_final,
        "n_steps": n_steps,
        "resultados": resultados,
        "todos_pasaron": todos_pasaron,
    }


# ---------------------------------------------------------------------------
# Aritmetica ternaria generica
# ---------------------------------------------------------------------------
_OPS = {
    "add": bt_add,
    "sub": bt_sub,
    "mul": bt_mul,
    "div": bt_div,
}


def ternary_op(mode, a, b):
    fn = _OPS[mode]
    result_bt = fn(to_bt(a), to_bt(b))
    result = from_bt(result_bt)
    trits_no_cero = int(np.count_nonzero(result_bt))
    return {
        "operacion": mode,
        "a": a, "b": b,
        "resultado": result,
        "trits_no_cero": trits_no_cero,
    }


# ---------------------------------------------------------------------------
# mode="validate"
# ---------------------------------------------------------------------------
def validate():
    checks = []

    r = ternary_op("add", 1.5, -0.3333333333)
    checks.append(("add", abs(r["resultado"] - 1.1666666667) < 1e-9))

    r = ternary_op("div", 22.0, 7.0)
    checks.append(("div 22/7", abs(r["resultado"] - 22 / 7) < 1e-9))

    ide = verify_ide_h3(betas=(0.0, 0.05), n_steps=500)
    checks.append(("beta=0 vs LambdaCDM",
                    ide["resultados"][0]["python"]["error_rel"] < 1e-9))
    checks.append(("beta=0.05 forma cerrada",
                    ide["resultados"][1]["ternario"]["error_rel"] < 1e-9))

    all_ok = all(ok for _, ok in checks)
    return {"checks": [{"nombre": n, "paso": ok} for n, ok in checks], "todos_pasaron": all_ok, "validation_passed": all_ok}


# ---------------------------------------------------------------------------
# Entry point / schema
# ---------------------------------------------------------------------------
TOOL_SCHEMA = {
    "name": "ternary_arithmetic_tool",
    "description": (
        "Aritmetica ternaria balanceada (trits -1,0,1) generica, mas verificacion "
        "cruzada de 4 motores (Python/scipy, Rust, C++, ternario) del modelo de "
        "energia oscura interactuante ide_h3."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["verify_ide_h3", "add", "sub", "mul", "div", "validate"],
            },
            "a": {"type": "number", "description": "Operando A (para add/sub/mul/div)"},
            "b": {"type": "number", "description": "Operando B (para add/sub/mul/div)"},
            "betas": {
                "type": "array", "items": {"type": "number"},
                "description": "Valores de beta a probar (para verify_ide_h3)",
            },
            "z_final": {"type": "number", "description": "Redshift final de integracion"},
            "n_steps": {"type": "integer", "description": "Pasos de RK4 (paso fijo)"},
        },
        "required": ["mode"],
    },
}


def ternary_arithmetic_tool(mode, a=None, b=None, betas=None,
                             z_final=DEFAULT_Z_FINAL, n_steps=DEFAULT_N_STEPS):
    """Funcion nucleo, usable directo en Python/tests (no es el handler MCP)."""
    if mode == "verify_ide_h3":
        return verify_ide_h3(tuple(betas) if betas else DEFAULT_BETAS, z_final, n_steps)
    if mode in _OPS:
        if a is None or b is None:
            raise ValueError(f"mode={mode!r} requiere 'a' y 'b'")
        return ternary_op(mode, a, b)
    if mode == "validate":
        return validate()
    raise ValueError(f"mode desconocido: {mode!r}")


def _handle(args):
    """Handler MCP: recibe el dict `args` de tools/call y delega."""
    return ternary_arithmetic_tool(
        mode=args.get("mode"),
        a=args.get("a"),
        b=args.get("b"),
        betas=args.get("betas"),
        z_final=args.get("z_final", DEFAULT_Z_FINAL),
        n_steps=args.get("n_steps", DEFAULT_N_STEPS),
    )


register_tool("ternary_arithmetic_tool", TOOL_SCHEMA, _handle)


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
