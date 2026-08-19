"""
semiclassical_cosmology_tool.py

Fase 2 del plan quantum_astro: puente a cosmologia semiclasica. Implementa
la ecuacion de Friedmann modificada con la correccion holonomica estandar
de Loop Quantum Cosmology (LQC):

    H^2 = kappa * rho(a) * (1 - rho(a)/rho_c)

donde kappa := 8*pi*G/3 (parametro directo, para no forzar a fijar G y
unidades por separado), rho(a) = rho0 * (a0/a)^(3*(1+w)) para un fluido de
ecuacion de estado w constante, y rho_c es la densidad critica de LQC
(tipica del orden de la densidad de Planck; aqui es un parametro libre en
las mismas unidades que rho0).

Esta forma es time-simetrica alrededor del bounce (rho=rho_c, H=0) para w
constante: a(t) = a(-t) tomando t=0 en el bounce. Se explota esa simetria
para integrar solo la rama expansiva (t>=0) y reflejar, evitando deteccion
de eventos o cambios de signo delicados cerca de H=0.

mode: "friedmann_lqg_correction"
  Integra la rama expansiva desde el bounce y devuelve a(t), H(t), rho(t)
  simetricos en t in [-t_max, t_max].

mode: "bounce_dynamics"
  Diagnostico analitico del punto de bounce: a_min, y el signo de
  (addot/a) en t=0 obtenido diferenciando H^2(a) en vez de H(t) (H=0 ahi,
  asi que dH/dt se calcula via la regla de la cadena sobre H^2, que es
  regular incluso cuando H->0). Confirma si es un bounce genuino
  (addot/a > 0) o un punto de retorno espurio.

mode: "power_spectrum"
  Utilidad generica de FFT sobre una serie temporal (por ejemplo, un canal
  de salida de friedmann_lqg_correction u otra fuente). No implementa el
  pipeline completo de C_ell de CMB (transfer functions, perturbaciones,
  etc.) — eso queda fuera de alcance de esta fase; aqui se expone la
  primitiva espectral para que ese pipeline se pueda construir encima.

NOTA DE ALCANCE: el fluido de fondo es homogeneo e isotropo (FLRW, w
constante, sin perturbaciones ni anisotropias). Es la version "juguete"
estandar de LQC que aparece en la literatura para ilustrar la resolucion
de la singularidad del Big Bang; no reemplaza un codigo de LQC completo.
"""

import numpy as np
from scipy.integrate import solve_ivp


# ---------------------------------------------------------------------------
# Fisica: densidad, H^2(a), y sus derivadas
# ---------------------------------------------------------------------------

def _rho(a, rho0, a0, w):
    return rho0 * (a0 / a) ** (3.0 * (1.0 + w))


def _rho_prime(a, rho0, a0, w):
    """d(rho)/da"""
    return -3.0 * (1.0 + w) * _rho(a, rho0, a0, w) / a


def _H_squared(a, rho0, a0, w, rho_c, kappa):
    rho = _rho(a, rho0, a0, w)
    val = kappa * rho * (1.0 - rho / rho_c)
    return max(val, 0.0), rho


def _a_min(rho0, a0, w, rho_c):
    """Escala factor en el bounce: rho(a_min) = rho_c."""
    if abs(1.0 + w) < 1e-12:
        raise ValueError("w = -1 (constante cosmologica pura) no define un bounce vs a: rho(a) es constante.")
    return a0 * (rho0 / rho_c) ** (1.0 / (3.0 * (1.0 + w)))


# ---------------------------------------------------------------------------
# mode: friedmann_lqg_correction
# ---------------------------------------------------------------------------

def _solve_expanding_branch(a_min, rho0, a0, w, rho_c, kappa, t_max, n_points):
    def rhs(t, y):
        a = y[0]
        a = max(a, a_min)  # proteccion numerica contra overshoot bajo a_min
        H2, _ = _H_squared(a, rho0, a0, w, rho_c, kappa)
        return [a * np.sqrt(H2)]

    t_eval = np.linspace(0.0, t_max, n_points)
    sol = solve_ivp(
        rhs, [0.0, t_max], [a_min], t_eval=t_eval,
        method="RK45", rtol=1e-9, atol=1e-12,
    )
    if not sol.success:
        raise RuntimeError(f"Integracion fallo: {sol.message}")
    return t_eval, sol.y[0]


def friedmann_lqg_correction(params):
    rho0 = float(params.get("rho0", 1.0))
    a0 = float(params.get("a0", 1.0))
    w = float(params.get("w", 0.0))
    rho_c = float(params.get("rho_c", 100.0))
    kappa = float(params.get("kappa", 1.0))
    t_max = float(params.get("t_max", 5.0))
    n_points = int(params.get("n_points", 200))

    if rho0 >= rho_c:
        raise ValueError("rho0 debe ser < rho_c (rho0 es la densidad de referencia en a0, fuera del bounce).")

    a_min = _a_min(rho0, a0, w, rho_c)

    t_pos, a_pos = _solve_expanding_branch(a_min, rho0, a0, w, rho_c, kappa, t_max, n_points)

    # Reflejar para la rama contractiva (t<0) usando la simetria a(t) = a(-t).
    t_full = np.concatenate([-t_pos[::-1][:-1], t_pos])
    a_full = np.concatenate([a_pos[::-1][:-1], a_pos])

    rho_full = _rho(a_full, rho0, a0, w)
    H_full = np.empty_like(a_full)
    for i, (a_i, t_i) in enumerate(zip(a_full, t_full)):
        H2, _ = _H_squared(a_i, rho0, a0, w, rho_c, kappa)
        H_full[i] = np.sqrt(H2) if t_i >= 0 else -np.sqrt(H2)

    # Validacion interna: H numerico (diferencias finitas de a) vs H analitico.
    dadt_numeric = np.gradient(a_full, t_full)
    H_numeric = dadt_numeric / a_full
    max_rel_err = float(np.max(np.abs(H_numeric - H_full) / (np.abs(H_full) + 1e-8)))

    return {
        "mode": "friedmann_lqg_correction",
        "params_used": {
            "rho0": rho0, "a0": a0, "w": w, "rho_c": rho_c, "kappa": kappa,
            "t_max": t_max, "n_points": n_points,
        },
        "a_min_bounce": a_min,
        "t": [round(float(x), 10) for x in t_full],
        "a": [round(float(x), 10) for x in a_full],
        "H": [round(float(x), 10) for x in H_full],
        "rho": [round(float(x), 10) for x in rho_full],
        "validation": {
            "max_relative_error_H_numeric_vs_analytic": round(max_rel_err, 8),
            "note": "H numerico = d(ln a)/dt via diferencias finitas centradas, comparado contra H=+-sqrt(kappa*rho*(1-rho/rho_c)). Error grande cerca de t=0 es normal (H=0 ahi, division por valor pequeno).",
        },
        "note": (
            "Bounce en t=0 por construccion (rama expansiva integrada desde a_min "
            "y reflejada usando la simetria temporal a(t)=a(-t), valida para w constante). "
            "rho_c es la densidad critica LQG; el bounce ocurre cuando rho(a) alcanza rho_c."
        ),
    }


# ---------------------------------------------------------------------------
# mode: bounce_dynamics (diagnostico analitico, sin depender de H=0 numerico)
# ---------------------------------------------------------------------------

def bounce_dynamics(params):
    rho0 = float(params.get("rho0", 1.0))
    a0 = float(params.get("a0", 1.0))
    w = float(params.get("w", 0.0))
    rho_c = float(params.get("rho_c", 100.0))
    kappa = float(params.get("kappa", 1.0))

    if rho0 >= rho_c:
        raise ValueError("rho0 debe ser < rho_c.")

    a_min = _a_min(rho0, a0, w, rho_c)

    # addot/a en el bounce, derivado analiticamente desde H^2(a) via la
    # regla de la cadena (evita 0/0 al diferenciar H directamente donde H=0):
    #   2 H dH/dt = G'(a) * a * H   =>   dH/dt = (1/2) G'(a) a   (regular en H=0)
    #   addot/a = dH/dt + H^2  ->  en el bounce H=0, entonces:
    #   addot/a |_bounce = (1/2) G'(a_min) a_min
    # con G(a) = kappa*rho(a)*(1-rho(a)/rho_c), y en a_min: rho=rho_c por
    # definicion, asi que (1 - 2*rho/rho_c) = -1 en G'(a_min):
    #   G'(a_min) = 3*kappa*(1+w)*rho_c / a_min
    G_prime_at_min = 3.0 * kappa * (1.0 + w) * rho_c / a_min
    addot_over_a = 0.5 * G_prime_at_min * a_min  # = 1.5*kappa*(1+w)*rho_c

    is_true_bounce = addot_over_a > 0

    return {
        "mode": "bounce_dynamics",
        "params_used": {"rho0": rho0, "a0": a0, "w": w, "rho_c": rho_c, "kappa": kappa},
        "a_min": a_min,
        "rho_at_bounce": rho_c,
        "H_at_bounce": 0.0,
        "addot_over_a_at_bounce": addot_over_a,
        "is_true_bounce": is_true_bounce,
        "note": (
            "addot/a en el bounce = 1.5*kappa*(1+w)*rho_c, derivado analiticamente "
            "(no por diferenciacion numerica de H, que es singular en H=0). "
            "Para w > -1 y rho_c > 0 el resultado es siempre > 0: todo fluido con "
            "ecuacion de estado normal produce un bounce genuino bajo esta correccion "
            "holonomica, sin ajuste fino de parametros. is_true_bounce=false solo "
            "puede darse con w <= -1 (energia oscura fantasma/cosmologica pura)."
        ),
    }


# ---------------------------------------------------------------------------
# mode: power_spectrum (utilidad FFT generica, no pipeline CMB completo)
# ---------------------------------------------------------------------------

def power_spectrum(params):
    signal = params.get("signal")
    if signal is None:
        raise ValueError("Falta 'signal' (lista de valores reales) en params.")
    dt = float(params.get("dt", 1.0))
    detrend = bool(params.get("detrend", True))

    y = np.asarray(signal, dtype=float)
    n = len(y)
    if n < 4:
        raise ValueError("signal necesita al menos 4 puntos.")

    if detrend:
        y = y - np.mean(y)

    freqs = np.fft.rfftfreq(n, d=dt)
    spectrum = np.fft.rfft(y)
    power = np.abs(spectrum) ** 2 / n

    peak_idx = int(np.argmax(power[1:]) + 1) if n > 2 else 0  # ignora componente DC

    return {
        "mode": "power_spectrum",
        "n_samples": n,
        "dt": dt,
        "detrended": detrend,
        "frequencies": [round(float(f), 10) for f in freqs],
        "power": [round(float(p), 10) for p in power],
        "peak_frequency": round(float(freqs[peak_idx]), 10) if n > 2 else None,
        "note": (
            "FFT generica de una serie temporal real. No es un pipeline de C_ell "
            "de CMB (faltan transfer functions y fisica de perturbaciones) — "
            "expone la primitiva espectral para construir eso encima si hace falta."
        ),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_MODE_DISPATCH = {
    "friedmann_lqg_correction": friedmann_lqg_correction,
    "bounce_dynamics": bounce_dynamics,
    "power_spectrum": power_spectrum,
}


def compute_semiclassical_cosmology_tool(mode, params=None):
    params = params or {}
    if mode not in _MODE_DISPATCH:
        raise ValueError(
            f"mode '{mode}' no reconocido. Disponibles: {sorted(_MODE_DISPATCH.keys())}"
        )
    return _MODE_DISPATCH[mode](params)


# ---------------------------------------------------------------------------
# Schema MCP
# ---------------------------------------------------------------------------

SEMICLASSICAL_COSMOLOGY_TOOL_SCHEMA = {
    "name": "semiclassical_cosmology_tool",
    "description": (
        "Fase 2 del puente cuantico-cosmologico: ecuacion de Friedmann modificada "
        "con la correccion holonomica estandar de Loop Quantum Cosmology "
        "H^2 = kappa*rho(a)*(1-rho(a)/rho_c), para un fluido FLRW homogeneo de "
        "ecuacion de estado w constante. mode=friedmann_lqg_correction integra la "
        "trayectoria a(t) simetrica alrededor del bounce; mode=bounce_dynamics da "
        "el diagnostico analitico (a_min, addot/a en el bounce, si es un bounce "
        "genuino) sin depender de diferenciacion numerica donde H=0; "
        "mode=power_spectrum es una utilidad FFT generica sobre cualquier serie "
        "temporal (no un pipeline completo de C_ell de CMB)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["friedmann_lqg_correction", "bounce_dynamics", "power_spectrum"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "rho0": {"type": "number", "description": "Densidad de referencia en a=a0 (debe ser < rho_c)."},
                    "a0": {"type": "number", "description": "Escala factor de referencia."},
                    "w": {"type": "number", "description": "Ecuacion de estado del fluido (0=materia, 1/3=radiacion). w=-1 no soportado."},
                    "rho_c": {"type": "number", "description": "Densidad critica de LQC (mismas unidades que rho0)."},
                    "kappa": {"type": "number", "description": "8*pi*G/3, parametro directo (default 1.0, unidades naturales)."},
                    "t_max": {"type": "number", "description": "Solo friedmann_lqg_correction: extension temporal a cada lado del bounce."},
                    "n_points": {"type": "integer", "description": "Solo friedmann_lqg_correction: puntos por rama."},
                    "signal": {"type": "array", "description": "Solo power_spectrum: serie temporal real."},
                    "dt": {"type": "number", "description": "Solo power_spectrum: paso temporal de la serie."},
                    "detrend": {"type": "boolean", "description": "Solo power_spectrum: restar la media antes de la FFT."},
                },
            },
        },
        "required": ["mode", "params"],
    },
}

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("semiclassical_cosmology_tool", SEMICLASSICAL_COSMOLOGY_TOOL_SCHEMA, lambda args, _f=compute_semiclassical_cosmology_tool: _f(**args))
