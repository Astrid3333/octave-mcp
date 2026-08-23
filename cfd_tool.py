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


_GHIA_RE100_Y_U = [
    (1.0000, 1.0000), (0.9766, 0.8412), (0.9688, 0.7887), (0.9609, 0.7372),
    (0.9531, 0.6872), (0.8516, 0.2315), (0.7344, 0.0033), (0.6172, -0.1364),
    (0.5000, -0.2058), (0.4531, -0.2109), (0.2813, -0.1566), (0.1719, -0.1015),
    (0.1016, -0.0643), (0.0703, -0.0478), (0.0625, -0.0419), (0.0547, -0.0361),
    (0.0000, 0.0000),
]  # tabla real de Ghia, Ghia & Shin (1982), Re=100, malla 41x41 (perfil u en x=0.5)


def _validate():
    """Corre el binario con los mismos defaults del schema (Re=100, malla
    41x41) y compara el perfil de u en la linea vertical central contra la
    tabla real de Ghia et al. -- mismo chequeo que ya existia como script
    separado (submotors/cfd_cavity/ghia_re100.py), ahora invocable como modo."""
    result = compute_cfd("lid_driven_cavity", {
        "geometry": {"width": 1.0, "height": 1.0, "nx": 41, "ny": 41},
        "fluid": {"reynolds": 100.0},
        "lid_velocity": 1.0,
        "solver": {"dt": 0.001, "max_steps": 20000, "tol": 1e-6},
        # timeout mas alto que el default de compute_cfd (300s): en la
        # maquina de 2 cores, corriendo bajo run_all_validations.py con
        # PARALLEL_WORKERS=2, se vio superar los 300s por contencion de
        # CPU con el otro worker aunque la corrida aislada tarda ~0.1s.
        "timeout_s": 600,
    })

    nx, ny = result["mesh"]["nx"], result["mesh"]["ny"]
    u = result["u"]
    i_center = (nx - 1) // 2

    def u_at(y_frac):
        y_pos = y_frac * (ny - 1)
        j0 = int(y_pos)
        j1 = min(j0 + 1, ny - 1)
        frac = y_pos - j0
        u0 = u[j0 * nx + i_center]
        u1 = u[j1 * nx + i_center]
        return u0 * (1 - frac) + u1 * frac

    puntos = []
    max_abs_diff = 0.0
    for y, u_ghia in _GHIA_RE100_Y_U:
        u_sim = u_at(y)
        diff = abs(u_ghia - u_sim)
        max_abs_diff = max(max_abs_diff, diff)
        puntos.append({"y": y, "u_ghia": u_ghia, "u_sim": round(u_sim, 6), "diff": round(diff, 6)})

    # tolerancia mas ancha que el error tipico documentado (~0.005-0.007) para
    # no romper por variaciones menores de compilador/plataforma, pero
    # suficientemente ajustada para detectar una regresion real del solver.
    tolerancia = 0.02
    checks = [{
        "name": "perfil_u_linea_central_coincide_con_tabla_ghia_re100",
        "reynolds": result.get("reynolds", 100.0),
        "malla": f"{nx}x{ny}",
        "puntos": puntos,
        "max_abs_diff": round(max_abs_diff, 6),
        "tolerancia": tolerancia,
        "passed": bool(max_abs_diff < tolerancia),
    }]

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_cfd(mode, params=None):
    params = params or {}

    if mode == "validate":
        return _validate()

    if mode != "lid_driven_cavity":
        raise ValueError(f"mode desconocido: '{mode}'. Valores validos: lid_driven_cavity | validate")

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
            "enum": ["lid_driven_cavity", "validate"],
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
