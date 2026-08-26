"""
marine_ecosystem_impact_tool.py
================================

Tres componentes físicos/ecológicos cerrados y verificables por separado,
pensados para evaluar condiciones de riesgo de marea roja (floraciones
algales nocivas, FAN) e impacto sobre bosques de algas (kelp) en costas
de surgencia como el sur de Chile:

1. Transporte de Ekman / índice de surgencia costera (Bakun)
   -----------------------------------------------------------
   Estrés del viento sobre el oceano (Large & Pond, 1981, coeficiente de
   arrastre dependiente de la velocidad del viento):

       Cd = 1.2e-3                          si |W| < 11 m/s
       Cd = (0.49 + 0.065*|W|) * 1e-3       si 11 <= |W| <= 25 m/s

       tau = rho_aire * Cd * |W| * W   (vector, N/m^2)

   Transporte de Ekman integrado en la capa de mezcla (Pond & Pickard,
   "Introductory Dynamical Oceanography", cap. 9):

       Mx = tau_y / (rho_agua * f)
       My = -tau_x / (rho_agua * f)

   con f = 2*Omega*sin(lat) el parametro de Coriolis (Omega=7.2921e-5
   rad/s). El signo de f invierte automaticamente el sentido del
   transporte entre hemisferios (a la derecha del viento en el
   hemisferio norte, a la izquierda en el sur).

   El indice de surgencia (Bakun) es la proyeccion de ese transporte
   sobre la normal costa-afuera: valores positivos indican transporte
   neto de agua superficial hacia el oceano abierto, lo que fuerza el
   ascenso de agua profunda rica en nutrientes (surgencia) — condicion
   precursora clasica de floraciones algales cuando luego el viento se
   relaja y la columna se estratifica (Trainer et al. 2010; Ryan et
   al. 2005, costa oeste de EEUU, mismo mecanismo fisico aplicable a
   Chile).

2. Estratificacion: frecuencia de Brunt-Vaisala
   -----------------------------------------------
       N^2(z) = -(g/rho0) * d(rho)/dz

   Una columna con N^2 alto (fuertemente estratificada) retiene una
   floracion cerca de la superficie en vez de dispersarla por mezcla
   vertical — el segundo ingrediente fisico del riesgo de marea roja.

3. Dinamica de biomasa de bosque de algas (kelp)
   ------------------------------------------------
   Crecimiento logistico estandar con termino de mortalidad adicional
   (por ejemplo asociado a estres termico o exposicion a toxinas de una
   floracion — el usuario provee la tasa de mortalidad, este modulo no
   inventa una formula de acoplamiento no citable):

       dB/dt = r*B*(1 - B/K) - m*B

   Con m constante esto sigue siendo logistico con tasa y capacidad de
   carga efectivas (r_eff = r-m, K_eff = K*r_eff/r si r_eff>0), lo que
   permite validar el integrador numerico contra la solucion analitica
   cerrada del logistico.

NOTA DE ALCANCE: este modulo entrega los DOS indicadores fisicos
estandar (surgencia + estratificacion) que la literatura usa en
conjunto para evaluar favorabilidad de floracion, y la dinamica de
biomasa de kelp por separado. No se inventa un "indice compuesto de
riesgo de marea roja" con pesos arbitrarios sin respaldo — esa
combinacion es una decision de manejo/umbral local, no una ley fisica
cerrada, y queda a criterio del usuario combinar los 3 outputs.
"""

import numpy as np

TOOL_NAME = "marine_ecosystem_impact_tool"
TOOL_MODES = ["ekman_upwelling", "stratification", "kelp_dynamics", "validate"]

OMEGA_EARTH = 7.2921e-5  # rad/s, velocidad angular de rotacion terrestre
G = 9.81                 # m/s^2


# ----------------------------------------------------------------------
# 1. Transporte de Ekman / indice de surgencia (Bakun)
# ----------------------------------------------------------------------

def coriolis_parameter(lat_deg):
    """f = 2*Omega*sin(lat). Negativo en el hemisferio sur."""
    return 2.0 * OMEGA_EARTH * np.sin(np.deg2rad(lat_deg))


def drag_coefficient(wind_speed_ms):
    """Coeficiente de arrastre de Large & Pond (1981)."""
    w = np.asarray(wind_speed_ms, dtype=float)
    cd = np.where(w < 11.0, 1.2e-3, (0.49 + 0.065 * w) * 1e-3)
    return cd


def wind_stress(wind_speed_ms, wind_dir_from_deg, rho_air=1.225):
    """
    Estres del viento (tau_x, tau_y) en N/m^2, convencion meteorologica
    de direccion (wind_dir_from_deg = de donde viene el viento, grados
    desde el norte en sentido horario). Componentes en (este, norte).
    """
    speed = float(wind_speed_ms)
    cd = float(drag_coefficient(speed))
    dir_rad = np.deg2rad(wind_dir_from_deg)
    # El viento SOPLA HACIA la direccion opuesta a la que viene
    u = -speed * np.sin(dir_rad)
    v = -speed * np.cos(dir_rad)
    tau_x = rho_air * cd * speed * u
    tau_y = rho_air * cd * speed * v
    return float(tau_x), float(tau_y)


def ekman_transport(wind_speed_ms, wind_dir_from_deg, lat_deg,
                     rho_air=1.225, rho_water=1025.0):
    """Transporte de Ekman (Mx, My) en m^2/s (por metro de costa)."""
    tau_x, tau_y = wind_stress(wind_speed_ms, wind_dir_from_deg, rho_air)
    f = coriolis_parameter(lat_deg)
    if abs(f) < 1e-10:
        raise ValueError("Parametro de Coriolis ~0 (latitud ecuatorial); "
                          "el balance de Ekman no aplica cerca del ecuador")
    Mx = tau_y / (rho_water * f)
    My = -tau_x / (rho_water * f)
    return float(Mx), float(My)


def upwelling_index(wind_speed_ms, wind_dir_from_deg, lat_deg,
                     offshore_direction_deg, rho_air=1.225, rho_water=1025.0):
    """
    Proyecta el transporte de Ekman sobre la normal costa-afuera
    (offshore_direction_deg = rumbo, grados desde el norte, que apunta
    desde la costa hacia mar abierto). Positivo = favorable a surgencia.
    """
    Mx, My = ekman_transport(wind_speed_ms, wind_dir_from_deg, lat_deg,
                              rho_air, rho_water)
    off_rad = np.deg2rad(offshore_direction_deg)
    n_east = np.sin(off_rad)
    n_north = np.cos(off_rad)
    cross_shore = Mx * n_east + My * n_north           # componente costa-afuera
    along_shore = -Mx * n_north + My * n_east           # componente paralela a costa
    return {
        "Mx_m2s": Mx,
        "My_m2s": My,
        "transport_magnitude_m2s": float(np.hypot(Mx, My)),
        "cross_shore_upwelling_index_m2s": float(cross_shore),
        "along_shore_transport_m2s": float(along_shore),
        "coriolis_f": float(coriolis_parameter(lat_deg)),
        "upwelling_favorable": bool(cross_shore > 0),
    }


# ----------------------------------------------------------------------
# 2. Estratificacion: frecuencia de Brunt-Vaisala
# ----------------------------------------------------------------------

def brunt_vaisala(depths_m, densities_kgm3, rho0=1025.0, g=G):
    """
    N^2 = (g/rho0) * d(rho)/dz  vía diferencias centradas, con z=depths_m
    definido POSITIVO HACIA ABAJO (profundidad, convencion oceanografica
    habitual para perfiles de CTD). Nota: la forma clasica N^2=-(g/rho0)*
    drho/dz corresponde a z positivo hacia ARRIBA (altura); al usar
    profundidad el signo se invierte, por eso aqui es +(g/rho0)*drho/dz
    (columna estable = densidad crece con la profundidad = drho/dz>0 =>
    N^2>0, correcto).
    Devuelve N2 por punto interior (extremos con diferencias hacia
    adelante/atras de primer orden).
    """
    z = np.asarray(depths_m, dtype=float)
    rho = np.asarray(densities_kgm3, dtype=float)
    if len(z) != len(rho) or len(z) < 2:
        raise ValueError("depths_m y densities_kgm3 deben tener la misma "
                          "longitud >= 2")
    n = len(z)
    drho_dz = np.empty(n)
    drho_dz[1:-1] = (rho[2:] - rho[:-2]) / (z[2:] - z[:-2])
    drho_dz[0] = (rho[1] - rho[0]) / (z[1] - z[0])
    drho_dz[-1] = (rho[-1] - rho[-2]) / (z[-1] - z[-2])
    N2 = (g / rho0) * drho_dz
    return N2.tolist()


# ----------------------------------------------------------------------
# 3. Dinamica logistica de biomasa de kelp
# ----------------------------------------------------------------------

def _kelp_rhs(B, r, K, m):
    return r * B * (1.0 - B / K) - m * B


def kelp_biomass_dynamics(B0, r, K, mortality_rate, t_end_days, dt_days=0.1):
    """Integra dB/dt = r*B*(1-B/K) - m*B via RK4."""
    n_steps = int(round(t_end_days / dt_days))
    t = np.linspace(0.0, n_steps * dt_days, n_steps + 1)
    B = np.empty(n_steps + 1)
    B[0] = float(B0)
    h = dt_days
    for i in range(n_steps):
        b = B[i]
        k1 = _kelp_rhs(b, r, K, mortality_rate)
        k2 = _kelp_rhs(b + 0.5 * h * k1, r, K, mortality_rate)
        k3 = _kelp_rhs(b + 0.5 * h * k2, r, K, mortality_rate)
        k4 = _kelp_rhs(b + h * k3, r, K, mortality_rate)
        b_next = b + (h / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        B[i + 1] = max(b_next, 0.0)
    return {
        "t_days": t.tolist(),
        "biomass": B.tolist(),
        "final_biomass": float(B[-1]),
        "r_eff": float(r - mortality_rate),
    }


def _logistic_analytic(t, B0, r, K):
    """Solucion cerrada del logistico puro (sin mortalidad)."""
    return K * B0 * np.exp(r * t) / (K + B0 * (np.exp(r * t) - 1.0))


# ----------------------------------------------------------------------
# Validacion
# ----------------------------------------------------------------------

def _validate():
    checks = []

    # --- Check 1: coeficiente de arrastre contra valores citados de
    # Large & Pond (1981) en los dos regimenes
    cd10 = float(drag_coefficient(10.0))
    cd20 = float(drag_coefficient(20.0))
    check1 = abs(cd10 - 1.2e-3) < 1e-9 and abs(cd20 - 1.79e-3) < 1e-9
    checks.append({
        "name": "drag_coefficient_large_pond_1981",
        "passed": bool(check1),
        "detail": f"Cd(10 m/s)={cd10:.6f} (ref 0.0012), Cd(20 m/s)={cd20:.6f} (ref 0.00179)",
    })

    # --- Check 2: descomposicion costa-afuera/paralela es ortogonal
    # (consistencia geometrica: |M|^2 = cross_shore^2 + along_shore^2)
    res = upwelling_index(wind_speed_ms=8.0, wind_dir_from_deg=20.0,
                           lat_deg=-42.0, offshore_direction_deg=270.0)
    lhs = res["transport_magnitude_m2s"] ** 2
    rhs = res["cross_shore_upwelling_index_m2s"] ** 2 + res["along_shore_transport_m2s"] ** 2
    check2 = abs(lhs - rhs) < 1e-8 * max(lhs, 1e-8)
    checks.append({
        "name": "descomposicion_ortogonal_costa",
        "passed": bool(check2),
        "detail": f"|M|^2={lhs:.6e}, cross^2+along^2={rhs:.6e}",
    })

    # --- Check 3: el transporte de Ekman invierte de signo entre
    # hemisferios para el mismo viento (mismo modulo, |lat| igual)
    Mx_s, My_s = ekman_transport(10.0, 200.0, lat_deg=-40.0)
    Mx_n, My_n = ekman_transport(10.0, 200.0, lat_deg=40.0)
    check3 = abs(Mx_s + Mx_n) < 1e-9 and abs(My_s + My_n) < 1e-9
    checks.append({
        "name": "inversion_hemisferica",
        "passed": bool(check3),
        "detail": f"sur=({Mx_s:.6f},{My_s:.6f}) norte=({Mx_n:.6f},{My_n:.6f})",
    })

    # --- Check 4: latitud ecuatorial da error controlado
    try:
        ekman_transport(10.0, 200.0, lat_deg=0.0)
        check4 = False
        check4_detail = "no lanzo ValueError en el ecuador"
    except ValueError:
        check4 = True
        check4_detail = "ValueError controlado como se esperaba"
    checks.append({
        "name": "latitud_ecuatorial_da_error",
        "passed": bool(check4),
        "detail": check4_detail,
    })

    # --- Check 5: Brunt-Vaisala contra perfil analitico exponencial
    # rho(z) = rho0*exp(z/H)  =>  N^2(z) = (g/H)*exp(z/H)  (NO es
    # constante — crece con z; se compara punto a punto, no contra un
    # valor unico)
    H = 200.0
    rho0 = 1025.0
    z = np.linspace(0.0, 100.0, 50)
    rho = rho0 * np.exp(z / H)
    N2 = np.array(brunt_vaisala(z, rho, rho0=rho0))
    N2_analytic = (G / H) * np.exp(z / H)
    # excluir extremos (diferencias de menor orden ahi)
    rel_err = np.abs(N2[2:-2] - N2_analytic[2:-2]) / N2_analytic[2:-2]
    check5 = bool(np.all(rel_err < 0.01))
    checks.append({
        "name": "brunt_vaisala_perfil_exponencial",
        "passed": check5,
        "detail": f"max error relativo (rango interior)={rel_err.max():.4e}",
    })

    # --- Check 6: columna homogenea (rho constante) da N^2 = 0 exacto
    rho_flat = np.full(20, 1025.0)
    z_flat = np.linspace(0, 50, 20)
    N2_flat = np.array(brunt_vaisala(z_flat, rho_flat))
    check6 = bool(np.all(np.abs(N2_flat) < 1e-12))
    checks.append({
        "name": "brunt_vaisala_columna_homogenea",
        "passed": check6,
        "detail": f"max|N2|={np.max(np.abs(N2_flat)):.2e} (esperado 0)",
    })

    # --- Check 7: kelp sin mortalidad converge a la solucion analitica
    # cerrada del logistico puro
    r, K, B0 = 0.05, 100.0, 5.0
    sim = kelp_biomass_dynamics(B0, r, K, mortality_rate=0.0,
                                 t_end_days=200.0, dt_days=0.5)
    t_arr = np.array(sim["t_days"])
    B_num = np.array(sim["biomass"])
    B_analytic = _logistic_analytic(t_arr, B0, r, K)
    max_rel_err = float(np.max(np.abs(B_num - B_analytic) / K))
    check7 = max_rel_err < 1e-3
    checks.append({
        "name": "kelp_logistico_puro_vs_analitico",
        "passed": bool(check7),
        "detail": f"max error relativo (fraccion de K)={max_rel_err:.2e}",
    })

    # --- Check 8: con mortalidad alta (m > r) la biomasa decae hacia 0
    sim_decline = kelp_biomass_dynamics(B0=50.0, r=0.05, K=100.0,
                                         mortality_rate=0.20,
                                         t_end_days=100.0, dt_days=0.5)
    check8 = sim_decline["final_biomass"] < 50.0 * 0.05
    checks.append({
        "name": "kelp_declina_con_mortalidad_alta",
        "passed": bool(check8),
        "detail": f"biomasa final={sim_decline['final_biomass']:.4f} "
                   f"(inicial=50.0, mortality_rate=0.20 > r=0.05)",
    })

    # --- Check 9: con mortalidad moderada (m < r) converge al K
    # efectivo K*(r-m)/r, no al K original
    r9, K9, m9 = 0.08, 100.0, 0.03
    sim_eff = kelp_biomass_dynamics(B0=5.0, r=r9, K=K9, mortality_rate=m9,
                                     t_end_days=500.0, dt_days=0.5)
    K_eff_expected = K9 * (r9 - m9) / r9
    check9 = abs(sim_eff["final_biomass"] - K_eff_expected) < 0.02 * K_eff_expected
    checks.append({
        "name": "kelp_capacidad_de_carga_efectiva",
        "passed": bool(check9),
        "detail": f"final={sim_eff['final_biomass']:.4f}, "
                   f"K_eff esperado={K_eff_expected:.4f}",
    })

    # --- Check 10: biomasa nunca negativa
    sim_extreme = kelp_biomass_dynamics(B0=10.0, r=0.05, K=100.0,
                                         mortality_rate=5.0,
                                         t_end_days=50.0, dt_days=0.5)
    check10 = bool(np.all(np.array(sim_extreme["biomass"]) >= 0.0))
    checks.append({
        "name": "kelp_biomasa_no_negativa",
        "passed": check10,
        "detail": f"min biomasa={min(sim_extreme['biomass']):.6f}",
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "validation_passed": bool(all_passed),
        "n_checks": len(checks),
        "n_passed": sum(1 for c in checks if c["passed"]),
        "checks": checks,
    }


# ----------------------------------------------------------------------
# Dispatch / registro
# ----------------------------------------------------------------------

def run(arguments):
    mode = arguments.get("mode", "validate")
    params = arguments.get("params", {}) or {}

    if mode == "ekman_upwelling":
        return upwelling_index(
            wind_speed_ms=params["wind_speed_ms"],
            wind_dir_from_deg=params["wind_dir_from_deg"],
            lat_deg=params["lat_deg"],
            offshore_direction_deg=params["offshore_direction_deg"],
            rho_air=params.get("rho_air", 1.225),
            rho_water=params.get("rho_water", 1025.0),
        )
    elif mode == "stratification":
        return {
            "N2": brunt_vaisala(
                depths_m=params["depths_m"],
                densities_kgm3=params["densities_kgm3"],
                rho0=params.get("rho0", 1025.0),
            )
        }
    elif mode == "kelp_dynamics":
        return kelp_biomass_dynamics(
            B0=params["B0"],
            r=params["r"],
            K=params["K"],
            mortality_rate=params.get("mortality_rate", 0.0),
            t_end_days=params["t_end_days"],
            dt_days=params.get("dt_days", 0.1),
        )
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode!r}. Modos validos: {TOOL_MODES}")


TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Indicadores fisicos de riesgo de marea roja (transporte de Ekman/"
        "indice de surgencia de Bakun, frecuencia de Brunt-Vaisala para "
        "estratificacion) y dinamica logistica de biomasa de bosque de "
        "algas (kelp) con mortalidad."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": TOOL_MODES},
            "params": {
                "type": "object",
                "description": (
                    "ekman_upwelling: {wind_speed_ms, wind_dir_from_deg, lat_deg, "
                    "offshore_direction_deg} | stratification: {depths_m, "
                    "densities_kgm3} | kelp_dynamics: {B0, r, K, mortality_rate?, "
                    "t_end_days, dt_days?}"
                ),
            },
        },
        "required": ["mode"],
    },
}


def _register():
    try:
        from tool_registry import register_tool
        register_tool(name=TOOL_NAME, schema=TOOL_SCHEMA, handler=run)
    except ImportError:
        pass


_register()


if __name__ == "__main__":
    import json
    print(json.dumps(run({"mode": "validate"}), indent=2))
