#!/usr/bin/env python3
"""
virtual_pharmacokinetics.py

Modelo PBPK (Physiologically-Based PharmacoKinetic) compartimental,
flow-limited (perfusion-limited), en numpy puro (sin scipy, sin httk).

Filosofia de diseno (ver notas de Astrid):
  1. Las ECUACIONES (balance de masa flow-limited entre compartimentos
     perfundidos por sangre) son fisiologia estandar de PBPK -- se
     validan aca mismo por conservacion de masa, linealidad y estado
     estacionario, SIN depender de ninguna cifra externa de httk/EPA.
  2. La TABLA DE FISIOLOGIA (volumenes de organo, flujos sanguineos)
     son valores estandar de referencia de la literatura (orden de
     magnitud correcto, ampliamente citados en trabajos de PBPK) pero
     estan marcados explicitamente como APROXIMADOS -- si se necesita
     reproducir los resultados exactos de httk, hay que reemplazar
     PHYSIOLOGY_HUMAN_70KG por la tabla real de physiology.data de esa
     libreria.
  3. Los parametros QUIMICOS (coeficientes de particion tejido:sangre
     Kp, clearance hepatico/renal, ka de absorcion oral) son SIEMPRE
     inputs obligatorios del usuario -- esta tool nunca los estima ni
     los inventa a partir de la estructura de la molecula.

Compartimentos: sangre (arterial+venosa mezclada), higado, rinon,
intestino (gut), musculo, tejido adiposo, resto del cuerpo (lumped).
Absorcion oral opcional via deposito de intestino (luz intestinal)
con cinetica de primer orden ka.
"""

import json
import sys
import math
import numpy as np

try:
    from scipy.integrate import solve_ivp
    _HAVE_SCIPY = True
except ImportError:
    _HAVE_SCIPY = False

# ---------------------------------------------------------------------
# 1) TABLA DE FISIOLOGIA -- APROXIMADA, NO ES LA TABLA EXACTA DE httk
# ---------------------------------------------------------------------
# Valores de referencia estandar para un humano adulto de 70 kg,
# ampliamente citados en la literatura de PBPK (orden de magnitud
# correcto). Volumenes en L, flujos sanguineos en L/h.
# NOTA: si se necesita reproducir httk exactamente, reemplazar esta
# tabla por su physiology.data real.
PHYSIOLOGY_HUMAN_70KG_APPROX = {
    "body_weight_kg": 70.0,
    "cardiac_output_L_per_h": 336.0,  # ~5.6 L/min
    "tissues": {
        # nombre: {volumen_L, fraccion_del_gasto_cardiaco}
        "liver":   {"volume_L": 1.8,  "flow_frac": 0.255},  # arterial hepatica, sin contar portal via gut
        "kidney":  {"volume_L": 0.31, "flow_frac": 0.190},
        "gut":     {"volume_L": 1.65, "flow_frac": 0.150},  # drena a higado (portal), no directo a vena cava
        "muscle":  {"volume_L": 29.0, "flow_frac": 0.170},
        "adipose": {"volume_L": 14.0, "flow_frac": 0.050},
        "rest":    {"volume_L": 8.0,  "flow_frac": 0.185},  # piel, hueso, cerebro, etc. lumped
    },
    "blood_volume_L": 5.0,
}


def _validate_physiology(phys):
    tissues = phys["tissues"]
    frac_sum = sum(t["flow_frac"] for t in tissues.values())
    if abs(frac_sum - 1.0) > 1e-6:
        raise ValueError(
            f"Las fracciones de flujo de la tabla de fisiologia deben sumar 1.0, "
            f"suman {frac_sum:.6f}"
        )
    return phys


PHYSIOLOGY_HUMAN_70KG_APPROX = _validate_physiology(PHYSIOLOGY_HUMAN_70KG_APPROX)

TISSUE_ORDER = ["liver", "kidney", "gut", "muscle", "adipose", "rest"]


# ---------------------------------------------------------------------
# 2) MODELO COMPARTIMENTAL FLOW-LIMITED
# ---------------------------------------------------------------------
# Vector de estado y = [Cart, C_liver, C_kidney, C_gut, C_muscle,
#                        C_adipose, C_rest, A_gut_lumen, A_eliminated]
#
# Cart es la concentracion de sangre mezclada (arterial=venosa, se
# asume equilibrio instantaneo en pulmon -- simplificacion estandar
# para farmacos no volatiles). A_gut_lumen es la masa (no conc.) de
# dosis oral aun sin absorber. A_eliminated acumula la masa eliminada
# (hepatica + renal) solo para el chequeo de conservacion de masa.

N_TISSUES = len(TISSUE_ORDER)
IDX_CART = 0
IDX_TISSUE0 = 1
IDX_GUT_LUMEN = IDX_TISSUE0 + N_TISSUES
IDX_ELIM = IDX_GUT_LUMEN + 1
STATE_SIZE = IDX_ELIM + 1


def _tissue_idx(name):
    return IDX_TISSUE0 + TISSUE_ORDER.index(name)


def build_flows(phys):
    """Convierte flow_frac de la tabla de fisiologia en flujos absolutos (L/h)."""
    Qco = phys["cardiac_output_L_per_h"]
    Q = {name: Qco * t["flow_frac"] for name, t in phys["tissues"].items()}
    V = {name: t["volume_L"] for name, t in phys["tissues"].items()}
    return Qco, Q, V


def make_derivative_fn(phys, Kp, CLh, CLr, ka, infusion_rate_fn):
    """
    Devuelve una funcion dydt(t, y) para el modelo PBPK.

    Kp: dict tejido -> coeficiente de particion tejido:sangre (obligatorio,
        adimensional; Kp=1 significa que la concentracion tisular en
        equilibrio iguala a la de la sangre)
    CLh: clearance hepatico intrinseco (L/h), actua sobre C_liver/Kp_liver
         (modelo well-stirred estandar)
    CLr: clearance renal (L/h), actua sobre C_kidney/Kp_kidney
    ka: constante de absorcion oral de primer orden (1/h); 0 si no hay
        dosis oral
    infusion_rate_fn: funcion t -> tasa de infusion IV (masa/h) en sangre
    """
    Qco, Q, V = build_flows(phys)
    Vb = phys["blood_volume_L"]

    def dydt(t, y):
        Cart = y[IDX_CART]
        Ct = {name: y[_tissue_idx(name)] for name in TISSUE_ORDER}
        A_gut_lumen = y[IDX_GUT_LUMEN]

        dy = np.zeros(STATE_SIZE)

        # --- absorcion oral: primer orden desde la luz intestinal ---
        absorb_rate = ka * A_gut_lumen  # masa/h
        dy[IDX_GUT_LUMEN] = -absorb_rate

        # --- tejidos no eliminadores (perfusion-limited estandar) ---
        # Vi * dCi/dt = Qi * (Cart - Ci/Kpi)
        venous_return = 0.0  # suma de Qi * (Ci/Kpi) que vuelve a la sangre
        elim_rate = 0.0

        for name in TISSUE_ORDER:
            Ci = Ct[name]
            Vi = V[name]
            Qi = Q[name]
            Kpi = Kp[name]
            Cout_i = Ci / Kpi  # concentracion venosa saliente del tejido

            if name == "gut":
                # el intestino recibe flujo arterial normal, mas la
                # masa absorbida de la dosis oral entra directo al
                # compartimento tisular del intestino; su salida NO va
                # a la sangre general sino al higado (circulacion
                # portal) -- se maneja en la rama "liver" de abajo.
                dCi = (Qi * (Cart - Cout_i) + absorb_rate) / Vi
                dy[_tissue_idx(name)] = dCi
                continue

            if name == "liver":
                # el higado recibe flujo arterial propio + el drenaje
                # portal del intestino (Qgut * Cgut/Kpgut), y elimina
                # farmaco por clearance hepatico intrinseco (well-stirred)
                Qgut = Q["gut"]
                Cout_gut = Ct["gut"] / Kp["gut"]
                Qliver_total = Qi + Qgut  # todo lo que sale del higado hacia vena cava
                inflow = Qi * Cart + Qgut * Cout_gut
                outflow = Qliver_total * Cout_i
                hepatic_elim = CLh * Cout_i
                dCi = (inflow - outflow - hepatic_elim) / Vi
                dy[_tissue_idx(name)] = dCi
                venous_return += Qliver_total * Cout_i
                elim_rate += hepatic_elim
                continue

            if name == "kidney":
                renal_elim = CLr * Cout_i
                dCi = (Qi * (Cart - Cout_i) - renal_elim) / Vi
                dy[_tissue_idx(name)] = dCi
                venous_return += Qi * Cout_i
                elim_rate += renal_elim
                continue

            # tejidos simples sin eliminacion: muscle, adipose, rest
            dCi = Qi * (Cart - Cout_i) / Vi
            dy[_tissue_idx(name)] = dCi
            venous_return += Qi * Cout_i

        # --- sangre mezclada (compartimento central) ---
        # Vb * dCart/dt = venous_return - Qco*Cart + infusion(t)
        infusion = infusion_rate_fn(t)
        dy[IDX_CART] = (venous_return - Qco * Cart + infusion) / Vb

        dy[IDX_ELIM] = elim_rate

        return dy

    return dydt


def _rk4_fixed(dydt, y0, t_span, n_steps):
    t0, t1 = t_span
    dt = (t1 - t0) / n_steps
    t = t0
    y = np.array(y0, dtype=float)
    ts = np.zeros(n_steps + 1)
    ys = np.zeros((n_steps + 1, len(y0)))
    ts[0] = t
    ys[0] = y
    for i in range(n_steps):
        k1 = dydt(t, y)
        k2 = dydt(t + dt / 2, y + dt / 2 * k1)
        k3 = dydt(t + dt / 2, y + dt / 2 * k2)
        k4 = dydt(t + dt, y + dt * k3)
        y = y + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        t = t + dt
        ts[i + 1] = t
        ys[i + 1] = y
        if not np.all(np.isfinite(y)):
            raise FloatingPointError(
                f"RK4 fijo diverge en t={t:.4f} (paso dt={dt:.3e} demasiado grande "
                f"para la rigidez del sistema -- reintentar con mas n_steps o con scipy instalado)"
            )
    return ts, ys


def rk4_integrate(dydt, y0, t_span, n_steps):
    """
    Integra el sistema PBPK. Los compartimentos de bajo volumen y alto
    flujo (ej. rinon) son numericamente rigidos (stiff) -- igual que en
    httk, que resuelve esto con un solver tipo LSODA. Si scipy esta
    disponible se usa LSODA (robusto ante rigidez); si no, se cae a un
    RK4 de paso fijo con subdivision automatica del paso hasta que no
    diverja (mas lento, pero sin dependencias nuevas).
    """
    t0, t1 = t_span
    if _HAVE_SCIPY:
        t_eval = np.linspace(t0, t1, n_steps + 1)

        def dydt_scipy(t, y):
            return dydt(t, y)

        sol = solve_ivp(dydt_scipy, (t0, t1), np.array(y0, dtype=float),
                         method="LSODA", t_eval=t_eval, rtol=1e-8, atol=1e-10)
        if not sol.success:
            raise RuntimeError(f"LSODA fallo: {sol.message}")
        return sol.t, sol.y.T

    # fallback sin scipy: subdivide el paso hasta que no diverja
    attempt_steps = n_steps
    for _ in range(6):
        try:
            return _rk4_fixed(dydt, y0, t_span, attempt_steps)
        except FloatingPointError:
            attempt_steps *= 4
    raise FloatingPointError(
        "El sistema es demasiado rigido para RK4 de paso fijo incluso subdividiendo "
        "el paso 4^6 veces -- instalar scipy para usar LSODA"
    )


# ---------------------------------------------------------------------
# 3) INTERFAZ DE ALTO NIVEL
# ---------------------------------------------------------------------

def _resolve_Kp(kp_param):
    """
    kp_param puede ser:
      - un numero (float/int): mismo Kp para todos los tejidos
      - un dict {tejido: Kp} con las 6 claves de TISSUE_ORDER
    """
    if isinstance(kp_param, (int, float)):
        return {name: float(kp_param) for name in TISSUE_ORDER}
    if isinstance(kp_param, dict):
        missing = [name for name in TISSUE_ORDER if name not in kp_param]
        if missing:
            raise ValueError(f"Faltan coeficientes Kp para: {missing}")
        return {name: float(kp_param[name]) for name in TISSUE_ORDER}
    raise ValueError("Kp debe ser un numero (uniforme) o un dict por tejido")


def simulate(params):
    """
    params esperado:
      dose_mg: dosis total (obligatorio)
      route: "iv_bolus" | "iv_infusion" | "oral"  (default "iv_bolus")
      infusion_duration_h: requerido si route == "iv_infusion"
      ka_per_h: requerido si route == "oral" (constante de absorcion 1a orden)
      Kp: numero o dict por tejido (OBLIGATORIO, coef. de particion tejido:sangre)
      CLh_L_per_h: clearance hepatico (default 0.0)
      CLr_L_per_h: clearance renal (default 0.0)
      duration_h: tiempo total de simulacion (default 24)
      n_steps: pasos de integracion (default 2000)
      physiology: tabla de fisiologia opcional (default PHYSIOLOGY_HUMAN_70KG_APPROX)
      output_times_h: lista opcional de tiempos donde reportar (si no, usa la grilla completa)
    """
    if "dose_mg" not in params:
        raise ValueError("dose_mg es obligatorio")
    if "Kp" not in params:
        raise ValueError(
            "Kp es obligatorio (coeficiente de particion tejido:sangre) -- "
            "esta tool no estima parametros quimicos, deben suministrarse"
        )

    dose = float(params["dose_mg"])
    route = params.get("route", "iv_bolus")
    Kp = _resolve_Kp(params["Kp"])
    CLh = float(params.get("CLh_L_per_h", 0.0))
    CLr = float(params.get("CLr_L_per_h", 0.0))
    duration_h = float(params.get("duration_h", 24.0))
    n_steps = int(params.get("n_steps", 2000))
    phys = params.get("physiology", PHYSIOLOGY_HUMAN_70KG_APPROX)
    phys = _validate_physiology(phys)

    y0 = np.zeros(STATE_SIZE)
    ka = 0.0
    infusion_rate_fn = lambda t: 0.0

    if route == "iv_bolus":
        y0[IDX_CART] = dose / phys["blood_volume_L"]
    elif route == "iv_infusion":
        if "infusion_duration_h" not in params:
            raise ValueError("infusion_duration_h es obligatorio para route='iv_infusion'")
        T_inf = float(params["infusion_duration_h"])
        rate = dose / T_inf  # mg/h
        infusion_rate_fn = lambda t, rate=rate, T_inf=T_inf: rate if t < T_inf else 0.0
    elif route == "oral":
        if "ka_per_h" not in params:
            raise ValueError("ka_per_h es obligatorio para route='oral'")
        ka = float(params["ka_per_h"])
        y0[IDX_GUT_LUMEN] = dose
    else:
        raise ValueError(f"route desconocido: {route}")

    dydt = make_derivative_fn(phys, Kp, CLh, CLr, ka, infusion_rate_fn)
    ts, ys = rk4_integrate(dydt, y0, (0.0, duration_h), n_steps)

    result = {
        "t_h": ts.tolist(),
        "C_blood_mg_per_L": ys[:, IDX_CART].tolist(),
    }
    for name in TISSUE_ORDER:
        result[f"C_{name}_mg_per_L"] = ys[:, _tissue_idx(name)].tolist()
    result["mass_eliminated_mg"] = ys[:, IDX_ELIM].tolist()
    result["mass_gut_lumen_mg"] = ys[:, IDX_GUT_LUMEN].tolist()

    if "output_times_h" in params:
        out_t = np.array(params["output_times_h"], dtype=float)
        sampled = {"t_h": out_t.tolist()}
        for key in result:
            if key == "t_h":
                continue
            sampled[key] = np.interp(out_t, ts, result[key]).tolist()
        result = sampled

    result["physiology_note"] = (
        "Tabla de fisiologia APROXIMADA (valores estandar de literatura, "
        "no la tabla exacta de httk/EPA)"
    )
    return result


def _total_mass_in_system(y, phys):
    Vb = phys["blood_volume_L"]
    _, _, V = build_flows(phys)
    total = y[IDX_CART] * Vb
    for name in TISSUE_ORDER:
        total += y[_tissue_idx(name)] * V[name]
    total += y[IDX_GUT_LUMEN]
    total += y[IDX_ELIM]
    return total


# ---------------------------------------------------------------------
# 4) SELF-TEST -- conservacion de masa, linealidad, estado estacionario
# ---------------------------------------------------------------------

def run_self_test():
    checks = []
    phys = PHYSIOLOGY_HUMAN_70KG_APPROX

    # --- Check 1: fracciones de flujo suman 1.0 ---
    frac_sum = sum(t["flow_frac"] for t in phys["tissues"].values())
    checks.append({
        "name": "fisiologia: fracciones de flujo suman 1.0",
        "passed": bool(abs(frac_sum - 1.0) < 1e-9),
        "detail": f"suma={frac_sum:.9f}",
    })

    # --- Check 2: conservacion de masa, IV bolus SIN eliminacion ---
    Kp_uniform = {name: 1.5 for name in TISSUE_ORDER}
    dydt = make_derivative_fn(phys, Kp_uniform, CLh=0.0, CLr=0.0, ka=0.0,
                               infusion_rate_fn=lambda t: 0.0)
    y0 = np.zeros(STATE_SIZE)
    dose = 100.0
    y0[IDX_CART] = dose / phys["blood_volume_L"]
    ts, ys = rk4_integrate(dydt, y0, (0.0, 48.0), 4000)
    masses = np.array([_total_mass_in_system(y, phys) for y in ys])
    max_rel_drift = np.max(np.abs(masses - dose)) / dose
    checks.append({
        "name": "conservacion de masa (IV bolus, sin eliminacion, Kp uniforme)",
        "passed": bool(max_rel_drift < 1e-6),
        "detail": f"max drift relativo={max_rel_drift:.3e} (dosis={dose} mg)",
    })

    # --- Check 3: conservacion de masa CON eliminacion (masa + eliminado = dosis) ---
    dydt_elim = make_derivative_fn(phys, Kp_uniform, CLh=20.0, CLr=10.0, ka=0.0,
                                    infusion_rate_fn=lambda t: 0.0)
    ts2, ys2 = rk4_integrate(dydt_elim, y0, (0.0, 48.0), 4000)
    masses2 = np.array([_total_mass_in_system(y, phys) for y in ys2])
    max_rel_drift2 = np.max(np.abs(masses2 - dose)) / dose
    checks.append({
        "name": "conservacion de masa (IV bolus, CON clearance hepatico+renal)",
        "passed": bool(max_rel_drift2 < 1e-6),
        "detail": f"max drift relativo={max_rel_drift2:.3e}",
    })

    # --- Check 4: conservacion de masa con dosis ORAL (absorcion incluida) ---
    dydt_oral = make_derivative_fn(phys, Kp_uniform, CLh=5.0, CLr=2.0, ka=0.5,
                                    infusion_rate_fn=lambda t: 0.0)
    y0_oral = np.zeros(STATE_SIZE)
    y0_oral[IDX_GUT_LUMEN] = dose
    ts3, ys3 = rk4_integrate(dydt_oral, y0_oral, (0.0, 72.0), 6000)
    masses3 = np.array([_total_mass_in_system(y, phys) for y in ys3])
    max_rel_drift3 = np.max(np.abs(masses3 - dose)) / dose
    checks.append({
        "name": "conservacion de masa (dosis oral, absorcion + clearance)",
        "passed": bool(max_rel_drift3 < 1e-6),
        "detail": f"max drift relativo={max_rel_drift3:.3e}",
    })

    # --- Check 5: linealidad (doblar la dosis dobla la concentracion) ---
    r1 = simulate({
        "dose_mg": 50.0, "route": "iv_bolus", "Kp": 2.0,
        "CLh_L_per_h": 15.0, "CLr_L_per_h": 5.0,
        "duration_h": 24.0, "n_steps": 1500,
    })
    r2 = simulate({
        "dose_mg": 100.0, "route": "iv_bolus", "Kp": 2.0,
        "CLh_L_per_h": 15.0, "CLr_L_per_h": 5.0,
        "duration_h": 24.0, "n_steps": 1500,
    })
    c1 = np.array(r1["C_blood_mg_per_L"])
    c2 = np.array(r2["C_blood_mg_per_L"])
    # evitar division por ~0 en t=0 tardio; comparar en la region donde c1 no es ~0
    mask = c1 > 1e-8
    ratio = c2[mask] / c1[mask]
    max_dev = np.max(np.abs(ratio - 2.0))
    checks.append({
        "name": "linealidad: dosis x2 => concentracion x2 en todo t",
        "passed": bool(max_dev < 1e-6),
        "detail": f"max desviacion de la razon 2.0: {max_dev:.3e}",
    })

    # --- Check 6: estado estacionario en infusion continua ---
    # a t grande, tasa de eliminacion total (hepatica+renal) debe igualar
    # la tasa de infusion, y las derivadas deben ser ~0
    CLh_ss, CLr_ss = 8.0, 3.0
    infusion_rate = 10.0  # mg/h
    dydt_inf = make_derivative_fn(phys, Kp_uniform, CLh=CLh_ss, CLr=CLr_ss, ka=0.0,
                                   infusion_rate_fn=lambda t: infusion_rate)
    y0_inf = np.zeros(STATE_SIZE)
    ts4, ys4 = rk4_integrate(dydt_inf, y0_inf, (0.0, 500.0), 20000)
    y_end = ys4[-1]
    dy_end = dydt_inf(ts4[-1], y_end)
    max_deriv = np.max(np.abs(dy_end[:IDX_GUT_LUMEN]))  # excluye gut_lumen (no aplica) y elim (crece siempre)
    elim_rate_at_end = dy_end[IDX_ELIM]
    elim_vs_infusion_err = abs(elim_rate_at_end - infusion_rate) / infusion_rate
    checks.append({
        "name": "estado estacionario (infusion continua): derivadas ~0",
        "passed": bool(max_deriv < 1e-3),
        "detail": f"max |dC/dt| en compartimentos a t=500h: {max_deriv:.3e}",
    })
    checks.append({
        "name": "estado estacionario: tasa de eliminacion = tasa de infusion",
        "passed": bool(elim_vs_infusion_err < 1e-3),
        "detail": f"elim_rate={elim_rate_at_end:.6f} mg/h vs infusion={infusion_rate} mg/h "
                  f"(err rel={elim_vs_infusion_err:.3e})",
    })

    # --- Check 7: equilibrio de largo plazo sin eliminacion converge a
    #     Dosis / Volumen_efectivo (con Kp uniforme, todo se reparte
    #     proporcional al volumen aparente Vi*Kp) ---
    Kp_u = 3.0
    dydt_noelim = make_derivative_fn(phys, {name: Kp_u for name in TISSUE_ORDER},
                                      CLh=0.0, CLr=0.0, ka=0.0,
                                      infusion_rate_fn=lambda t: 0.0)
    y0b = np.zeros(STATE_SIZE)
    dose_b = 200.0
    y0b[IDX_CART] = dose_b / phys["blood_volume_L"]
    tsb, ysb = rk4_integrate(dydt_noelim, y0b, (0.0, 2000.0), 40000)
    _, _, V = build_flows(phys)
    V_eff = phys["blood_volume_L"] + sum(V[n] * Kp_u for n in TISSUE_ORDER)
    C_blood_eq_expected = dose_b / V_eff
    C_blood_eq_actual = ysb[-1, IDX_CART]
    rel_err_eq = abs(C_blood_eq_actual - C_blood_eq_expected) / C_blood_eq_expected
    checks.append({
        "name": "equilibrio largo plazo sin eliminacion = Dosis/Volumen_efectivo (Kp uniforme)",
        "passed": bool(rel_err_eq < 1e-4),
        "detail": f"esperado={C_blood_eq_expected:.6f} mg/L, obtenido={C_blood_eq_actual:.6f} mg/L "
                  f"(err rel={rel_err_eq:.3e})",
    })

    # --- Check 8: Kp por tejido invalido (dict incompleto) levanta ValueError ---
    raised = False
    try:
        simulate({"dose_mg": 10.0, "Kp": {"liver": 1.0}})  # faltan tejidos
    except ValueError:
        raised = True
    checks.append({
        "name": "Kp incompleto (dict) levanta ValueError",
        "passed": raised,
        "detail": "",
    })

    # --- Check 9: falta de Kp obligatorio levanta ValueError ---
    raised2 = False
    try:
        simulate({"dose_mg": 10.0})
    except ValueError:
        raised2 = True
    checks.append({
        "name": "Kp ausente levanta ValueError (no se estima nunca)",
        "passed": raised2,
        "detail": "",
    })

    total = len(checks)
    passed = sum(1 for c in checks if c["passed"])
    return {"total": total, "passed": passed, "all_passed": passed == total, "checks": checks}


# ---------------------------------------------------------------------
# 5) DISPATCH / CLI
# ---------------------------------------------------------------------

TOOL_SCHEMA = {
    "name": "virtual_pharmacokinetics",
    "description": (
        "Simulacion PBPK compartimental (flow-limited) de la distribucion "
        "de un compuesto en un cuerpo humano de referencia. Requiere "
        "parametros quimicos obligatorios (Kp, clearance) -- no los estima. "
        "La tabla de fisiologia es aproximada (no es la tabla exacta de httk)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["simulate", "self_test", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "dose_mg": {"type": "number"},
                    "route": {"type": "string", "enum": ["iv_bolus", "iv_infusion", "oral"]},
                    "infusion_duration_h": {"type": "number"},
                    "ka_per_h": {"type": "number"},
                    "Kp": {"description": "numero (uniforme) o dict por tejido"},
                    "CLh_L_per_h": {"type": "number"},
                    "CLr_L_per_h": {"type": "number"},
                    "duration_h": {"type": "number"},
                    "n_steps": {"type": "integer"},
                    "output_times_h": {"type": "array", "items": {"type": "number"}},
                },
                "required": ["dose_mg", "Kp"],
            },
        },
        "required": ["mode"],
    },
}


def run(mode, params=None):
    params = params or {}
    if mode == "validate":
        r = run_self_test()
        return {"checks": r["checks"], "validation_passed": r["all_passed"], "n_checks": r["total"]}
    if mode == "simulate":
        return simulate(params)
    elif mode == "self_test":
        return run_self_test()
    else:
        raise ValueError(f"modo desconocido: {mode}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "uso: virtual_pharmacokinetics.py <mode> [params_json]"}))
        sys.exit(1)
    mode = sys.argv[1]
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    try:
        out = run(mode, params)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)


def _register():
    """
    Auto-registro estilo octave-mcp (patron self-registrante via
    tool_registry, register_tool(name, schema, handler)).
    """
    try:
        import tool_registry
        def _handler(args):
            return run(args.get("mode"), args.get("params"))
        tool_registry.register_tool("virtual_pharmacokinetics", TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()

