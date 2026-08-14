"""
cross_validation_tool.py

Corre el mismo sistema dinamico con dos motores numericos independientes
(Octave ode45 y scipy solve_ivp/RK45) y compara resultados -- box-counting
dimension por ahora, extensible a otras metricas.

Nace de un caso real: fractal_dimension_tool.py media dimension ~1.14 para
el atractor Chen-Lee con pocos puntos (sesgo de submuestreo). Al subir la
resolucion y validar con un segundo motor completamente independiente
(distinto lenguaje, distinto solver, distinto codigo de box-counting) se
confirmo que el valor real converge a ~1.55, no a la cifra especulada
(~2.5) sin fuente verificada. Este modulo automatiza esa validacion
cruzada para no depender de un unico motor cuando la confianza en el
numero importa.
"""
import subprocess
import tempfile
import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fractal_dimension_tool import _box_counting_dimension

SYSTEMS = {
    "chen_lee": {
        "octave_rhs": "[a*s(1) - s(2)*s(3); b*s(2) + s(1)*s(3); c*s(3) + s(1)*s(2)/3]",
        "scipy_rhs": lambda s, a, b, c: [a*s[0] - s[1]*s[2], b*s[1] + s[0]*s[2], c*s[2] + s[0]*s[1]/3],
        "default_params": {"a": 5.0, "b": -10.0, "c": -0.38},
        "y0": [1.0, 1.0, 1.0],
    },
}


def _run_octave(system, params, t_max, n_steps, transient_frac, timeout=120):
    spec = SYSTEMS[system]
    p = {**spec["default_params"], **params}
    y0 = spec["y0"]
    transient_idx = max(1, int(n_steps * transient_frac))
    var_names = list(p.keys())
    assigns = "; ".join(f"{k} = {v}" for k, v in p.items())
    y0_str = "; ".join(str(v) for v in y0)
    octave_code = f"""
{assigns};
f = @(t, s) {spec['octave_rhs']};
tspan = linspace(0, {t_max}, {n_steps});
[t, S] = ode45(f, tspan, [{y0_str}]);
S = S({transient_idx}:end, :);
printf("%.8e ", S');
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as fh:
        fh.write(octave_code)
        script_path = fh.name
    try:
        r = subprocess.run(["octave", "--no-gui", "--no-init-file", script_path],
                            capture_output=True, text=True, timeout=timeout)
    finally:
        os.unlink(script_path)
    if r.returncode != 0:
        return None, r.stderr.strip()
    vals = [float(x) for x in r.stdout.split()]
    dim = len(y0)
    pts = [tuple(vals[i:i+dim]) for i in range(0, len(vals), dim)]
    return pts, None


def _run_scipy(system, params, t_max, n_steps, transient_frac):
    from scipy.integrate import solve_ivp
    import numpy as np
    spec = SYSTEMS[system]
    p = {**spec["default_params"], **params}
    y0 = spec["y0"]
    rhs = spec["scipy_rhs"]

    def f(t, s):
        return rhs(s, **p)

    t_eval = np.linspace(0, t_max, n_steps)
    sol = solve_ivp(f, [0, t_max], y0, t_eval=t_eval, rtol=1e-9, atol=1e-9, method="RK45")
    pts = sol.y.T
    cut = int(n_steps * transient_frac)
    pts = pts[cut:]
    return [tuple(row) for row in pts], None


def _validate_cross_validation() -> dict:
    """Corre chen_lee con resolucion reducida (t_max=50, n_steps=5000, ~2.6s
    medido) en vez de los defaults reales (t_max=2000, n_steps=200000, que
    tardan minutos) -- elegida por tener margen real bajo tolerance
    (rel_diff ~0.024 vs tolerance=0.15). Una resolucion mas chica probada
    (t_max=20, n_steps=2000) dio rel_diff=0.144, casi en el limite -- mismo
    sesgo de submuestreo que esta tool fue creada para detectar, descartada
    por riesgo de falso negativo. No verifica solo que no tire excepcion:
    exige rango fisico razonable en las dimensiones y margen real bajo
    tolerancia, no solo el booleano cross_validated al limite."""
    checks = []
    try:
        r = compute_cross_validation(t_max=50, n_steps=5000)
    except Exception as e:
        return {"mode": "validate", "validation_passed": False,
                "checks": [{"name": "compute_cross_validation no tira excepcion", "passed": False, "error": str(e)}]}

    checks.append({"name": "respuesta sin campo error", "passed": "error" not in r, "got": r.get("error")})

    n_o, n_s = r.get("n_points_octave", 0), r.get("n_points_scipy", 0)
    checks.append({"name": "ambos motores devuelven puntos (>0)", "passed": n_o > 0 and n_s > 0, "got": {"octave": n_o, "scipy": n_s}})

    dim_o, dim_s = r.get("dimension_octave_ode45"), r.get("dimension_scipy_rk45")
    dims_sane = all(isinstance(d, (int, float)) and 0.3 < d < 3.0 for d in (dim_o, dim_s) if d is not None)
    checks.append({"name": "dimensiones en rango fisico razonable (0.3-3.0)", "passed": dims_sane, "got": {"octave": dim_o, "scipy": dim_s}})

    rel_diff, tol = r.get("relative_difference", 1.0), r.get("tolerance", 0.0)
    margin_ok = r.get("cross_validated") is True and rel_diff < (tol / 2)
    checks.append({"name": "cross_validated==True con margen real (rel_diff < tolerance/2)", "passed": margin_ok, "got": {"cross_validated": r.get("cross_validated"), "relative_difference": rel_diff, "tolerance": tol}})

    return {
        "mode": "validate",
        "validation_passed": all(c["passed"] for c in checks),
        "checks": checks,
        "not_covered": [
            "caso negativo (forzar cross_validated=False para confirmar que el flag detecta divergencia real, no solo confirma acuerdo)",
            "otros sistemas dinamicos -- SYSTEMS solo tiene chen_lee implementado hoy",
        ],
    }


def compute_cross_validation(system="chen_lee", params=None, t_max=2000, n_steps=200000,
                              transient_frac=0.1, tolerance=0.15, mode=None):
    if mode == "validate":
        return _validate_cross_validation()
    if system not in SYSTEMS:
        return {"error": f"sistema desconocido: {system}", "sistemas_disponibles": list(SYSTEMS.keys())}
    params = params or {}

    pts_octave, err_octave = _run_octave(system, params, t_max, n_steps, transient_frac)
    if pts_octave is None:
        return {"error": "fallo integracion Octave", "stderr": err_octave}

    pts_scipy, err_scipy = _run_scipy(system, params, t_max, n_steps, transient_frac)
    if pts_scipy is None:
        return {"error": "fallo integracion scipy", "stderr": err_scipy}

    dim_octave, _ = _box_counting_dimension(pts_octave, n_scales=20)
    dim_scipy, _ = _box_counting_dimension(pts_scipy, n_scales=20)

    rel_diff = abs(dim_octave - dim_scipy) / max(abs(dim_octave), abs(dim_scipy), 1e-9)
    cross_validated = rel_diff <= tolerance

    return {
        "system": system,
        "params_used": {**SYSTEMS[system]["default_params"], **params},
        "n_points_octave": len(pts_octave),
        "n_points_scipy": len(pts_scipy),
        "dimension_octave_ode45": dim_octave,
        "dimension_scipy_rk45": dim_scipy,
        "relative_difference": rel_diff,
        "tolerance": tolerance,
        "cross_validated": cross_validated,
        "nota": (
            "Dos motores numericos independientes (Octave ode45 y scipy RK45), "
            "dos integraciones separadas, mismo box-counting. Si cross_validated=false, "
            "no confiar en ninguno de los dos numeros sin investigar mas."
        ),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(compute_cross_validation(t_max=500, n_steps=50000), indent=2, ensure_ascii=False))
