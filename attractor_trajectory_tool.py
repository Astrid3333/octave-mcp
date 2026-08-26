"""
attractor_trajectory_tool.py

Extension del trabajo de lyapunov_tool: expone la trayectoria completa
x(t), y(t), z(t) de sistemas caoticos conocidos (Lorenz, Chen-Lee,
Burke-Shaw, Rossler, custom) en vez de solo devolver lambda_1 y el
estado final. Incluye proyecciones 2D (xy, xz, yz) ya downsampled para
graficar directamente sin saturar el payload.

Sistemas no son stiff (a diferencia de enzyme_kinetics) -> ode45 con
timeout=60 es de sobra.
"""

import os
import subprocess
import tempfile

ATTRACTOR_TRAJECTORY_SCHEMA = {
    "description": (
        "Integra sistemas caoticos conocidos (Lorenz, Chen-Lee, Burke-Shaw, "
        "Rossler, o custom via ecuaciones propias) y devuelve la trayectoria "
        "completa x(t),y(t),z(t) mas proyecciones 2D (xy/xz/yz) downsampled "
        "listas para graficar. Complementa a lyapunov_tool (que solo da "
        "lambda_1) y a chaos_diagnosis_tool (que diagnostica caos en series "
        "observadas 1D)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["trajectory", "validate"],
                "default": "trajectory",
            },
            "system": {
                "type": "string",
                "enum": ["lorenz", "chen_lee", "burke_shaw", "rossler", "custom"],
                "default": "lorenz",
            },
            "params": {
                "type": "object",
                "description": (
                    "Parametros del sistema. Defaults clasicos por sistema si se "
                    "omite (Lorenz: sigma=10,rho=28,beta=8/3; Chen-Lee: a=5,b=-10,c=-0.38; "
                    "Burke-Shaw: s=10,v=4.272; Rossler: a=0.2,b=0.2,c=5.7)."
                ),
            },
            "custom_odes": {
                "type": "string",
                "description": (
                    "Solo si system='custom'. Expresion Octave del RHS como funcion "
                    "de (t,s) donde s=[x;y;z], ej: '[10*(s(2)-s(1)); s(1)*(28-s(3))-s(2); s(1)*s(2)-(8/3)*s(3)]'"
                ),
            },
            "initial_condition": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Estado inicial [x0,y0,z0]. Default [1,1,1].",
            },
            "t_max": {"type": "number", "default": 40.0},
            "n_points": {"type": "integer", "default": 4000},
            "downsample_for_plot": {
                "type": "integer",
                "default": 500,
                "description": "Numero de puntos a devolver en las proyecciones 2D (independiente de n_points usado para integrar).",
            },
        },
    },
}

_DEFAULTS = {
    "lorenz": {"sigma": 10.0, "rho": 28.0, "beta": 8.0 / 3.0},
    "chen_lee": {"a": 5.0, "b": -10.0, "c": -0.38},
    "burke_shaw": {"s": 10.0, "v": 4.272},
    "rossler": {"a": 0.2, "b": 0.2, "c": 5.7},
}


def _run_octave(code, timeout=60):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as fh:
        fh.write(code)
        script_path = fh.name
    try:
        r = subprocess.run(
            ["octave", "--no-gui", "--no-init-file", script_path],
            capture_output=True, text=True, timeout=timeout,
        )
    finally:
        os.unlink(script_path)
    if r.returncode != 0:
        return None, r.stderr.strip()
    return r.stdout.strip(), None


def _rhs_expr(system, params, custom_odes):
    if system == "lorenz":
        p = {**_DEFAULTS["lorenz"], **(params or {})}
        return (
            f"sigma={p['sigma']}; rho={p['rho']}; beta={p['beta']};\n"
            "f = @(t,s) [sigma*(s(2)-s(1)); s(1)*(rho-s(3))-s(2); s(1)*s(2)-beta*s(3)];\n"
        )
    if system == "chen_lee":
        p = {**_DEFAULTS["chen_lee"], **(params or {})}
        return (
            f"a={p['a']}; b={p['b']}; c={p['c']};\n"
            "f = @(t,s) [a*s(1)-s(2)*s(3); b*s(2)+s(1)*s(3); c*s(3)+s(1)*s(2)/3];\n"
        )
    if system == "burke_shaw":
        p = {**_DEFAULTS["burke_shaw"], **(params or {})}
        return (
            f"s_=({p['s']}); v={p['v']};\n"
            "f = @(t,s) [-s_*(s(1)+s(2)); -s(2)-s_*s(1)*s(3); s_*s(1)*s(2)+v];\n"
        )
    if system == "rossler":
        p = {**_DEFAULTS["rossler"], **(params or {})}
        return (
            f"a={p['a']}; b={p['b']}; c={p['c']};\n"
            "f = @(t,s) [-s(2)-s(3); s(1)+a*s(2); b+s(3)*(s(1)-c)];\n"
        )
    if system == "custom":
        if not custom_odes:
            raise ValueError("system='custom' requiere custom_odes")
        return f"f = @(t,s) {custom_odes};\n"
    raise ValueError(f"sistema desconocido: {system}")


def compute_attractor_trajectory(
    mode="trajectory",
    system="lorenz",
    params=None,
    custom_odes=None,
    initial_condition=None,
    t_max=40.0,
    n_points=4000,
    downsample_for_plot=500,
    **kwargs,
):
    if mode == "validate":
        return _validate_attractor_trajectory()

    ic = initial_condition or [1.0, 1.0, 1.0]
    try:
        rhs = _rhs_expr(system, params, custom_odes)
    except ValueError as e:
        return {"error": str(e)}

    code = (
        rhs
        + f"tspan = linspace(0,{t_max},{n_points});\n"
        + f"[t,S] = ode45(f, tspan, [{ic[0]};{ic[1]};{ic[2]}]);\n"
        + "printf(\"%.8f \", S');\n"
    )
    out, err = _run_octave(code)
    if out is None:
        return {"error": "octave fallo", "stderr": err}

    vals = [float(v) for v in out.split()]
    triples = [(vals[i], vals[i + 1], vals[i + 2]) for i in range(0, len(vals), 3)]
    x_vals = [p[0] for p in triples]
    y_vals = [p[1] for p in triples]
    z_vals = [p[2] for p in triples]

    step = max(1, len(triples) // downsample_for_plot)
    idx = list(range(0, len(triples), step))

    return {
        "mode": "trajectory",
        "system": system,
        "params_used": {**_DEFAULTS.get(system, {}), **(params or {})} if system != "custom" else {"custom_odes": custom_odes},
        "initial_condition": ic,
        "t_max": t_max,
        "n_points_integrated": len(triples),
        "final_state": {"x": round(x_vals[-1], 6), "y": round(y_vals[-1], 6), "z": round(z_vals[-1], 6)},
        "trajectory_bounds": {
            "x": [round(min(x_vals), 4), round(max(x_vals), 4)],
            "y": [round(min(y_vals), 4), round(max(y_vals), 4)],
            "z": [round(min(z_vals), 4), round(max(z_vals), 4)],
        },
        "projection_xy": [{"x": round(x_vals[i], 4), "y": round(y_vals[i], 4)} for i in idx],
        "projection_xz": [{"x": round(x_vals[i], 4), "z": round(z_vals[i], 4)} for i in idx],
        "projection_yz": [{"y": round(y_vals[i], 4), "z": round(z_vals[i], 4)} for i in idx],
        "n_points_plot": len(idx),
    }


def _validate_attractor_trajectory() -> dict:
    """3 checks: 1) Lorenz con params default no diverge (bounded, sin NaN/Inf)
    en t_max=40. 2) Efecto mariposa: dos corridas de Lorenz con IC separadas
    por 1e-8 divergen (distancia final >> distancia inicial) -- umbral a t=30
    (no t=20, que todavia esta en regimen lineal segun lo encontrado hoy).
    3) Rossler con params default produce una orbita con z siempre >= 0 en el
    grueso de la trayectoria (propiedad conocida del atractor de Rossler:
    z se mantiene cerca de 0 salvo picos esporadicos)."""
    checks = []

    r1 = compute_attractor_trajectory(system="lorenz", t_max=40.0, n_points=4000, initial_condition=[1, 1, 1])
    if "error" in r1:
        checks.append({"name": "lorenz default: sin error", "passed": False, "got": r1})
    else:
        b = r1["trajectory_bounds"]
        bounded = all(abs(b[k][0]) < 100 and abs(b[k][1]) < 100 for k in ("x", "y", "z"))
        checks.append({"name": "lorenz no diverge (bounded |x|,|y|,|z| < 100)",
                        "passed": bool(bounded), "got": b})

    r_a = compute_attractor_trajectory(system="lorenz", t_max=30.0, n_points=3000, initial_condition=[1, 1, 1])
    r_b = compute_attractor_trajectory(system="lorenz", t_max=30.0, n_points=3000, initial_condition=[1 + 1e-8, 1, 1])
    if "error" in r_a or "error" in r_b:
        checks.append({"name": "efecto mariposa: sin error", "passed": False, "got": {"a": r_a, "b": r_b}})
    else:
        fa, fb = r_a["final_state"], r_b["final_state"]
        d_final = ((fa["x"] - fb["x"]) ** 2 + (fa["y"] - fb["y"]) ** 2 + (fa["z"] - fb["z"]) ** 2) ** 0.5
        checks.append({"name": "efecto mariposa: distancia final (t=30) >> 1e-8 inicial (umbral d > 1.0)",
                        "passed": bool(d_final > 1.0), "got": {"d_final": round(d_final, 4)}})

    r_ross = compute_attractor_trajectory(system="rossler", t_max=100.0, n_points=5000, initial_condition=[1, 1, 1])
    if "error" in r_ross:
        checks.append({"name": "rossler default: sin error", "passed": False, "got": r_ross})
    else:
        z_min = r_ross["trajectory_bounds"]["z"][0]
        checks.append({"name": "rossler: z_min > -5 (atractor no colapsa a valores extremos negativos)",
                        "passed": bool(z_min > -5), "got": {"z_min": z_min}})

    return {"mode": "validate", "validation_passed": all(c["passed"] for c in checks), "checks": checks}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_attractor_trajectory(system="lorenz", t_max=40.0, n_points=2000), indent=2)[:2000])
    print("---VALIDATE---")
    print(json.dumps(_validate_attractor_trajectory(), indent=2, ensure_ascii=False))


try:
    from tool_registry import register_tool
    register_tool(
        name="attractor_trajectory",
        schema={**ATTRACTOR_TRAJECTORY_SCHEMA, "name": "attractor_trajectory"},
        handler=lambda args: compute_attractor_trajectory(**args),
    )
except ImportError:
    pass
