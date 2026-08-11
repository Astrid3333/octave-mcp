"""
acoustics_tool.py

Acustica: propagacion de ondas de presion en 1D (FDTD), modos de resonancia
de cavidades rectangulares (habitaciones), y tiempo de reverberacion
(formula de Sabine). Complementa infrasound_tool.py (que cubre propagacion
al aire libre / atenuacion atmosferica a larga distancia) con acustica de
interiores y ondas guiadas.

Modos:
  - pressure_wave_1d: resuelve p_tt = c^2 * p_xx via diferencias finitas
    explicitas (leapfrog), bordes Dirichlet (p=0, "pared abierta"/nodo de
    presion) o Neumann (dp/dx=0, "pared rigida"/antinodo). preset
    'known_first_mode' compara contra la solucion analitica exacta
    p(x,t) = sin(pi*x/L)*cos(c*pi/L*t) (bordes Dirichlet). preset 'custom'
    acepta perfil inicial arbitrario.
  - room_modes: frecuencias propias de una cavidad rectangular rigida
    (Lx,Ly,Lz) via f_nlm = (c/2)*sqrt((nx/Lx)^2+(ny/Ly)^2+(nz/Lz)^2),
    devuelve las N mas bajas ordenadas, clasificadas en axiales/tangenciales/
    oblicuas segun cuantos indices son no nulos.
  - reverberation_sabine: tiempo de reverberacion RT60 = 0.161*V/A (Sabine,
    metros/segundos), con A = suma(area_i * alpha_i) sobre las superficies
    dadas.
  - validate: corre casos con solucion/comportamiento conocido para cada
    submodulo (ver detalle en cada validacion).
"""

import numpy as np


def _sound_speed(temperature_c=20.0):
    # misma aproximacion que infrasound_tool: c = 331.3*sqrt(1+T/273.15) m/s
    return float(331.3 * np.sqrt(1.0 + temperature_c / 273.15))


def _pressure_wave_1d(L=1.0, c=343.0, n_points=100, t_final=None,
                       preset="known_first_mode", initial_profile=None,
                       boundary="dirichlet"):
    if n_points < 3:
        raise ValueError("n_points debe ser >= 3")
    dx = L / (n_points - 1)
    courant = 0.5  # margen de seguridad bajo CFL (courant <= 1 para estabilidad)
    dt = courant * dx / c
    if t_final is None:
        t_final = 200 * dt
    n_steps = max(1, int(round(t_final / dt)))
    t_actual = n_steps * dt

    x = np.linspace(0.0, L, n_points)
    known = None

    if preset == "custom":
        if initial_profile is None or len(initial_profile) != n_points:
            raise ValueError(f"preset='custom' requiere 'initial_profile' de longitud {n_points}")
        p0 = np.array(initial_profile, dtype=float)
    elif preset == "known_first_mode":
        p0 = np.sin(np.pi * x / L)
        known = {
            "solucion_analitica": "p(x,t) = sin(pi*x/L) * cos(c*pi/L*t)",
            "nota": "primer modo normal, velocidad inicial cero, bordes Dirichlet (p=0)",
        }
    else:
        raise ValueError(f"preset desconocido: {preset}")

    p_prev = p0.copy()
    p_curr = p0.copy()  # velocidad inicial (dp/dt) = 0
    r2 = courant ** 2

    snapshots = [p_curr.copy()]
    snap_every = max(1, n_steps // 8)

    for step in range(1, n_steps + 1):
        p_next = np.zeros(n_points)
        p_next[1:-1] = (2 * p_curr[1:-1] - p_prev[1:-1]
                         + r2 * (p_curr[2:] - 2 * p_curr[1:-1] + p_curr[:-2]))
        if boundary == "dirichlet":
            p_next[0] = 0.0
            p_next[-1] = 0.0
        elif boundary == "neumann":
            # dp/dx=0 en los bordes: reflejo el vecino interior (pared rigida)
            p_next[0] = p_next[1]
            p_next[-1] = p_next[-2]
        else:
            raise ValueError(f"boundary desconocido: {boundary}")
        p_prev, p_curr = p_curr, p_next
        if step % snap_every == 0:
            snapshots.append(p_curr.copy())

    result = {
        "mode": "pressure_wave_1d",
        "L": L, "c": c, "n_points": n_points, "boundary": boundary,
        "dx": round(dx, 6), "dt": round(dt, 8), "courant_number": courant,
        "cfl_stable": courant <= 1.0,
        "n_steps": n_steps, "t_final": round(t_actual, 6),
        "p_final_sample": [round(v, 6) for v in p_curr[::max(1, n_points // 10)]],
        "n_snapshots_taken": len(snapshots),
    }
    if known:
        p_analytic = np.sin(np.pi * x / L) * np.cos(c * np.pi / L * t_actual)
        max_err = float(np.max(np.abs(p_curr - p_analytic)))
        result["max_error_vs_analytic"] = round(max_err, 8)
        result["known_reference"] = known
    return result


def _room_modes(Lx=5.0, Ly=4.0, Lz=3.0, c=343.0, n_max=4, top_n=15):
    modes = []
    for nx in range(0, n_max + 1):
        for ny in range(0, n_max + 1):
            for nz in range(0, n_max + 1):
                if nx == 0 and ny == 0 and nz == 0:
                    continue
                f = (c / 2.0) * np.sqrt((nx / Lx) ** 2 + (ny / Ly) ** 2 + (nz / Lz) ** 2)
                n_nonzero = (nx > 0) + (ny > 0) + (nz > 0)
                kind = {1: "axial", 2: "tangencial", 3: "oblicua"}[n_nonzero]
                modes.append({"nx": nx, "ny": ny, "nz": nz, "frequency_hz": round(float(f), 3), "kind": kind})
    modes.sort(key=lambda m: m["frequency_hz"])
    return {
        "mode": "room_modes",
        "Lx": Lx, "Ly": Ly, "Lz": Lz, "c": c, "n_max": n_max,
        "n_modes_computed": len(modes),
        "lowest_modes": modes[:top_n],
        "schroeder_frequency_estimate_hz": None,
        "nota": "cavidad rectangular rigida (Neumann en las 6 caras); f_nlm=(c/2)*sqrt((nx/Lx)^2+(ny/Ly)^2+(nz/Lz)^2)",
    }


def _reverberation_sabine(volume_m3, surfaces):
    """surfaces: lista de {"area": m2, "alpha": coef. absorcion [0,1], "label": opcional}"""
    if not surfaces:
        raise ValueError("reverberation_sabine requiere 'surfaces' (lista no vacia)")
    total_absorption = 0.0
    breakdown = []
    for s in surfaces:
        area = s["area"]
        alpha = s["alpha"]
        if not (0.0 <= alpha <= 1.0):
            raise ValueError(f"coeficiente de absorcion fuera de rango [0,1]: {alpha}")
        a = area * alpha
        total_absorption += a
        breakdown.append({"label": s.get("label", ""), "area_m2": area, "alpha": alpha, "absorption_sabins": round(a, 4)})
    if total_absorption <= 0:
        raise ValueError("absorcion total <= 0, RT60 indefinido")
    rt60 = 0.161 * volume_m3 / total_absorption
    return {
        "mode": "reverberation_sabine",
        "volume_m3": volume_m3,
        "total_absorption_sabins": round(total_absorption, 4),
        "rt60_s": round(float(rt60), 4),
        "surfaces": breakdown,
        "formula": "RT60 = 0.161 * V / A  (Sabine, V en m3, A en sabins metricos)",
    }


def _validate():
    # 1) pressure_wave_1d: primer modo normal debe coincidir con la analitica
    pw = _pressure_wave_1d(L=1.0, c=343.0, n_points=80, preset="known_first_mode", boundary="dirichlet")
    # tolerancia acorde al error de truncacion O(dx^2, dt^2) del esquema explicito,
    # no O(1e-3) como en un solver espectral
    pw_ok = pw["max_error_vs_analytic"] < 1e-2

    # 2) room_modes: modo axial mas bajo de una habitacion 5x4x3 a 20C debe
    #    coincidir con f = c/(2*Lx) (nx=1,ny=0,nz=0), dimension mas larga -> modo mas bajo
    c = _sound_speed(20.0)
    rm = _room_modes(Lx=5.0, Ly=4.0, Lz=3.0, c=c, n_max=3, top_n=5)
    f_expected = c / (2.0 * 5.0)
    f_lowest = rm["lowest_modes"][0]["frequency_hz"]
    room_ok = abs(f_lowest - f_expected) < 0.01

    # 3) reverberation_sabine: sala muy absorbente (alpha=1 en todas las caras)
    #    debe dar RT60 chico; sala poco absorbente (alpha=0.05) debe dar RT60 grande
    surfaces_absorbent = [{"area": 94.0, "alpha": 1.0, "label": "todas las superficies"}]
    surfaces_reflective = [{"area": 94.0, "alpha": 0.05, "label": "todas las superficies"}]
    rt_absorbent = _reverberation_sabine(60.0, surfaces_absorbent)["rt60_s"]
    rt_reflective = _reverberation_sabine(60.0, surfaces_reflective)["rt60_s"]
    sabine_ok = rt_reflective > rt_absorbent

    return {
        "mode": "validate",
        "pressure_wave_1d": {"max_error_vs_analytic": pw["max_error_vs_analytic"], "passed": bool(pw_ok)},
        "room_modes": {
            "sound_speed_20C_ms": round(c, 3),
            "lowest_mode_expected_hz": round(f_expected, 3),
            "lowest_mode_computed_hz": f_lowest,
            "passed": bool(room_ok),
        },
        "reverberation_sabine": {
            "rt60_absorbent_s": rt_absorbent,
            "rt60_reflective_s": rt_reflective,
            "expected": "sala reflectante (alpha bajo) debe tener RT60 mayor que sala absorbente (alpha alto)",
            "passed": bool(sabine_ok),
        },
        "validation_passed": bool(pw_ok and room_ok and sabine_ok),
    }


def compute_acoustics_tool(mode="validate", params=None):
    params = params or {}
    if mode == "pressure_wave_1d":
        return _pressure_wave_1d(
            L=params.get("L", 1.0),
            c=params.get("c", 343.0),
            n_points=params.get("n_points", 100),
            t_final=params.get("t_final"),
            preset=params.get("preset", "known_first_mode"),
            initial_profile=params.get("initial_profile"),
            boundary=params.get("boundary", "dirichlet"),
        )
    elif mode == "room_modes":
        return _room_modes(
            Lx=params.get("Lx", 5.0),
            Ly=params.get("Ly", 4.0),
            Lz=params.get("Lz", 3.0),
            c=params.get("c", 343.0),
            n_max=params.get("n_max", 4),
            top_n=params.get("top_n", 15),
        )
    elif mode == "reverberation_sabine":
        return _reverberation_sabine(
            volume_m3=params["volume_m3"],
            surfaces=params["surfaces"],
        )
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


ACOUSTICS_TOOL_SCHEMA = {
    "name": "acoustics_tool",
    "description": (
        "Acustica: propagacion de ondas de presion 1D via FDTD (mode='pressure_wave_1d', "
        "bordes dirichlet/neumann, preset 'known_first_mode' valida contra solucion analitica); "
        "modos de resonancia de cavidades rectangulares rigidas (mode='room_modes', "
        "f_nlm=(c/2)*sqrt((nx/Lx)^2+(ny/Ly)^2+(nz/Lz)^2), clasificados axial/tangencial/oblicua); "
        "tiempo de reverberacion via formula de Sabine (mode='reverberation_sabine', "
        "RT60=0.161*V/A). Complementa infrasound_tool (atenuacion atmosferica a larga distancia) "
        "con acustica de interiores. mode='validate' corre los tres casos de referencia."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["pressure_wave_1d", "room_modes", "reverberation_sabine", "validate"],
                "default": "validate",
            },
            "params": {
                "type": "object",
                "description": (
                    "pressure_wave_1d: {L, c, n_points, t_final, preset, initial_profile, boundary}. "
                    "room_modes: {Lx, Ly, Lz, c, n_max, top_n}. "
                    "reverberation_sabine: {volume_m3, surfaces:[{area, alpha, label}]}."
                ),
            },
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_acoustics_tool("validate"), indent=2, ensure_ascii=False))
