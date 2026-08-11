"""
biorefinery_tool.py
Balances de masa y energia para procesos de biorrefineria (biomasa -> biocombustible).
Primera tanda del roadmap de "matematica de biopetroleo": mass_balance, energy_balance,
hhv_correlation (poder calorifico via composicion elemental), yield_efficiency.
Segunda tanda: cinetica quimica (Arrhenius, ley de velocidad, conversion integrada en
batch) para pirolisis/hidrotratamiento -- el "que tan rapido" que complementa a los
balances de masa/energia ("cuanto entra y sale").
Sigue el patron: compute_biorefinery(mode, params) + BIOREFINERY_TOOL_SCHEMA

Integrar en server.py:
  - import: from biorefinery_tool import compute_biorefinery, BIOREFINERY_TOOL_SCHEMA
  - dispatcher: elif tool_name == "biorefinery_tool":
                    result = compute_biorefinery(args.get("mode"), args.get("params"))
  - schema list: agregar BIOREFINERY_TOOL_SCHEMA
"""

import math

T_REF_DEFAULT = 298.15  # K
R_GAS = 8.314462618  # J/(mol*K)


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
# Modo: arrhenius (directo / dos_puntos / regresion)
# ---------------------------------------------------------------------------
def _mode_arrhenius(p):
    """
    Ecuacion de Arrhenius: k = A * exp(-Ea / (R*T))  [T en K, Ea en J/mol, R=8.314462618]

    submodo="directo": dados A, Ea (J/mol o kJ/mol via unidades_Ea), T -> calcula k.
    submodo="dos_puntos": dados (T1,k1) y (T2,k2) -> resuelve Ea y A por sistema exacto
        Ea = -R * ln(k2/k1) / (1/T2 - 1/T1)
        A  = k1 / exp(-Ea/(R*T1))
    submodo="regresion": dada una lista de pares (T,k) [minimo 2, tipicamente 3+] ->
        regresion lineal de ln(k) vs 1/T (grafico de Arrhenius linealizado):
        ln(k) = ln(A) - (Ea/R)*(1/T)
        pendiente = -Ea/R  ->  Ea = -R*pendiente
        intercepto = ln(A)  ->  A = exp(intercepto)
        Se reporta tambien R^2 del ajuste como medida de que tan bien se comporta
        Arrhenius en el rango de T dado (util para detectar cambio de mecanismo/regimen
        difusion-limitado en pirolisis/hidrotratamiento).
    """
    submodo = p.get("submodo", "directo")

    if submodo == "directo":
        A = p["A"]
        Ea = p["Ea"]
        if p.get("unidades_Ea", "J/mol") == "kJ/mol":
            Ea = Ea * 1000.0
        T = p["T"]
        k = A * math.exp(-Ea / (R_GAS * T))
        return {
            "submodo": submodo, "A": A, "Ea_J_mol": Ea, "T_K": T, "k": k,
            "formula": "k = A * exp(-Ea/(R*T))",
        }

    elif submodo == "dos_puntos":
        T1, k1 = p["T1"], p["k1"]
        T2, k2 = p["T2"], p["k2"]
        if T1 == T2:
            raise ValueError("T1 y T2 deben ser distintas para resolver Ea por dos puntos.")
        Ea = -R_GAS * math.log(k2 / k1) / (1.0 / T2 - 1.0 / T1)
        A = k1 / math.exp(-Ea / (R_GAS * T1))
        # verificacion cruzada con el segundo punto
        k2_check = A * math.exp(-Ea / (R_GAS * T2))
        return {
            "submodo": submodo,
            "puntos": {"T1_K": T1, "k1": k1, "T2_K": T2, "k2": k2},
            "Ea_J_mol": Ea, "Ea_kJ_mol": Ea / 1000.0, "A": A,
            "verificacion_k2": k2_check,
            "error_relativo_verificacion_pct": 100 * abs(k2_check - k2) / k2 if k2 else None,
        }

    elif submodo == "regresion":
        datos = p["datos"]  # lista de {"T":.., "k":..}
        n = len(datos)
        if n < 2:
            raise ValueError("Se necesitan al menos 2 pares (T,k) para la regresion; 3+ recomendado.")

        x = [1.0 / d["T"] for d in datos]      # 1/T
        y = [math.log(d["k"]) for d in datos]  # ln(k)

        x_mean = sum(x) / n
        y_mean = sum(y) / n
        Sxx = sum((xi - x_mean) ** 2 for xi in x)
        Sxy = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
        if Sxx == 0:
            raise ValueError("Todas las T son iguales; no se puede ajustar una recta.")

        pendiente = Sxy / Sxx
        intercepto = y_mean - pendiente * x_mean

        Ea = -R_GAS * pendiente
        A = math.exp(intercepto)

        y_pred = [intercepto + pendiente * xi for xi in x]
        ss_res = sum((yi - ypi) ** 2 for yi, ypi in zip(y, y_pred))
        ss_tot = sum((yi - y_mean) ** 2 for yi in y)
        r_cuadrado = 1 - ss_res / ss_tot if ss_tot else None

        return {
            "submodo": submodo, "n_puntos": n,
            "pendiente_lnk_vs_invT": pendiente, "intercepto_lnk": intercepto,
            "Ea_J_mol": Ea, "Ea_kJ_mol": Ea / 1000.0, "A": A,
            "r_cuadrado": r_cuadrado,
            "interpretacion_r2": (
                "Ajuste lineal fuerte: cinetica Arrhenius consistente en el rango de T dado."
                if (r_cuadrado is not None and r_cuadrado > 0.98) else
                "Ajuste lineal debil: posible cambio de mecanismo o regimen "
                "difusion-limitado dentro del rango de T -- revisar datos por tramos."
            ),
        }

    else:
        raise ValueError(f"submodo desconocido: {submodo}. Usar: directo | dos_puntos | regresion")


# ---------------------------------------------------------------------------
# Modo: rate_law (ley de velocidad de orden general, multi-reactivo)
# ---------------------------------------------------------------------------
def _mode_rate_law(p):
    """
    Ley de velocidad general: -r = k * prod(C_i ^ orden_i)
    reactivos: lista de {"nombre","C"(concentracion),"orden"(exponente en la ley)}.
    Reporta la velocidad de reaccion y el orden global (suma de ordenes parciales).
    """
    k = p["k"]
    reactivos = p["reactivos"]

    rate = k
    detalle = []
    orden_global = 0.0
    for r in reactivos:
        C = r["C"]
        orden = r["orden"]
        contrib = C ** orden
        rate *= contrib
        orden_global += orden
        detalle.append({
            "nombre": r.get("nombre"), "C": C, "orden": orden, "C_elevado_orden": contrib,
        })

    return {
        "k": k, "reactivos": detalle, "orden_global": orden_global,
        "velocidad_reaccion": rate,
        "formula": "-r = k * prod(C_i ^ orden_i)",
    }


# ---------------------------------------------------------------------------
# Modo: batch_conversion (formas integradas, reactor batch, orden 0/1/2)
# ---------------------------------------------------------------------------
def _mode_batch_conversion(p):
    """
    Formas integradas de la ley de velocidad para un reactor batch de un solo
    reactivo limitante A -> productos, ordenes 0, 1 y 2. Dados C0, k y orden, mas
    exactamente uno de {t, X} (el otro None o ausente), resuelve el que falta y
    devuelve tambien la concentracion C = C0*(1-X).

    Orden 0: C = C0 - k*t            ; X = k*t/C0            ; t = X*C0/k
    Orden 1: C = C0*exp(-k*t)        ; X = 1 - exp(-k*t)      ; t = -ln(1-X)/k
    Orden 2: C = C0/(1 + k*C0*t)     ; X = k*C0*t/(1+k*C0*t)  ; t = X/(k*C0*(1-X))
    (orden 2 asume -r = k*C^2 para un unico reactivo, caso mas comun en cinetica
    de pirolisis/craqueo termico simplificada)
    """
    orden = p["orden"]
    C0 = p["C0"]
    k = p["k"]
    t = p.get("t")
    X = p.get("X")

    if (t is None) == (X is None):
        raise ValueError("Dar exactamente uno de {t, X} (el otro None o ausente) para resolver el faltante.")

    if orden == 0:
        if t is None:
            if not (0 <= X < 1):
                raise ValueError("X debe estar en [0,1) para orden 0.")
            t = X * C0 / k
        else:
            X = min(1.0, k * t / C0)
        C = C0 * (1 - X)

    elif orden == 1:
        if t is None:
            if not (0 <= X < 1):
                raise ValueError("X debe estar en [0,1) para orden 1.")
            t = -math.log(1 - X) / k
        else:
            X = 1 - math.exp(-k * t)
        C = C0 * (1 - X)

    elif orden == 2:
        if t is None:
            if not (0 <= X < 1):
                raise ValueError("X debe estar en [0,1) para orden 2.")
            t = X / (k * C0 * (1 - X))
        else:
            kC0t = k * C0 * t
            X = kC0t / (1 + kC0t)
        C = C0 * (1 - X)

    else:
        raise ValueError(f"orden desconocido: {orden}. Usar: 0 | 1 | 2")

    return {
        "orden": orden, "C0": C0, "k": k,
        "t": t, "X": X, "C": C,
        "vida_media": _vida_media(orden, C0, k),
    }


def _vida_media(orden, C0, k):
    """Tiempo de vida media (X=0.5) segun el orden; None si no aplica/diverge."""
    if orden == 0:
        return 0.5 * C0 / k
    elif orden == 1:
        return math.log(2) / k
    elif orden == 2:
        return 1.0 / (k * C0)
    return None


# ---------------------------------------------------------------------------
# Modo: pyrolysis_yield (clasificacion de regimen + distribucion tipica de productos)
# ---------------------------------------------------------------------------
_BRIDGWATER_REGIMENES = {
    "lenta": {
        "liquido_pct": 30.0, "char_pct": 35.0, "gas_pct": 35.0,
        "descripcion": "Pirolisis lenta / carbonizacion: calentamiento bajo, residencia larga "
                       "(horas-dias), T_pico ~400C. Maximiza char.",
        "condiciones_tipicas": "calentamiento <10 C/min, residencia de vapor: horas a dias",
    },
    "intermedia": {
        "liquido_pct": 50.0, "char_pct": 25.0, "gas_pct": 25.0,
        "descripcion": "Pirolisis intermedia: calentamiento moderado, residencia ~2-30s, "
                       "T_pico ~500C. Reparto mas parejo entre las tres fracciones.",
        "condiciones_tipicas": "calentamiento 10-300 C/min, residencia de vapor: 2-30s",
    },
    "rapida": {
        "liquido_pct": 75.0, "char_pct": 12.0, "gas_pct": 13.0,
        "descripcion": "Pirolisis rapida (fast pyrolysis): calentamiento alto, residencia de "
                       "vapor muy corta (<~2s), T_pico ~500C. Maximiza bio-oil/liquido "
                       "(de ese liquido, tipicamente ~25% es agua).",
        "condiciones_tipicas": "calentamiento >300 C/min, residencia de vapor: <2s",
    },
    "gasificacion": {
        "liquido_pct": 5.0, "char_pct": 10.0, "gas_pct": 85.0,
        "descripcion": "Gasificacion: T_pico alta (>700-800C), residencia larga. Maximiza gas "
                       "de sintesis; el liquido/char remanente es marginal.",
        "condiciones_tipicas": "T_pico >700-800C, residencia de vapor: larga",
    },
}


def _mode_pyrolysis_yield(p):
    """
    Distribucion tipica de productos de pirolisis (liquido/bio-oil, char, gas) segun
    el regimen operacional, con valores de referencia de Bridgwater (2012, "Review of
    fast pyrolysis of biomass and product upgrading", Biomass and Bioenergy 38).

    IMPORTANTE: estos son rangos tipicos de literatura por categoria de proceso, no una
    correlacion continua ajustada a biomasa/reactor especifico -- sirven como estimacion
    preliminar de orden de magnitud, no como sustituto de datos experimentales propios
    (que es lo que alimenta a mass_balance/yield_efficiency una vez que hay planta o
    reactor de banco operando).

    Uso:
      a) p["regimen"] explicito: uno de "lenta"|"intermedia"|"rapida"|"gasificacion"
         -> devuelve directamente esos rendimientos de referencia.
      b) Clasificacion automatica desde condiciones de proceso:
         p["heating_rate_C_min"], p["tiempo_residencia_vapor_s"] (opcional),
         p["T_pico_C"] (opcional).
         Regla: T_pico_C >= 700 -> gasificacion (prioridad sobre heating rate).
                heating_rate > 300 C/min (o residencia < 2s si se da) -> rapida.
                heating_rate < 10 C/min -> lenta.
                resto -> intermedia.

    Si m_feed y HHV_feed se dan (opcional), tambien devuelve la masa/energia estimada
    de cada fraccion (mismo espiritu que yield_efficiency, pero a priori en vez de
    a partir de datos medidos).
    """
    regimen = p.get("regimen")

    if regimen is None:
        T_pico = p.get("T_pico_C")
        heating_rate = p.get("heating_rate_C_min")
        residencia = p.get("tiempo_residencia_vapor_s")

        if T_pico is not None and T_pico >= 700:
            regimen = "gasificacion"
        elif heating_rate is None:
            raise ValueError(
                "Dar 'regimen' explicito, o al menos 'heating_rate_C_min' "
                "(opcionalmente 'tiempo_residencia_vapor_s' y 'T_pico_C') para clasificar."
            )
        elif heating_rate > 300 or (residencia is not None and residencia < 2):
            regimen = "rapida"
        elif heating_rate < 10:
            regimen = "lenta"
        else:
            regimen = "intermedia"

    if regimen not in _BRIDGWATER_REGIMENES:
        raise ValueError(
            f"regimen desconocido: {regimen}. Usar: "
            + " | ".join(_BRIDGWATER_REGIMENES.keys())
        )

    ref = _BRIDGWATER_REGIMENES[regimen]
    resultado = {
        "regimen_clasificado": regimen,
        "liquido_pct": ref["liquido_pct"],
        "char_pct": ref["char_pct"],
        "gas_pct": ref["gas_pct"],
        "descripcion": ref["descripcion"],
        "condiciones_tipicas": ref["condiciones_tipicas"],
        "fuente": "Bridgwater (2012), Biomass and Bioenergy 38 -- valores tipicos, no correlacion continua",
    }

    m_feed = p.get("m_feed")
    if m_feed is not None:
        HHV_feed = p.get("HHV_feed")
        resultado["fracciones_masa"] = {
            "liquido": m_feed * ref["liquido_pct"] / 100.0,
            "char": m_feed * ref["char_pct"] / 100.0,
            "gas": m_feed * ref["gas_pct"] / 100.0,
        }
        if HHV_feed is not None:
            resultado["energia_feed_MJ"] = m_feed * HHV_feed

    return resultado


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
    elif mode == "arrhenius":
        return _mode_arrhenius(params)
    elif mode == "rate_law":
        return _mode_rate_law(params)
    elif mode == "batch_conversion":
        return _mode_batch_conversion(params)
    elif mode == "pyrolysis_yield":
        return _mode_pyrolysis_yield(params)
    else:
        raise ValueError(
            f"Modo desconocido: {mode}. Usar: mass_balance | energy_balance | "
            "hhv_correlation | yield_efficiency | arrhenius | rate_law | "
            "batch_conversion | pyrolysis_yield"
        )


BIOREFINERY_TOOL_SCHEMA = {
    "name": "biorefinery_tool",
    "description": (
        "Balances de masa/energia y cinetica quimica para procesos de conversion de "
        "biomasa a biocombustible (pirolisis, hidrotratamiento, fermentacion, etc). "
        "mode='mass_balance': balance de masa global en estado estacionario, "
        "resuelve una incognita o reporta error de cierre. mode='energy_balance': "
        "balance de energia (calor sensible+latente) via entalpias especificas, "
        "resuelve Q o reporta cierre. mode='hhv_correlation': estima poder "
        "calorifico superior e inferior (HHV/LHV) a partir de composicion "
        "elemental C/H/O/N/S/Ash via correlacion de Channiwala-Parikh (2002). "
        "mode='yield_efficiency': rendimientos masicos y energeticos de "
        "producto(s) respecto a la materia prima, y eficiencia energetica "
        "global del proceso. mode='arrhenius': k=A*exp(-Ea/RT) directo, o resuelve "
        "Ea/A por dos puntos (T,k) o por regresion lineal ln(k) vs 1/T sobre 3+ "
        "puntos (con R^2 del ajuste). mode='rate_law': velocidad de reaccion de "
        "orden general multi-reactivo, -r=k*prod(C_i^orden_i). "
        "mode='batch_conversion': formas integradas orden 0/1/2 para reactor batch, "
        "resuelve t o X (conversion) dado el otro, mas concentracion y vida media. "
        "mode='pyrolysis_yield': distribucion tipica de productos (liquido/char/gas) "
        "por regimen de pirolisis (lenta/intermedia/rapida/gasificacion), explicito o "
        "clasificado desde velocidad de calentamiento/residencia/T_pico, via valores "
        "de referencia de Bridgwater (2012)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "mass_balance", "energy_balance", "hhv_correlation", "yield_efficiency",
                    "arrhenius", "rate_law", "batch_conversion", "pyrolysis_yield",
                ],
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
    # --- cinetica ---
    print(compute_biorefinery("arrhenius", {"submodo": "directo", "A": 1.0e13, "Ea": 150.0, "unidades_Ea": "kJ/mol", "T": 773.15}))
    print(compute_biorefinery("arrhenius", {"submodo": "dos_puntos", "T1": 673.15, "k1": 0.002, "T2": 773.15, "k2": 0.05}))
    print(compute_biorefinery("arrhenius", {"submodo": "regresion", "datos": [
        {"T": 623.15, "k": 0.0008}, {"T": 673.15, "k": 0.002},
        {"T": 723.15, "k": 0.012}, {"T": 773.15, "k": 0.05},
    ]}))
    print(compute_biorefinery("rate_law", {
        "k": 0.02, "reactivos": [{"nombre": "biomasa", "C": 5.0, "orden": 1.0}],
    }))
    print(compute_biorefinery("batch_conversion", {"orden": 1, "C0": 5.0, "k": 0.02, "t": 60.0}))
    print(compute_biorefinery("batch_conversion", {"orden": 2, "C0": 5.0, "k": 0.02, "X": 0.8}))
    # --- pyrolysis_yield ---
    print(compute_biorefinery("pyrolysis_yield", {"regimen": "rapida"}))
    print(compute_biorefinery("pyrolysis_yield", {"heating_rate_C_min": 500, "tiempo_residencia_vapor_s": 1.0}))
    print(compute_biorefinery("pyrolysis_yield", {"heating_rate_C_min": 5}))
    print(compute_biorefinery("pyrolysis_yield", {"T_pico_C": 850}))
    print(compute_biorefinery("pyrolysis_yield", {"regimen": "rapida", "m_feed": 100.0, "HHV_feed": 18.0}))
