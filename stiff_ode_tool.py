"""
stiff_ode_tool.py

Módulo para octave-mcp: integra sistemas de ODEs (rígidos o no) usando
los solvers implícitos de Octave (ode15s, ode23s) o lsode (ODEPACK,
conmuta automáticamente entre stiff/no-stiff). Pensado para sistemas
donde RK4/ode45 se vuelve prohibitivamente lento (constantes de tiempo
muy dispares, reacciones químicas rápidas + lentas, etc).

INTEGRACIÓN EN server.py (mismo patrón que lyapunov_tool.py):

    from stiff_ode_tool import integrate_stiff_ode, STIFF_ODE_TOOL_SCHEMA

    TOOLS.append(STIFF_ODE_TOOL_SCHEMA)
    # y en el dispatcher tools/call:
    elif tool_name == "integrate_stiff_ode":
        result = integrate_stiff_ode(**args)
        resp = {...}

PRESETS incluidos: van_der_pol (stiff clásico), robertson (reacción
química rígida de libro de texto), custom (ecuaciones libres).
"""

import subprocess
import tempfile
import os
import re
from textwrap import dedent

PRESET_SYSTEMS = {
    "van_der_pol": {
        "params": {"mu": 1000.0},
        "equations": "y(2); mu*(1-y(1)^2)*y(2) - y(1)",
        "default_y0": [2.0, 0.0],
        "default_tspan": [0.0, 3000.0],
    },
    "robertson": {
        # Clasico problema stiff de cinetica quimica (Robertson 1966):
        # A->B (lenta), B+B->C+B (muy rapida), B+C->A+C (moderada)
        "params": {"k1": 0.04, "k2": 3e7, "k3": 1e4},
        "equations": (
            "-k1*y(1) + k3*y(2)*y(3); "
            "k1*y(1) - k3*y(2)*y(3) - k2*y(2)^2; "
            "k2*y(2)^2"
        ),
        "default_y0": [1.0, 0.0, 0.0],
        "default_tspan": [0.0, 4e5],
    },
}

_VALID_OCTAVE_TOKEN = re.compile(r"^[a-zA-Z0-9_\.\+\-\*/\(\)\[\]\s,;:^]+$")


def _sanitize_expr(expr: str) -> str:
    if not _VALID_OCTAVE_TOKEN.match(expr):
        raise ValueError(
            "La expresión contiene caracteres no permitidos. "
            "Solo se admiten operadores matemáticos, y(i), nombres de parámetros."
        )
    return expr


def integrate_stiff_ode(
    system: str = "van_der_pol",
    custom_equations: str | None = None,
    custom_params: dict | None = None,
    y0: list[float] | None = None,
    tspan: list[float] | None = None,
    solver: str = "ode15s",
    n_output_points: int = 50,
    rel_tol: float = 1e-6,
    abs_tol: float = 1e-8,
    octave_bin: str = "octave",
    timeout_s: int = 60,
    mode: str | None = None,
    **kwargs,
) -> dict:
    """
    Integra un sistema de ODEs (potencialmente rígido) con un solver implícito.

    Args:
        system: "van_der_pol", "robertson", o "custom".
        custom_equations: si system="custom", ecuaciones Octave separadas por ';'.
        custom_params: dict {nombre: valor}; override de preset o params de custom.
        y0: condición inicial (por defecto, la del preset).
        tspan: [t0, tfin] (por defecto, el del preset).
        solver: "ode15s" (BDF/NDF, recomendado), "ode23s" (Rosenbrock,
            bueno para muy stiff / discontinuidades), o "lsode" (ODEPACK,
            conmuta automático stiff/no-stiff).
        n_output_points: cantidad de puntos a devolver (muestreados uniformemente).
        rel_tol / abs_tol: tolerancias del integrador.

    Returns:
        dict con t, y (lista de listas), solver usado, y metadatos.
    """
    if mode == "validate":
        return _validate_stiff_ode(octave_bin=octave_bin, timeout_s=timeout_s)

    if solver not in ("ode15s", "ode23s", "lsode"):
        raise ValueError("solver debe ser 'ode15s', 'ode23s' o 'lsode'.")

    if system == "custom":
        if not custom_equations:
            raise ValueError("system='custom' requiere custom_equations.")
        equations = _sanitize_expr(custom_equations)
        params = custom_params or {}
        y0 = y0 or [1.0, 0.0]
        tspan = tspan or [0.0, 10.0]
    else:
        if system not in PRESET_SYSTEMS:
            raise ValueError(f"system debe ser uno de {list(PRESET_SYSTEMS)} o 'custom'.")
        preset = PRESET_SYSTEMS[system]
        equations = preset["equations"]
        params = {**preset["params"], **(custom_params or {})}
        y0 = y0 or preset["default_y0"]
        tspan = tspan or preset["default_tspan"]

    param_assignments = "\n".join(f"{k} = {v};" for k, v in params.items())
    y0_str = "[" + "; ".join(str(v) for v in y0) + "]"
    t_out_str = f"linspace({tspan[0]}, {tspan[1]}, {n_output_points})"

    if solver in ("ode15s", "ode23s"):
        script = dedent(f"""
            1;
            {param_assignments}
            f = @(t,y) [{equations}];
            y0 = {y0_str};
            t_out = {t_out_str};
            opts = odeset('RelTol',{rel_tol},'AbsTol',{abs_tol},'InitialStep',1e-6);
            sol = {solver}(f, [{tspan[0]}, {tspan[1]}], y0, opts);
            n_dims_out = numel(y0);
            Yi = zeros(n_dims_out, numel(t_out));
            for i_dim = 1:n_dims_out
              Yi(i_dim,:) = interp1(sol.x, sol.y(i_dim,:), t_out);
            end
            printf('T_OUT=');
            printf('%.6g,', t_out);
            printf('\\n');
            printf('Y_OUT=');
            for i = 1:rows(Yi)
              printf('%.6g,', Yi(i,:));
              printf(';');
            end
            printf('\\n');
            printf('N_STEPS=%d\\n', numel(sol.x));
        """).strip()
    else:  # lsode
        script = dedent(f"""
            1;
            {param_assignments}
            f = @(y,t) [{equations}];
            y0 = {y0_str};
            t_out = {t_out_str};
            lsode_options('relative tolerance', {rel_tol});
            lsode_options('absolute tolerance', {abs_tol});
            Y = lsode(f, y0, t_out);
            printf('T_OUT=');
            printf('%.6g,', t_out);
            printf('\\n');
            printf('Y_OUT=');
            for i = 1:columns(Y)
              printf('%.6g,', Y(:,i));
              printf(';');
            end
            printf('\\n');
            printf('N_STEPS=%d\\n', numel(t_out));
        """).strip()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".m", delete=False, dir=tempfile.gettempdir()
    ) as tf:
        tf.write(script)
        script_path = tf.name

    try:
        result = subprocess.run(
            [octave_bin, "--no-gui", "-q", script_path],
            capture_output=True, text=True, timeout=timeout_s,
        )
    finally:
        os.unlink(script_path)

    if result.returncode != 0:
        return {"error": "Octave devolvió un error.", "stderr": result.stderr.strip(), "stdout": result.stdout.strip()}

    out = result.stdout
    t_match = re.search(r"T_OUT=([\d.,eE+\-]+)", out)
    y_match = re.search(r"Y_OUT=(.+)", out)
    n_steps_match = re.search(r"N_STEPS=(\d+)", out)

    if not t_match or not y_match:
        return {"error": "No se pudo parsear la salida de Octave.", "stdout": out}

    t_vals = [float(v) for v in t_match.group(1).strip(",").split(",")]
    y_rows_raw = y_match.group(1).strip(";").split(";")
    y_vals = [
        [float(v) for v in row.strip(",").split(",")]
        for row in y_rows_raw if row.strip()
    ]

    return {
        "t": t_vals,
        "y": y_vals,  # y[i] = trayectoria de la componente i en cada t
        "solver": solver,
        "system": system,
        "params": params,
        "y0": y0,
        "tspan": tspan,
        "n_internal_steps": int(n_steps_match.group(1)) if n_steps_match else None,
        "nota": (
            "y[0] es la primera componente, y[1] la segunda, etc, cada una "
            "muestreada en los mismos n_output_points tiempos de 't'."
        ),
    }


def _validate_stiff_ode(octave_bin: str = "octave", timeout_s: int = 60):
    """
    Autochequeo con dos sistemas custom de solucion analitica exacta,
    probando los dos solvers implicitos principales:
    - decaimiento exponencial y'=-k*y (solver ode15s): y(t) = y0*exp(-k*t).
    - oscilador armonico y1'=y2, y2'=-w^2*y1 (solver lsode): y1(t) = cos(w*t),
      con y0=[1,0].
    Ambos evaluados contra la formula cerrada en el ultimo punto de la
    malla de salida (que coincide exacto con tspan[1] via linspace).
    """
    import math

    checks = []
    tol = 0.01

    # --- decaimiento exponencial, ode15s ---
    k = 0.7
    y0_1 = 2.0
    tspan1 = [0.0, 3.0]
    r1 = integrate_stiff_ode(
        system="custom", custom_equations="-k*y(1)", custom_params={"k": k},
        y0=[y0_1], tspan=tspan1, solver="ode15s", n_output_points=50,
        octave_bin=octave_bin, timeout_s=timeout_s,
    )
    if "error" in r1:
        ok1, got1 = False, r1.get("error")
    else:
        t_final = r1["t"][-1]
        y_final = r1["y"][0][-1]
        expected = y0_1 * math.exp(-k * t_final)
        ok1 = abs(y_final - expected) < tol
        got1 = f"y_final={y_final:.6g} vs esperado={expected:.6g}"
    checks.append({
        "name": "custom y'=-0.7*y (ode15s): decaimiento exponencial vs formula cerrada y0*exp(-k*t)",
        "passed": ok1, "got": got1,
    })

    # --- oscilador armonico, lsode ---
    w = 2.0
    tspan2 = [0.0, 1.5]
    r2 = integrate_stiff_ode(
        system="custom", custom_equations="y(2); -w2*y(1)", custom_params={"w2": w ** 2},
        y0=[1.0, 0.0], tspan=tspan2, solver="lsode", n_output_points=50,
        octave_bin=octave_bin, timeout_s=timeout_s,
    )
    if "error" in r2:
        ok2, got2 = False, r2.get("error")
    else:
        t_final2 = r2["t"][-1]
        y_final2 = r2["y"][0][-1]
        expected2 = math.cos(w * t_final2)
        ok2 = abs(y_final2 - expected2) < tol
        got2 = f"y1_final={y_final2:.6g} vs esperado={expected2:.6g}"
    checks.append({
        "name": "custom oscilador armonico w=2 (lsode): y1(t) vs cos(w*t)",
        "passed": ok2, "got": got2,
    })

    return {"mode": "validate", "validation_passed": bool(all(c["passed"] for c in checks)), "checks": checks}


STIFF_ODE_TOOL_SCHEMA = {
    "name": "integrate_stiff_ode",
    "description": (
        "Integra un sistema de ecuaciones diferenciales ordinarias, incluyendo "
        "sistemas rígidos/stiff (donde métodos explícitos como ode45/RK4 son "
        "extremadamente lentos), usando solvers implícitos de Octave (ode15s, "
        "ode23s) o lsode. Presets: van_der_pol (stiff clásico), robertson "
        "(cinética química rígida), o custom."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "system": {
                "type": "string",
                "enum": ["van_der_pol", "robertson", "custom"],
                "default": "van_der_pol",
            },
            "custom_equations": {
                "type": "string",
                "description": "Solo si system='custom'. Ecuaciones Octave separadas por ';', usando y(1),y(2),...",
            },
            "custom_params": {"type": "object"},
            "y0": {"type": "array", "items": {"type": "number"}},
            "tspan": {"type": "array", "items": {"type": "number"}, "description": "[t0, tfin]"},
            "solver": {"type": "string", "enum": ["ode15s", "ode23s", "lsode"], "default": "ode15s"},
            "n_output_points": {"type": "integer", "default": 50},
            "rel_tol": {"type": "number", "default": 1e-6},
            "abs_tol": {"type": "number", "default": 1e-8},
            "mode": {
                "type": "string",
                "enum": ["validate"],
                "description": "Si es 'validate', ejecuta el autochequeo interno (decaimiento exponencial vs ode15s, oscilador armonico vs lsode) e ignora el resto de los parametros.",
            },
        },
        "required": [],
    },
}


if __name__ == "__main__":
    import json as _json
    for sys_name, solver in [("van_der_pol", "ode15s"), ("van_der_pol", "lsode"), ("robertson", "ode15s")]:
        r = integrate_stiff_ode(system=sys_name, solver=solver, n_output_points=50)
        if "error" in r:
            print(sys_name, solver, "-> ERROR:", r["error"], r.get("stderr", ""))
        else:
            print(sys_name, solver, "-> OK, n_internal_steps =", r["n_internal_steps"], "| y_final =", [row[-1] for row in r["y"]])
