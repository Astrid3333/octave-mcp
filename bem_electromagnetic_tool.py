"""
bem_electromagnetic_tool.py

Puente hacia el submotor Rust bem_electromagnetic (~/octave-mcp/submotors/bem_electromagnetic):
resuelve electrostatica 2D (ecuacion de Laplace, sin fuente de volumen) via
metodo de elementos de contorno (BEM), potencial de capa simple, sobre uno o
mas conductores con condicion Dirichlet (potencial fijo) o Neumann (derivada
normal fija). El binario hace el ensamblado (matriz densa via funcion de
Green 2D, cuadratura Gauss-16 + termino singular en forma cerrada) y el
solver LU denso; esta tool solo arma la entrada, invoca el binario, y
opcionalmente persiste el resultado en el workspace via
workspace_tool.save_run (mismo patron que fem_electromagnetic_tool), para
graficar despues con plot_tool.

A diferencia de fem_electromagnetic_tool, este submotor no requiere una
malla de volumen (distmesh_tool) -- la geometria de entrada es directamente
el contorno de cada conductor (lista de vertices, panel = segmento entre
vertices consecutivos, cerrado automaticamente).

Modo 'validate': 100% offline (no depende de red, a diferencia de
terrain_elevation_tool -- BEM es matematica pura), construye un conductor
cilindrico discretizado en poligono regular, con potencial V0 fijo, y
compara la solucion numerica contra la analitica conocida para el problema
exterior sin fuentes (derivacion: capa simple con densidad constante por
simetria circular, equivalente a una carga puntual en el centro para el
dominio exterior -- ver notas de sesion):

    phi(r) = V0 * ln(r) / ln(R),   r >= R   (requiere R != 1)

donde R es el radio del conductor. Corrido para n=40 y n=80 paneles, para
confirmar que el error cae al refinar la malla de contorno.
"""
import json
import math
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_BINARY = os.path.join(_HERE, "submotors", "bem_electromagnetic", "target", "release", "bem_electromagnetic")

_VALID_MODES = ["electrostatics_2d", "validate"]


def _run_binary(payload, timeout_s=60):
    if not os.path.isfile(_BINARY):
        raise FileNotFoundError(
            f"binario no encontrado en {_BINARY}. Correr 'cargo build --release' "
            f"en submotors/bem_electromagnetic/ primero."
        )
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


def _circle_boundary(radius, n, v0):
    boundary = [
        [radius * math.cos(2 * math.pi * k / n), radius * math.sin(2 * math.pi * k / n)]
        for k in range(n)
    ]
    return {"boundary": boundary, "bc": {"type": "dirichlet", "value": v0}}


def _potential_at_point(x, y, conductors):
    """1 punto de evaluacion via eval_grid degenerado (nx=1, ny=1): el
    binario ya maneja (nx-1).max(1) y (ny-1).max(1), asi que un grid de un
    solo punto no divide por cero."""
    out = _run_binary({
        "mode": "electrostatics_2d",
        "conductors": conductors,
        "eval_grid": {"x_min": x, "x_max": x, "y_min": y, "y_max": y, "nx": 1, "ny": 1},
        "run_id": None,
    })
    return out["grid"]["potential"][0]


def _validate():
    # Nota sobre los umbrales: BEM con paneles rectos aproximando un circulo
    # converge O(1/n^2) en el caso Dirichlet (a diferencia de Neumann, que
    # converge O(1/n) -- ver comentario en submotors/bem_electromagnetic/src/main.rs).
    # Por eso no se exige un umbral absoluto fijo en n=40 (una discretizacion
    # gruesa de un circulo en poligono todavia tiene error de faceta no
    # despreciable) -- se exige que el error absoluto en n=80 sea chico Y que
    # la razon de error n40/n80 sea consistente con orden 2 (~4x, con margen).
    checks = []
    radius = 2.0
    v0 = 1.0
    eval_r = [3.0, 4.0, 5.0, 10.0]
    max_err_by_n = {}

    for n in (40, 80):
        conductor = _circle_boundary(radius, n, v0)
        out = _run_binary({"mode": "electrostatics_2d", "conductors": [conductor], "eval_grid": None, "run_id": None})

        max_residual = max(abs(p - v0) for p in out["panel_potential"])
        checks.append({
            "nombre": f"residuo_bc_sobre_paneles_n{n}",
            "paso": max_residual < 1e-6,
            "detalle": {"max_residual": max_residual},
        })

        puntos = []
        max_err = 0.0
        for r in eval_r:
            analitico = v0 * math.log(r) / math.log(radius)
            numerico = _potential_at_point(r, 0.0, [conductor])
            err = abs(numerico - analitico)
            max_err = max(max_err, err)
            puntos.append({"r": r, "analitico": analitico, "numerico": numerico, "error_abs": err})
        max_err_by_n[n] = max_err

        checks.append({
            "nombre": f"comparacion_analitica_exterior_n{n}",
            "paso": max_err < (5e-3 if n == 80 else 2e-2),
            "detalle": {"max_error_abs": max_err, "puntos": puntos},
        })

    ratio = max_err_by_n[40] / max_err_by_n[80]
    checks.append({
        "nombre": "convergencia_orden_2_al_refinar",
        "paso": 2.5 < ratio < 6.0,
        "detalle": {"max_err_n40": max_err_by_n[40], "max_err_n80": max_err_by_n[80], "ratio": ratio},
    })

    todos_pasaron = all(c["paso"] for c in checks)
    return {"checks": checks, "todos_pasaron": todos_pasaron, "validation_passed": todos_pasaron}


def compute_bem_electromagnetic(mode, params=None):
    params = params or {}

    if mode not in _VALID_MODES:
        raise ValueError(f"mode desconocido: '{mode}'. Valores validos: {_VALID_MODES}")

    if mode == "validate":
        return _validate()

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
                    "panel_mid": result["panel_mid"],
                    "sigma": result["sigma"],
                    "panel_potential": result["panel_potential"],
                    "grid": result.get("grid"),
                },
                {"tool": "bem_electromagnetic_tool", "mode": mode},
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
            "enum": _VALID_MODES,
            "default": "electrostatics_2d",
        },
        "conductors": {
            "type": "array",
            "description": "Lista de conductores. Cada uno: boundary (vertices del contorno, poligono cerrado automaticamente) + bc (dirichlet: potencial fijo, o neumann: derivada normal fija).",
            "items": {
                "type": "object",
                "properties": {
                    "boundary": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                    },
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
            "description": "Grilla rectangular opcional para evaluar potencial y campo (Ex, Ey) fuera de los paneles, pensada para graficar con plot_tool.",
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
            "description": "Si se indica, guarda paneles/potencial/grilla en el workspace para graficar despues con plot_tool.",
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
            "description": "Electromagnetismo via BEM (metodo de elementos de contorno): resuelve electrostatica 2D (ecuacion de Laplace) sobre uno o mas conductores con potencial fijo (Dirichlet) o flujo fijo (Neumann), discretizando solo el contorno (no el volumen). Delega el ensamblado (matriz densa, funcion de Green 2D) y el solver LU a un submotor Rust externo (subprocess+JSON). Modo 'validate' corre offline contra la solucion analitica de un conductor cilindrico cargado.",
            "inputSchema": BEM_ELECTROMAGNETIC_TOOL_SCHEMA,
        },
        handler=lambda args: compute_bem_electromagnetic(args.get("mode"), args),
    )
except ImportError:
    pass
