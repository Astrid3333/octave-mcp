"""
gait_analysis_tool.py

Analisis de marcha en plano sagital (2D):
  - joint_angles: angulos articulares (cadera/rodilla/tobillo) a partir de
    trayectorias de marcadores (cadera, rodilla, tobillo, metatarso/toe, y
    hombro opcional para un angulo de cadera relativo al tronco).
  - inverse_dynamics: dinamica inversa de marcha via Newton-Euler recursivo
    distal->proximal (pie -> pierna/shank -> muslo/thigh), a partir de
    trayectorias de marcadores + fuerza de reaccion del suelo (GRF) aplicada
    en el marcador distal del pie (aproximacion de centro de presion), usando
    parametros antropometricos estandar (tabla de Winter: fraccion de masa,
    posicion del centro de masa y radio de giro por segmento, relativos al
    segmento proximal->distal).
  - validate: chequeo cerrado de la ecuacion de momento contra un segmento
    aislado en equilibrio estatico (muslo horizontal, fijo en cadera, extremo
    distal libre): M_cadera debe igualar peso * brazo_horizontal_al_COM.

Convenciones:
  - Todas las posiciones son series temporales de puntos 2D (x,y) en metros,
    eje y hacia arriba (vertical), eje x horizontal (direccion de progresion).
  - Angulos de segmento: arctan2(dy,dx) del vector proximal->distal.
  - angulo_rodilla = angulo_muslo - angulo_pierna (flexion positiva cuando el
    segmento distal rota hacia atras respecto al proximal).
  - angulo_tobillo = angulo_pie - angulo_pierna - 90 grados (offset para que
    0 sea la posicion neutra pie-perpendicular-a-pierna).
  - angulo_cadera: si se da marcador de hombro, angulo del tronco (cadera->
    hombro) menos angulo del muslo, menos 180 (0 = muslo colineal y alineado
    con el tronco hacia abajo); si no se da hombro, se reporta el angulo del
    muslo respecto a la horizontal global como proxy.
  - Momentos articulares en dinamica inversa: se reportan como el momento que
    el segmento PROXIMAL ejerce sobre el segmento DISTAL en cada articulacion
    (convencion de "momento de reaccion articular"); en equilibrio esto
    equivale al momento neto muscular+ligamentoso requerido en esa
    articulacion.
"""

import numpy as np
import tool_registry

G = 9.81

# Tabla antropometrica (Winter, "Biomechanics and Motor Control of Human
# Movement"): fraccion de masa corporal, posicion del COM como fraccion de
# la longitud del segmento medida desde el extremo PROXIMAL, y radio de giro
# alrededor del COM como fraccion de la longitud del segmento.
ANTHRO = {
    "foot":  {"mass_frac": 0.0145, "com_frac": 0.50,  "rog_frac": 0.475},
    "shank": {"mass_frac": 0.0465, "com_frac": 0.433, "rog_frac": 0.302},
    "thigh": {"mass_frac": 0.100,  "com_frac": 0.433, "rog_frac": 0.323},
}


def _arr(x):
    return np.asarray(x, dtype=float)


def _segment_angle(prox, dist):
    d = dist - prox
    return np.arctan2(d[..., 1], d[..., 0])


def _cross2d(r, f):
    # r, f: arrays (..., 2) -> escalar r_x*f_y - r_y*f_x
    return r[..., 0] * f[..., 1] - r[..., 1] * f[..., 0]


def _segment_kinematics(prox, dist, dt, body_mass, seg_key):
    """Cinematica de un segmento rigido (posicion, velocidad, aceleracion del
    COM; angulo, velocidad y aceleracion angular) mas sus propiedades de
    masa/inercia via la tabla antropometrica."""
    prox = _arr(prox)
    dist = _arr(dist)
    params = ANTHRO[seg_key]
    com_frac = params["com_frac"]
    length = np.linalg.norm(dist - prox, axis=-1)
    mean_length = float(np.mean(length))
    mass = params["mass_frac"] * body_mass
    I_com = mass * (params["rog_frac"] * mean_length) ** 2

    com = prox + com_frac * (dist - prox)
    if len(com) > 1:
        vel_com = np.gradient(com, dt, axis=0)
        acc_com = np.gradient(vel_com, dt, axis=0)
    else:
        vel_com = np.zeros_like(com)
        acc_com = np.zeros_like(com)

    angle = _segment_angle(prox, dist)
    angle_unwrapped = np.unwrap(angle) if len(angle) > 1 else angle
    if len(angle) > 1:
        omega = np.gradient(angle_unwrapped, dt)
        alpha = np.gradient(omega, dt)
    else:
        omega = np.zeros_like(angle)
        alpha = np.zeros_like(angle)

    unit = np.zeros_like(prox)
    nz = length > 1e-12
    unit[nz] = (dist[nz] - prox[nz]) / length[nz][:, None]

    r_prox_from_com = -com_frac * mean_length * unit
    r_dist_from_com = (1.0 - com_frac) * mean_length * unit

    return {
        "com": com, "mass": mass, "I_com": I_com,
        "acc_com": acc_com, "alpha": alpha,
        "r_prox_from_com": r_prox_from_com, "r_dist_from_com": r_dist_from_com,
        "length": length, "angle": angle,
    }


def _newton_euler_proximal(seg, F_distal, M_distal):
    """Dado un segmento (dict de _segment_kinematics) y la fuerza/momento
    conocidos en su extremo DISTAL (ejercidos sobre el segmento por el
    vecino distal o por el suelo), resuelve la fuerza y el momento en su
    extremo PROXIMAL que satisfacen Newton-Euler en cada instante."""
    m = seg["mass"]
    g_vec = np.array([0.0, -G])
    F_proximal = m * seg["acc_com"] - m * g_vec[None, :] - F_distal

    M_proximal = (
        seg["I_com"] * seg["alpha"]
        - M_distal
        - _cross2d(seg["r_dist_from_com"], F_distal)
        - _cross2d(seg["r_prox_from_com"], F_proximal)
    )
    return F_proximal, M_proximal


def compute_joint_angles(hip, knee, ankle, toe, shoulder=None):
    hip, knee, ankle, toe = _arr(hip), _arr(knee), _arr(ankle), _arr(toe)
    thigh_ang = _segment_angle(hip, knee)
    shank_ang = _segment_angle(knee, ankle)
    foot_ang = _segment_angle(ankle, toe)

    knee_angle_deg = np.degrees(thigh_ang - shank_ang)
    ankle_angle_deg = np.degrees(foot_ang - shank_ang) - 90.0

    if shoulder is not None:
        shoulder = _arr(shoulder)
        trunk_ang = _segment_angle(hip, shoulder)
        hip_angle_deg = np.degrees(trunk_ang - thigh_ang) - 180.0
        hip_reference = "trunk (hombro-cadera) menos muslo, 0=colineal extendido"
    else:
        hip_angle_deg = np.degrees(thigh_ang)
        hip_reference = "angulo del muslo respecto a la horizontal global (sin marcador de tronco)"

    n = len(hip)
    return {
        "mode": "joint_angles",
        "n_frames": n,
        "hip_angle_deg": [round(float(v), 4) for v in np.atleast_1d(hip_angle_deg)],
        "knee_angle_deg": [round(float(v), 4) for v in np.atleast_1d(knee_angle_deg)],
        "ankle_angle_deg": [round(float(v), 4) for v in np.atleast_1d(ankle_angle_deg)],
        "hip_angle_reference": hip_reference,
        "conventions": {
            "knee": "angulo_muslo - angulo_pierna (flexion positiva)",
            "ankle": "angulo_pie - angulo_pierna - 90 (0=neutro perpendicular)",
        },
    }


def compute_inverse_dynamics(hip, knee, ankle, toe, dt, body_mass, grf,
                              cop=None, free_moment=None):
    hip, knee, ankle, toe = _arr(hip), _arr(knee), _arr(ankle), _arr(toe)
    grf = _arr(grf)
    n = len(hip)
    cop = _arr(cop) if cop is not None else toe
    M_ground = _arr(free_moment) if free_moment is not None else np.zeros(n)

    foot = _segment_kinematics(ankle, toe, dt, body_mass, "foot")
    shank = _segment_kinematics(knee, ankle, dt, body_mass, "shank")
    thigh = _segment_kinematics(hip, knee, dt, body_mass, "thigh")

    # --- Pie: fuerza/momento distal conocidos = GRF aplicada en cop ---
    r_cop_from_com = cop - foot["com"]
    F_distal_foot = grf
    M_distal_foot = M_ground + _cross2d(r_cop_from_com - foot["r_dist_from_com"], grf)
    # nota: si cop coincide con el marcador distal (toe), r_cop_from_com ==
    # r_dist_from_com y el termino cruzado extra se anula.
    F_ankle_prox, M_ankle = _newton_euler_proximal(foot, F_distal_foot, M_distal_foot)

    # --- Pierna: reaccion de Newton en el tobillo = -(fuerza/momento que
    # la pierna ejerce sobre el pie) ---
    F_distal_shank = -F_ankle_prox
    M_distal_shank = -M_ankle
    F_knee_prox, M_knee = _newton_euler_proximal(shank, F_distal_shank, M_distal_shank)

    # --- Muslo ---
    F_distal_thigh = -F_knee_prox
    M_distal_thigh = -M_knee
    F_hip_prox, M_hip = _newton_euler_proximal(thigh, F_distal_thigh, M_distal_thigh)

    def _fmt_vec(v):
        return [[round(float(a), 4), round(float(b), 4)] for a, b in v]

    def _fmt_scalar(v):
        return [round(float(x), 4) for x in np.atleast_1d(v)]

    return {
        "mode": "inverse_dynamics",
        "n_frames": n,
        "ankle_moment_Nm": _fmt_scalar(M_ankle),
        "knee_moment_Nm": _fmt_scalar(M_knee),
        "hip_moment_Nm": _fmt_scalar(M_hip),
        "ankle_joint_force_N": _fmt_vec(F_ankle_prox),
        "knee_joint_force_N": _fmt_vec(F_knee_prox),
        "hip_joint_force_N": _fmt_vec(F_hip_prox),
        "segment_masses_kg": {
            "foot": round(float(foot["mass"]), 4),
            "shank": round(float(shank["mass"]), 4),
            "thigh": round(float(thigh["mass"]), 4),
        },
        "moment_convention": "momento ejercido por el segmento proximal sobre el distal en cada articulacion (= momento neto muscular+ligamentoso en equilibrio)",
    }


def _static_single_segment_check():
    """Chequeo cerrado: muslo horizontal, fijo en cadera, extremo (rodilla)
    libre (sin fuerza aplicada), en reposo total (a=0, alpha=0). La
    ecuacion de Newton-Euler debe reproducir el resultado de estatica
    elemental: M_cadera = peso_muslo * distancia_horizontal_cadera-COM.
    """
    body_mass = 70.0
    n = 5
    hip = np.tile([0.0, 0.9], (n, 1))
    length = 0.45
    knee = np.tile([length, 0.9], (n, 1))  # muslo horizontal, apuntando en +x
    dt = 0.01

    thigh = _segment_kinematics(hip, knee, dt, body_mass, "thigh")
    F_distal = np.zeros((n, 2))  # extremo (rodilla) libre, sin fuerza aplicada
    M_distal = np.zeros(n)
    F_prox, M_prox = _newton_euler_proximal(thigh, F_distal, M_distal)

    mass = ANTHRO["thigh"]["mass_frac"] * body_mass
    com_frac = ANTHRO["thigh"]["com_frac"]
    expected_M = mass * G * (com_frac * length)  # peso * brazo horizontal
    expected_Fy = mass * G  # la cadera debe soportar todo el peso (Fy hacia arriba)

    mid = n // 2
    err_M = abs(float(M_prox[mid]) - expected_M)
    err_Fy = abs(float(F_prox[mid][1]) - expected_Fy)
    err_Fx = abs(float(F_prox[mid][0]))

    return {
        "name": "static_single_segment_thigh_hip_moment",
        "expected_hip_moment_Nm": round(expected_M, 6),
        "computed_hip_moment_Nm": round(float(M_prox[mid]), 6),
        "error_moment": round(err_M, 8),
        "expected_hip_Fy_N": round(expected_Fy, 6),
        "computed_hip_Fy_N": round(float(F_prox[mid][1]), 6),
        "error_Fy": round(err_Fy, 8),
        "error_Fx": round(err_Fx, 8),
        "passed": bool(err_M < 1e-3 and err_Fy < 1e-3 and err_Fx < 1e-6),
    }


def _joint_angle_sanity_check():
    """Chequeo: si cadera, rodilla y tobillo estan colineales (pierna
    perfectamente extendida), el angulo de rodilla debe ser 0."""
    hip = [[0.0, 1.0]]
    knee = [[0.0, 0.5]]
    ankle = [[0.0, 0.0]]
    toe = [[0.15, 0.0]]  # pie perpendicular a la pierna (posicion neutra)
    res = compute_joint_angles(hip, knee, ankle, toe)
    knee_err = abs(res["knee_angle_deg"][0])
    ankle_err = abs(res["ankle_angle_deg"][0])
    return {
        "name": "joint_angles_collinear_leg_zero_knee",
        "knee_angle_deg": res["knee_angle_deg"][0],
        "ankle_angle_deg": res["ankle_angle_deg"][0],
        "error_knee": round(knee_err, 8),
        "error_ankle": round(ankle_err, 8),
        "passed": bool(knee_err < 1e-6 and ankle_err < 1e-6),
    }


def validate():
    checks = [_static_single_segment_check(), _joint_angle_sanity_check()]
    return {
        "mode": "validate",
        "checks": checks,
        "validation_passed": all(c["passed"] for c in checks),
    }


def compute_gait_analysis(mode="validate", **kwargs):
    if mode == "joint_angles":
        return compute_joint_angles(**kwargs)
    elif mode == "inverse_dynamics":
        return compute_inverse_dynamics(**kwargs)
    elif mode == "validate":
        return validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


GAIT_ANALYSIS_TOOL_SCHEMA = {
    "name": "gait_analysis_tool",
    "description": (
        "Analisis de marcha en plano sagital 2D: angulos articulares de "
        "cadera/rodilla/tobillo a partir de trayectorias de marcadores "
        "(joint_angles), y dinamica inversa via Newton-Euler recursivo "
        "distal->proximal para momentos y fuerzas articulares usando "
        "antropometria estandar de Winter (inverse_dynamics). mode=validate "
        "corre un chequeo cerrado contra estatica elemental de un segmento "
        "aislado."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["joint_angles", "inverse_dynamics", "validate"]},
            "hip": {"type": "array", "description": "serie temporal de posiciones [x,y] del marcador de cadera"},
            "knee": {"type": "array"},
            "ankle": {"type": "array"},
            "toe": {"type": "array"},
            "shoulder": {"type": "array", "description": "opcional, para angulo de cadera relativo al tronco"},
            "dt": {"type": "number", "description": "paso de tiempo entre frames, en segundos"},
            "body_mass": {"type": "number", "description": "masa corporal total en kg"},
            "grf": {"type": "array", "description": "serie temporal de fuerza de reaccion del suelo [Fx,Fy] en N"},
            "cop": {"type": "array", "description": "opcional, centro de presion; por defecto usa el marcador toe"},
            "free_moment": {"type": "array", "description": "opcional, momento libre del suelo por frame (Nm); por defecto 0"},
        },
        "required": ["mode"],
    },
}


def _handler(args):
    args = dict(args or {})
    mode = args.pop("mode", "validate")
    params = args.pop("params", None) or {}
    merged = {**params, **args}
    return compute_gait_analysis(mode=mode, **merged)


tool_registry.register_tool("gait_analysis_tool", GAIT_ANALYSIS_TOOL_SCHEMA, _handler)


if __name__ == "__main__":
    import json
    print(json.dumps(validate(), indent=2, ensure_ascii=False))
