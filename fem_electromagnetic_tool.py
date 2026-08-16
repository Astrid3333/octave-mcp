"""
fem_electromagnetic_tool.py

Puente hacia el submotor Rust fem_poisson2d (~/octave-mcp/submotors/fem_poisson2d):
resuelve la ecuacion de Poisson 2D (electrostatica) sobre malla triangular P1,
via subprocess + JSON. El binario hace el ensamblado FEM y el solver CG; esta
tool solo arma la entrada, invoca el binario, y opcionalmente persiste el
resultado en el workspace via workspace_tool.save_run (mismo patron que
statmech_partition_tool.temperature_sweep) para graficar despues con plot_tool.

Validado contra caso analitico phi(x,y)=x (Dirichlet lineal, fuente=0):
error maximo ~5e-10 en malla 11x11, ver notas de sesion.
"""
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_BINARY = os.path.join(_HERE, "submotors", "fem_poisson2d", "target", "release", "fem_poisson2d")


def compute_fem_electromagnetic(mode, params=None):
    params = params or {}

    if mode != "poisson_2d":
        raise ValueError(f"mode desconocido: '{mode}'. Valores validos: poisson_2d")

    if not os.path.isfile(_BINARY):
        raise FileNotFoundError(
            f"binario no encontrado en {_BINARY}. Correr 'cargo build --release' "
            f"en submotors/fem_poisson2d/ primero."
        )

    run_id = params.get("run_id")
    payload = {
        "mode": mode,
        "geometry": params.get("geometry", {}),
        "boundary_conditions": params.get("boundary_conditions", []),
        "source": params.get("source", {"type": "constant", "value": 0.0}),
        "run_id": run_id,
    }

    proc = subprocess.run(
        [_BINARY],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=params.get("timeout_s", 60),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"submotor fem_poisson2d fallo: {proc.stderr.strip()[:500]}")

    result = json.loads(proc.stdout)

    if run_id:
        try:
            from workspace_tool import save_run
            save_run(
                run_id,
                {
                    "nodes": result["mesh"]["nodes"],
                    "triangles": result["mesh"]["triangles"],
                    "potential": result["potential"],
                },
                {"tool": "fem_electromagnetic_tool", "mode": mode},
            )
            result["workspace_saved"] = True
        except Exception as e:
            result["workspace_saved"] = False
            result["workspace_save_error"] = str(e)

    return result


FEM_ELECTROMAGNETIC_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["poisson_2d"],
            "default": "poisson_2d",
        },
        "geometry": {
            "type": "object",
            "description": "Rectangulo con grilla estructurada nx*ny.",
            "properties": {
                "type": {"type": "string", "enum": ["rectangle"], "default": "rectangle"},
                "width": {"type": "number", "default": 1.0},
                "height": {"type": "number", "default": 1.0},
                "nx": {"type": "integer", "default": 20},
                "ny": {"type": "integer", "default": 20},
            },
        },
        "boundary_conditions": {
            "type": "array",
            "description": "Lista de condiciones por borde (left/right/top/bottom).",
            "items": {
                "type": "object",
                "properties": {
                    "edge": {"type": "string", "enum": ["left", "right", "top", "bottom"]},
                    "type": {"type": "string", "enum": ["dirichlet", "neumann"]},
                    "value": {"type": "number"},
                },
            },
        },
        "source": {
            "type": "object",
            "description": "Termino fuente (densidad de carga) del lado derecho de Poisson.",
            "properties": {
                "type": {"type": "string", "enum": ["constant"], "default": "constant"},
                "value": {"type": "number", "default": 0.0},
            },
        },
        "run_id": {
            "type": "string",
            "description": "Si se indica, guarda mesh/potential en el workspace para graficar despues con plot_tool.",
        },
        "timeout_s": {"type": "integer", "default": 60},
    },
    "required": ["mode"],
}

try:
    from tool_registry import register_tool
    register_tool(
        name="fem_electromagnetic_tool",
        schema={
            "name": "fem_electromagnetic_tool",
            "description": "Electromagnetismo via FEM: resuelve la ecuacion de Poisson 2D (electrostatica) sobre malla triangular P1 (modo poisson_2d), delegando el ensamblado y el solver CG a un submotor Rust externo (subprocess+JSON) para evitar dependencias numericas pesadas en el venv principal.",
            "inputSchema": FEM_ELECTROMAGNETIC_TOOL_SCHEMA,
        },
        handler=lambda args: compute_fem_electromagnetic(args.get("mode"), args),
    )
except ImportError:
    pass
