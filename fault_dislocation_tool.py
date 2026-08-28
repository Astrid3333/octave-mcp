"""
fault_dislocation_tool.py

Deformacion elastica de un semi-espacio por deslizamiento en una falla
rectangular, via las formulas de Okada (1985), usando el motor de
referencia okada_wrapper (wrapper de Python sobre el codigo FORTRAN
original dc3d/dc3d0 de Okada -- no una reimplementacion de las formulas
a mano, evita el riesgo clasico de errores de signo en la notacion de
Chinnery).

Referencia:
  Okada, Y. (1985), Surface deformation due to shear and tensile
  faults in a half-space, Bull. Seismol. Soc. Am., 75(4), 1135-1154.

Convencion de coordenadas:
  - Marco mapa: x=este, y=norte, z=arriba (todo en km salvo que se
    indique lo contrario). El plano z=0 es la superficie libre.
  - strike_deg: rumbo de la falla, medido en grados desde el norte,
    en sentido horario (convencion estandar sismologica).
  - dip_deg: buzamiento, 0-90 grados.
  - rake_deg: cabeceo del deslizamiento (0=strike-slip puro sinistral
    left-lateral con esta convencion U1, 90=dip-slip inverso puro),
    convencion Aki & Richards (1980).
  - "profundidad" de referencia que recibe el usuario es la del borde
    superior de la falla (top_depth_km, positiva hacia abajo) -- mas
    intuitiva para trabajar con datos sismologicos reales que la
    profundidad al origen local que usa dc3d internamente. Internamente
    se convierte a profundidad del CENTROIDE de la falla (convencion
    estandar, la misma que reportan la mayoria de soluciones de falla
    finita/W-phase de USGS), porque es el punto de referencia que usa
    dc3dwrapper.
"""

import math
from typing import Any, Dict, List, Tuple

import numpy as np
from okada_wrapper import dc3dwrapper


def _alpha_from_nu(nu: float) -> float:
    """alpha = (lambda+mu)/(lambda+2mu) = 1/(2*(1-nu)). Para nu=0.25,
    alpha=2/3 (caso mas comun en la literatura, medio de Poisson)."""
    return 1.0 / (2.0 * (1.0 - nu))


def _rotate_to_fault_frame(dx_east: float, dy_north: float, strike_deg: float) -> Tuple[float, float]:
    """Rota un offset (este,norte) relativo al punto de referencia de la
    falla al marco local de Okada: x_local a lo largo del rumbo,
    y_local perpendicular horizontal. La matriz de rotacion usada es
    una involucion (M @ M = I), por lo que la misma funcion sirve para
    rotar displacement local -> mapa (ver _rotate_from_fault_frame)."""
    s = math.radians(strike_deg)
    x_local = dx_east * math.sin(s) + dy_north * math.cos(s)
    y_local = dx_east * math.cos(s) - dy_north * math.sin(s)
    return x_local, y_local


def _rotate_from_fault_frame(u1_strike: float, u2_perp: float, strike_deg: float) -> Tuple[float, float]:
    """Inversa de _rotate_to_fault_frame (la misma matriz, por ser
    involucion): pasa un vector horizontal del marco local de Okada
    de vuelta a componentes (este,norte) del mapa."""
    s = math.radians(strike_deg)
    u_east = u1_strike * math.sin(s) + u2_perp * math.cos(s)
    u_north = u1_strike * math.cos(s) - u2_perp * math.sin(s)
    return u_east, u_north


def _single_point_deformation(
    x_east: float, y_north: float, z_up: float,
    strike_deg: float, dip_deg: float,
    top_depth_km: float, length_km: float, width_km: float,
    slip_m: float, rake_deg: float, opening_m: float,
    ref_x: float, ref_y: float, nu: float,
) -> Dict[str, Any]:
    dx = x_east - ref_x
    dy = y_north - ref_y
    x_local, y_local = _rotate_to_fault_frame(dx, dy, strike_deg)

    dip_rad = math.radians(dip_deg)
    centroid_depth_km = top_depth_km + (width_km / 2.0) * math.sin(dip_rad)

    rake_rad = math.radians(rake_deg)
    U1 = slip_m * math.cos(rake_rad)  # componente strike-slip
    U2 = slip_m * math.sin(rake_rad)  # componente dip-slip
    U3 = opening_m                    # componente tensile

    alpha = _alpha_from_nu(nu)
    success, u, grad_u = dc3dwrapper(
        alpha,
        [x_local, y_local, z_up],
        centroid_depth_km,
        dip_deg,
        [-length_km / 2.0, length_km / 2.0],
        [-width_km / 2.0, width_km / 2.0],
        [U1, U2, U3],
    )

    u_east, u_north = _rotate_from_fault_frame(float(u[0]), float(u[1]), strike_deg)
    return {
        "x_east_km": x_east, "y_north_km": y_north, "z_up_km": z_up,
        "success": int(success),
        "u_east_m": round(u_east, 8),
        "u_north_m": round(u_north, 8),
        "u_up_m": round(float(u[2]), 8),
        "horizontal_magnitude_m": round(math.hypot(u_east, u_north), 8),
    }


def _forward_deformation(params: Dict[str, Any]) -> Dict[str, Any]:
    points = params["observation_points"]  # [[x_east,y_north], ...] o [[x,y,z_up],...]
    strike_deg = float(params["strike_deg"])
    dip_deg = float(params["dip_deg"])
    rake_deg = float(params["rake_deg"])
    slip_m = float(params["slip_m"])
    length_km = float(params["length_km"])
    width_km = float(params["width_km"])
    top_depth_km = float(params["top_depth_km"])
    opening_m = float(params.get("opening_m", 0.0))
    ref = params.get("reference_point", [0.0, 0.0])
    ref_x, ref_y = float(ref[0]), float(ref[1])
    nu = float(params.get("nu", 0.25))

    if not (0.0 <= dip_deg <= 90.0):
        raise ValueError(f"dip_deg debe estar en [0,90], recibido {dip_deg}")
    if length_km <= 0 or width_km <= 0:
        raise ValueError("length_km y width_km deben ser > 0")

    results = []
    for p in points:
        x_e, y_n = float(p[0]), float(p[1])
        z_up = float(p[2]) if len(p) > 2 else 0.0
        if z_up > 0:
            raise ValueError(f"z_up debe ser <= 0 (superficie o subsuperficie), recibido {z_up}")
        results.append(_single_point_deformation(
            x_e, y_n, z_up, strike_deg, dip_deg, top_depth_km,
            length_km, width_km, slip_m, rake_deg, opening_m,
            ref_x, ref_y, nu,
        ))

    return {
        "mode": "forward_deformation",
        "n_points": len(results),
        "centroid_depth_km": round(top_depth_km + (width_km / 2.0) * math.sin(math.radians(dip_deg)), 6),
        "results": results,
        "any_singular": any(r["success"] != 0 for r in results),
    }


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

def _check(name, passed, **extra):
    d = {"name": name, "passed": bool(passed)}
    d.update(extra)
    return d


def _validate() -> Dict[str, Any]:
    checks = []

    alpha = _alpha_from_nu(0.25)
    success_ref, u_ref, _ = dc3dwrapper(
        alpha, [1.0, 0.0, -1.0], 3.0, 70.0, [-0.5, 0.5], [-0.5, 0.5], [1.0, 0.0, 0.0],
    )
    expected = np.array([0.0047249, -0.00303486, 0.00658863])
    err = float(np.max(np.abs(np.array(u_ref) - expected)))
    checks.append(_check("engine_matches_reference_case", err < 1e-6,
                          details=f"max abs diff vs referencia: {err:.2e}"))

    base_params = {
        "observation_points": [[5.0, 0.0]],
        "strike_deg": 30.0, "dip_deg": 60.0, "rake_deg": 90.0,
        "slip_m": 1.0, "length_km": 10.0, "width_km": 8.0,
        "top_depth_km": 2.0, "nu": 0.25,
    }

    r1 = _forward_deformation(base_params)["results"][0]
    p2 = dict(base_params); p2["slip_m"] = 2.0
    r2 = _forward_deformation(p2)["results"][0]
    ratio = r2["horizontal_magnitude_m"] / r1["horizontal_magnitude_m"] if r1["horizontal_magnitude_m"] > 0 else None
    checks.append(_check("linear_in_slip", ratio is not None and abs(ratio - 2.0) < 1e-6,
                          details=f"|u(2*slip)|/|u(slip)| = {ratio}"))

    p_far = dict(base_params); p_far["observation_points"] = [[50.0, 0.0]]
    r_far = _forward_deformation(p_far)["results"][0]
    checks.append(_check("decays_with_distance",
                          r_far["horizontal_magnitude_m"] < r1["horizontal_magnitude_m"],
                          details=f"|u| a 5km={r1['horizontal_magnitude_m']:.6f}, a 50km={r_far['horizontal_magnitude_m']:.6f}"))

    delta = 47.0
    p_rot = dict(base_params)
    p_rot["strike_deg"] = base_params["strike_deg"] + delta
    ox, oy = base_params["observation_points"][0]
    d_rad = math.radians(delta)
    ox2 = ox * math.cos(d_rad) + oy * math.sin(d_rad)
    oy2 = -ox * math.sin(d_rad) + oy * math.cos(d_rad)
    p_rot["observation_points"] = [[ox2, oy2]]
    r_rot = _forward_deformation(p_rot)["results"][0]
    mag_diff = abs(r_rot["horizontal_magnitude_m"] - r1["horizontal_magnitude_m"])
    checks.append(_check("rotational_invariance", mag_diff < 1e-9,
                          details=f"|u_horiz| original={r1['horizontal_magnitude_m']:.9f}, rotado={r_rot['horizontal_magnitude_m']:.9f}"))

    checks.append(_check("no_singular_points", not _forward_deformation(base_params)["any_singular"],
                          details="success flag de dc3d == 0 en todos los puntos"))

    total_passed = sum(1 for c in checks if c["passed"])
    return {
        "checks": checks,
        "total_passed": total_passed,
        "total_checks": len(checks),
        "status": "success" if total_passed == len(checks) else "failed",
    }


def run(mode: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if mode == "forward_deformation":
        return _forward_deformation(params)
    elif mode == "validate":
        return _validate()
    else:
        return {"error": f"modo desconocido: {mode!r} (validos: forward_deformation, validate)"}


from tool_registry import register_tool

FAULT_DISLOCATION_TOOL_SCHEMA = {
    "name": "fault_dislocation_tool",
    "description": (
        "Deformacion elastica de un semi-espacio por deslizamiento en una "
        "falla rectangular (Okada 1985) via okada_wrapper. Modo "
        "forward_deformation: desplazamientos (este/norte/vertical) en "
        "puntos de observacion dados strike/dip/rake/slip/geometria de "
        "falla. Modo validate: autotest interno."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["forward_deformation", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "observation_points": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                        "description": "[[x_este_km, y_norte_km, (z_up_km opcional)], ...]",
                    },
                    "strike_deg": {"type": "number"},
                    "dip_deg": {"type": "number"},
                    "rake_deg": {"type": "number"},
                    "slip_m": {"type": "number"},
                    "length_km": {"type": "number"},
                    "width_km": {"type": "number"},
                    "top_depth_km": {"type": "number"},
                    "opening_m": {"type": "number", "default": 0.0},
                    "reference_point": {
                        "type": "array", "items": {"type": "number"}, "default": [0.0, 0.0],
                    },
                    "nu": {"type": "number", "default": 0.25},
                },
            },
        },
        "required": ["mode"],
    },
}

register_tool(
    "fault_dislocation_tool",
    FAULT_DISLOCATION_TOOL_SCHEMA,
    run,
)


if __name__ == "__main__":
    import json
    print(json.dumps(run("validate", {}), indent=2, ensure_ascii=False))
