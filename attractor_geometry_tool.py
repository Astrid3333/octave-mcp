"""
attractor_geometry_tool.py -- Geometria diferencial de trayectorias sobre
atractores caoticos: curvatura, torsion, y discriminacion de zonas de
movimiento lento vs. rapido.

Contexto: es el tercer eje del documento sobre atractores caoticos que
disparo esta serie de tools (junto con chaos_diagnosis_tool para
lambda1/significancia estadistica y correlation_dimension_tool para D2).
A diferencia de esos dos, esta tool no mide "es caotico" -- mide la
estructura geometrica local de una trayectoria ya generada: que tan curvada
esta en cada punto (curvatura kappa), que tanto se tuerce fuera del plano
osculador (torsion tau), y donde el sistema se mueve rapido vs. lento
(util para, por ejemplo, distinguir el tiempo que un sistema pasa cerca de
cada "ala" del atractor de Lorenz de el tiempo que pasa en la transicion
entre alas).

Formulas estandar (Frenet-Serret) para una curva parametrizada r(t):
    velocidad v = r'
    aceleracion a = r''
    jerk j = r'''
    kappa = |v x a| / |v|^3
    tau   = (v x a) . j / |v x a|^2

Las derivadas se estiman por diferencias finitas centradas (con forward/
backward en los bordes) a partir de la trayectoria discreta y su dt -- no
se asume forma analitica del sistema que genero la trayectoria, para que
esta tool sirva sobre CUALQUIER trayectoria 3D (Lorenz, Hastings-Powell
levantado a 3D, datos experimentales, etc.), no solo sobre Lorenz.

El modo 'lorenz_demo' genera la trayectoria via lorenz_tool.compute_lorenz
en vez de reimplementar la integracion -- mismo criterio de no-duplicacion
que uso correlation_dimension_tool con _lorenz_series.
"""

import math

try:
    from lorenz_tool import compute_lorenz
except ImportError:
    compute_lorenz = None


# ---------------------------------------------------------------------------
# Algebra vectorial minima (3D)
# ---------------------------------------------------------------------------

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    return math.sqrt(_dot(a, a))


# ---------------------------------------------------------------------------
# Derivadas por diferencias finitas
# ---------------------------------------------------------------------------

def _derivative(points, dt):
    """Diferencias finitas centradas en el interior, forward/backward en
    los bordes. points: lista de tuplas 3D. Devuelve lista de la misma
    longitud."""
    n = len(points)
    out = [None] * n
    if n < 2:
        return [(0.0, 0.0, 0.0)] * n
    out[0] = tuple((points[1][k] - points[0][k]) / dt for k in range(3))
    out[n - 1] = tuple((points[n - 1][k] - points[n - 2][k]) / dt for k in range(3))
    for i in range(1, n - 1):
        out[i] = tuple((points[i + 1][k] - points[i - 1][k]) / (2 * dt) for k in range(3))
    return out


# ---------------------------------------------------------------------------
# Curvatura, torsion, velocidad (rapidez)
# ---------------------------------------------------------------------------

def _curvature_torsion(traj, dt):
    v = _derivative(traj, dt)
    a = _derivative(v, dt)
    j = _derivative(a, dt)

    speeds, curvaturas, torsiones = [], [], []
    for vi, ai, ji in zip(v, a, j):
        speed = _norm(vi)
        speeds.append(speed)

        cross_va = _cross(vi, ai)
        norm_cross = _norm(cross_va)

        kappa = (norm_cross / speed ** 3) if speed > 1e-9 else None
        curvaturas.append(kappa)

        tau = (_dot(cross_va, ji) / norm_cross ** 2) if norm_cross > 1e-9 else None
        torsiones.append(tau)

    return speeds, curvaturas, torsiones


def _clasificar_zonas(speeds, umbral_std=1.0):
    """Clasifica cada punto en 'zona_lenta' / 'intermedia' / 'zona_rapida'
    segun su rapidez relativa a la media +/- umbral_std desvios. No hay un
    umbral fisico universal -- es relativo a la propia trayectoria, lo que
    tiene sentido porque lo que interesa es DONDE dentro de este atractor
    en particular el sistema se mueve mas lento o mas rapido que su
    comportamiento tipico, no un valor absoluto comparable entre sistemas
    distintos."""
    n = len(speeds)
    mean_v = sum(speeds) / n
    var = sum((s - mean_v) ** 2 for s in speeds) / n
    std_v = math.sqrt(var)
    zonas = []
    for s in speeds:
        if std_v == 0:
            zonas.append("intermedia")
        elif s < mean_v - umbral_std * std_v:
            zonas.append("zona_lenta")
        elif s > mean_v + umbral_std * std_v:
            zonas.append("zona_rapida")
        else:
            zonas.append("intermedia")
    return zonas, mean_v, std_v


def _contar_cambios_de_signo(valores):
    """Cuenta cuantas veces la torsion cambia de signo a lo largo de la
    trayectoria (ignorando None). Relevante para atractores tipo Lorenz:
    la torsion cambia de signo cada vez que la trayectoria salta de una
    ala a la otra, asi que un numero de cambios > 0 es evidencia de
    estructura de dos lobulos, no una curva plana o de un solo lobulo."""
    limpios = [v for v in valores if v is not None]
    cambios = 0
    for a, b in zip(limpios, limpios[1:]):
        if a == 0 or b == 0:
            continue
        if (a > 0) != (b > 0):
            cambios += 1
    return cambios


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def compute_attractor_geometry(mode="trajectory", x=None, y=None, z=None, dt=1.0,
                                n_steps=6000, sigma=10.0, rho=28.0, beta=8.0 / 3.0,
                                y0=(1.0, 1.0, 1.0), discard=1000,
                                downsample_for_plot=1500,
                                umbral_std=1.0,
                                **kwargs):
    if mode == "validate":
        return _validate_attractor_geometry()

    if mode == "lorenz_demo":
        if compute_lorenz is None:
            return {"error": "lorenz_tool no disponible en este entorno."}
        r = compute_lorenz(mode="simulate", n_steps=n_steps, dt=dt, sigma=sigma,
                            rho=rho, beta=beta, y0=list(y0), discard=discard,
                            downsample_for_plot=n_steps)
        traj = [(p["x"], p["y"], p["z"]) for p in r["trajectory_sample"]]
    else:
        # mode == "trajectory": trayectoria provista por el usuario
        if not x or not y or not z:
            return {"error": "modo 'trajectory' requiere x, y, z (listas de igual longitud)."}
        if not (len(x) == len(y) == len(z)):
            return {"error": f"x, y, z deben tener la misma longitud (recibido {len(x)}, {len(y)}, {len(z)})."}
        if len(x) < 10:
            return {"error": f"trayectoria demasiado corta ({len(x)} puntos), se requieren al menos 10."}
        traj = list(zip(x, y, z))

    speeds, curvaturas, torsiones = _curvature_torsion(traj, dt)
    zonas, mean_v, std_v = _clasificar_zonas(speeds, umbral_std)
    cambios_signo_torsion = _contar_cambios_de_signo(torsiones)

    n = len(traj)
    frac_lenta = zonas.count("zona_lenta") / n
    frac_rapida = zonas.count("zona_rapida") / n
    frac_intermedia = zonas.count("intermedia") / n

    curv_validas = [k for k in curvaturas if k is not None]
    curvatura_promedio = sum(curv_validas) / len(curv_validas) if curv_validas else None

    # submuestreo para la respuesta (la trayectoria completa puede ser larga)
    n_show = min(n, downsample_for_plot)
    stride = max(1, n // n_show)
    idxs = list(range(0, n, stride))[:n_show]

    sample = []
    for i in idxs:
        sample.append({
            "x": traj[i][0], "y": traj[i][1], "z": traj[i][2],
            "rapidez": round(speeds[i], 6),
            "curvatura": round(curvaturas[i], 6) if curvaturas[i] is not None else None,
            "torsion": round(torsiones[i], 6) if torsiones[i] is not None else None,
            "zona": zonas[i],
        })

    return {
        "mode": mode,
        "n_points": n,
        "dt": dt,
        "rapidez_media": round(mean_v, 6),
        "rapidez_desvio": round(std_v, 6),
        "curvatura_promedio": round(curvatura_promedio, 6) if curvatura_promedio is not None else None,
        "torsion_cambios_de_signo": cambios_signo_torsion,
        "fracciones_zona": {
            "zona_lenta": round(frac_lenta, 4),
            "intermedia": round(frac_intermedia, 4),
            "zona_rapida": round(frac_rapida, 4),
        },
        "trajectory_sample": sample,
        "nota": (
            "zona_lenta/zona_rapida se definen relativo a la rapidez media +/- "
            "umbral_std desvios de ESTA trayectoria (no es un umbral absoluto "
            "comparable entre sistemas distintos). torsion_cambios_de_signo > 0 "
            "es evidencia de que la trayectoria alterna entre regiones "
            "geometricamente distintas (p.ej. las dos alas de Lorenz); una "
            "curva plana o de un solo lobulo tendria 0 cambios."
        ),
    }


def _validate_attractor_geometry() -> dict:
    """4 checks sobre la trayectoria de Lorenz clasica (via lorenz_demo,
    mismos params de referencia que usan lorenz_tool y correlation_dimension_
    tool): 1) curvatura y torsion sin NaN/inf en los puntos donde estan
    definidas (rapidez > 0). 2) curvatura promedio > 0 (una trayectoria
    genuinamente curva, no una linea recta degenerada). 3) existen tanto
    zona_lenta como zona_rapida con fraccion > 0 (hay variacion real de
    rapidez, no una trayectoria a velocidad constante). 4) la torsion
    cambia de signo al menos una vez (evidencia de estructura de dos alas,
    no un lobulo unico o una curva plana con torsion identicamente nula)."""
    checks = []

    if compute_lorenz is None:
        return {
            "mode": "validate", "validation_passed": False,
            "checks": [{"name": "lorenz_tool disponible", "passed": False,
                        "got": {"error": "lorenz_tool no disponible en este entorno"}}],
        }

    r = compute_attractor_geometry(mode="lorenz_demo", n_steps=6000, dt=0.01, discard=1000,
                                    downsample_for_plot=6000)
    if "error" in r:
        return {"mode": "validate", "validation_passed": False,
                "checks": [{"name": "lorenz_demo: sin error", "passed": False, "got": r}]}

    curvaturas = [p["curvatura"] for p in r["trajectory_sample"]]
    torsiones = [p["torsion"] for p in r["trajectory_sample"]]

    finitas = all(math.isfinite(k) for k in curvaturas if k is not None) and \
              all(math.isfinite(t) for t in torsiones if t is not None)
    checks.append({
        "name": "lorenz: curvatura/torsion finitas donde estan definidas",
        "passed": finitas,
        "got": {"n_points": r["n_points"]},
    })

    checks.append({
        "name": "lorenz: curvatura_promedio > 0 (trayectoria genuinamente curva)",
        "passed": bool(r["curvatura_promedio"] is not None and r["curvatura_promedio"] > 0),
        "got": {"curvatura_promedio": r["curvatura_promedio"]},
    })

    frac = r["fracciones_zona"]
    hay_variacion = frac["zona_lenta"] > 0 and frac["zona_rapida"] > 0
    checks.append({
        "name": "lorenz: existen zona_lenta y zona_rapida (variacion real de rapidez)",
        "passed": hay_variacion,
        "got": {"fracciones_zona": frac},
    })

    checks.append({
        "name": "lorenz: torsion cambia de signo al menos una vez (estructura de dos alas)",
        "passed": bool(r["torsion_cambios_de_signo"] > 0),
        "got": {"torsion_cambios_de_signo": r["torsion_cambios_de_signo"]},
    })

    return {"mode": "validate", "validation_passed": all(c["passed"] for c in checks), "checks": checks}


# ---------------------------------------------------------------------------
# Schema + registro
# ---------------------------------------------------------------------------

ATTRACTOR_GEOMETRY_SCHEMA = {
    "description": (
        "Geometria diferencial (Frenet-Serret) de una trayectoria 3D: curvatura, "
        "torsion, y discriminacion de zonas de movimiento lento vs. rapido. "
        "Modos: 'trajectory' (usa x,y,z provistos por el usuario), 'lorenz_demo' "
        "(genera la trayectoria de Lorenz internamente via lorenz_tool), "
        "'validate' (self-test)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["trajectory", "lorenz_demo", "validate"], "default": "trajectory"},
            "x": {"type": "array", "items": {"type": "number"}, "description": "Solo modo trajectory."},
            "y": {"type": "array", "items": {"type": "number"}, "description": "Solo modo trajectory."},
            "z": {"type": "array", "items": {"type": "number"}, "description": "Solo modo trajectory."},
            "dt": {"type": "number", "default": 1.0},
            "umbral_std": {"type": "number", "default": 1.0, "description": "Desvios estandar de rapidez para clasificar zona_lenta/zona_rapida."},
            "n_steps": {"type": "integer", "default": 6000, "description": "Solo modo lorenz_demo."},
            "sigma": {"type": "number", "default": 10.0, "description": "Solo modo lorenz_demo."},
            "rho": {"type": "number", "default": 28.0, "description": "Solo modo lorenz_demo."},
            "beta": {"type": "number", "default": 2.6666666666666665, "description": "Solo modo lorenz_demo."},
            "discard": {"type": "integer", "default": 1000, "description": "Solo modo lorenz_demo."},
            "downsample_for_plot": {"type": "integer", "default": 1500},
        },
        "required": [],
    },
}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_attractor_geometry(mode="lorenz_demo", n_steps=2000), indent=2, ensure_ascii=False)[:2000])
    print("---VALIDATE---")
    print(json.dumps(_validate_attractor_geometry(), indent=2, ensure_ascii=False))


try:
    from tool_registry import register_tool
    register_tool(
        name="attractor_geometry",
        schema={**ATTRACTOR_GEOMETRY_SCHEMA, "name": "attractor_geometry"},
        handler=lambda args: compute_attractor_geometry(**args),
    )
except ImportError:
    pass
