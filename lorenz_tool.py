"""
lorenz_tool.py -- Sistema de Lorenz (atractor caotico clasico) como tool
independiente, expuesta con schema + modo validate.

Contexto: chaos_diagnosis_tool.py ya tiene una _lorenz_series() interna que
devuelve solo la componente x, usada como serie de referencia para testear
el pipeline de diagnostico de caos (lambda1, surrogates) y de dimension de
correlacion (D2). Esta tool es distinta en proposito: expone la trayectoria
COMPLETA (x, y, z) para poder graficar el atractor en 3D, permite variar
sigma/rho/beta desde afuera, y agrega un modo "efecto_mariposa" con dos
condiciones iniciales casi identicas para ilustrar sensibilidad a condiciones
iniciales (la propiedad definitoria del caos, mas alla del sistema puntual).

Integracion: RK4 puro Python, mismo patron que _lorenz_series en
chaos_diagnosis_tool.py y que predator_prey_chaos_tool.py.

El modo validate NO reinventa los checks de "es caotico" -- delega en
chaos_diagnosis_tool (lambda1 > 0 con surrogates) y correlation_dimension_tool
(D2 ~ 2.05) sobre la serie x generada aca, para no duplicar logica de
significancia estadistica que ya esta resuelta y validada en esos modulos.
"""

import math

try:
    from chaos_diagnosis_tool import compute_chaos_diagnosis
except ImportError:
    compute_chaos_diagnosis = None

try:
    from correlation_dimension_tool import compute_correlation_dimension
except ImportError:
    compute_correlation_dimension = None


# ---------------------------------------------------------------------------
# Integracion RK4
# ---------------------------------------------------------------------------

def _lorenz_step(y, dt, sigma, rho, beta):
    def f(state):
        x, yv, z = state
        return (
            sigma * (yv - x),
            x * (rho - z) - yv,
            x * yv - beta * z,
        )
    k1 = f(y)
    y2 = [y[j] + dt / 2 * k1[j] for j in range(3)]
    k2 = f(y2)
    y3 = [y[j] + dt / 2 * k2[j] for j in range(3)]
    k3 = f(y3)
    y4 = [y[j] + dt * k3[j] for j in range(3)]
    k4 = f(y4)
    return [y[j] + dt / 6 * (k1[j] + 2 * k2[j] + 2 * k3[j] + k4[j]) for j in range(3)]


def _lorenz_trajectory(n_steps=6000, dt=0.01, sigma=10.0, rho=28.0, beta=8.0 / 3.0,
                        y0=(1.0, 1.0, 1.0), discard=1000):
    """Devuelve la trayectoria completa (x, y, z) tras descartar el transitorio.
    A diferencia de _lorenz_series (chaos_diagnosis_tool), NO trunca a solo x --
    hace falta el estado completo para graficar el atractor."""
    y = list(y0)
    traj = []
    for i in range(n_steps + discard):
        y = _lorenz_step(y, dt, sigma, rho, beta)
        if i >= discard:
            traj.append(tuple(y))
    return traj


def _downsample(traj, max_points):
    if len(traj) <= max_points:
        return traj
    stride = max(1, len(traj) // max_points)
    return traj[::stride]


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def compute_lorenz(mode="simulate", n_steps=6000, dt=0.01,
                    sigma=10.0, rho=28.0, beta=8.0 / 3.0,
                    y0=(1.0, 1.0, 1.0), discard=1000,
                    downsample_for_plot=2000,
                    perturbacion_inicial=1e-5,
                    **kwargs):
    if mode == "validate":
        return _validate_lorenz()

    if mode == "efecto_mariposa":
        y0_b = (y0[0] + perturbacion_inicial, y0[1], y0[2])
        traj_a = _lorenz_trajectory(n_steps, dt, sigma, rho, beta, y0, discard)
        traj_b = _lorenz_trajectory(n_steps, dt, sigma, rho, beta, y0_b, discard)

        # divergencia: distancia euclidea entre las dos trayectorias en el
        # tiempo, para mostrar el crecimiento exponencial temprano tipico de
        # sensibilidad a condiciones iniciales (no es una medicion formal de
        # lambda1 -- para eso esta chaos_diagnosis_tool sobre la serie x)
        divergencia = [
            math.sqrt(sum((a[k] - b[k]) ** 2 for k in range(3)))
            for a, b in zip(traj_a, traj_b)
        ]
        n_show = min(len(traj_a), downsample_for_plot)
        idxs = list(range(0, len(traj_a), max(1, len(traj_a) // n_show)))[:n_show]

        return {
            "mode": "efecto_mariposa",
            "perturbacion_inicial": perturbacion_inicial,
            "n_steps": n_steps,
            "trayectoria_a": [{"x": traj_a[i][0], "y": traj_a[i][1], "z": traj_a[i][2]} for i in idxs],
            "trayectoria_b": [{"x": traj_b[i][0], "y": traj_b[i][1], "z": traj_b[i][2]} for i in idxs],
            "divergencia_euclidea": [round(divergencia[i], 6) for i in idxs],
            "nota": (
                "divergencia_euclidea es la distancia entre las dos trayectorias "
                "en cada paso, partiendo de una diferencia inicial de "
                f"{perturbacion_inicial} en x. El crecimiento aproximadamente "
                "exponencial temprano ilustra sensibilidad a condiciones "
                "iniciales; para una medicion formal del exponente de Lyapunov "
                "usar chaos_diagnosis_tool sobre la serie x de este sistema."
            ),
        }

    # mode == "simulate" (default)
    traj = _lorenz_trajectory(n_steps, dt, sigma, rho, beta, y0, discard)
    traj_plot = _downsample(traj, downsample_for_plot)

    xs = [p[0] for p in traj]
    ys = [p[1] for p in traj]
    zs = [p[2] for p in traj]

    return {
        "mode": "simulate",
        "params": {"sigma": sigma, "rho": rho, "beta": round(beta, 6), "dt": dt,
                    "n_steps": n_steps, "discard": discard},
        "bounds": {
            "x": [round(min(xs), 6), round(max(xs), 6)],
            "y": [round(min(ys), 6), round(max(ys), 6)],
            "z": [round(min(zs), 6), round(max(zs), 6)],
        },
        "n_points": len(traj),
        "trajectory_sample": [{"x": p[0], "y": p[1], "z": p[2]} for p in traj_plot],
        "nota": (
            "trajectory_sample esta submuestreada a downsample_for_plot puntos "
            "para no saturar la respuesta; bounds y n_points corresponden a la "
            "trayectoria completa (post-discard)."
        ),
    }


def _validate_lorenz() -> dict:
    """4 checks: 1) sin NaN/inf en la trayectoria (integracion estable con
    los params clasicos). 2) el atractor efectivamente ocupa las dos alas
    (bounds de x cruzan cero en ambos signos con margen -- si no, la
    trayectoria colapso a un punto fijo o quedo en una sola ala, seria un
    bug de integracion). 3) chaos_diagnosis_tool sobre la serie x debe dar
    lambda1 > 0 (caos confirmado, delega la logica de significancia
    estadistica en el modulo que ya la tiene resuelta). 4) correlation_
    dimension_tool sobre la misma serie debe dar D2 en rango razonable
    (mismo umbral que usa correlation_dimension_tool internamente para su
    propio caso Lorenz, [1.7, 2.4])."""
    checks = []

    r = compute_lorenz(mode="simulate", n_steps=6000, dt=0.01, discard=1000)
    xs = [p["x"] for p in r["trajectory_sample"]]

    finito = all(math.isfinite(v) for p in r["trajectory_sample"] for v in (p["x"], p["y"], p["z"]))
    checks.append({
        "name": "lorenz clasico: trayectoria finita (sin NaN/inf, dt=0.01 estable)",
        "passed": finito,
        "got": {"n_points": r["n_points"]},
    })

    x_bounds = r["bounds"]["x"]
    ocupa_dos_alas = x_bounds[0] < -5 and x_bounds[1] > 5
    checks.append({
        "name": "lorenz clasico: atractor ocupa ambas alas (bounds x cruzan cero con margen)",
        "passed": ocupa_dos_alas,
        "got": {"x_bounds": x_bounds},
    })

    if compute_chaos_diagnosis is not None:
        diag = compute_chaos_diagnosis(mode="series", series=xs, dt=0.01)
        lambda1_cmp = diag.get("lambda1_comparacion_surrogates")
        checks.append({
            "name": "lorenz clasico: lambda1_comparacion_surrogates > 0 (via chaos_diagnosis_tool)",
            "passed": bool(lambda1_cmp is not None and lambda1_cmp > 0),
            "got": {"lambda1_comparacion_surrogates": lambda1_cmp, "diagnostico": diag.get("diagnostico")},
        })
    else:
        checks.append({
            "name": "lorenz clasico: lambda1 > 0 (via chaos_diagnosis_tool)",
            "passed": False,
            "got": {"error": "chaos_diagnosis_tool no disponible en este entorno"},
        })

    if compute_correlation_dimension is not None:
        d2r = compute_correlation_dimension(mode="series", series=xs, dt=0.01, max_points=400)
        d2 = d2r.get("D2_dimension_correlacion")
        checks.append({
            "name": "lorenz clasico: D2 en [1.7, 2.4] (via correlation_dimension_tool, ref. literatura ~2.05)",
            "passed": bool(d2 is not None and 1.7 <= d2 <= 2.4),
            "got": {"D2": d2},
        })
    else:
        checks.append({
            "name": "lorenz clasico: D2 en [1.7, 2.4] (via correlation_dimension_tool)",
            "passed": False,
            "got": {"error": "correlation_dimension_tool no disponible en este entorno"},
        })

    return {"mode": "validate", "validation_passed": all(c["passed"] for c in checks), "checks": checks}


# ---------------------------------------------------------------------------
# Schema + registro
# ---------------------------------------------------------------------------

LORENZ_SCHEMA = {
    "description": (
        "Simula el sistema de Lorenz (atractor caotico clasico, modelo simplificado "
        "de conveccion atmosferica). Modos: 'simulate' (trayectoria x,y,z completa "
        "para graficar el atractor), 'efecto_mariposa' (dos trayectorias con "
        "condiciones iniciales casi identicas, para ilustrar sensibilidad a "
        "condiciones iniciales), 'validate' (self-test)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["simulate", "efecto_mariposa", "validate"], "default": "simulate"},
            "n_steps": {"type": "integer", "default": 6000, "description": "Pasos de integracion tras descartar el transitorio."},
            "dt": {"type": "number", "default": 0.01},
            "sigma": {"type": "number", "default": 10.0},
            "rho": {"type": "number", "default": 28.0},
            "beta": {"type": "number", "default": 2.6666666666666665},
            "y0": {"type": "array", "items": {"type": "number"}, "default": [1.0, 1.0, 1.0]},
            "discard": {"type": "integer", "default": 1000, "description": "Pasos de transitorio a descartar antes de registrar la trayectoria."},
            "downsample_for_plot": {"type": "integer", "default": 2000, "description": "Maximo de puntos devueltos para graficar."},
            "perturbacion_inicial": {"type": "number", "default": 1e-5, "description": "Solo para modo efecto_mariposa: diferencia inicial en x entre las dos trayectorias."},
        },
        "required": [],
    },
}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_lorenz(mode="simulate", n_steps=2000), indent=2, ensure_ascii=False)[:2000])
    print("---VALIDATE---")
    print(json.dumps(_validate_lorenz(), indent=2, ensure_ascii=False))


try:
    from tool_registry import register_tool
    register_tool(
        name="lorenz",
        schema={**LORENZ_SCHEMA, "name": "lorenz"},
        handler=lambda args: compute_lorenz(**args),
    )
except ImportError:
    pass
