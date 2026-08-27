"""
unified_dark_sector_tool.py
============================

Marco numérico unificado para modelos cosmológicos de "sector oscuro" con
acoplamiento energía oscura <-> materia oscura, sobre fondo FRW plano.

Formalismo común (todas las familias comparten esta base):

    Friedmann:      E(x)^2 = Omega_r0 * exp(-4x) + Omega_m(x) + Omega_de(x)

    Continuidad:    dOmega_de/dx + 3(1+w) Omega_de = -q(x, E, Om, Ode)
                    dOmega_m /dx + 3 Omega_m        = +q(x, E, Om, Ode)

donde x = ln(a) (x=0 hoy, x<0 pasado), E = H/H0, y q(x,...) es la tasa de
transferencia adimensional (q>0: energía oscura -> materia).

Se cubren cuatro familias dentro de ESTE MISMO formalismo, para que sean
directamente comparables entre sí:

  Familia 0 - LCDM sin acoplamiento           (control / caso límite, q=0)
  Familia 1 - Lambda(t)CDM, ansatz Wang-Meng   rho_Lambda ~ a^-xi
              (Ozer & Taha 1987; Wang & Meng 2005)      -> Omega_de(x) prescrito,
              CERRADO en forma analítica para Omega_de(x) y para q(x);
              Omega_m(x) se resuelve por cuadratura (factor integrante) Y por
              ODE numérica independiente, y ambos se contrastan en self_test.
  Familia 2 - IDE genérico con Q = 3*beta*H^3*rho_crit0/H0^2
              (acoplamiento cúbico en H, motivado por literatura de tensión H0,
              Wang, Yang & Pavon 2016 y similares) -> requiere integración
              numérica completa porque q depende de E(x) de forma implícita.
  Familia 3 - Lambda_s CDM de signo-cambiante  Lambda(z) = Lambda_s0 *
              tanh(k*(z_dagger - z)) / tanh(k*z_dagger)
              (ansatz fenomenológico tipo Akarsu et al., motivado por ajustes
              a DESI BAO 2024) -> Omega_de(x) prescrito, mismo tratamiento
              cerrado/cuadratura que la Familia 1.
  Sandbox   - Gamma(x, E, Om, Ode) arbitraria provista por el usuario,
              resuelta con el mismo integrador numérico genérico que la
              Familia 2. Documentada explícitamente como marco exploratorio,
              SIN respaldo de ningún paper específico.

Todas las familias reducen exactamente a LCDM cuando el parámetro de
acoplamiento -> 0 (o, para la Familia 3, cuando z_dagger -> infinito). Esto
se usa como chequeo de regresión en self_test(), junto con verificación de
conservación de energía total y contraste cerrado-vs-numérico.

NADA en este módulo ha sido ajustado a datos observacionales reales (BAO,
SNe Ia, CMB); es un motor de integración de las ecuaciones de fondo, no un
pipeline de inferencia. Ver seccion "Honestidad de alcance" al final.
"""

from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp, quad
from dataclasses import dataclass
from typing import Callable, Optional, Literal
import warnings

# ---------------------------------------------------------------------------
# 1. Fondo cosmológico y cambio de variable x = ln(a)
# ---------------------------------------------------------------------------

@dataclass
class Cosmology:
    """Parámetros del fondo homogéneo, hoy (x=0, z=0). Sólo plano (Omega_k=0)."""
    H0: float = 70.0        # km/s/Mpc
    Om0: float = 0.3        # materia (bariones + materia oscura) hoy
    Or0: float = 8.24e-5    # radiación (fotones + neutrinos) hoy, valor típico

    @property
    def Ode0(self) -> float:
        """Omega_de hoy, fijado por planitud: Om0 + Or0 + Ode0 = 1."""
        return 1.0 - self.Om0 - self.Or0

    def __post_init__(self):
        if self.Om0 < 0 or self.Or0 < 0:
            raise ValueError("Om0 y Or0 deben ser >= 0")
        if self.Ode0 < -1e-3:
            raise ValueError(f"Om0+Or0={self.Om0+self.Or0:.4f} > 1: Ode0 negativo hoy, "
                              "revisa los parámetros (no es lo mismo que signo-cambiante).")


def x_of_z(z):
    z = np.asarray(z, dtype=float)
    return -np.log1p(z)


def z_of_x(x):
    x = np.asarray(x, dtype=float)
    return np.expm1(-x)


# ---------------------------------------------------------------------------
# 2. Familias con Omega_de(x) PRESCRITO en forma cerrada
#    (Familia 0 = LCDM, Familia 1 = Wang-Meng, Familia 3 = signo-cambiante)
# ---------------------------------------------------------------------------
#
# Para w=-1 fijo (fluido tipo-Lambda, no quintaesencia), 3(1+w)=0, así que la
# ecuación de continuidad de Ode se reduce a:
#       dOmega_de/dx = -q(x)   =>   q(x) = -dOmega_de/dx
# Esto permite resolver Omega_m(x) por factor integrante (cuadratura exacta):
#       Omega_m(x) = exp(-3x) * [ Om0 + integral_0^x q(x') exp(3x') dx' ]
# sin necesidad de un solver ODE implícito, porque q(x) no depende de E(x).

def _Ode_LCDM(x, cosmo: Cosmology, **_):
    x = np.asarray(x, dtype=float)
    return cosmo.Ode0 * np.ones_like(x)

def _dOde_dx_LCDM(x, cosmo: Cosmology, **_):
    x = np.asarray(x, dtype=float)
    return np.zeros_like(x)


def _Ode_WangMeng(x, cosmo: Cosmology, xi: float = 0.01, **_):
    """rho_Lambda(a) ~ a^{-xi}.  xi=0 => LCDM exacto."""
    return cosmo.Ode0 * np.exp(-xi * np.asarray(x, dtype=float))

def _dOde_dx_WangMeng(x, cosmo: Cosmology, xi: float = 0.01, **_):
    return -xi * _Ode_WangMeng(x, cosmo, xi=xi)


def _Ode_signswitch(x, cosmo: Cosmology, z_dagger: float = 2.0, k: float = 5.0, **_):
    """Lambda_s(z) = Lambda_s0 * tanh(k*(z_dagger - z)) / tanh(k*z_dagger).
    z_dagger -> infinito  =>  tanh(k(z_dagger-z))/tanh(k z_dagger) -> 1 => LCDM."""
    z = z_of_x(x)
    denom = np.tanh(k * z_dagger)
    if abs(denom) < 1e-12:
        raise ValueError("k*z_dagger demasiado pequeño; tanh(k*z_dagger) ~ 0.")
    return cosmo.Ode0 * np.tanh(k * (z_dagger - z)) / denom

def _dOde_dx_signswitch(x, cosmo: Cosmology, z_dagger: float = 2.0, k: float = 5.0, **_):
    z = z_of_x(x)
    dzdx = -(1.0 + z)                      # dz/dx = -(1+z)
    denom = np.tanh(k * z_dagger)
    arg = k * (z_dagger - z)
    sech2 = 1.0 - np.tanh(arg) ** 2
    dS_dz = -k * sech2
    return cosmo.Ode0 / denom * dS_dz * dzdx


def _integrate_from_zero(rhs, y0, x_eval):
    """Integra rhs (con condición inicial y0 en x=0) y evalúa en x_eval,
    devolviendo el resultado en el MISMO orden que x_eval de entrada.

    solve_ivp exige t_eval monótono en la dirección de integración, así que
    el pasado (x<=0, integrado desde 0 hacia atrás) y el futuro (x>0,
    integrado desde 0 hacia adelante) se resuelven por separado y se
    reensamblan en el orden original.
    """
    x_eval = np.asarray(x_eval, dtype=float)
    n_state = len(y0)
    result = np.empty((n_state, len(x_eval)))

    past_idx = np.where(x_eval <= 0.0)[0]
    fut_idx = np.where(x_eval > 0.0)[0]

    if len(past_idx) > 0:
        order = np.argsort(x_eval[past_idx])          # ascendente: mas negativo primero
        x_past_desc = x_eval[past_idx][order][::-1]     # descendente: 0 -> mas negativo
        target_idx = past_idx[order][::-1]
        if x_past_desc[-1] == 0.0:
            # todos los puntos pedidos son x=0 (caso degenerado, sin integrar)
            result[:, target_idx] = np.tile(np.asarray(y0).reshape(-1, 1), (1, len(target_idx)))
        else:
            sol = solve_ivp(rhs, (0.0, x_past_desc[-1]), y0, t_eval=x_past_desc,
                             rtol=1e-10, atol=1e-14, method="RK45")
            if not sol.success:
                raise RuntimeError(f"Integración (pasado) falló: {sol.message}")
            result[:, target_idx] = sol.y

    if len(fut_idx) > 0:
        order = np.argsort(x_eval[fut_idx])
        x_fut_asc = x_eval[fut_idx][order]
        target_idx = fut_idx[order]
        sol = solve_ivp(rhs, (0.0, x_fut_asc[-1]), y0, t_eval=x_fut_asc,
                         rtol=1e-10, atol=1e-14, method="RK45")
        if not sol.success:
            raise RuntimeError(f"Integración (futuro) falló: {sol.message}")
        result[:, target_idx] = sol.y

    return result


# Registro de familias tipo "A" (Omega_de prescrito en forma cerrada)
_PRESCRIBED_FAMILIES = {
    "lcdm":        (_Ode_LCDM,        _dOde_dx_LCDM),
    "wang_meng":   (_Ode_WangMeng,    _dOde_dx_WangMeng),
    "signswitch":  (_Ode_signswitch,  _dOde_dx_signswitch),
}


def solve_prescribed(x_eval, cosmo: Cosmology, family: str, method: str = "quadrature",
                      **family_kwargs):
    """Resuelve Omega_m(x), Omega_de(x), E(x) para una familia con Omega_de(x)
    prescrito en forma cerrada (lcdm, wang_meng, signswitch).

    method='quadrature' -> factor integrante (scipy.integrate.quad, cerrado)
    method='ode'         -> mismo q(x) pero integrado con solve_ivp (RK45),
                             para contraste independiente en self_test.
    """
    x_eval = np.atleast_1d(np.asarray(x_eval, dtype=float))
    if family not in _PRESCRIBED_FAMILIES:
        raise ValueError(f"familia '{family}' no es de tipo prescrito: {list(_PRESCRIBED_FAMILIES)}")
    Ode_fn, dOde_fn = _PRESCRIBED_FAMILIES[family]

    Ode_vals = Ode_fn(x_eval, cosmo, **family_kwargs)

    def q_of_x(x):
        return -float(dOde_fn(np.array([x]), cosmo, **family_kwargs)[0])

    if method == "quadrature":
        Om_vals = np.empty_like(x_eval)
        for i, xv in enumerate(x_eval):
            if xv == 0.0:
                integral = 0.0
            else:
                integrand = lambda xp: q_of_x(xp) * np.exp(3 * xp)
                integral, _err = quad(integrand, 0.0, xv, limit=200)
            Om_vals[i] = np.exp(-3 * xv) * (cosmo.Om0 + integral)
    elif method == "ode":
        def rhs(x, y):
            Om = y[0]
            return [-3.0 * Om + q_of_x(x)]
        Om_vals = _integrate_from_zero(rhs, [cosmo.Om0], x_eval)[0]
    else:
        raise ValueError("method debe ser 'quadrature' u 'ode'")

    Or_vals = cosmo.Or0 * np.exp(-4 * x_eval)
    E2 = Or_vals + Om_vals + Ode_vals
    if np.any(E2 < 0):
        warnings.warn("E(x)^2 < 0 en algún punto: parámetros fuera del rango físico.")
    E_vals = np.sqrt(np.abs(E2))
    return {"x": x_eval, "z": z_of_x(x_eval), "Om": Om_vals, "Ode": Ode_vals,
            "Or": Or_vals, "E": E_vals}


# ---------------------------------------------------------------------------
# 3. Familias con acoplamiento IMPLÍCITO q(x, E, Om, Ode)
#    (Familia 2 = Q~H^3, y el sandbox Gamma(z) arbitrario)
# ---------------------------------------------------------------------------
#
# Aquí q depende de E(x), que a su vez depende de Om(x) y Ode(x): el sistema
# es genuinamente acoplado y se integra con un solver ODE implícito (RK45).

def q_H3(x, E, Om, Ode, beta: float = 0.0, w: float = -1.0):
    """Familia 2: Q = 3*beta*H^3*rho_crit0/H0^2  =>  q(x,E) = 3*beta*E(x)^2.
    beta=0 => LCDM exacto (regresión)."""
    return 3.0 * beta * E ** 2


def solve_coupled(x_eval, cosmo: Cosmology, q_fn: Callable, w: float = -1.0,
                   **q_kwargs):
    """Integra el sistema acoplado completo (Friedmann + continuidad) para una
    q(x, E, Om, Ode) arbitraria — usado por la Familia 2 (Q~H^3) y el sandbox.

    q_fn debe tener firma q_fn(x, E, Om, Ode, **q_kwargs) -> float
    w es el parámetro de ecuación de estado del fluido oscuro (w=-1 => Lambda).
    """
    x_eval = np.atleast_1d(np.asarray(x_eval, dtype=float))

    def rhs(x, y):
        Om, Ode = y
        Or = cosmo.Or0 * np.exp(-4 * x)
        E2 = Or + Om + Ode
        E = np.sqrt(max(E2, 1e-30))
        q = q_fn(x, E, Om, Ode, **q_kwargs)
        dOm = -3.0 * Om + q
        dOde = -3.0 * (1.0 + w) * Ode - q
        return [dOm, dOde]

    y0 = [cosmo.Om0, cosmo.Ode0]
    Om_out, Ode_out = _integrate_from_zero(rhs, y0, x_eval)

    Or_vals = cosmo.Or0 * np.exp(-4 * x_eval)
    E2 = Or_vals + Om_out + Ode_out
    E_vals = np.sqrt(np.abs(E2))
    return {"x": x_eval, "z": z_of_x(x_eval), "Om": Om_out, "Ode": Ode_out,
            "Or": Or_vals, "E": E_vals}


# ---------------------------------------------------------------------------
# 4. Interfaz única de alto nivel
# ---------------------------------------------------------------------------

FamilyName = Literal["lcdm", "wang_meng", "ide_h3", "signswitch", "custom"]


def compute_Hz(z, cosmo: Cosmology, family: FamilyName, **params):
    """Punto de entrada único. Devuelve dict con z, E(z)=H(z)/H0, H(z) [km/s/Mpc],
    Omega_m(z), Omega_de(z).

    family='lcdm'                -> sin parámetros extra
    family='wang_meng'            -> xi (float, default 0.01)
    family='signswitch'           -> z_dagger (float, default 2.0), k (float, default 5.0)
    family='ide_h3'               -> beta (float, default 0.0)
    family='custom'               -> q_fn (callable(x,E,Om,Ode,**kw)), w (float, default -1.0),
                                      + kwargs para q_fn
    """
    x = x_of_z(z)
    if family in _PRESCRIBED_FAMILIES:
        out = solve_prescribed(x, cosmo, family, method="quadrature", **params)
    elif family == "ide_h3":
        beta = params.pop("beta", 0.0)
        w = params.pop("w", -1.0)
        out = solve_coupled(x, cosmo, q_H3, w=w, beta=beta)
    elif family == "custom":
        q_fn = params.pop("q_fn")
        w = params.pop("w", -1.0)
        out = solve_coupled(x, cosmo, q_fn, w=w, **params)
    else:
        raise ValueError(f"familia desconocida: {family}")
    out["H"] = out["E"] * cosmo.H0
    return out


# ---------------------------------------------------------------------------
# 5. self_test — verificación interna, NO ajuste a datos observacionales
# ---------------------------------------------------------------------------

def self_test(verbose: bool = True) -> bool:
    """Batería de chequeos de consistencia interna:
      (a) Familia 0 (LCDM) reproduce Omega_m(x)=Om0*exp(-3x) exacto.
      (b) Familia 1 (Wang-Meng): cuadratura cerrada vs ODE numérica independiente.
      (c) Familia 2 (Q~H^3) con beta=0 colapsa a LCDM (regresión).
      (d) Familia 3 (signswitch) con z_dagger grande colapsa a LCDM.
      (e) Conservación de energía total: d(Om+Ode)/dx + 3 Om + 3(1+w) Ode ~ 0
          para TODAS las familias acopladas (q se cancela en la suma, por
          construcción de las ecuaciones de continuidad).
      (f) H(z=0) = H0 en todas las familias.
    Devuelve True si todo pasa dentro de tolerancia; imprime detalle si verbose.
    """
    ok = True
    tol = 1e-6
    cosmo = Cosmology(H0=70.0, Om0=0.3, Or0=8.24e-5)
    z_grid = np.array([0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 20.0, 200.0])
    x_grid = x_of_z(z_grid)

    def check(name, cond, detail=""):
        nonlocal ok
        status = "OK" if cond else "FALLA"
        if not cond:
            ok = False
        if verbose:
            print(f"  [{status}] {name}" + (f"  ({detail})" if detail else ""))

    if verbose:
        print("=== self_test: unified_dark_sector_tool ===")

    # (a) LCDM exacto
    out_lcdm = solve_prescribed(x_grid, cosmo, "lcdm")
    Om_analytic = cosmo.Om0 * np.exp(-3 * x_grid)
    err_a = np.max(np.abs(out_lcdm["Om"] - Om_analytic))
    check("(a) LCDM: Omega_m(x) = Om0*exp(-3x) exacto", err_a < tol, f"err_max={err_a:.2e}")

    # (b) Wang-Meng: cuadratura vs ODE numérica independiente
    # (error RELATIVO: Omega_m abarca ~9 órdenes de magnitud entre z=0 y z=200)
    xi_test = 0.15
    out_quad = solve_prescribed(x_grid, cosmo, "wang_meng", method="quadrature", xi=xi_test)
    out_ode = solve_prescribed(x_grid, cosmo, "wang_meng", method="ode", xi=xi_test)
    err_b = np.max(np.abs(out_quad["Om"] - out_ode["Om"]) / out_quad["Om"])
    check("(b) Wang-Meng: cuadratura cerrada == ODE numérica independiente (rel.)",
          err_b < 1e-6, f"err_rel_max={err_b:.2e}")
    # y también contra la fórmula cerrada de Wang-Meng derivada analíticamente:
    # Om(x) = [Om0 - xi*Ode0/(3-xi)]*exp(-3x) + [xi*Ode0/(3-xi)]*exp(-xi*x)
    C = cosmo.Om0 - xi_test * cosmo.Ode0 / (3 - xi_test)
    A = xi_test * cosmo.Ode0 / (3 - xi_test)
    Om_wm_analytic = C * np.exp(-3 * x_grid) + A * np.exp(-xi_test * x_grid)
    err_b2 = np.max(np.abs(out_quad["Om"] - Om_wm_analytic) / Om_wm_analytic)
    check("(b') Wang-Meng: cuadratura == fórmula cerrada C*e^-3x + A*e^-xi*x (rel.)",
          err_b2 < 1e-6, f"err_rel_max={err_b2:.2e}")

    # (c) IDE H^3 con beta=0 -> LCDM (error relativo, mismo motivo que (b))
    out_h3_zero = solve_coupled(x_grid, cosmo, q_H3, w=-1.0, beta=0.0)
    err_c_om = np.max(np.abs(out_h3_zero["Om"] - Om_analytic) / Om_analytic)
    err_c_ode = np.max(np.abs(out_h3_zero["Ode"] - cosmo.Ode0)) / cosmo.Ode0
    check("(c) IDE Q~H^3 con beta=0 colapsa a LCDM (rel.)",
          err_c_om < 1e-5 and err_c_ode < 1e-5, f"err_Om={err_c_om:.2e}, err_Ode={err_c_ode:.2e}")

    # (d) signswitch con z_dagger grande -> LCDM
    out_ss = solve_prescribed(x_grid[1:], cosmo, "signswitch", z_dagger=1e4, k=1.0)  # excluye x=0 (trivial)
    err_d = np.max(np.abs(out_ss["Ode"] - cosmo.Ode0))
    check("(d) signswitch con z_dagger->grande colapsa a LCDM (Omega_de const.)",
          err_d < 1e-3, f"err_max={err_d:.2e}")

    # (e) conservación de energía total para una familia acoplada no trivial (beta!=0).
    # d(Om+Ode)/dx = -3*Om - 3(1+w)*Ode  DEBE cumplirse pase lo que pase con q(x),
    # porque q se cancela al sumar las dos ecuaciones de continuidad: es una
    # identidad estructural del formalismo, no algo que dependa del modelo.
    # Dominio acotado (Om,Ode ~ O(1)) para que el residuo relativo vía diferencias
    # finitas centradas sea una prueba limpia (sin el rango dinámico de z=200).
    beta_test = 0.02
    x_fine = np.linspace(-2.0, 0.5, 600)
    out_h3 = solve_coupled(x_fine, cosmo, q_H3, w=-1.0, beta=beta_test)
    Om_i, Ode_i = out_h3["Om"], out_h3["Ode"]
    d_sum_dx = np.gradient(Om_i + Ode_i, x_fine, edge_order=2)
    rhs_expected = -3 * Om_i  # w=-1 => 3(1+w)*Ode = 0
    residual_rel = np.abs(d_sum_dx - rhs_expected) / np.abs(rhs_expected)
    max_res = np.max(residual_rel[10:-10])  # recorta bordes del gradiente numérico
    check("(e) Conservación total d(Om+Ode)/dx = -3*Om-3(1+w)*Ode (IDE H^3, beta=0.02, rel.)",
          max_res < 1e-3, f"err_rel_max={max_res:.2e}")

    # (f) H(z=0) = H0 en todas las familias
    for fam, kw in [("lcdm", {}), ("wang_meng", {"xi": 0.1}),
                    ("signswitch", {"z_dagger": 2.0, "k": 5.0}),
                    ("ide_h3", {"beta": 0.05})]:
        out = compute_Hz(np.array([0.0]), cosmo, fam, **kw)
        err_f = abs(out["H"][0] - cosmo.H0)
        check(f"(f) H(z=0)=H0 para familia '{fam}'", err_f < 1e-6, f"err={err_f:.2e}")

    if verbose:
        print(f"=== resultado global: {'TODO OK' if ok else 'HAY FALLAS'} ===")
    return ok


# ---------------------------------------------------------------------------
# 6. Honestidad de alcance (léase antes de usar los resultados)
# ---------------------------------------------------------------------------
#
# - Familia 0 (LCDM) y Familia 1 (Wang-Meng): tienen respaldo directo en
#   literatura (Ozer & Taha 1987; Wang & Meng 2005) y fórmula cerrada
#   verificable, la más sólida de las cuatro para contrastar con datos reales.
# - Familia 2 (Q~H^3): motivada por la fenomenología reciente de tensión H0,
#   pero la forma funcional de Gamma es una ELECCIÓN, no una predicción única;
#   distintos papers usan Q~H, Q~H^2 rho, Q~H^3, etc. Este módulo implementa
#   Q~H^3 como caso representativo, no como "la" familia IDE.
# - Familia 3 (signswitch): ansatz fenomenológico reciente (2023-2024),
#   motivado por ajustes a DESI BAO, más especulativo y con menos literatura
#   de respaldo que las Familias 0-1. La forma tanh() usada aquí es una
#   parametrización suave elegida por el autor de este módulo para tener un
#   ansatz C-infinito y fácil de integrar; NO es necesariamente la
#   parametrización exacta de ningún paper citado — para reproducir un paper
#   específico, reemplazar _Ode_signswitch por su forma funcional exacta.
# - Sandbox (family='custom'): sin respaldo de ningún paper. Sirve para que
#   el usuario explore su propia Gamma(x,E,Om,Ode) y compare con H(z)
#   observado externamente; este módulo NO incluye datos observacionales ni
#   hace ajuste (fit) a BAO/SNe/CMB.
#
# Ninguna de las cuatro familias ha sido validada aquí contra datos reales;
# self_test() sólo verifica consistencia matemática interna del integrador.




# ---------------------------------------------------------------------------
# 7. Registro como tool MCP
# ---------------------------------------------------------------------------
#
# Nota de alcance: solo se exponen las familias con parámetros puramente
# numéricos (lcdm, wang_meng, signswitch, ide_h3). La familia 'custom' pide
# una q_fn (callable Python) que no se puede transportar por JSON-RPC, así
# que queda fuera del tool público; sigue disponible llamando a compute_Hz()
# directamente desde Python.

from tool_registry import register_tool

_EXPOSED_FAMILIES = ("lcdm", "wang_meng", "signswitch", "ide_h3")


def compute_unified_dark_sector_tool(mode: str, params: dict | None = None):
    params = dict(params or {})

    if mode == "self_test":
        ok = self_test(verbose=False)
        return {"mode": "self_test", "all_pass": ok}

    if mode == "compute_Hz":
        family = params.get("family", "lcdm")
        if family not in _EXPOSED_FAMILIES:
            raise ValueError(
                f"family debe ser una de {_EXPOSED_FAMILIES} "
                f"('custom' no esta expuesta via MCP: requiere una funcion "
                f"Python arbitraria, usar compute_Hz() directamente)"
            )
        z = params.get("z")
        if z is None:
            raise ValueError("falta 'z' (lista de redshifts)")
        z_arr = np.atleast_1d(np.asarray(z, dtype=float))

        cosmo = Cosmology(
            H0=params.get("H0", 70.0),
            Om0=params.get("Om0", 0.3),
            Or0=params.get("Or0", 8.24e-5),
        )

        family_kwargs = {}
        if family == "wang_meng":
            family_kwargs["xi"] = params.get("xi", 0.01)
        elif family == "signswitch":
            family_kwargs["z_dagger"] = params.get("z_dagger", 2.0)
            family_kwargs["k"] = params.get("k", 5.0)
        elif family == "ide_h3":
            family_kwargs["beta"] = params.get("beta", 0.0)
            family_kwargs["w"] = params.get("w", -1.0)

        out = compute_Hz(z_arr, cosmo, family, **family_kwargs)
        return {
            "mode": "compute_Hz",
            "family": family,
            "z": out["z"].tolist(),
            "H_km_s_Mpc": out["H"].tolist(),
            "E": out["E"].tolist(),
            "Omega_m": out["Om"].tolist(),
            "Omega_de": out["Ode"].tolist(),
        }

    raise ValueError(f"mode desconocido: {mode!r} (usar 'compute_Hz' o 'self_test')")


UNIFIED_DARK_SECTOR_TOOL_SCHEMA = {
    "name": "unified_dark_sector_tool",
    "description": (
        "Calcula H(z) y Omega_m(z)/Omega_de(z) bajo un formalismo Friedmann+"
        "continuidad unificado, para cuatro familias de sector oscuro "
        "comparables entre si: lcdm (control), wang_meng (rho_de~a^-xi, "
        "Ozer&Taha 1987/Wang&Meng 2005), signswitch (Lambda_s tanh, ansatz "
        "tipo Akarsu et al. motivado por DESI BAO 2024), ide_h3 (acoplamiento "
        "Q~beta*H^3). Ninguna familia esta ajustada a datos observacionales "
        "reales, ver docstring del modulo. mode='self_test' corre las "
        "verificaciones internas (regresion a LCDM, conservacion de energia, "
        "cuadratura vs ODE)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["compute_Hz", "self_test"],
                "description": "compute_Hz: evalua H(z) para una familia. self_test: corre self_test() interno.",
            },
            "params": {
                "type": "object",
                "properties": {
                    "family": {
                        "type": "string",
                        "enum": list(_EXPOSED_FAMILIES),
                        "description": "Familia de sector oscuro (default lcdm). 'custom' no esta expuesta via MCP.",
                    },
                    "z": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Redshifts donde evaluar H(z) (requerido para compute_Hz)",
                    },
                    "H0": {"type": "number", "description": "H0 en km/s/Mpc (default 70.0)"},
                    "Om0": {"type": "number", "description": "Omega_m hoy (default 0.3)"},
                    "Or0": {"type": "number", "description": "Omega_r hoy (default 8.24e-5)"},
                    "xi": {"type": "number", "description": "Solo wang_meng: exponente rho_de~a^-xi (default 0.01)"},
                    "z_dagger": {"type": "number", "description": "Solo signswitch: redshift de cambio de signo (default 2.0)"},
                    "k": {"type": "number", "description": "Solo signswitch: agudeza de la transicion tanh (default 5.0)"},
                    "beta": {"type": "number", "description": "Solo ide_h3: intensidad de acoplamiento Q~beta*H^3 (default 0.0)"},
                    "w": {"type": "number", "description": "Solo ide_h3: ecuacion de estado del fluido oscuro (default -1.0)"},
                },
            },
        },
        "required": ["mode"],
    },
}


register_tool(
    name="unified_dark_sector_tool",
    schema=UNIFIED_DARK_SECTOR_TOOL_SCHEMA,
    handler=lambda args: compute_unified_dark_sector_tool(
        args.get("mode"), args.get("params")
    ),
)


if __name__ == "__main__":
    import json
    print(json.dumps(compute_unified_dark_sector_tool("self_test"), indent=2))
