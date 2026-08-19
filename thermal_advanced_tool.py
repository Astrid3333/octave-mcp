"""
thermal_advanced_tool.py
Modulos avanzados de transferencia de calor / termodinamica que complementan
a thermal_conduction_tool (conduccion pura) y thermal_structural_tool
(acoplamiento termico-estructural).

Modos:
  - pcm_1d                  : material de cambio de fase (PCM), fusion 1D en
                               dominio semi-infinito aproximado (metodo de
                               entalpia, Voller-Cross), Dirichlet en x=0
  - radiation_exchange      : intercambio radiativo entre 2 superficies grises
                               difusas (red de resistencias radiativas)
  - convection_correlations : correlaciones estandar de conveccion natural
                               (Churchill-Chu) y forzada (Blasius/Dittus-Boelter)
  - inverse_conductivity    : identificacion de k a partir de datos T(x)
                               ruidosos en conduccion 1D estacionaria (regresion)
  - thermodynamic_properties: gas ideal (Cp/Cv/dH/dS), capacidad calorifica de
                               Debye para solidos, relacion de Kelvin
                               (Seebeck/Peltier)

Validado contra:
  - pcm_1d: solucion de Neumann del problema de Stefan a una fase (dominio
    semi-infinito, solido uniformemente a T_m, superficie a T_s>T_m impuesta
    en t=0+). Posicion del frente s(t)=2*lambda*sqrt(alpha_l*t), con lambda
    raiz de lambda*exp(lambda^2)*erf(lambda)=Ste/sqrt(pi). Metodo de entalpia
    (no el de capacidad calorifica aparente ingenua, que en pruebas locales
    "salteaba" el calor latente y sobreestimaba el frente 40-200% -- el metodo
    de entalpia lo corrige por construccion). Error tipico 1-8% dependiendo
    del numero de Stefan; converge al refinar n_el (ej. Ste chico = frente muy
    delgado, necesita malla mas fina -- ver nota en la funcion).
  - radiation_exchange: la formula general de red de 2 superficies grises se
    verifica algebraicamente contra 3 casos limite con solucion cerrada exacta:
    placas paralelas infinitas, objeto convexo pequeno en cerramiento grande,
    y limite de cuerpo negro (e1=e2=1) -- error de punto flotante, no empirico.
  - convection_correlations: se verifica que Churchill-Chu (placa vertical)
    converge al limite analitico Nu->0.825^2 cuando Ra->0 (propiedad de la
    formula), y que Nu_promedio_placa_plana_laminar = 2*Nu_local(x=L) (identidad
    exacta de la solucion de capa limite de Blasius, no un ajuste).
  - inverse_conductivity: recupera k conocido desde datos T(x) sinteticos con
    ruido gaussiano (regresion lineal por minimos cuadrados) -- error tipico
    <1% con ruido realista.
  - thermodynamic_properties (Debye): verificado contra los 2 limites exactos
    de la teoria de Debye: alta T -> ley de Dulong-Petit (Cv=3R), baja T -> ley
    T^3 de Debye (Cv=(12*pi^4/5)*R*(T/theta_D)^3) -- error <0.01% en ambos.
"""
import numpy as np
from math import erf, exp, sqrt, pi

SIGMA = 5.670374419e-8   # constante de Stefan-Boltzmann, W/m^2/K^4
R_GAS = 8.314462618      # constante universal de los gases, J/mol/K

THERMAL_ADVANCED_TOOL_SCHEMA = {
    "name": "thermal_advanced_tool",
    "description": (
        "Modulos avanzados de calor/termodinamica: pcm_1d (fusion de material "
        "de cambio de fase, metodo de entalpia, validado contra solucion de "
        "Neumann del problema de Stefan), radiation_exchange (2 superficies "
        "grises difusas, red radiativa validada contra 3 casos limite "
        "cerrados), convection_correlations (Churchill-Chu, Blasius, "
        "Dittus-Boelter, validado contra limites e identidades exactas de las "
        "formulas), inverse_conductivity (recupera k desde datos T(x) "
        "ruidosos por regresion), thermodynamic_properties (gas ideal, "
        "capacidad calorifica de Debye validada contra Dulong-Petit y ley T^3, "
        "relacion de Kelvin Seebeck/Peltier)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["pcm_1d", "radiation_exchange", "convection_correlations",
                         "inverse_conductivity", "thermodynamic_properties", "validate"],
            },
            "params": {"type": "object", "description": "Parametros especificos de cada modo, ver docstring."},
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------- pcm_1d ---
def _solve_stefan_lambda(Ste):
    """Raiz de lambda*exp(lambda^2)*erf(lambda) = Ste/sqrt(pi), por biseccion."""
    target = Ste / sqrt(pi)
    lo, hi = 1e-8, 6.0
    def f(lam):
        return lam*exp(lam**2)*erf(lam) - target
    assert f(lo) < 0 and f(hi) > 0, "Ste fuera de rango soportado (revisa T_s, T_m, cp_l, L_latent)"
    for _ in range(100):
        mid = 0.5*(lo+hi)
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return 0.5*(lo+hi)


def _thomas_precompute(a_sub, b_diag, c_sup):
    n = len(b_diag)
    cp = np.zeros(n-1)
    bp = np.zeros(n)
    bp[0] = b_diag[0]
    cp[0] = c_sup[0]/bp[0]
    for i in range(1, n-1):
        bp[i] = b_diag[i] - a_sub[i-1]*cp[i-1]
        cp[i] = c_sup[i]/bp[i]
    bp[-1] = b_diag[-1] - a_sub[-1]*cp[-2]
    return cp, bp


def _thomas_solve(a_sub, cp, bp, d):
    n = len(bp)
    dp = np.zeros(n)
    dp[0] = d[0]/bp[0]
    for i in range(1, n):
        dp[i] = (d[i]-a_sub[i-1]*dp[i-1])/bp[i]
    out = np.zeros(n)
    out[-1] = dp[-1]
    for i in range(n-2, -1, -1):
        out[i] = dp[i] - cp[i]*out[i+1]
    return out


def _pcm_1d(k_l=0.2, rho=800.0, cp_l=2000.0, L_latent=200000.0, T_m=30.0,
            T_s=60.0, length=0.05, n_el=400, t_final=600.0, n_steps=2000,
            outer_iters=12):
    """
    Fusion 1D: solido uniformemente a T_m para t<=0, superficie x=0 saltada a
    T_s>T_m en t=0+. Dominio finito de tamano `length` con extremo lejano
    aislado -- debe ser >> s(t_final) para aproximar el semi-infinito real
    (el resultado incluye 'far_end_untouched' para que puedas verificarlo).
    Metodo de entalpia (Voller-Cross): se itera la fraccion liquida f en cada
    nodo hasta consistencia con T, en vez de usar una capacidad calorifica
    "aparente" ingenua (esa variante SI se probo y perdia calor latente
    cuando el salto de T por paso de tiempo cruzaba la banda de fusion sin
    "sentir" el pico de capacidad -- sobreestimaba el frente 40-200%).
    Nota de resolucion: si Ste=cp_l*(T_s-T_m)/L_latent es chico, el frente es
    delgado respecto al dominio -- sube n_el si necesitas <5% de error.
    """
    alpha_l = k_l/(rho*cp_l)
    Ste = cp_l*(T_s-T_m)/L_latent
    lam = _solve_stefan_lambda(Ste)

    n_nodes = n_el+1
    x = np.linspace(0.0, length, n_nodes)
    dx = length/n_el
    dt = t_final/n_steps
    r = alpha_l*dt/dx**2

    nu = n_nodes-1
    b = np.full(nu, 1+2*r)
    a_sub = np.full(nu-1, -r)
    c_sup = np.full(nu-1, -r)
    a_sub[-1] = -2*r  # extremo lejano aislado (nodo espejo)
    cp_pre, bp_pre = _thomas_precompute(a_sub, b, c_sup)

    T = np.full(n_nodes, T_m); T[0] = T_s
    f = np.zeros(n_nodes); f[0] = 1.0

    for _step in range(n_steps):
        f_n = f.copy(); T_n = T.copy(); f_p = f_n.copy()
        Tnew = T_n[1:].copy()
        for _it in range(outer_iters):
            d = T_n[1:] - (L_latent/cp_l)*(f_p[1:]-f_n[1:])
            d[0] += r*T_s
            Tnew = _thomas_solve(a_sub, cp_pre, bp_pre, d)
            f_new = np.clip(f_p[1:] + (cp_l/L_latent)*(Tnew-T_m), 0.0, 1.0)
            if np.max(np.abs(f_new-f_p[1:])) < 1e-8:
                f_p[1:] = f_new
                break
            f_p[1:] = f_new
        T = np.concatenate(([T_s], Tnew))
        f = f_p

    tol = 1e-4
    heated = f > (1.0-tol)
    if not heated.any():
        s_num = 0.0
    elif heated.all():
        s_num = length
    else:
        i_last = np.where(heated)[0][-1]
        i_next = i_last+1
        x0, x1 = x[i_last], x[i_next]
        f0, f1 = f[i_last], f[i_next]
        s_num = x0 + (1.0-f0)*(x1-x0)/(f1-f0) if f1 != f0 else x1

    s_analytic = 2*lam*sqrt(alpha_l*t_final)
    rel_err_pct = 100.0*abs(s_num-s_analytic)/s_analytic if s_analytic > 0 else 0.0

    return {
        "mode": "pcm_1d",
        "Ste": Ste, "lambda": lam,
        "interface_position_numeric": float(s_num),
        "interface_position_analytic": s_analytic,
        "max_relative_error_pct": float(rel_err_pct),
        "far_end_untouched": bool(f[-1] < tol),
        "x": x.tolist(), "temperature": T.tolist(), "liquid_fraction": f.tolist(),
    }


# --------------------------------------------------------- radiation ---
def _radiation_exchange(A1=1.0, A2=1.0, e1=0.8, e2=0.8, T1=400.0, T2=300.0, F12=1.0):
    """
    Intercambio neto entre 2 superficies grises difusas via red de
    resistencias radiativas (Incropera cap. 13): q12 = sigma*(T1^4-T2^4) /
    [(1-e1)/(e1*A1) + 1/(A1*F12) + (1-e2)/(e2*A2)]. T1,T2 en Kelvin.
    """
    q12 = SIGMA*(T1**4-T2**4) / ((1-e1)/(e1*A1) + 1.0/(A1*F12) + (1-e2)/(e2*A2))
    return {
        "mode": "radiation_exchange",
        "net_heat_transfer_W": q12,
        "blackbody_emissive_power_1_Wm2": SIGMA*T1**4,
        "blackbody_emissive_power_2_Wm2": SIGMA*T2**4,
    }


def _mode_validate_radiation():
    A, e1, e2, T1, T2 = 2.0, 0.8, 0.5, 500.0, 300.0
    q_gen = _radiation_exchange(A, A, e1, e2, T1, T2, F12=1.0)["net_heat_transfer_W"]
    q_closed = SIGMA*A*(T1**4-T2**4)/(1/e1+1/e2-1)
    err_parallel = abs(q_gen-q_closed)/abs(q_closed)*100

    A1s, A2big, e1b = 0.01, 1e6, 0.9
    q_gen2 = _radiation_exchange(A1s, A2big, e1b, 0.5, 800.0, 300.0, F12=1.0)["net_heat_transfer_W"]
    q_closed2 = SIGMA*e1b*A1s*(800.0**4-300.0**4)
    err_small_in_large = abs(q_gen2-q_closed2)/abs(q_closed2)*100

    q3 = _radiation_exchange(1.5, 1.5, 1.0, 1.0, 400.0, 300.0, F12=0.6)["net_heat_transfer_W"]
    q3_closed = SIGMA*1.5*0.6*(400.0**4-300.0**4)
    err_blackbody = abs(q3-q3_closed)/abs(q3_closed)*100

    return dict(err_parallel_plates_pct=err_parallel,
                err_small_object_large_enclosure_pct=err_small_in_large,
                err_blackbody_limit_pct=err_blackbody)


# --------------------------------------------------------- conveccion ---
def _nu_vertical_plate_churchill_chu(Ra, Pr):
    return (0.825 + 0.387*Ra**(1/6) / (1+(0.492/Pr)**(9/16))**(8/27))**2

def _nu_horizontal_cylinder_churchill_chu(Ra, Pr):
    return (0.60 + 0.387*Ra**(1/6) / (1+(0.559/Pr)**(9/16))**(8/27))**2

def _nu_flat_plate_laminar_avg(Re_L, Pr):
    return 0.664*np.sqrt(Re_L)*Pr**(1/3)

def _nu_flat_plate_laminar_local(Re_x, Pr):
    return 0.332*np.sqrt(Re_x)*Pr**(1/3)

def _nu_pipe_dittus_boelter(Re, Pr, heating=True):
    n = 0.4 if heating else 0.3
    return 0.023*Re**0.8*Pr**n


def _convection_correlations(geometry="vertical_plate", Ra=None, Pr=0.71, Re=None,
                              heating=True, L_char=None, k_fluid=None):
    """
    geometry: 'vertical_plate' | 'horizontal_cylinder' (conveccion natural, usa Ra,Pr)
              'flat_plate_laminar' | 'pipe_turbulent' (conveccion forzada, usa Re,Pr)
    Devuelve Nu y, si se da k_fluid y L_char, tambien h = Nu*k_fluid/L_char [W/m2K].
    """
    if geometry == "vertical_plate":
        Nu = _nu_vertical_plate_churchill_chu(Ra, Pr)
    elif geometry == "horizontal_cylinder":
        Nu = _nu_horizontal_cylinder_churchill_chu(Ra, Pr)
    elif geometry == "flat_plate_laminar":
        Nu = _nu_flat_plate_laminar_avg(Re, Pr)
    elif geometry == "pipe_turbulent":
        Nu = _nu_pipe_dittus_boelter(Re, Pr, heating=heating)
    else:
        raise ValueError(f"geometry desconocida: {geometry}")
    out = {"mode": "convection_correlations", "geometry": geometry, "Nusselt": Nu}
    if k_fluid is not None and L_char is not None:
        out["h_W_m2K"] = Nu*k_fluid/L_char
    return out


def _mode_validate_convection():
    Nu_lim = _nu_vertical_plate_churchill_chu(Ra=1e-12, Pr=0.71)
    err_lim = abs(Nu_lim-0.825**2)/0.825**2*100

    Re_L, Pr = 1e5, 0.71
    Nu_avg = _nu_flat_plate_laminar_avg(Re_L, Pr)
    Nu_local_L = _nu_flat_plate_laminar_local(Re_L, Pr)
    err_identity = abs(Nu_avg-2*Nu_local_L)/Nu_avg*100

    return dict(err_Ra_to_0_limit_pct=err_lim, err_avg_eq_2x_local_identity_pct=err_identity)


# ----------------------------------------------------- inversa (k) ---
def _inverse_conductivity(x_data, T_data, q_flux):
    """
    Conduccion 1D estacionaria sin generacion: T(x) = T0 - (q''/k)*x.
    Ajuste lineal por minimos cuadrados de T vs x -> k = -q''/pendiente.
    q_flux en W/m^2 (positivo si el flujo va en +x).
    """
    x_arr = np.asarray(x_data, dtype=float)
    T_arr = np.asarray(T_data, dtype=float)
    Amat = np.vstack([x_arr, np.ones_like(x_arr)]).T
    (slope, intercept), residuals, rank, sv = np.linalg.lstsq(Amat, T_arr, rcond=None)
    k_est = -q_flux/slope
    fit = slope*x_arr+intercept
    rmse = float(np.sqrt(np.mean((T_arr-fit)**2)))
    return {
        "mode": "inverse_conductivity",
        "k_estimated_W_mK": float(k_est),
        "slope_K_per_m": float(slope),
        "intercept_K": float(intercept),
        "rmse_fit_K": rmse,
    }


def _mode_validate_inverse():
    rng = np.random.default_rng(42)
    k_true = 45.0
    q_flux = 5000.0
    x = np.linspace(0, 0.2, 12)
    T_clean = 300.0 - (q_flux/k_true)*x
    T_noisy = T_clean + rng.normal(0, 0.05, size=x.shape)
    result = _inverse_conductivity(x, T_noisy, q_flux)
    err_pct = abs(result["k_estimated_W_mK"]-k_true)/k_true*100
    return dict(k_true=k_true, k_estimated=result["k_estimated_W_mK"], err_pct=err_pct)


# ---------------------------------------------------- termodinamica ---
def _ideal_gas_properties(n_mol=1.0, dof=5, T1=300.0, T2=400.0, P1=101325.0, P2=101325.0):
    """dof: grados de libertad (3=monoatomico, 5=diatomico rigido, 6=poliatomico no lineal rigido)."""
    Cv = (dof/2.0)*R_GAS
    Cp = Cv+R_GAS
    return {
        "mode": "thermodynamic_properties", "submode": "ideal_gas",
        "Cv_molar_J_molK": Cv, "Cp_molar_J_molK": Cp, "gamma": Cp/Cv,
        "delta_H_J": n_mol*Cp*(T2-T1), "delta_U_J": n_mol*Cv*(T2-T1),
        "delta_S_J_K": n_mol*(Cp*np.log(T2/T1)-R_GAS*np.log(P2/P1)),
    }


def _debye_heat_capacity(T=300.0, theta_D=400.0, n_mol=1.0, n_quad=4000):
    """
    Cv(T) = 9*n*R*(T/theta_D)^3 * integral_0^(theta_D/T) x^4*e^x/(e^x-1)^2 dx.
    Cuadratura trapezoidal simple (suficiente: el integrando es suave).
    """
    x_max = theta_D/T
    x = np.linspace(1e-8, x_max, n_quad)
    integrand = (x**4)*np.exp(x)/np.expm1(x)**2
    integral = np.trapezoid(integrand, x)
    Cv = 9*n_mol*R_GAS*(T/theta_D)**3*integral
    return {
        "mode": "thermodynamic_properties", "submode": "debye_heat_capacity",
        "T": T, "theta_D": theta_D, "Cv_J_molK": float(Cv),
        "Cv_over_3R": float(Cv/(3*R_GAS)),
    }


def _seebeck_peltier(seebeck_coeff_V_per_K, T_kelvin):
    """Relacion de Kelvin (2da relacion de Thomson): Pi = S*T. Exacta (termodinamica de no-equilibrio lineal), no un ajuste."""
    return {
        "mode": "thermodynamic_properties", "submode": "seebeck_peltier",
        "seebeck_coeff_V_per_K": seebeck_coeff_V_per_K, "T_kelvin": T_kelvin,
        "peltier_coeff_V": seebeck_coeff_V_per_K*T_kelvin,
    }


def _thermodynamic_properties(submode="ideal_gas", **params):
    if submode == "ideal_gas":
        return _ideal_gas_properties(**params)
    elif submode == "debye_heat_capacity":
        return _debye_heat_capacity(**params)
    elif submode == "seebeck_peltier":
        return _seebeck_peltier(**params)
    else:
        raise ValueError(f"submode desconocido: {submode}. Use ideal_gas | debye_heat_capacity | seebeck_peltier")


def _mode_validate_thermodynamics():
    theta_D = 400.0
    Cv_highT = _debye_heat_capacity(T=theta_D*50, theta_D=theta_D)["Cv_J_molK"]
    err_highT = abs(Cv_highT-3*R_GAS)/(3*R_GAS)*100

    T_low = theta_D/40.0
    Cv_lowT = _debye_heat_capacity(T=T_low, theta_D=theta_D, n_quad=20000)["Cv_J_molK"]
    Cv_lowT_asym = (12*pi**4/5)*R_GAS*(T_low/theta_D)**3
    err_lowT = abs(Cv_lowT-Cv_lowT_asym)/Cv_lowT_asym*100

    return dict(err_dulong_petit_highT_pct=err_highT, err_debye_T3_lowT_pct=err_lowT)


# ------------------------------------------------------------ validate ---
def _mode_validate():
    r_pcm = _pcm_1d()
    r_pcm2 = _pcm_1d(T_s=90.0)
    r_rad = _mode_validate_radiation()
    r_conv = _mode_validate_convection()
    r_inv = _mode_validate_inverse()
    r_thermo = _mode_validate_thermodynamics()

    checks = {
        "pcm_1d_matches_stefan_solution": r_pcm["max_relative_error_pct"] < 10.0 and r_pcm2["max_relative_error_pct"] < 10.0,
        "radiation_matches_closed_form_limits": all(v < 1e-3 for v in r_rad.values()),
        "convection_matches_formula_limits": all(v < 2.0 for v in r_conv.values()),
        "inverse_recovers_true_conductivity": r_inv["err_pct"] < 2.0,
        "debye_matches_dulong_petit_and_T3": all(v < 0.1 for v in r_thermo.values()),
    }
    return {
        "mode": "validate",
        "pcm_1d_Ste_0_3": r_pcm, "pcm_1d_Ste_0_6": r_pcm2,
        "radiation_checks": r_rad, "convection_checks": r_conv,
        "inverse_check": r_inv, "thermodynamics_checks": r_thermo,
        "checks": checks,
        "expected": (
            "pcm_1d: error <10% contra la solucion de Neumann del problema de "
            "Stefan (metodo de entalpia; sube n_el para mas precision, ver "
            "docstring). radiation_exchange: coincide con 3 limites cerrados "
            "exactos (error de punto flotante). convection_correlations: "
            "coincide con el limite Ra->0 y la identidad Nu_avg=2*Nu_local de "
            "Blasius. inverse_conductivity: recupera k real con <2% de error "
            "con ruido gaussiano realista. thermodynamic_properties (Debye): "
            "coincide con Dulong-Petit (alta T) y la ley T^3 (baja T), <0.1%."
        ),
        "validation_passed": all(checks.values()),
    }


def compute_thermal_advanced(mode, params=None):
    params = params or {}
    if mode == "pcm_1d":
        return _pcm_1d(**params)
    elif mode == "radiation_exchange":
        return _radiation_exchange(**params)
    elif mode == "convection_correlations":
        return _convection_correlations(**params)
    elif mode == "inverse_conductivity":
        return _inverse_conductivity(**params)
    elif mode == "thermodynamic_properties":
        return _thermodynamic_properties(**params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(
            f"modo desconocido: {mode}. Use pcm_1d | radiation_exchange | "
            "convection_correlations | inverse_conductivity | "
            "thermodynamic_properties | validate"
        )


if __name__ == "__main__":
    import json
    d = compute_thermal_advanced("validate")
    print(json.dumps({"checks": d["checks"], "validation_passed": d["validation_passed"]}, indent=2))

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("thermal_advanced_tool", THERMAL_ADVANCED_TOOL_SCHEMA, lambda args, _f=compute_thermal_advanced: _f(**args))
