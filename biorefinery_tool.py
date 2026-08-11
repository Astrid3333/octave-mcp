"""
biorefinery_tool.py
Balances de masa y energia para procesos de biorrefineria (biomasa -> biocombustible).
Primera tanda del roadmap de "matematica de biopetroleo": mass_balance, energy_balance,
hhv_correlation (poder calorifico via composicion elemental), yield_efficiency.
Sigue el patron: compute_biorefinery(mode, params) + BIOREFINERY_TOOL_SCHEMA

Integrar en server.py:
  - import: from biorefinery_tool import compute_biorefinery, BIOREFINERY_TOOL_SCHEMA
  - dispatcher: elif tool_name == "biorefinery_tool":
                    result = compute_biorefinery(args.get("mode"), args.get("params"))
  - schema list: agregar BIOREFINERY_TOOL_SCHEMA
"""

import math

T_REF_DEFAULT = 298.15  # K


# ---------------------------------------------------------------------------
# Modo: mass_balance
# ---------------------------------------------------------------------------
def _mode_mass_balance(p):
    """
    Balance de masa global en estado estacionario: sum(m_in) = sum(m_out).
    streams_in / streams_out: lista de {"nombre":.., "m":.. (o None si es la incognita)}
    Si hay exactamente una incognita (m=None) en todo el sistema, se resuelve por cierre.
    Si no hay incognitas, se reporta el error de cierre (deberia ser ~0 en un balance
    perfecto; sirve para validar datos experimentales).
    """
    streams_in = p["streams_in"]
    streams_out = p["streams_out"]

    incognitas = []
    for s in streams_in:
        if s.get("m") is None:
            incognitas.append(("in", s))
    for s in streams_out:
        if s.get("m") is None:
            incognitas.append(("out", s))

    if len(incognitas) > 1:
        raise ValueError(
            f"Hay {len(incognitas)} incognitas (streams con m=None); el balance de masa "
            "global solo permite resolver una a la vez."
        )

    sum_in_known = sum(s["m"] for s in streams_in if s.get("m") is not None)
    sum_out_known = sum(s["m"] for s in streams_out if s.get("m") is not None)

    resultado = {
        "streams_in": streams_in,
        "streams_out": streams_out,
        "suma_in_conocida": sum_in_known,
        "suma_out_conocida": sum_out_known,
    }

    if incognitas:
        lado, stream = incognitas[0]
        if lado == "in":
            # sum_in_known + m_incognita = sum_out_known
            m_solved = sum_out_known - sum_in_known
        else:
            # sum_in_known = sum_out_known + m_incognita
            m_solved = sum_in_known - sum_out_known
        if m_solved < 0:
            raise ValueError(
                f"El cierre de masa da un valor negativo ({m_solved}) para "
                f"'{stream.get('nombre', '?')}'; revisar los datos de entrada."
            )
        stream["m"] = m_solved
        resultado["incognita_resuelta"] = {
            "nombre": stream.get("nombre"), "lado": lado, "m_solved": m_solved
        }
    else:
        cierre = sum_in_known - sum_out_known
        error_pct = 100 * cierre / sum_in_known if sum_in_known else None
        resultado["cierre_balance"] = cierre
        resultado["error_cierre_pct"] = error_pct

    return resultado


# ---------------------------------------------------------------------------
# Modo: energy_balance (calor sensible + latente, sin energia quimica)
# ---------------------------------------------------------------------------
def _specific_enthalpy(stream, T_ref):
    """h especifico (J/kg) relativo a T_ref: sensible + latente si se da cambio de fase."""
    cp = stream.get("cp", 0.0)  # J/(kg*K)
    T = stream["T"]
    latent_kJ_kg = stream.get("latent_heat", 0.0)  # kJ/kg, aplicado tal cual (signo lo pone el usuario)
    return cp * (T - T_ref) + latent_kJ_kg * 1000.0


def _mode_energy_balance(p):
    """
    Balance de energia global en estado estacionario (sin energia cinetica/potencial,
    sin energia quimica de reaccion -- eso se cubre en yield_efficiency via HHV):
        sum(m_in * h_in) + Q = sum(m_out * h_out) + W
    streams_in / streams_out: {"nombre","m","cp"(J/kg/K),"T"(K),"latent_heat"(kJ/kg, opcional)}
    Q: calor externo agregado (W o J, signo positivo = entra al sistema). None -> se resuelve.
    W: trabajo extraido (default 0).
    """
    streams_in = p["streams_in"]
    streams_out = p["streams_out"]
    T_ref = p.get("T_ref", T_REF_DEFAULT)
    Q = p.get("Q")
    W = p.get("W", 0.0)

    H_in = sum(s["m"] * _specific_enthalpy(s, T_ref) for s in streams_in)
    H_out = sum(s["m"] * _specific_enthalpy(s, T_ref) for s in streams_out)

    resultado = {
        "H_in_J": H_in, "H_out_J": H_out, "T_ref_K": T_ref, "W": W,
    }

    if Q is None:
        Q_solved = H_out + W - H_in
        resultado["Q_solved"] = Q_solved
        resultado["interpretacion"] = (
            "Q > 0: el proceso requiere agregar calor (endotermico neto)."
            if Q_solved > 0 else
            "Q < 0: el proceso libera calor neto (hay que retirarlo, ej. enfriamiento)."
        )
    else:
        cierre = (H_in + Q) - (H_out + W)
        resultado["Q"] = Q
        resultado["cierre_balance_J"] = cierre
        resultado["error_cierre_pct"] = 100 * cierre / H_in if H_in else None

    return resultado


# ---------------------------------------------------------------------------
# Modo: hhv_correlation (Channiwala-Parikh, 2002)
# ---------------------------------------------------------------------------
def _mode_hhv_correlation(p):
    """
    Estima el poder calorifico superior (HHV) a partir de composicion elemental
    (% masa, base seca libre de cenizas o base seca segun se especifique), via la
    correlacion de Channiwala-Parikh (Fuel, 2002) -- error tipico ~1.45% en un
    rango amplio de combustibles solidos/liquidos/gaseosos, incluida biomasa.

    HHV [MJ/kg] = 0.3491*C + 1.1783*H + 0.1005*S - 0.1034*O - 0.0151*N - 0.0211*Ash
    (C,H,O,N,S,Ash en % masa)

    Opcionalmente calcula LHV a partir de HHV, contenido de H y humedad:
    LHV = HHV - 2.442*(9*H_frac + M_frac)  [2.442 MJ/kg = calor latente de vaporizacion
    del agua a 25C; 9 kg H2O producidos por kg de H2 quemado, estequiometria 2H2+O2->2H2O]
    """
    C = p.get("C", 0.0)
    H = p.get("H", 0.0)
    O = p.get("O", 0.0)
    N = p.get("N", 0.0)
    S = p.get("S", 0.0)
    Ash = p.get("Ash", 0.0)

    total = C + H + O + N + S + Ash
    if not (90 <= total <= 110):
        raise ValueError(
            f"C+H+O+N+S+Ash = {total:.2f}%, deberia sumar ~100% (composicion en % masa)."
        )

    HHV = 0.3491 * C + 1.1783 * H + 0.1005 * S - 0.1034 * O - 0.0151 * N - 0.0211 * Ash

    resultado = {
        "composicion_pct": {"C": C, "H": H, "O": O, "N": N, "S": S, "Ash": Ash},
        "HHV_MJ_kg": HHV,
        "correlacion": "Channiwala-Parikh (2002), error tipico ~1.45%",
    }

    M_pct = p.get("humedad_pct", 0.0)  # humedad tal-cual, % masa, separada de la base seca de arriba
    H_frac = H / 100.0
    M_frac = M_pct / 100.0
    LHV = HHV - 2.442 * (9 * H_frac + M_frac)
    resultado["LHV_MJ_kg"] = LHV
    resultado["humedad_asumida_pct"] = M_pct

    return resultado


# ---------------------------------------------------------------------------
# Modo: yield_efficiency
# ---------------------------------------------------------------------------
def _mode_yield_efficiency(p):
    """
    Rendimientos masicos y energeticos de un proceso biomasa -> producto(s), y
    eficiencia energetica global del proceso.
    m_feed, HHV_feed (MJ/kg): materia prima.
    productos: lista de {"nombre","m","HHV"(MJ/kg)}.
    Q_utilities (MJ, opcional): energia externa neta consumida por el proceso
    (calor de proceso, electricidad de bombas/compresores, etc). Default 0.
    """
    m_feed = p["m_feed"]
    HHV_feed = p["HHV_feed"]
    productos = p["productos"]
    Q_utilities = p.get("Q_utilities", 0.0)

    E_feed = m_feed * HHV_feed

    resultados_productos = []
    E_productos_total = 0.0
    for prod in productos:
        Y_masico = prod["m"] / m_feed
        E_prod = prod["m"] * prod["HHV"]
        Y_energetico = E_prod / E_feed if E_feed else None
        E_productos_total += E_prod
        resultados_productos.append({
            "nombre": prod.get("nombre"),
            "m": prod["m"],
            "HHV_MJ_kg": prod["HHV"],
            "rendimiento_masico": Y_masico,
            "energia_MJ": E_prod,
            "rendimiento_energetico": Y_energetico,
        })

    eficiencia_global = E_productos_total / (E_feed + Q_utilities) if (E_feed + Q_utilities) else None

    return {
        "m_feed": m_feed,
        "HHV_feed_MJ_kg": HHV_feed,
        "energia_feed_MJ": E_feed,
        "Q_utilities_MJ": Q_utilities,
        "productos": resultados_productos,
        "energia_productos_total_MJ": E_productos_total,
        "eficiencia_energetica_global": eficiencia_global,
    }


# ---------------------------------------------------------------------------
# Dispatcher principal
# ---------------------------------------------------------------------------
def compute_biorefinery(mode, params=None):
    params = params or {}
    if mode == "mass_balance":
        return _mode_mass_balance(params)
    elif mode == "energy_balance":
        return _mode_energy_balance(params)
    elif mode == "hhv_correlation":
        return _mode_hhv_correlation(params)
    elif mode == "yield_efficiency":
        return _mode_yield_efficiency(params)
    else:
        raise ValueError(
            f"Modo desconocido: {mode}. Usar: mass_balance | energy_balance | "
            "hhv_correlation | yield_efficiency"
        )


BIOREFINERY_TOOL_SCHEMA = {
    "name": "biorefinery_tool",
    "description": (
        "Balances de masa y energia para procesos de conversion de biomasa a "
        "biocombustible (pirolisis, hidrotratamiento, fermentacion, etc). "
        "mode='mass_balance': balance de masa global en estado estacionario, "
        "resuelve una incognita o reporta error de cierre. mode='energy_balance': "
        "balance de energia (calor sensible+latente) via entalpias especificas, "
        "resuelve Q o reporta cierre. mode='hhv_correlation': estima poder "
        "calorifico superior e inferior (HHV/LHV) a partir de composicion "
        "elemental C/H/O/N/S/Ash via correlacion de Channiwala-Parikh (2002). "
        "mode='yield_efficiency': rendimientos masicos y energeticos de "
        "producto(s) respecto a la materia prima, y eficiencia energetica "
        "global del proceso."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["mass_balance", "energy_balance", "hhv_correlation", "yield_efficiency"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    # smoke test rapido
    print(compute_biorefinery("mass_balance", {
        "streams_in": [{"nombre": "biomasa", "m": 100.0}],
        "streams_out": [{"nombre": "biocombustible", "m": 35.0}, {"nombre": "char", "m": None}],
    }))
    print(compute_biorefinery("hhv_correlation", {"C": 49.5, "H": 6.0, "O": 43.0, "N": 0.5, "S": 0.0, "Ash": 1.0}))
    print(compute_biorefinery("yield_efficiency", {
        "m_feed": 100.0, "HHV_feed": 18.0,
        "productos": [{"nombre": "bio-oil", "m": 35.0, "HHV": 22.0}],
        "Q_utilities": 200.0,
    }))
