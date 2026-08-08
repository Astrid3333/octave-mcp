"""
lyapunov_tool.py

Módulo para octave-mcp: calcula el exponente de Lyapunov máximo (λ1)
de un sistema dinámico definido por el usuario, vía integración RK4
paralela + renormalización periódica, ejecutado en Octave.

INTEGRACIÓN EN octave_mcp.py (patrón FastMCP, igual que biosim-mcp/psyche-mcp):

    from lyapunov_tool import compute_lyapunov_exponent, LYAPUNOV_TOOL_SCHEMA

    # 1) Registrar el schema en la lista de types.Tool (o el decorador @mcp.tool
    #    si tu servidor usa FastMCP puro):
    #
    #    @mcp.tool()
    #    async def compute_lyapunov_exponent(...) -> dict:
    #        return compute_lyapunov_exponent(...)
    #
    # 2) Si tu servidor usa el patrón allowlist (como freecad_mcp_server.py,
    #    ~línea 2757: `elif name in [...]`), agregar "compute_lyapunov_exponent"
    #    tanto al bloque de schema como al allowlist. Con FastMCP el decorador
    #    ya resuelve el registro, no hace falta el allowlist manual.

PRESETS incluidos: chen_lee, burke_shaw, lorenz, rossler, custom (ecuaciones
libres en sintaxis Octave, con variables y(1), y(2), y(3), ...).
"""

import subprocess
import tempfile
import os
import re
from textwrap import dedent
import numpy as np
from workspace_tool import save_run

# --- Sistemas predefinidos (ya usados en tu trabajo de TritOS) ---
PRESET_SYSTEMS = {
    "chen_lee": {
        "params": {"a": 5.0, "b": -10.0, "c": -0.38},
        "equations": (
            "a*y(1) - y(2)*y(3); "
            "b*y(2) + y(1)*y(3); "
            "c*y(3) + y(1)*y(2)/3"
        ),
        "default_y0": [1.0, 1.0, 1.0],
        "default_dt": 0.01,
    },
    "burke_shaw": {
        "params": {"a": 10.0, "b": 4.272},
        "equations": (
            "-a*(y(1)+y(2)); "
            "-y(2)-a*y(1)*y(3); "
            "a*y(1)*y(2)+b"
        ),
        "default_y0": [1.0, 1.0, 1.0],
        "default_dt": 0.005,
    },
    "lorenz": {
        "params": {"sigma": 10.0, "rho": 28.0, "beta": 8.0 / 3.0},
        "equations": (
            "sigma*(y(2)-y(1)); "
            "y(1)*(rho-y(3))-y(2); "
            "y(1)*y(2)-beta*y(3)"
        ),
        "default_y0": [1.0, 1.0, 1.0],
        "default_dt": 0.01,
    },
    "rossler": {
        "params": {"a": 0.2, "b": 0.2, "c": 5.7},
        "equations": (
            "-y(2)-y(3); "
            "y(1)+a*y(2); "
            "b+y(3)*(y(1)-c)"
        ),
        "default_y0": [1.0, 1.0, 1.0],
        "default_dt": 0.02,
    },
}

_VALID_OCTAVE_TOKEN = re.compile(r"^[a-zA-Z0-9_\.\+\-\*/\(\)\[\]\s,;:^]+$")


def _sanitize_expr(expr: str) -> str:
    """Whitelist básico para evitar inyección en el script .m generado."""
    if not _VALID_OCTAVE_TOKEN.match(expr):
        raise ValueError(
            "La expresión contiene caracteres no permitidos. "
            "Solo se admiten operadores matemáticos, y(i), nombres de parámetros."
        )
    return expr


def compute_lyapunov_exponent(
    system: str = "chen_lee",
    custom_equations: str | None = None,
    custom_params: dict | None = None,
    y0: list[float] | None = None,
    dt: float | None = None,
    n_steps: int = 20000,
    d0: float = 1e-8,
    octave_bin: str = "octave",
    timeout_s: int = 60,
    run_id: str | None = None,
    save_trajectory_every: int = 10,
) -> dict:
    """
    Calcula el exponente de Lyapunov máximo (λ1) de un sistema dinámico.

    Args:
        system: uno de "chen_lee", "burke_shaw", "lorenz", "rossler", "custom".
        custom_equations: si system="custom", string Octave con las ecuaciones
            separadas por ';' usando y(1), y(2), y(3)... y los nombres en
            custom_params. Ej: "sigma*(y(2)-y(1)); y(1)*(rho-y(3))-y(2); y(1)*y(2)-beta*y(3)"
        custom_params: dict {nombre: valor} de parámetros usados en custom_equations.
        y0: condición inicial (por defecto, la del preset).
        dt: paso de integración RK4 (por defecto, el del preset).
        n_steps: cantidad de pasos de integración + renormalización.
        d0: separación inicial entre trayectorias vecinas.
        octave_bin: ejecutable de Octave (por si usás un path custom).
        timeout_s: timeout del subprocess.

    Returns:
        dict con lambda1, interpretacion, y metadatos de la corrida.
    """
    if system == "custom":
        if not custom_equations:
            raise ValueError("system='custom' requiere custom_equations.")
        equations = _sanitize_expr(custom_equations)
        params = custom_params or {}
        y0 = y0 or [1.0, 1.0, 1.0]
        dt = dt or 0.01
    else:
        if system not in PRESET_SYSTEMS:
            raise ValueError(
                f"system debe ser uno de {list(PRESET_SYSTEMS)} o 'custom'."
            )
        preset = PRESET_SYSTEMS[system]
        equations = preset["equations"]
        params = {**preset["params"], **(custom_params or {})}
        y0 = y0 or preset["default_y0"]
        dt = dt or preset["default_dt"]

    param_assignments = "\n".join(f"{k} = {v};" for k, v in params.items())
    y0_str = "[" + "; ".join(str(v) for v in y0) + "]"

    traj_path = None
    TRAJ_INIT = ""
    TRAJ_STEP = ""
    TRAJ_SAVE = ""
    if run_id:
        traj_fd, traj_path = tempfile.mkstemp(suffix=".txt")
        os.close(traj_fd)
        traj_path_octave = traj_path.replace("\\", "/")
        TRAJ_INIT = (
            f"traj = zeros(ceil(N/{save_trajectory_every})+1, dim);\n"
            "        traj(1,:) = y';\n"
            "        traj_idx = 1;"
        )
        TRAJ_STEP = (
            f"if mod(i, {save_trajectory_every}) == 0\n"
            "            traj_idx++;\n"
            "            traj(traj_idx,:) = y';\n"
            "          endif"
        )
        TRAJ_SAVE = (
            "traj = traj(1:traj_idx,:);\n"
            f"        save('-ascii', '{traj_path_octave}', 'traj');"
        )

    script = dedent(f"""
        1;
        {param_assignments}
        f = @(t,y) [{equations}];

        y0 = {y0_str};
        dt = {dt};
        N = {n_steps};
        d0 = {d0};

        y = y0(:);
        dim = numel(y);
        y2 = y + [d0; zeros(dim-1,1)];
        sum_log = 0;
        n_renorm = 0;
        {TRAJ_INIT}

        for i = 1:N
          k1=f(0,y);        k1b=f(0,y2);
          k2=f(0,y+dt/2*k1); k2b=f(0,y2+dt/2*k1b);
          k3=f(0,y+dt/2*k2); k3b=f(0,y2+dt/2*k2b);
          k4=f(0,y+dt*k3);   k4b=f(0,y2+dt*k3b);
          y  = y  + dt/6*(k1+2*k2+2*k3+k4);
          y2 = y2 + dt/6*(k1b+2*k2b+2*k3b+k4b);
          d = norm(y2-y);
          if d > 0
            sum_log = sum_log + log(d/d0);
            n_renorm++;
            y2 = y + (y2-y)*(d0/d);
          endif
          {TRAJ_STEP}
        end
        {TRAJ_SAVE}

        lambda1 = sum_log / (n_renorm*dt);
        printf('LAMBDA1=%.10f\\n', lambda1);
        printf('N_RENORM=%d\\n', n_renorm);
        printf('Y_FINAL=%.6f,%.6f,%.6f\\n', y(1), y(2), y(3));
    """).strip()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".m", delete=False, dir=tempfile.gettempdir()
    ) as tf:
        tf.write(script)
        script_path = tf.name

    try:
        result = subprocess.run(
            [octave_bin, "--no-gui", "-q", script_path],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    finally:
        os.unlink(script_path)

    if result.returncode != 0:
        if traj_path and os.path.exists(traj_path):
            os.unlink(traj_path)
        return {
            "error": "Octave devolvió un error.",
            "stderr": result.stderr.strip(),
            "stdout": result.stdout.strip(),
        }

    out = result.stdout
    lambda1_match = re.search(r"LAMBDA1=([-\d.]+)", out)
    n_renorm_match = re.search(r"N_RENORM=(\d+)", out)
    y_final_match = re.search(r"Y_FINAL=([-\d.,]+)", out)

    if not lambda1_match:
        if traj_path and os.path.exists(traj_path):
            os.unlink(traj_path)
        return {"error": "No se pudo parsear la salida de Octave.", "stdout": out}

    lambda1 = float(lambda1_match.group(1))

    if lambda1 > 0.01:
        interpretacion = "Caótico (sensibilidad exponencial a condiciones iniciales)"
    elif lambda1 < -0.01:
        interpretacion = "Estable / convergente (atractor de punto fijo o ciclo)"
    else:
        interpretacion = "Marginal (posible órbita periódica o cuasi-periódica)"

    trajectory_saved = False
    saved_run_id = None
    if traj_path and os.path.exists(traj_path):
        try:
            traj_data = np.loadtxt(traj_path)
            if traj_data.ndim == 1:
                traj_data = traj_data.reshape(1, -1)
            save_result = save_run(
                run_id,
                {"trayectoria": traj_data},
                {
                    "tool": "compute_lyapunov_exponent",
                    "system": system,
                    "params": params,
                    "y0": y0,
                    "dt": dt,
                    "n_steps": n_steps,
                    "save_trajectory_every": save_trajectory_every,
                    "lambda1": lambda1,
                },
            )
            saved_run_id = save_result.get("run_id")
            trajectory_saved = "error" not in save_result
        finally:
            os.unlink(traj_path)

    return {
        "lambda1": lambda1,
        "interpretacion": interpretacion,
        "system": system,
        "params": params,
        "y0": y0,
        "dt": dt,
        "n_steps": n_steps,
        "n_renorm_effective": int(n_renorm_match.group(1)) if n_renorm_match else None,
        "y_final": [float(v) for v in y_final_match.group(1).split(",")]
        if y_final_match
        else None,
        "trajectory_saved": trajectory_saved,
        "run_id": saved_run_id,
    }


# --- Schema para registro manual (patrón types.Tool / allowlist) ---
LYAPUNOV_TOOL_SCHEMA = {
    "name": "compute_lyapunov_exponent",
    "description": (
        "Calcula el exponente de Lyapunov máximo (λ1) de un sistema dinámico "
        "(presets: chen_lee, burke_shaw, lorenz, rossler, o ecuaciones custom) "
        "para cuantificar caos. λ1>0 confirma comportamiento caótico."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "system": {
                "type": "string",
                "enum": ["chen_lee", "burke_shaw", "lorenz", "rossler", "custom"],
                "default": "chen_lee",
            },
            "custom_equations": {
                "type": "string",
                "description": "Solo si system='custom'. Ecuaciones Octave separadas por ';', usando y(1),y(2),y(3).",
            },
            "custom_params": {"type": "object", "description": "Override de parámetros del preset, o params del sistema custom."},
            "y0": {"type": "array", "items": {"type": "number"}},
            "dt": {"type": "number"},
            "n_steps": {"type": "integer", "default": 20000},
            "d0": {"type": "number", "default": 1e-8},
            "run_id": {
                "type": "string",
                "description": "Si se indica, guarda la trayectoria completa en el workspace bajo este run_id (para graficar despues con plot_tool).",
            },
            "save_trajectory_every": {
                "type": "integer",
                "default": 10,
                "description": "Guardar 1 de cada N pasos de la trayectoria (solo si run_id esta presente).",
            },
        },
        "required": [],
    },
}


if __name__ == "__main__":
    # Prueba rápida standalone
    for sys_name in ("chen_lee", "burke_shaw", "lorenz", "rossler"):
        r = compute_lyapunov_exponent(system=sys_name, n_steps=15000)
        print(sys_name, "->", r.get("lambda1"), "|", r.get("interpretacion"))
