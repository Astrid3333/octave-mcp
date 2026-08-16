"""
cfd_tool.py

Puente hacia el submotor Rust cfd_cavity (~/octave-mcp/submotors/cfd_cavity):
resuelve la cavidad con tapa deslizante (lid-driven cavity) via formulacion
funcion de corriente-vorticidad, discretizada por diferencias finitas con
gradiente conjugado disperso (mismo stack sprs/ndarray que fem_poisson2d) y
formula de Thom para la vorticidad de pared. El binario hace todo el trabajo
numerico; esta tool solo arma la entrada, invoca el binario, y opcionalmente
persiste el resultado en el workspace via workspace_tool.save_run (mismo
patron que fem_electromagnetic_tool) para graficar despues con plot_tool.

Validado contra la tabla de Ghia, Ghia & Shin (1982) para Re=100: diferencias
absolutas maximas ~0.005-0.007 en el perfil de u de la linea vertical central,
sobre malla 41x41 (consistente con el error de discretizacion esperado para
esa resolucion). Ver notas de sesion.
"""
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_BINARY = os.path.join(_HERE, "submotors", "cfd_cavity", "target", "release", "cfd_cavity")


def compute_cfd(mode, params=None):
    params = params or {}

    if mode != "lid_driven_cavity":
        raise ValueError(f"mode desconocido: '{mode}'. Valores validos: lid_driven_cavity")

    if not os.path.isfile(_BINARY):
        raise FileNotFoundError(
            f"binario no encontrado en {_BINARY}. Correr 'cargo build --release' "
            f"en submotors/cfd_cavity/ primero."
        )

    run_id = params.get("run_id")
    payload = {
        "mode": mode,
        "geometry": params.get("geometry", {}),
        "fluid": params.get("fluid", {}),
        "lid_velocity": params.get("lid_velocity", 1.0),
        "solver": params.get("solver", {}),
        "run_id": run_id,
    }

    proc = subprocess.run(
        [_BINARY],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        # CFD explicito puede tardar bastante mas que Poisson (miles de pasos,
        # cada uno con un CG interno) -- default mas alto que fem_electromagnetic_tool.
        timeout=params.get("timeout_s", 300),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"submotor cfd_cavity fallo: {proc.stderr.strip()[:500]}")

    result = json.loads(proc.stdout)

    if run_id:
        try:
            from workspace_tool import save_run
            save_run(
                run_id,
                {
                    "u": result["u"],
                    "v": result["v"],
                    "psi": result["psi"],
                    "omega": result["omega"],
                    "mesh": result["mesh"],
                },
                {"tool": "cfd_tool", "mode": mode, "reynolds": result.get("reynolds")},
            )
            result["workspace_saved"] = True
        except Exception as e:
            result["workspace_saved"] = False
            result["workspace_save_error"] = str(e)

    return result


CFD_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["lid_driven_cavity"],
            "default": "lid_driven_cavity",
        },
        "geometry": {
            "type": "object",
            "description": "Cavidad rectangular con grilla estructurada nx*ny.",
            "properties": {
                "width": {"type": "number", "default": 1.0},
                "height": {"type": "number", "default": 1.0},
                "nx": {"type": "integer", "default": 41},
                "ny": {"type": "integer", "default": 41},
            },
        },
        "fluid": {
            "type": "object",
            "properties": {
                "reynolds": {"type": "number", "default": 100.0},
            },
        },
        "lid_velocity": {
            "type": "number",
            "default": 1.0,
            "description": "Velocidad tangencial de la tapa deslizante.",
        },
        "solver": {
            "type": "object",
            "properties": {
                "dt": {"type": "number", "default": 0.001},
                "max_steps": {"type": "integer", "default": 20000},
                "tol": {"type": "number", "default": 1e-6},
            },
        },
        "run_id": {
            "type": "string",
            "description": "Si se indica, guarda u/v/psi/omega/mesh en el workspace para graficar despues con plot_tool.",
        },
        "timeout_s": {"type": "integer", "default": 300},
    },
    "required": ["mode"],
}

try:
    from tool_registry import register_tool
    register_tool(
        name="cfd_tool",
        schema={
            "name": "cfd_tool",
            "description": "Dinamica de fluidos computacional: resuelve la cavidad con tapa deslizante (lid-driven cavity) via formulacion funcion de corriente-vorticidad, diferencias finitas y gradiente conjugado disperso (modo lid_driven_cavity), delegando el ensamblado y el solver a un submotor Rust externo (subprocess+JSON) para evitar dependencias numericas pesadas en el venv principal. Validado contra la tabla de Ghia, Ghia & Shin (1982) para Re=100.",
            "inputSchema": CFD_TOOL_SCHEMA,
        },
        handler=lambda args: compute_cfd(args.get("mode"), args),
    )
except ImportError:
    pass
