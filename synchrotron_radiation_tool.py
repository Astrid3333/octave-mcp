"""
synchrotron_radiation_tool.py

Radiación de sincrotrón de un electrón relativista individual en un campo
magnético, vía la formulación estándar de Rybicki & Lightman (Radiative
Processes in Astrophysics, cap. 6).

Fórmula central (potencia espectral por electrón, en unidades gaussianas):

    P(omega, gamma) = (sqrt(3) * q^3 * B * sin(theta)) / (2*pi*m_e*c^2) * F(X)

    X = omega / omega_c
    F(X) = X * integral_X^inf K_{5/3}(xi) dxi

donde:
    q       = carga del electrón (esu)
    B       = campo magnético (Gauss)
    theta   = ángulo de pitch entre v y B
    m_e     = masa del electrón
    c       = velocidad de la luz
    omega_c = (3/2) * gamma^2 * (q*B / (m_e*c)) * sin(theta)   [frecuencia crítica]

F(X) tiene dos límites asintóticos conocidos, usados como ancla de validación
(igual criterio que Fibonacci/metaplectic: no confiar solo en la integral
numérica, confirmarla contra fórmulas cerradas independientes):

    X << 1:  F(X) -> (4*pi/sqrt(3)) * (1/Gamma(1/3)) * (X/2)^(1/3)
    X >> 1:  F(X) -> sqrt(pi*X/2) * exp(-X)

Unidades: CGS-Gaussian en todo el módulo (estándar en astrofísica de altas
energías). No se mezclan con SI para evitar errores de factor.
"""

import math
from scipy.special import kv, gamma as gamma_fn
from scipy.integrate import quad

# ---------------------------------------------------------------------------
# Constantes físicas (CGS-Gaussian)
# ---------------------------------------------------------------------------
Q_E = 4.803204712570263e-10   # carga del electrón, esu (statC)
M_E = 9.1093837015e-28        # masa del electrón, g
C_LIGHT = 2.99792458e10       # velocidad de la luz, cm/s


# ---------------------------------------------------------------------------
# Núcleo matemático (genérico, no atado a ningún caso particular de B/gamma)
# ---------------------------------------------------------------------------

def _critical_frequency(gamma_lorentz, B_gauss, sin_theta):
    """omega_c = (3/2) * gamma^2 * (q*B / (m_e*c)) * sin(theta)"""
    omega_B = Q_E * B_gauss / (M_E * C_LIGHT)  # frecuencia de ciclotrón (rad/s)
    return 1.5 * gamma_lorentz**2 * omega_B * sin_theta


def _F_synchrotron(X):
    """
    F(X) = X * integral_X^inf K_{5/3}(xi) dxi

    Integración numérica vía sustitución logarítmica (xi = e^u). Se necesita
    porque el integrando abarca un rango dinámico enorme: para X pequeño,
    K_5/3(xi) diverge como xi^(-5/3) cerca del límite inferior, y para X
    grande la cola exponencial es tan chica que un quad ingenuo sobre un
    intervalo lineal fijo sufre cancelación numérica severa (confirmado:
    con quad lineal directo, X=1e-4 daba un resultado NEGATIVO, físicamente
    imposible ya que K_5/3>0 en todo el dominio). La sustitución u=ln(xi)
    comprime el rango dinámico y elimina el problema.
    """
    if X <= 0:
        raise ValueError("X debe ser positivo")

    upper = max(80.0, X * 10.0)  # margen generoso sobre el corte exponencial
    ln_X, ln_upper = math.log(X), math.log(upper)
    integral, _ = quad(
        lambda u: kv(5.0 / 3.0, math.exp(u)) * math.exp(u),
        ln_X, ln_upper, limit=400, epsabs=1e-300, epsrel=1e-10,
    )
    return X * integral


def _F_asymptotic_small_X(X):
    """Límite X << 1: F(X) -> (4*pi/sqrt(3)) * (1/Gamma(1/3)) * (X/2)^(1/3)"""
    return (4.0 * math.pi / math.sqrt(3.0)) * (1.0 / gamma_fn(1.0 / 3.0)) * (X / 2.0) ** (1.0 / 3.0)


def _F_asymptotic_large_X(X):
    """Límite X >> 1: F(X) -> sqrt(pi*X/2) * exp(-X)"""
    return math.sqrt(math.pi * X / 2.0) * math.exp(-X)


def _single_electron_power_spectrum(omega, gamma_lorentz, B_gauss, pitch_angle_rad):
    """
    Devuelve P(omega, gamma) en erg/s/Hz (potencia espectral, no integrada en
    ángulo sólido -- ya integrada sobre el cono de emisión, estándar de R&L).
    """
    sin_theta = math.sin(pitch_angle_rad)
    if sin_theta <= 0:
        return {
            "omega_c": 0.0,
            "X": None,
            "F_X": 0.0,
            "P_omega_gamma": 0.0,
            "nota": "sin_theta<=0: electron moviendose paralelo a B, sin emision de sincrotron",
        }

    omega_c = _critical_frequency(gamma_lorentz, B_gauss, sin_theta)
    X = omega / omega_c
    F_X = _F_synchrotron(X)

    prefactor = (math.sqrt(3.0) * Q_E**3 * B_gauss * sin_theta) / (2.0 * math.pi * M_E * C_LIGHT**2)
    P = prefactor * F_X

    return {
        "omega_c": omega_c,
        "X": X,
        "F_X": F_X,
        "P_omega_gamma": P,
    }


def _power_law_spectrum(omega_array, gamma_min, gamma_max, p_index, B_gauss, pitch_angle_rad,
                         n_electrons=200):
    """
    Espectro integrado de una población de electrones con distribución de
    ley de potencia N(gamma) ~ gamma^-p entre gamma_min y gamma_max, muestreada
    en n_electrons puntos log-espaciados (integración tipo trapecio en log-gamma).
    No es un ajuste analítico (ese requeriría funciones Gamma incompletas);
    es integración numérica directa sobre el núcleo de electrón único ya
    validado arriba -- mismo criterio de no introducir una segunda fórmula
    sin verificar cuando la numérica directa alcanza.
    """
    if gamma_min <= 0 or gamma_max <= gamma_min:
        raise ValueError("gamma_min debe ser > 0 y gamma_max > gamma_min")

    log_gammas = [
        gamma_min * (gamma_max / gamma_min) ** (i / (n_electrons - 1))
        for i in range(n_electrons)
    ]
    weights = [g ** (-p_index) for g in log_gammas]

    spectrum = []
    for omega in omega_array:
        total = 0.0
        for i in range(n_electrons - 1):
            g0, g1 = log_gammas[i], log_gammas[i + 1]
            w0, w1 = weights[i], weights[i + 1]
            P0 = _single_electron_power_spectrum(omega, g0, B_gauss, pitch_angle_rad)["P_omega_gamma"]
            P1 = _single_electron_power_spectrum(omega, g1, B_gauss, pitch_angle_rad)["P_omega_gamma"]
            total += 0.5 * (P0 * w0 + P1 * w1) * (g1 - g0)
        spectrum.append(total)

    return {
        "omega_array": list(omega_array),
        "j_omega": spectrum,
        "gamma_min": gamma_min,
        "gamma_max": gamma_max,
        "p_index": p_index,
        "n_electrons_muestreados": n_electrons,
        "nota": "j_omega = integral N(gamma)*P(omega,gamma) dgamma, N(gamma)~gamma^-p; integracion trapezoidal en malla log-gamma",
    }


# ---------------------------------------------------------------------------
# Validación (mismo patrón que el resto del repo: mode="validate")
# ---------------------------------------------------------------------------

def _validate_synchrotron_radiation():
    checks = []

    # Check 1: límite X << 1 -- la integral numérica debe converger al
    # límite asintótico cerrado dentro de tolerancia razonable
    X_small = 1e-4
    F_numeric = _F_synchrotron(X_small)
    F_asym = _F_asymptotic_small_X(X_small)
    rel_err_small = abs(F_numeric - F_asym) / F_asym
    checks.append({
        "name": "F(X) converge al limite asintotico X<<1 (formula cerrada independiente)",
        "passed": bool(rel_err_small < 5e-3),
        "X": X_small,
        "F_numerico": F_numeric,
        "F_asintotico": F_asym,
        "error_relativo": rel_err_small,
    })

    # Check 2: límite X >> 1. sqrt(pi*X/2)*exp(-X) es solo el termino lider
    # de una serie asintotica (siguiente correccion ~1-55/(72X)), asi que el
    # error relativo NO tiende a cero de golpe -- decae como potencia de 1/X.
    # Confirmado empiricamente: 12.5% en X=5, 3.6% en X=20, 1.5% en X=50.
    # El check real no es "coincide exacto en un X arbitrario" sino que el
    # error decae monotonamente al aumentar X (esa es la propiedad que
    # define a una serie asintotica valida, no una formula exacta).
    X_series = [10.0, 20.0, 30.0, 50.0]
    rel_errs = []
    for X_val in X_series:
        F_num = _F_synchrotron(X_val)
        F_asym = _F_asymptotic_large_X(X_val)
        rel_errs.append(abs(F_num - F_asym) / F_asym)
    monotonic_decay = all(rel_errs[i] > rel_errs[i + 1] for i in range(len(rel_errs) - 1))
    checks.append({
        "name": "error del limite asintotico X>>1 decae monotonamente al aumentar X (propiedad de serie asintotica, no formula exacta)",
        "passed": bool(monotonic_decay and rel_errs[-1] < 0.03),
        "X_values": X_series,
        "errores_relativos": rel_errs,
    })

    # Check 3: el pico de F(X) debe estar cerca de X~0.29 (resultado conocido
    # de R&L, el espectro de sincrotron de un electron pica en omega ~ 0.29*omega_c)
    X_grid = [0.05 * i for i in range(1, 40)]
    F_vals = [_F_synchrotron(x) for x in X_grid]
    X_peak = X_grid[F_vals.index(max(F_vals))]
    checks.append({
        "name": "pico de F(X) cerca de X=0.29 (resultado conocido de Rybicki & Lightman)",
        "passed": bool(0.15 < X_peak < 0.45),
        "X_peak_encontrado": X_peak,
    })

    # Check 4: P(omega,gamma) debe ser 0 cuando sin(theta)=0 (electron paralelo a B)
    res_parallel = _single_electron_power_spectrum(1e15, 10.0, 100.0, 0.0)
    checks.append({
        "name": "potencia nula si pitch_angle=0 (electron paralelo al campo)",
        "passed": bool(res_parallel["P_omega_gamma"] == 0.0),
        "got": res_parallel["P_omega_gamma"],
    })

    # Check 5: P(omega,gamma) > 0 para un caso físico normal (theta=pi/2)
    res_normal = _single_electron_power_spectrum(1e10, 10.0, 100.0, math.pi / 2.0)
    checks.append({
        "name": "potencia positiva en caso fisico normal (theta=pi/2, gamma=10, B=100G)",
        "passed": bool(res_normal["P_omega_gamma"] > 0.0),
        "P_omega_gamma": res_normal["P_omega_gamma"],
        "omega_c": res_normal["omega_c"],
    })

    # Check 6: escalado con B -- omega_c debe escalar linealmente con B
    omega_c_1 = _critical_frequency(10.0, 100.0, 1.0)
    omega_c_2 = _critical_frequency(10.0, 200.0, 1.0)
    checks.append({
        "name": "omega_c escala linealmente con B",
        "passed": bool(abs(omega_c_2 / omega_c_1 - 2.0) < 1e-9),
        "ratio_obtenido": omega_c_2 / omega_c_1,
    })

    # Check 7: escalado con gamma^2
    omega_c_g1 = _critical_frequency(10.0, 100.0, 1.0)
    omega_c_g2 = _critical_frequency(20.0, 100.0, 1.0)
    checks.append({
        "name": "omega_c escala con gamma^2",
        "passed": bool(abs(omega_c_g2 / omega_c_g1 - 4.0) < 1e-9),
        "ratio_obtenido": omega_c_g2 / omega_c_g1,
    })

    # Check 8: espectro de ley de potencia da valores finitos y positivos
    omega_test = [1e9, 1e10, 1e11]
    spec = _power_law_spectrum(omega_test, gamma_min=1.0, gamma_max=1000.0,
                                p_index=2.5, B_gauss=100.0, pitch_angle_rad=math.pi / 2.0,
                                n_electrons=50)
    all_positive = all(v > 0 for v in spec["j_omega"])
    checks.append({
        "name": "espectro integrado de ley de potencia da valores finitos y positivos",
        "passed": bool(all_positive and all(math.isfinite(v) for v in spec["j_omega"])),
        "j_omega": spec["j_omega"],
    })

    passed_all = all(c["passed"] for c in checks)
    return {
        "mode": "validate",
        "validation_passed": passed_all,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Dispatch principal
# ---------------------------------------------------------------------------

def compute_synchrotron_radiation(arguments):
    """
    Handler principal. Recibe el dict completo de argumentos (patron del
    repo: un solo parametro posicional, no **kwargs).

    Modos:
      - "single_electron": espectro de potencia de un electron individual
      - "power_law_spectrum": espectro integrado de una poblacion en ley de potencia
      - "critical_frequency": solo calcula omega_c dado gamma, B, pitch_angle
      - "validate": self-test contra limites asintoticos y escalados conocidos
    """
    mode = arguments.get("mode", "single_electron")
    params = arguments.get("params", {}) or {}

    if mode == "validate":
        return _validate_synchrotron_radiation()

    if mode == "critical_frequency":
        gamma_lorentz = params["gamma"]
        B_gauss = params["B_gauss"]
        pitch_angle_rad = params.get("pitch_angle_rad", math.pi / 2.0)
        omega_c = _critical_frequency(gamma_lorentz, B_gauss, math.sin(pitch_angle_rad))
        return {
            "mode": mode,
            "omega_c_rad_s": omega_c,
            "nu_c_Hz": omega_c / (2.0 * math.pi),
        }

    if mode == "single_electron":
        omega = params["omega"]
        gamma_lorentz = params["gamma"]
        B_gauss = params["B_gauss"]
        pitch_angle_rad = params.get("pitch_angle_rad", math.pi / 2.0)
        result = _single_electron_power_spectrum(omega, gamma_lorentz, B_gauss, pitch_angle_rad)
        result["mode"] = mode
        return result

    if mode == "power_law_spectrum":
        omega_array = params["omega_array"]
        gamma_min = params["gamma_min"]
        gamma_max = params["gamma_max"]
        p_index = params.get("p_index", 2.5)
        B_gauss = params["B_gauss"]
        pitch_angle_rad = params.get("pitch_angle_rad", math.pi / 2.0)
        n_electrons = params.get("n_electrons", 200)
        result = _power_law_spectrum(omega_array, gamma_min, gamma_max, p_index,
                                      B_gauss, pitch_angle_rad, n_electrons)
        result["mode"] = mode
        return result

    raise ValueError(f"Modo desconocido: {mode}")


# ---------------------------------------------------------------------------
# Schema (mismo patron que color_math_tool / persistent_homology_tool: enum
# de mode incluye 'validate' desde el vamos)
# ---------------------------------------------------------------------------

SYNCHROTRON_RADIATION_SCHEMA = {
    "name": "synchrotron_radiation_tool",
    "description": "Radiacion de sincrotron de electrones relativistas: espectro, frecuencia critica, y self-test.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["single_electron", "power_law_spectrum", "critical_frequency", "validate"],
                "description": "Modo de calculo. 'validate' corre el self-test contra limites asintoticos conocidos.",
            },
            "params": {
                "type": "object",
                "description": (
                    "single_electron: {omega, gamma, B_gauss, pitch_angle_rad=pi/2}. "
                    "power_law_spectrum: {omega_array, gamma_min, gamma_max, p_index=2.5, B_gauss, "
                    "pitch_angle_rad=pi/2, n_electrons=200}. "
                    "critical_frequency: {gamma, B_gauss, pitch_angle_rad=pi/2}. "
                    "Unidades CGS-Gaussian: omega en rad/s, B en Gauss."
                ),
            },
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# Auto-registro (patron del repo: try/except ImportError, register_tool al
# final del archivo)
# ---------------------------------------------------------------------------

try:
    from tool_registry import register_tool

    register_tool(
        "synchrotron_radiation_tool",
        SYNCHROTRON_RADIATION_SCHEMA,
        compute_synchrotron_radiation,
    )
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Self-test standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    result = compute_synchrotron_radiation({"mode": "validate"})
    print(json.dumps(result, indent=2, default=str))

    if not result["validation_passed"]:
        raise SystemExit("VALIDATE FALLO -- revisar checks arriba")
    print("\nTodos los checks PASSED.")
