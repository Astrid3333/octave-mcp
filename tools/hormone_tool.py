"""
hormone_tool.py

Motor combinado de cinetica/senalizacion hormonal para octave-mcp:

  - ligand_receptor_binding : ocupacion fraccional receptor-ligando
                               (Hill / Michaelis-Menten), afinidad,
                               cooperatividad.
  - dose_response           : curva dosis-respuesta farmacologica de
                               4 parametros (Emin, Emax, EC50, n).
  - axis_feedback           : retroalimentacion negativa de un eje
                               hormonal de 2 nodos (tipo eje
                               hipotalamo-hipofisis-organo diana),
                               ODE lineal con punto fijo analitico.
  - glucose_insulin_axis    : modelo minimo de Bergman (glucosa-
                               insulina), parametros de literatura,
                               vuelve al punto fijo basal analitico.
  - glycemic_response       : carga glicemica (GL = GI*carbs/100) +
                               estimacion de secrecion de insulina
                               relativa, pensado como puente hacia
                               ultra_processed_metabolism_tool.
  - validate                : auto-chequeos contra soluciones
                               analiticas / puntos fijos cerrados.

Sigue el patron de octave-mcp: self-registro via tool_registry al
final del archivo (try/except ImportError para poder correr standalone),
dispatcher compute_hormone_tool(mode=..., **kwargs), y validate() que
devuelve 'validation_passed' (nombre exacto que exige
run_all_validations.py).
"""

import numpy as np
from scipy.integrate import solve_ivp


# ---------------------------------------------------------------------
# 1. ligand_receptor_binding
# ---------------------------------------------------------------------

def _ligand_receptor_binding(ligand_conc, kd, hill_n=1.0, receptor_total=1.0):
    """Ocupacion fraccional theta = [L]^n / (Kd^n + [L]^n) (ecuacion de Hill;
    n=1 recupera Michaelis-Menten / Langmuir). receptor_total escala a
    receptores ocupados en unidades absolutas."""
    L = np.asarray(ligand_conc, dtype=float)
    if np.any(L < 0):
        raise ValueError("ligand_conc no puede ser negativo")
    if kd <= 0:
        raise ValueError("kd debe ser positivo")
    if hill_n <= 0:
        raise ValueError("hill_n debe ser positivo")

    Ln = np.power(L, hill_n)
    theta = Ln / (kd ** hill_n + Ln)
    occupied = theta * receptor_total
    return theta, occupied


def compute_ligand_receptor_binding(ligand_conc, kd, hill_n=1.0,
                                     receptor_total=1.0):
    theta, occupied = _ligand_receptor_binding(ligand_conc, kd, hill_n,
                                                receptor_total)
    single = np.isscalar(ligand_conc) or np.ndim(ligand_conc) == 0
    return {
        "fractional_occupancy": float(theta) if single else theta.tolist(),
        "receptors_occupied": float(occupied) if single else occupied.tolist(),
        "kd": kd,
        "hill_n": hill_n,
        "interpretation": (
            "cooperatividad positiva (sigmoidal)" if hill_n > 1 else
            "sin cooperatividad (hiperbolica, tipo Michaelis-Menten)" if hill_n == 1 else
            "cooperatividad negativa"
        ),
    }


# ---------------------------------------------------------------------
# 2. dose_response
# ---------------------------------------------------------------------

def _dose_response(dose, ec50, emax, emin=0.0, hill_n=1.0):
    D = np.asarray(dose, dtype=float)
    if np.any(D < 0):
        raise ValueError("dose no puede ser negativa")
    if ec50 <= 0:
        raise ValueError("ec50 debe ser positivo")
    if hill_n <= 0:
        raise ValueError("hill_n debe ser positivo")

    # Version robusta a D=0: usa (D/EC50)^n en vez de (EC50/D)^n para
    # evitar division por cero.
    Dn = np.power(D, hill_n)
    E = emin + (emax - emin) * Dn / (ec50 ** hill_n + Dn)
    return E


def compute_dose_response(dose, ec50, emax, emin=0.0, hill_n=1.0):
    E = _dose_response(dose, ec50, emax, emin, hill_n)
    single = np.isscalar(dose) or np.ndim(dose) == 0
    potency_note = "mayor EC50 = menor potencia (se necesita mas dosis)"
    return {
        "effect": float(E) if single else E.tolist(),
        "ec50": ec50,
        "emax": emax,
        "emin": emin,
        "hill_n": hill_n,
        "note": potency_note,
    }


# ---------------------------------------------------------------------
# 3. axis_feedback (eje hormonal de 2 nodos con retroalimentacion negativa)
# ---------------------------------------------------------------------
#
#   dH1/dt = k_prod - k_inhib * H2 - decay1 * H1     (ej. TSH)
#   dH2/dt = k_stim * H1 - decay2 * H2               (ej. hormona tiroidea)
#
# Punto fijo analitico (dH1/dt = dH2/dt = 0):
#   H2_ss = k_prod * k_stim / (decay1 * decay2 + k_inhib * k_stim)
#   H1_ss = (k_prod - k_inhib * H2_ss) / decay1

def _axis_steady_state(k_prod, k_inhib, k_stim, decay1, decay2):
    denom = decay1 * decay2 + k_inhib * k_stim
    h2_ss = k_prod * k_stim / denom
    h1_ss = (k_prod - k_inhib * h2_ss) / decay1
    return h1_ss, h2_ss


def _axis_rhs(t, y, k_prod, k_inhib, k_stim, decay1, decay2):
    h1, h2 = y
    dh1 = k_prod - k_inhib * h2 - decay1 * h1
    dh2 = k_stim * h1 - decay2 * h2
    return [dh1, dh2]


def compute_axis_feedback(k_prod, k_inhib, k_stim, decay1, decay2,
                           h1_0=0.0, h2_0=0.0, t_max=200.0):
    for name, val in [("k_prod", k_prod), ("k_inhib", k_inhib),
                       ("k_stim", k_stim), ("decay1", decay1),
                       ("decay2", decay2)]:
        if val <= 0:
            raise ValueError(f"{name} debe ser positivo")

    h1_ss, h2_ss = _axis_steady_state(k_prod, k_inhib, k_stim, decay1, decay2)

    sol = solve_ivp(
        _axis_rhs, [0, t_max], [h1_0, h2_0],
        args=(k_prod, k_inhib, k_stim, decay1, decay2),
        method="RK45", dense_output=False, max_step=t_max / 500,
        rtol=1e-8, atol=1e-10,
    )
    h1_final = float(sol.y[0, -1])
    h2_final = float(sol.y[1, -1])

    return {
        "h1_final": h1_final,
        "h2_final": h2_final,
        "h1_steady_state_analytic": h1_ss,
        "h2_steady_state_analytic": h2_ss,
        "t": sol.t.tolist(),
        "h1_trace": sol.y[0].tolist(),
        "h2_trace": sol.y[1].tolist(),
        "note": "H1 estimula H2, H2 inhibe H1 (retroalimentacion negativa clasica de ejes endocrinos)",
    }


# ---------------------------------------------------------------------
# 4. glucose_insulin_axis (modelo minimo de Bergman)
# ---------------------------------------------------------------------
#
# Bergman minimal model (Bergman, Ider, Bowden & Cobelli 1979;
# parametros tipicos de sujeto normal via Pacini & Bergman 1986):
#
#   dG/dt = -p1*(G - Gb) - X*G
#   dX/dt = -p2*X + p3*(I - Ib)
#   dI/dt = gamma*max(G - h, 0)*t_ - n*(I - Ib)      [secrecion simplificada]
#
# En estado basal (sin bolo de glucosa, G=Gb, X=0, I=Ib) el sistema
# esta exactamente en su punto fijo: dG/dt = dX/dt = dI/dt = 0.

_BERGMAN_DEFAULTS = dict(
    p1=0.028735,   # 1/min - efectividad de la glucosa
    p2=0.028344,   # 1/min - decaimiento de la accion insulinica remota
    p3=5.035e-5,   # 1/min por (uU/mL) - sensibilidad a insulina
    gamma=0.0332,  # uU/mL por min por (mg/dL) - tasa de secrecion
    h=95.0,        # mg/dL - umbral de secrecion (> Gb: en la formulacion
                   # clasica el termino de segunda fase es gamma*(G-h)*t,
                   # con dependencia EXPLICITA de t; si h < Gb ese termino
                   # nunca se apaga y crece sin limite incluso en reposo,
                   # asi que el punto fijo basal solo existe con h >= Gb)
    n=0.09,        # 1/min - clearance de insulina
    Gb=90.0,       # mg/dL - glucosa basal
    Ib=8.0,        # uU/mL - insulina basal
)


def _bergman_rhs(t, y, p1, p2, p3, gamma, h, n, Gb, Ib):
    G, X, I = y
    dG = -p1 * (G - Gb) - X * G
    dX = -p2 * X + p3 * (I - Ib)
    dI = gamma * max(G - h, 0.0) * t - n * (I - Ib)
    return [dG, dX, dI]


def compute_glucose_insulin_axis(glucose_bolus=0.0, t_max=180.0,
                                  params=None):
    p = dict(_BERGMAN_DEFAULTS)
    if params:
        p.update(params)

    G0 = p["Gb"] + glucose_bolus
    y0 = [G0, 0.0, p["Ib"]]

    sol = solve_ivp(
        _bergman_rhs, [0, t_max], y0,
        args=(p["p1"], p["p2"], p["p3"], p["gamma"], p["h"], p["n"],
              p["Gb"], p["Ib"]),
        method="LSODA", max_step=1.0, rtol=1e-8, atol=1e-10,
    )

    G_final = float(sol.y[0, -1])
    I_final = float(sol.y[2, -1])
    G_peak = float(np.max(sol.y[0]))
    I_peak = float(np.max(sol.y[2]))

    return {
        "t": sol.t.tolist(),
        "glucose_mg_dl": sol.y[0].tolist(),
        "insulin_action_remote": sol.y[1].tolist(),
        "insulin_uU_ml": sol.y[2].tolist(),
        "glucose_final": G_final,
        "insulin_final": I_final,
        "glucose_peak": G_peak,
        "insulin_peak": I_peak,
        "basal_glucose": p["Gb"],
        "basal_insulin": p["Ib"],
        "model": "Bergman minimal model (1979), parametros Pacini & Bergman 1986",
    }


# ---------------------------------------------------------------------
# 5. glycemic_response (puente con ultra_processed_metabolism_tool)
# ---------------------------------------------------------------------

def compute_glycemic_response(glycemic_index, carbs_g, insulin_index=None):
    if not (0 <= glycemic_index <= 200):
        raise ValueError("glycemic_index fuera de rango plausible (0-200)")
    if carbs_g < 0:
        raise ValueError("carbs_g no puede ser negativo")

    glycemic_load = glycemic_index * carbs_g / 100.0

    # Si no se da insulin_index, se estima como proporcional a la carga
    # glicemica (heuristica simple: II y GL suelen correlacionar fuerte,
    # r~0.8-0.9 en literatura de indices de insulina de Holt et al. 1997,
    # pero NO son identicos - se deja como estimacion aproximada).
    if insulin_index is None:
        insulin_response_est = glycemic_load * 1.0
        insulin_index_used = None
    else:
        insulin_response_est = glycemic_load * (insulin_index / 100.0)
        insulin_index_used = insulin_index

    if glycemic_load < 10:
        category = "baja"
    elif glycemic_load < 20:
        category = "media"
    else:
        category = "alta"

    return {
        "glycemic_load": glycemic_load,
        "category": category,
        "insulin_response_estimate": insulin_response_est,
        "insulin_index_used": insulin_index_used,
        "note": "insulin_response_estimate es una heuristica, no reemplaza un indice de insulina medido (Holt et al. 1997)",
    }


# ---------------------------------------------------------------------
# 6. validate
# ---------------------------------------------------------------------

def _validate():
    checks = []

    # Check 1: en [L]=Kd, theta debe ser exactamente 0.5 (Hill/MM)
    r = compute_ligand_receptor_binding(ligand_conc=5.0, kd=5.0, hill_n=1.0)
    err1 = abs(r["fractional_occupancy"] - 0.5)
    checks.append({
        "name": "ligand_receptor_binding: theta(L=Kd)=0.5",
        "value": r["fractional_occupancy"],
        "expected": 0.5,
        "error": err1,
        "passed": err1 < 1e-9,
    })

    # Check 2: cooperatividad - con hill_n=4 y L=Kd, sigue dando 0.5
    # (propiedad de la ecuacion de Hill independiente de n)
    r2 = compute_ligand_receptor_binding(ligand_conc=3.0, kd=3.0, hill_n=4.0)
    err2 = abs(r2["fractional_occupancy"] - 0.5)
    checks.append({
        "name": "ligand_receptor_binding: theta(L=Kd)=0.5 con cooperatividad n=4",
        "value": r2["fractional_occupancy"],
        "expected": 0.5,
        "error": err2,
        "passed": err2 < 1e-9,
    })

    # Check 3: dose_response en D=EC50 da el punto medio exacto entre
    # Emin y Emax
    dr = compute_dose_response(dose=10.0, ec50=10.0, emax=100.0, emin=0.0,
                                hill_n=1.0)
    expected_mid = 50.0
    err3 = abs(dr["effect"] - expected_mid)
    checks.append({
        "name": "dose_response: E(D=EC50) = punto medio",
        "value": dr["effect"],
        "expected": expected_mid,
        "error": err3,
        "passed": err3 < 1e-9,
    })

    # Check 4: dose_response en D=0 da Emin exacto
    dr0 = compute_dose_response(dose=0.0, ec50=10.0, emax=100.0, emin=5.0,
                                 hill_n=2.0)
    err4 = abs(dr0["effect"] - 5.0)
    checks.append({
        "name": "dose_response: E(D=0) = Emin",
        "value": dr0["effect"],
        "expected": 5.0,
        "error": err4,
        "passed": err4 < 1e-9,
    })

    # Check 5: axis_feedback converge al punto fijo analitico partiendo
    # lejos de el
    af = compute_axis_feedback(k_prod=2.0, k_inhib=0.5, k_stim=1.0,
                                decay1=0.3, decay2=0.2,
                                h1_0=0.0, h2_0=0.0, t_max=300.0)
    err5_h1 = abs(af["h1_final"] - af["h1_steady_state_analytic"])
    err5_h2 = abs(af["h2_final"] - af["h2_steady_state_analytic"])
    checks.append({
        "name": "axis_feedback: convergencia a punto fijo analitico (H1)",
        "value": af["h1_final"],
        "expected": af["h1_steady_state_analytic"],
        "error": err5_h1,
        "passed": err5_h1 < 1e-4,
    })
    checks.append({
        "name": "axis_feedback: convergencia a punto fijo analitico (H2)",
        "value": af["h2_final"],
        "expected": af["h2_steady_state_analytic"],
        "error": err5_h2,
        "passed": err5_h2 < 1e-4,
    })

    # Check 6: axis_feedback ya en el punto fijo (h1_0, h2_0 = steady
    # state analitico) se queda ahi (derivadas ~0)
    h1_ss, h2_ss = _axis_steady_state(2.0, 0.5, 1.0, 0.3, 0.2)
    af_ss = compute_axis_feedback(k_prod=2.0, k_inhib=0.5, k_stim=1.0,
                                   decay1=0.3, decay2=0.2,
                                   h1_0=h1_ss, h2_0=h2_ss, t_max=50.0)
    err6 = abs(af_ss["h1_final"] - h1_ss) + abs(af_ss["h2_final"] - h2_ss)
    checks.append({
        "name": "axis_feedback: punto fijo es invariante",
        "value": err6,
        "expected": 0.0,
        "error": err6,
        "passed": err6 < 1e-6,
    })

    # Check 7: glucose_insulin_axis sin bolo (glucose_bolus=0) se queda
    # exactamente en el estado basal (punto fijo analitico del modelo
    # de Bergman)
    gi_basal = compute_glucose_insulin_axis(glucose_bolus=0.0, t_max=120.0)
    err7 = (abs(gi_basal["glucose_final"] - gi_basal["basal_glucose"]) +
            abs(gi_basal["insulin_final"] - gi_basal["basal_insulin"]))
    checks.append({
        "name": "glucose_insulin_axis: sin bolo permanece en punto fijo basal",
        "value": err7,
        "expected": 0.0,
        "error": err7,
        "passed": err7 < 1e-6,
    })

    # Check 8: glucose_insulin_axis con bolo positivo produce un pico de
    # glucosa por encima de basal y luego una respuesta de insulina por
    # encima de basal (direccion fisiologica correcta)
    gi_bolus = compute_glucose_insulin_axis(glucose_bolus=75.0, t_max=180.0)
    direction_ok = (gi_bolus["glucose_peak"] > gi_bolus["basal_glucose"] and
                    gi_bolus["insulin_peak"] > gi_bolus["basal_insulin"])
    checks.append({
        "name": "glucose_insulin_axis: bolo de glucosa eleva glucosa e insulina por encima de basal",
        "value": direction_ok,
        "expected": True,
        "error": 0.0 if direction_ok else 1.0,
        "passed": direction_ok,
    })

    # Check 9: glycemic_response - formula cerrada GL = GI*carbs/100
    gr = compute_glycemic_response(glycemic_index=70, carbs_g=50)
    expected_gl = 70 * 50 / 100.0
    err9 = abs(gr["glycemic_load"] - expected_gl)
    checks.append({
        "name": "glycemic_response: GL = GI*carbs/100",
        "value": gr["glycemic_load"],
        "expected": expected_gl,
        "error": err9,
        "passed": err9 < 1e-9,
    })

    # Check 10: manejo de errores - kd<=0 debe levantar ValueError
    raised = False
    try:
        compute_ligand_receptor_binding(ligand_conc=1.0, kd=-1.0)
    except ValueError:
        raised = True
    checks.append({
        "name": "ligand_receptor_binding: kd<=0 levanta ValueError",
        "value": raised,
        "expected": True,
        "error": 0.0 if raised else 1.0,
        "passed": raised,
    })

    all_pass = all(c["passed"] for c in checks)
    return {
        "validation_passed": all_pass,
        "checks": checks,
        "n_checks": len(checks),
        "n_passed": sum(1 for c in checks if c["passed"]),
    }


# ---------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------

def compute_hormone_tool(mode, **kwargs):
    if mode == "ligand_receptor_binding":
        return compute_ligand_receptor_binding(**kwargs)
    elif mode == "dose_response":
        return compute_dose_response(**kwargs)
    elif mode == "axis_feedback":
        return compute_axis_feedback(**kwargs)
    elif mode == "glucose_insulin_axis":
        return compute_glucose_insulin_axis(**kwargs)
    elif mode == "glycemic_response":
        return compute_glycemic_response(**kwargs)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            f"mode desconocido: {mode!r}. Opciones: ligand_receptor_binding, "
            "dose_response, axis_feedback, glucose_insulin_axis, "
            "glycemic_response, validate"
        )


# ---------------------------------------------------------------------
# Schema (patron inputSchema anidado, con description - ver bug de
# pair_production/synchrotron en octave-mcp.md que exigio esta forma)
# ---------------------------------------------------------------------

HORMONE_TOOL_SCHEMA = {
    "name": "hormone_tool",
    "description": (
        "Cinetica/senalizacion hormonal: union ligando-receptor "
        "(Hill/MM), curvas dosis-respuesta, retroalimentacion de ejes "
        "hormonales, y modo metabolico (eje glucosa-insulina de Bergman "
        "+ respuesta glicemica)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "ligand_receptor_binding",
                    "dose_response",
                    "axis_feedback",
                    "glucose_insulin_axis",
                    "glycemic_response",
                    "validate",
                ],
                "description": "Submodo a ejecutar",
            },
            "ligand_conc": {
                "type": "number",
                "description": "Concentracion de ligando (mode=ligand_receptor_binding)",
            },
            "kd": {
                "type": "number",
                "description": "Constante de disociacion (mode=ligand_receptor_binding)",
            },
            "hill_n": {
                "type": "number",
                "description": "Coeficiente de Hill (cooperatividad); default 1.0",
            },
            "receptor_total": {
                "type": "number",
                "description": "Receptores totales, para escalar a unidades absolutas; default 1.0",
            },
            "dose": {
                "type": "number",
                "description": "Dosis (mode=dose_response)",
            },
            "ec50": {
                "type": "number",
                "description": "Dosis de efecto medio (mode=dose_response)",
            },
            "emax": {
                "type": "number",
                "description": "Efecto maximo (mode=dose_response)",
            },
            "emin": {
                "type": "number",
                "description": "Efecto minimo/basal (mode=dose_response); default 0.0",
            },
            "k_prod": {
                "type": "number",
                "description": "Tasa de produccion de H1 (mode=axis_feedback)",
            },
            "k_inhib": {
                "type": "number",
                "description": "Tasa de inhibicion de H1 por H2 (mode=axis_feedback)",
            },
            "k_stim": {
                "type": "number",
                "description": "Tasa de estimulacion de H2 por H1 (mode=axis_feedback)",
            },
            "decay1": {
                "type": "number",
                "description": "Tasa de decaimiento de H1 (mode=axis_feedback)",
            },
            "decay2": {
                "type": "number",
                "description": "Tasa de decaimiento de H2 (mode=axis_feedback)",
            },
            "h1_0": {
                "type": "number",
                "description": "Condicion inicial H1 (mode=axis_feedback); default 0.0",
            },
            "h2_0": {
                "type": "number",
                "description": "Condicion inicial H2 (mode=axis_feedback); default 0.0",
            },
            "t_max": {
                "type": "number",
                "description": "Tiempo maximo de integracion (axis_feedback / glucose_insulin_axis)",
            },
            "glucose_bolus": {
                "type": "number",
                "description": "Bolo de glucosa sobre el basal, mg/dL (mode=glucose_insulin_axis); default 0.0",
            },
            "params": {
                "type": "object",
                "description": "Override de parametros del modelo de Bergman (mode=glucose_insulin_axis)",
            },
            "glycemic_index": {
                "type": "number",
                "description": "Indice glicemico 0-200 (mode=glycemic_response)",
            },
            "carbs_g": {
                "type": "number",
                "description": "Carbohidratos en gramos (mode=glycemic_response)",
            },
            "insulin_index": {
                "type": "number",
                "description": "Indice de insulina opcional (mode=glycemic_response)",
            },
        },
        "required": ["mode"],
    },
}


def _register():
    try:
        import tool_registry
        tool_registry.register_tool(
            "hormone_tool", HORMONE_TOOL_SCHEMA, compute_hormone_tool
        )
    except ImportError:
        pass


_register()


if __name__ == "__main__":
    import json
    result = _validate()
    print(json.dumps(
        {"validation_passed": result["validation_passed"],
         "n_passed": result["n_passed"], "n_checks": result["n_checks"]},
        indent=2,
    ))
    for c in result["checks"]:
        status = "OK" if c["passed"] else "FALLO"
        print(f"[{status}] {c['name']}: valor={c['value']} error={c['error']}")
