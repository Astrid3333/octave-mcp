"""
survey_tools.py
Herramientas matemáticas de topografía para octave-mcp.
Patrón: una función compute_X(mode, **params) por dominio, numpy puro.
Ángulos de entrada/salida en grados salvo que se indique lo contrario.
"""

import numpy as np


# ---------------------------------------------------------------------------
# 1. ÁNGULOS Y DIRECCIONES
# ---------------------------------------------------------------------------
def compute_survey_angles(mode, **params):
    if mode == "bearing_azimuth":
        de = float(params["delta_e"])
        dn = float(params["delta_n"])
        output = params.get("output", "both")

        az = (np.degrees(np.arctan2(de, dn))) % 360.0

        # rumbo cuadrantal (bearing) a partir del azimut
        if 0 <= az <= 90:
            quad, ref = "NE", az
        elif 90 < az <= 180:
            quad, ref = "SE", 180 - az
        elif 180 < az <= 270:
            quad, ref = "SW", az - 180
        else:
            quad, ref = "NW", 360 - az

        deg = int(ref)
        minutes_full = (ref - deg) * 60
        minu = int(minutes_full)
        sec = round((minutes_full - minu) * 60, 2)
        bearing_str = f"N{deg}°{minu}'{sec}\"E" if quad == "NE" else \
                      f"S{deg}°{minu}'{sec}\"E" if quad == "SE" else \
                      f"S{deg}°{minu}'{sec}\"W" if quad == "SW" else \
                      f"N{deg}°{minu}'{sec}\"W"

        result = {}
        if output in ("both", "azimuth"):
            result["azimuth_deg"] = az
        if output in ("both", "bearing"):
            result["bearing_quadrant"] = quad
            result["bearing_angle_deg"] = ref
            result["bearing_str"] = bearing_str
        return result

    elif mode == "angle_closure":
        angles = np.array(params["angles"], dtype=float)  # grados, ángulos interiores medidos
        n = int(params.get("n", len(angles)))
        theoretical_sum = (n - 2) * 180.0
        measured_sum = float(np.sum(angles))
        misclosure = measured_sum - theoretical_sum
        correction_per_angle = -misclosure / n
        adjusted_angles = (angles + correction_per_angle).tolist()
        return {
            "n": n,
            "theoretical_sum_deg": theoretical_sum,
            "measured_sum_deg": measured_sum,
            "misclosure_deg": misclosure,
            "correction_per_angle_deg": correction_per_angle,
            "adjusted_angles_deg": adjusted_angles,
        }

    elif mode == "mean_angle_reduction":
        face_left = np.array(params["face_left"], dtype=float)   # grados
        face_right = np.array(params["face_right"], dtype=float)  # grados

        if len(face_left) != len(face_right):
            raise ValueError("face_left y face_right deben tener igual longitud")

        # normaliza FR restando (o sumando) 180° para que quede en el mismo círculo que FL
        fr_norm = np.where(face_right >= 180.0, face_right - 180.0, face_right + 180.0)
        mean_angles = ((face_left + fr_norm) / 2.0) % 360.0
        spread = np.abs(face_left - fr_norm)

        return {
            "mean_angles_deg": mean_angles.tolist(),
            "fl_fr_spread_deg": spread.tolist(),
            "overall_mean_deg": float(np.mean(mean_angles)),
        }

    else:
        raise ValueError(f"Modo desconocido para survey_angles: {mode}")


# ---------------------------------------------------------------------------
# 2. DISTANCIAS Y CORRECCIONES
# ---------------------------------------------------------------------------
def compute_survey_distance(mode, **params):
    if mode == "slope_correction":
        L = float(params["slope_distance"])
        method = params.get("method", "angle")

        if method == "angle":
            theta = np.radians(float(params["angle_deg"]))
            correction = L * (1 - np.cos(theta))
            horizontal_distance = L * np.cos(theta)
        elif method == "height":
            h = float(params["height_diff"])
            correction_approx = (h ** 2) / (2 * L)
            horizontal_distance_exact = np.sqrt(max(L ** 2 - h ** 2, 0.0))
            return {
                "slope_distance": L,
                "height_diff": h,
                "correction_approx": correction_approx,
                "horizontal_distance_exact": horizontal_distance_exact,
                "horizontal_distance_approx": L - correction_approx,
            }
        else:
            raise ValueError("method debe ser 'angle' o 'height'")

        return {
            "slope_distance": L,
            "angle_deg": params["angle_deg"],
            "correction": correction,
            "horizontal_distance": horizontal_distance,
        }

    elif mode == "stadia":
        k = float(params.get("k", 100.0))     # factor de intervalo estadimétrico
        s = float(params["s"])                # intercepto de mira
        theta = np.radians(float(params["angle_deg"]))  # ángulo vertical desde horizontal
        c = float(params.get("c", 0.0))       # constante instrumental

        horizontal_distance = k * s * (np.cos(theta) ** 2) + c * np.cos(theta)
        vertical_component = (k * s / 2.0) * np.sin(2 * theta) + c * np.sin(theta)

        return {
            "k": k, "s": s, "angle_deg": params["angle_deg"], "c": c,
            "horizontal_distance": horizontal_distance,
            "vertical_component": vertical_component,
        }

    elif mode == "edm_correction":
        Dm = float(params["measured_distance"])
        delta_n = float(params["delta_n"])       # variación de índice de refracción (ppm o fracción)
        n0 = float(params.get("n0", 1.0))
        Dc = Dm * (1 + delta_n / n0)
        return {
            "measured_distance": Dm,
            "delta_n": delta_n,
            "n0": n0,
            "corrected_distance": Dc,
            "correction": Dc - Dm,
        }

    else:
        raise ValueError(f"Modo desconocido para survey_distance: {mode}")


# ---------------------------------------------------------------------------
# 3. CURVATURA Y REFRACCIÓN
# ---------------------------------------------------------------------------
def compute_survey_curvature(mode="curvature_refraction", **params):
    if mode != "curvature_refraction":
        raise ValueError(f"Modo desconocido para survey_curvature: {mode}")

    theta_obs = float(params["observed_angle_deg"])
    d = float(params["distance"])                  # metros
    k = float(params.get("k", 0.13))                # coeficiente de refracción promedio
    R = float(params.get("R", 6371000.0))           # radio terrestre, m
    sign = 1.0 if params.get("direction", "add") == "add" else -1.0

    correction_rad = (1 - k) * d / (2 * R)
    correction_deg = np.degrees(correction_rad)
    correction_arcsec = correction_deg * 3600.0

    theta_corr = theta_obs + sign * correction_deg

    return {
        "observed_angle_deg": theta_obs,
        "distance_m": d,
        "k": k,
        "R_m": R,
        "correction_deg": correction_deg,
        "correction_arcsec": correction_arcsec,
        "corrected_angle_deg": theta_corr,
    }


# ---------------------------------------------------------------------------
# 4. POLIGONALES Y AJUSTES
# ---------------------------------------------------------------------------
def _traverse_deltas(sides):
    """sides: lista de {'length':L, 'bearing_deg':az} (az = azimut desde norte, 0-360)."""
    lengths = np.array([s["length"] for s in sides], dtype=float)
    azimuths = np.radians([s["bearing_deg"] for s in sides])
    de = lengths * np.sin(azimuths)
    dn = lengths * np.cos(azimuths)
    return lengths, de, dn


def compute_traverse_adjustment(mode, **params):
    sides = params.get("sides")

    if mode == "linear_misclosure":
        lengths, de, dn = _traverse_deltas(sides)
        sum_de, sum_dn = float(np.sum(de)), float(np.sum(dn))
        E = float(np.hypot(sum_de, sum_dn))
        return {"sum_delta_e": sum_de, "sum_delta_n": sum_dn, "linear_misclosure": E}

    elif mode == "relative_accuracy":
        lengths, de, dn = _traverse_deltas(sides)
        sum_de, sum_dn = float(np.sum(de)), float(np.sum(dn))
        E = float(np.hypot(sum_de, sum_dn))
        P = float(np.sum(lengths))
        RA = E / P if P else float("nan")
        denom = (P / E) if E else float("inf")
        return {
            "linear_misclosure": E, "perimeter": P,
            "relative_accuracy": RA,
            "relative_accuracy_ratio": f"1:{denom:.0f}" if np.isfinite(denom) else "1:inf",
        }

    elif mode == "closure_check":
        lengths, de, dn = _traverse_deltas(sides)
        n = len(sides)
        angles = params.get("angles")  # opcional, ángulos interiores medidos
        out = {
            "sum_delta_e": float(np.sum(de)),
            "sum_delta_n": float(np.sum(dn)),
            "closes_linearly": bool(np.isclose(np.sum(de), 0, atol=params.get("tol", 1e-3)) and
                                     np.isclose(np.sum(dn), 0, atol=params.get("tol", 1e-3))),
        }
        if angles is not None:
            angles = np.array(angles, dtype=float)
            theoretical_sum = (n - 2) * 180.0
            out["angular_misclosure_deg"] = float(np.sum(angles) - theoretical_sum)
        return out

    elif mode in ("bowditch", "transit_rule", "full_traverse"):
        lengths, de, dn = _traverse_deltas(sides)
        sum_de, sum_dn = float(np.sum(de)), float(np.sum(dn))
        P = float(np.sum(lengths))
        E = float(np.hypot(sum_de, sum_dn))

        if mode in ("bowditch", "full_traverse"):
            corr_e_bow = -sum_de * (lengths / P)
            corr_n_bow = -sum_dn * (lengths / P)
            adj_de_bow = de + corr_e_bow
            adj_dn_bow = dn + corr_n_bow

        if mode in ("transit_rule", "full_traverse"):
            abs_de_sum = np.sum(np.abs(de)) or 1.0
            abs_dn_sum = np.sum(np.abs(dn)) or 1.0
            corr_e_tr = -sum_de * (np.abs(de) / abs_de_sum)
            corr_n_tr = -sum_dn * (np.abs(dn) / abs_dn_sum)
            adj_de_tr = de + corr_e_tr
            adj_dn_tr = dn + corr_n_tr

        start_e = float(params.get("start_e", 0.0))
        start_n = float(params.get("start_n", 0.0))

        result = {
            "perimeter": P,
            "linear_misclosure": E,
            "relative_accuracy_ratio": f"1:{(P/E):.0f}" if E else "1:inf",
        }

        if mode == "bowditch":
            coords_e = start_e + np.cumsum(adj_de_bow)
            coords_n = start_n + np.cumsum(adj_dn_bow)
            result.update({
                "adjusted_delta_e": adj_de_bow.tolist(),
                "adjusted_delta_n": adj_dn_bow.tolist(),
                "adjusted_coords": list(zip(coords_e.tolist(), coords_n.tolist())),
            })
        elif mode == "transit_rule":
            coords_e = start_e + np.cumsum(adj_de_tr)
            coords_n = start_n + np.cumsum(adj_dn_tr)
            result.update({
                "adjusted_delta_e": adj_de_tr.tolist(),
                "adjusted_delta_n": adj_dn_tr.tolist(),
                "adjusted_coords": list(zip(coords_e.tolist(), coords_n.tolist())),
            })
        else:  # full_traverse: ambos métodos para comparar
            coords_e_bow = start_e + np.cumsum(adj_de_bow)
            coords_n_bow = start_n + np.cumsum(adj_dn_bow)
            coords_e_tr = start_e + np.cumsum(adj_de_tr)
            coords_n_tr = start_n + np.cumsum(adj_dn_tr)
            result.update({
                "bowditch": {
                    "adjusted_delta_e": adj_de_bow.tolist(),
                    "adjusted_delta_n": adj_dn_bow.tolist(),
                    "adjusted_coords": list(zip(coords_e_bow.tolist(), coords_n_bow.tolist())),
                },
                "transit_rule": {
                    "adjusted_delta_e": adj_de_tr.tolist(),
                    "adjusted_delta_n": adj_dn_tr.tolist(),
                    "adjusted_coords": list(zip(coords_e_tr.tolist(), coords_n_tr.tolist())),
                },
            })
        return result

    else:
        raise ValueError(f"Modo desconocido para traverse_adjustment: {mode}")


# ---------------------------------------------------------------------------
# 5. CURVAS HORIZONTALES Y VERTICALES
# ---------------------------------------------------------------------------
def compute_survey_curves(mode, **params):
    if mode == "horizontal_circular":
        R = float(params["radius"])
        delta = float(params["delta_deg"])
        delta_rad = np.radians(delta)

        T = R * np.tan(delta_rad / 2)
        L = R * delta_rad
        E = R * (1 / np.cos(delta_rad / 2) - 1)   # externa
        M = R * (1 - np.cos(delta_rad / 2))        # ordenada media
        C = 2 * R * np.sin(delta_rad / 2)           # cuerda larga

        return {
            "radius": R, "delta_deg": delta,
            "tangent": T, "arc_length": L,
            "external": E, "mid_ordinate": M, "chord": C,
        }

    elif mode == "vertical_parabolic":
        g1 = float(params["g1_pct"])   # pendiente de entrada, %
        g2 = float(params["g2_pct"])   # pendiente de salida, %
        L = float(params["length"])    # longitud de la curva
        elev_pvi = float(params["elev_pvi"])
        station_pvi = float(params.get("station_pvi", 0.0))

        station_pvc = station_pvi - L / 2
        station_pvt = station_pvi + L / 2
        elev_pvc = elev_pvi - (g1 / 100.0) * (L / 2)
        elev_pvt = elev_pvi + (g2 / 100.0) * (L / 2)
        r = (g2 - g1) / L  # tasa de cambio de pendiente, %/estación-unidad

        out = {
            "g1_pct": g1, "g2_pct": g2, "length": L,
            "station_pvc": station_pvc, "station_pvi": station_pvi, "station_pvt": station_pvt,
            "elev_pvc": elev_pvc, "elev_pvi": elev_pvi, "elev_pvt": elev_pvt,
            "rate_of_change_pct_per_unit": r,
        }

        # punto alto/bajo, si existe (g1 y g2 de signo opuesto)
        if g1 != g2:
            x_turn = -g1 * L / (g2 - g1)  # medido desde PVC
            if 0 <= x_turn <= L:
                elev_turn = elev_pvc + (g1 / 100.0) * x_turn + (r / (2 * L)) * (x_turn ** 2) * 100.0
                # nota: fórmula en unidades consistentes; ver evaluación puntual abajo para exactitud
                out["turning_point_station"] = station_pvc + x_turn
                out["turning_point_offset_from_pvc"] = x_turn

        x_eval = params.get("x_from_pvc")
        if x_eval is not None:
            x_eval = float(x_eval)
            elev_x = elev_pvc + (g1 / 100.0) * x_eval + ((g2 - g1) / 100.0) / (2 * L) * (x_eval ** 2)
            out["x_from_pvc"] = x_eval
            out["elevation_at_x"] = elev_x

        return out

    else:
        raise ValueError(f"Modo desconocido para survey_curves: {mode}")


# ---------------------------------------------------------------------------
# 6. ÁREAS Y VOLÚMENES
# ---------------------------------------------------------------------------
def compute_survey_area_volume(mode, **params):
    if mode == "polygon_shoelace":
        points = np.array(params["points"], dtype=float)  # [[x,y], ...]
        x, y = points[:, 0], points[:, 1]
        x_next = np.roll(x, -1)
        y_next = np.roll(y, -1)
        area = 0.5 * abs(np.sum(x * y_next - x_next * y))
        return {"n_points": len(points), "area": float(area)}

    elif mode == "earthwork_avg_end_area":
        areas = np.array(params["areas"], dtype=float)
        if "distances" in params:
            distances = np.array(params["distances"], dtype=float)
        else:
            interval = float(params["station_interval"])
            distances = np.full(len(areas) - 1, interval)

        if len(distances) != len(areas) - 1:
            raise ValueError("distances debe tener len(areas)-1 elementos")

        volumes = (areas[:-1] + areas[1:]) / 2.0 * distances
        return {
            "segment_volumes": volumes.tolist(),
            "total_volume": float(np.sum(volumes)),
        }

    elif mode == "contour_volume":
        areas = np.array(params["contour_areas"], dtype=float)
        h = float(params["contour_interval"])
        method = params.get("method", "average_end_area")

        if method == "average_end_area":
            volumes = (areas[:-1] + areas[1:]) / 2.0 * h
            total = float(np.sum(volumes))
        elif method == "prismoidal":
            # requiere número impar de áreas (pares de segmentos con área intermedia)
            if len(areas) < 3 or len(areas) % 2 == 0:
                raise ValueError("prismoidal requiere un número impar de áreas (>=3)")
            total = 0.0
            volumes = []
            for i in range(0, len(areas) - 2, 2):
                v = (h / 3.0) * (areas[i] + 4 * areas[i + 1] + areas[i + 2])
                volumes.append(v)
                total += v
        elif method == "cone_bottom":
            # último segmento tratado como cono si el área final tiende a 0
            volumes = ((areas[:-1] + areas[1:]) / 2.0 * h).tolist()
            if areas[-1] > 0:
                volumes[-1] = (h / 3.0) * areas[-2]  # aproximación cono
            total = float(np.sum(volumes))
        else:
            raise ValueError("method debe ser 'average_end_area', 'prismoidal' o 'cone_bottom'")

        return {"method": method, "segment_volumes": volumes if isinstance(volumes, list) else volumes.tolist(),
                "total_volume": total}

    else:
        raise ValueError(f"Modo desconocido para survey_area_volume: {mode}")


# ---------------------------------------------------------------------------
# SCHEMAS (para TOOLS list en server.py)
# ---------------------------------------------------------------------------
SURVEY_ANGLES_TOOL_SCHEMA = {
    "name": "survey_angles_tool",
    "description": "Angulos y direcciones topograficas: bearing/azimut desde coordenadas, cierre angular de poligono, reduccion de angulos face-left/face-right.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["bearing_azimuth", "angle_closure", "mean_angle_reduction"]},
            "delta_e": {"type": "number"},
            "delta_n": {"type": "number"},
            "output": {"type": "string", "enum": ["both", "bearing", "azimuth"]},
            "angles": {"type": "array", "items": {"type": "number"}},
            "n": {"type": "integer"},
            "face_left": {"type": "array", "items": {"type": "number"}},
            "face_right": {"type": "array", "items": {"type": "number"}},
        },
        "required": ["mode"],
    },
}

SURVEY_DISTANCE_TOOL_SCHEMA = {
    "name": "survey_distance_tool",
    "description": "Correcciones de distancia: pendiente a horizontal, taquimetria/estadia, correccion EDM por indice de refraccion.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["slope_correction", "stadia", "edm_correction"]},
            "slope_distance": {"type": "number"},
            "angle_deg": {"type": "number"},
            "method": {"type": "string", "enum": ["angle", "height"]},
            "height_diff": {"type": "number"},
            "k": {"type": "number"},
            "s": {"type": "number"},
            "c": {"type": "number"},
            "measured_distance": {"type": "number"},
            "delta_n": {"type": "number"},
            "n0": {"type": "number"},
        },
        "required": ["mode"],
    },
}

SURVEY_CURVATURE_TOOL_SCHEMA = {
    "name": "survey_curvature_tool",
    "description": "Correccion combinada de curvatura terrestre y refraccion para angulos verticales observados.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["curvature_refraction"]},
            "observed_angle_deg": {"type": "number"},
            "distance": {"type": "number"},
            "k": {"type": "number"},
            "R": {"type": "number"},
            "direction": {"type": "string", "enum": ["add", "subtract"]},
        },
        "required": ["mode", "observed_angle_deg", "distance"],
    },
}

TRAVERSE_ADJUSTMENT_TOOL_SCHEMA = {
    "name": "traverse_adjustment_tool",
    "description": "Ajuste de poligonales: regla de Bowditch, regla del transito, cierre lineal, precision relativa, o full_traverse con ambos metodos.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["bowditch", "transit_rule", "closure_check", "linear_misclosure", "relative_accuracy", "full_traverse"],
            },
            "sides": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "length": {"type": "number"},
                        "bearing_deg": {"type": "number"},
                    },
                    "required": ["length", "bearing_deg"],
                },
            },
            "angles": {"type": "array", "items": {"type": "number"}},
            "start_e": {"type": "number"},
            "start_n": {"type": "number"},
            "tol": {"type": "number"},
        },
        "required": ["mode", "sides"],
    },
}

SURVEY_CURVES_TOOL_SCHEMA = {
    "name": "survey_curves_tool",
    "description": "Elementos de curva circular horizontal (T, L, E, M, cuerda) o curva vertical parabolica (elevaciones, punto alto/bajo).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["horizontal_circular", "vertical_parabolic"]},
            "radius": {"type": "number"},
            "delta_deg": {"type": "number"},
            "g1_pct": {"type": "number"},
            "g2_pct": {"type": "number"},
            "length": {"type": "number"},
            "elev_pvi": {"type": "number"},
            "station_pvi": {"type": "number"},
            "x_from_pvc": {"type": "number"},
        },
        "required": ["mode"],
    },
}

SURVEY_AREA_VOLUME_TOOL_SCHEMA = {
    "name": "survey_area_volume_tool",
    "description": "Area por coordenadas (shoelace), volumen de movimiento de tierra por area media entre secciones, volumen entre curvas de nivel.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["polygon_shoelace", "earthwork_avg_end_area", "contour_volume"]},
            "points": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
            "areas": {"type": "array", "items": {"type": "number"}},
            "distances": {"type": "array", "items": {"type": "number"}},
            "station_interval": {"type": "number"},
            "contour_areas": {"type": "array", "items": {"type": "number"}},
            "contour_interval": {"type": "number"},
            "method": {"type": "string", "enum": ["average_end_area", "prismoidal", "cone_bottom"]},
        },
        "required": ["mode"],
    },
}
