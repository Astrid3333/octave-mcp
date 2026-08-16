"""
bem_electromagnetic_tool.py

Puente hacia el submotor Rust bem_electromagnetic (~/octave-mcp/submotors/bem_electromagnetic):
resuelve electrostatica 2D via metodo indirecto de potencial de capa simple
(BEM), con condiciones Dirichlet (potencial prescrito) y Neumann (derivada
normal / carga prescrita) por conductor. Cuadratura Gauss-Legendre de 8 puntos
para paneles regulares, forma cerrada exacta para el autotermino Dirichlet, y
salto -sigma/2 exacto (por simetria de panel recto) para el autotermino
Neumann. Solver denso (LU, nalgebra) porque el sistema BEM no es simetrico ni
disperso.

Validado contra el capacitor cilindrico (dos conductores concentricos):
- Caso Dirichlet puro: diff ~0.05% (discretizacion geometrica del circulo
  aproximado por poligono, converge O(1/n^2)).
- Caso mixto Dirichlet/Neumann: converge O(1/n) en el flujo (mas lento que
  Dirichlet porque la normal de cada panel recto es constante, mientras la
  normal real del contorno curvo rota continuamente -- desajuste O(h)
  intrinseco a BEM con paneles planos, no un bug). Medido empiricamente:
  n=40 -> 1.66%, n=80 -> 0.85%, n=160 -> 0.43%, n=320 -> 0.22%.
Ver notas de sesion.
"""
import json
import math
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_BINARY = os.path.join(_HERE, "submotors", "bem_electromagnetic", "target", "release", "bem_electromagnetic")


def _circle_points(r, n):
    return [[r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)] for k in range(n)]


def _run_binary(payload, timeout_s):
    proc = subprocess.run(
        [_BINARY],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"submotor bem_electromagnetic fallo: {proc.stderr.strip()[:500]}")
    return json.loads(proc.stdout)


def _validate():
    """Caso coaxial mixto Dirichlet/Neumann a n=40 (rapido), contra la
    solucion analitica del capacitor cilindrico. Tolerancia con margen sobre
    el error medido empiricamente en esta resolucion (~1.66%)."""
    r_int, r_ext = 0.3, 1.0
    v_inner = 1.0
    n_per_circle = 40

    dphidn_inner = v_inner / (r_int * math.log(r_int / r_ext))
    sigma_analitico_inner = -dphidn_inner

    payload = {
        "mode": "electrostatics_2d",
        "conductors": [
            {"boundary": _circle_points(r_int, n_per_circle), "bc": {"type": "neumann", "value": dphidn_inner}},
            {"boundary": _circle_points(r_ext, n_per_circle), "bc": {"type": "dirichlet", "value": 0.0}},
        ],
        "eval_grid": None,
        "run_id": None,
    }
    result = _run_binary(payload, timeout_s=30)

    sigma_inner_bem = result["sigma"][0]
    rel_err = abs(sigma_inner_bem - sigma_analitico_inner) / abs(sigma_analitico_inner)
    tolerance = 0.03  # margen sobre el ~1.66% medido a n=40

    return {
        "mode": "validate",
        "check": "coaxial_mixed_bc_n40",
        "sigma_analitico_inner": sigma_analitico_inner,
        "sigma_bem_inner": sigma_inner_bem,
        "rel_err": rel_err,
        "tolerance": tolerance,
        "validation_passed": rel_err < tolerance,
    }


def compute_bem_electromagnetic(mode, params=None):
    params = params or {}

    if mode == "validate":
        return _validate()

    if mode != "electrostatics_2d":
        raise ValueError(f"mode desconocido: '{mode}'. Valores validos: electrostatics_2d, validate")

    if not os.path.isfile(_BINARY):
        raise FileNotFoundError(
            f"binario no encontrado en {_BINARY}. Correr 'cargo build --release' "
            f"en submotors/bem_electromagnetic/ primero."
        )

    run_id = params.get("run_id")
    payload = {
        "mode": mode,
        "conductors": params.get("conductors", []),
        "eval_grid": params.get("eval_grid"),
        "run_id": run_id,
    }

    result = _run_binary(payload, timeout_s=params.get("timeout_s", 60))

    if run_id:
        try:
            from workspace_tool import save_run
            save_run(
                run_id,
                {
                    "sigma": result["sigma"],
                    "panel_mid": result["panel_mid"],
                    "panel_potential": result["panel_potential"],
                    "grid": result.get("grid"),
                },
                {"tool": "bem_electromagnetic_tool", "mode": mode, "n_panels": result.get("n_panels")},
            )
            result["workspace_saved"] = True
        except Exception as e:
            result["workspace_saved"] = False
            result["workspace_save_error"] = str(e)

    return result


BEM_ELECTROMAGNETIC_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["electrostatics_2d", "validate"],
            "default": "electrostatics_2d",
        },
        "conductors": {
            "type": "array",
            "description": "Lista de conductores. Cada uno: {boundary: [[x,y],...] poligono cerrado, bc: {type: 'dirichlet'|'neumann', value: number}}.",
            "items": {
                "type": "object",
                "properties": {
                    "boundary": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                    "bc": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["dirichlet", "neumann"]},
                            "value": {"type": "number"},
                        },
                    },
                },
            },
        },
        "eval_grid": {
            "type": "object",
            "description": "Opcional: grilla 2D para evaluar potencial y campo (ex, ey).",
            "properties": {
                "x_min": {"type": "number"},
                "x_max": {"type": "number"},
                "y_min": {"type": "number"},
                "y_max": {"type": "number"},
                "nx": {"type": "integer"},
                "ny": {"type": "integer"},
            },
        },
        "run_id": {
            "type": "string",
            "description": "Si se indica, guarda sigma/panel_mid/panel_potential/grid en el workspace para graficar despues con plot_tool.",
        },
        "timeout_s": {"type": "integer", "default": 60},
    },
    "required": ["mode"],
}

try:
    from tool_registry import register_tool
    register_tool(
        name="bem_electromagnetic_tool",
        schema={
            "name": "bem_electromagnetic_tool",
            "description": "Electrostatica 2D via metodo de elementos de frontera (BEM), potencial de capa simple indirecto, con condiciones Dirichlet y Neumann por conductor (modo electrostatics_2d), delegando el ensamblado y el solver denso a un submotor Rust externo (subprocess+JSON). Validado contra el capacitor cilindrico: Dirichlet converge O(1/n^2) (~0.05%), Neumann converge O(1/n) (~0.85% a n=80) por el desajuste intrinseco de normal constante por panel recto.",
            "inputSchema": BEM_ELECTROMAGNETIC_TOOL_SCHEMA,
        },
        handler=lambda args: compute_bem_electromagnetic(args.get("mode"), args),
    )
except ImportError:
    pass
