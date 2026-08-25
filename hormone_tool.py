"""
hormone_tool: matematicas de hormonas y senalizacion celular -- hormonas
peptidicas (via aminoacid_tool), esteroides, cinetica de union
hormona-receptor, dosis-respuesta (Hill), downregulation de receptores,
transduccion de senal y metabolismo/clearance.
"""
import math
import re
import numpy as np

# --- Base de datos de hormonas (metadata de referencia, no se usa para MW --
# la masa de peptidos se recalcula siempre desde la secuencia real via
# aminoacid_tool) ---
HORMONE_DB = {
    'insulin': {
        'type': 'peptide',
        'sequence': 'GIVEQCCTSICSLYQLENYCN',  # Cadena A (simplificada, sin cadena B ni puentes S-S)
        'half_life': 5,  # minutos
        'receptor': 'insulin_receptor',
        'function': 'glucose_metabolism',
    },
    'glucagon': {
        'type': 'peptide',
        'sequence': 'HSQGTFTSDYSKYLDSRRAQDFVQWLMNT',
        'half_life': 5,
        'receptor': 'glucagon_receptor',
        'function': 'glycogenolysis',
    },
    'cortisol': {
        'type': 'steroid',
        'formula': 'C21H30O5',
        'logP': 1.61,
        'half_life': 90,
        'receptor': 'glucocorticoid_receptor',
        'function': 'stress_response',
    },
    'testosterone': {
        'type': 'steroid',
        'formula': 'C19H28O2',
        'logP': 3.32,
        'half_life': 60,
        'receptor': 'androgen_receptor',
        'function': 'masculinization',
    },
    'estradiol': {
        'type': 'steroid',
        'formula': 'C18H24O2',
        'logP': 4.01,
        'half_life': 30,
        'receptor': 'estrogen_receptor',
        'function': 'feminization',
    },
    'adrenaline': {
        'type': 'catecholamine',
        'formula': 'C9H13NO3',
        'half_life': 2,
        'receptor': 'beta_adrenergic',
        'function': 'fight_or_flight',
    },
}

RECEPTOR_DB = {
    'insulin_receptor': {'Kd': 1e-9, 'Bmax': 10000, 'kon': 1e6, 'koff': 0.001, 'signal_pathway': 'PI3K/AKT'},
    'glucagon_receptor': {'Kd': 5e-9, 'Bmax': 5000, 'kon': 1e6, 'koff': 0.005, 'signal_pathway': 'cAMP/PKA'},
    'glucocorticoid_receptor': {'Kd': 1e-8, 'Bmax': 30000, 'kon': 1e5, 'koff': 0.001, 'signal_pathway': 'transcriptional_regulation'},
}

ELEMENT_MASS = {'C': 12.011, 'H': 1.008, 'O': 15.999, 'N': 14.007, 'S': 32.065, 'I': 126.904}


def _trapz_compat(y, x):
    """np.trapz fue renombrado a np.trapezoid en numpy >=2.0 y removido en
    versiones futuras; esto funciona con cualquier version sin apostar a una."""
    if hasattr(np, 'trapezoid'):
        return np.trapezoid(y, x)
    return np.trapz(y, x)


def hormone_tool(mode, params):
    """
    mode: string, uno de los modos listados abajo.
    params: dict con los argumentos de tools/call (incluye 'mode' y el resto).

    Modos:
    - peptide_hormone: composicion/MW/pI de hormona peptidica (via aminoacid_tool)
    - steroid_hormone: masa molecular desde formula quimica
    - hormone_receptor: union hormona-receptor (equilibrio de Langmuir, ecuacion cuadratica exacta)
    - dose_response: curva dosis-respuesta (modelo de Hill)
    - binding_kinetics: cinetica de union kon/koff, t1/2 de union
    - receptor_saturation: curva de saturacion + datos para grafico de Scatchard
    - downregulation: modelo de regulacion a la baja de receptores
    - signal_transduction: amplificacion en cascada de senalizacion (deterministico)
    - hormone_metabolism: decaimiento exponencial, vida media, AUC
    - validate: autoverificacion
    """
    if mode == 'peptide_hormone':
        return _peptide_hormone_analysis(params)
    elif mode == 'steroid_hormone':
        return _steroid_hormone_analysis(params)
    elif mode == 'hormone_receptor':
        return _hormone_receptor_binding(params)
    elif mode == 'dose_response':
        return _dose_response(params)
    elif mode == 'binding_kinetics':
        return _binding_kinetics(params)
    elif mode == 'receptor_saturation':
        return _receptor_saturation(params)
    elif mode == 'downregulation':
        return _downregulation(params)
    elif mode == 'signal_transduction':
        return _signal_transduction(params)
    elif mode == 'hormone_metabolism':
        return _hormone_metabolism(params)
    elif mode == 'validate':
        return _validate_hormone()
    else:
        return {'error': f'Modo desconocido: {mode}', 'validation_passed': False}


def _peptide_hormone_analysis(params):
    hormone_name = params.get('hormone', '').lower()
    sequence = params.get('sequence', '').upper()
    detailed = params.get('detailed', True)

    if sequence:
        seq = sequence
    elif hormone_name in HORMONE_DB:
        seq = HORMONE_DB[hormone_name].get('sequence', '')
    else:
        return {'error': f'Hormona no encontrada: {hormone_name}', 'validation_passed': False}

    if not seq:
        return {'error': 'Secuencia no disponible', 'validation_passed': False}

    try:
        from aminoacid_tool import _aminoacid_composition, _calculate_pI, _calculate_charge, AMINO_ACIDS
    except ImportError:
        return {'error': 'aminoacid_tool no disponible', 'validation_passed': False}

    comp = _aminoacid_composition({'sequence': seq, 'detailed': True})
    if not comp.get('validation_passed'):
        return {'error': 'Secuencia invalida para aminoacid_tool', 'validation_passed': False}

    charge = _calculate_charge(seq, 7.0)
    pI = _calculate_pI(seq)
    hydrophobicities = [AMINO_ACIDS[aa]['hydrophobicity'] for aa in seq if aa in AMINO_ACIDS]
    avg_hydrophobicity = sum(hydrophobicities) / len(seq) if seq else 0

    result = {
        'hormone': hormone_name if hormone_name else 'custom_peptide',
        'sequence': seq,
        'length': len(seq),
        'molecular_weight': comp.get('molecular_weight', 0),
        'isoelectric_point': pI,
        'charge_at_ph7': charge,
        'avg_hydrophobicity': float(avg_hydrophobicity),
        'validation_passed': True,
    }

    if detailed:
        result['composition'] = comp.get('composition', {})
        result['amino_acid_frequency'] = comp.get('frequency', {})
        if hormone_name in HORMONE_DB:
            h_db = HORMONE_DB[hormone_name]
            result['receptor'] = h_db.get('receptor', 'unknown')
            result['half_life_min'] = h_db.get('half_life', None)
            result['function'] = h_db.get('function', 'unknown')

    return result


def _steroid_hormone_analysis(params):
    hormone_name = params.get('hormone', '').lower()
    formula = params.get('formula', '')

    if hormone_name not in HORMONE_DB and not formula:
        return {'error': f'Hormona no encontrada: {hormone_name}', 'validation_passed': False}

    h_data = HORMONE_DB.get(hormone_name, {})
    formula = formula or h_data.get('formula', '')
    if not formula:
        return {'error': 'Formula no disponible', 'validation_passed': False}

    pattern = r'([A-Z][a-z]?)(\d*)'
    matches = re.findall(pattern, formula)

    mass = 0.0
    atom_counts = {}
    for elem, count in matches:
        if not elem:
            continue
        count = int(count) if count else 1
        atom_counts[elem] = atom_counts.get(elem, 0) + count
        if elem in ELEMENT_MASS:
            mass += ELEMENT_MASS[elem] * count

    result = {
        'hormone': hormone_name if hormone_name else 'custom_steroid',
        'formula': formula,
        'molecular_weight': float(mass),
        'atom_counts': atom_counts,
        'validation_passed': True,
    }

    if hormone_name in HORMONE_DB:
        result.update({
            'logP': h_data.get('logP', None),
            'half_life_min': h_data.get('half_life', None),
            'receptor': h_data.get('receptor', 'unknown'),
            'function': h_data.get('function', 'unknown'),
        })

    return result


def _hormone_receptor_binding(params):
    """Equilibrio hormona-receptor tipo Langmuir, resuelto exacto (cuadratica)."""
    hormone = params.get('hormone', '').lower()
    L_total = params.get('ligand_concentration', 1e-9)
    R_total = params.get('receptor_concentration', 1e-10)
    Kd = params.get('Kd', None)

    if Kd is None:
        receptor_name = HORMONE_DB.get(hormone, {}).get('receptor', '')
        Kd = RECEPTOR_DB.get(receptor_name, {}).get('Kd', 1e-9)

    # [RL]^2 - (L_total + R_total + Kd)*[RL] + L_total*R_total = 0
    a = 1.0
    b = -(L_total + R_total + Kd)
    c = L_total * R_total
    discriminant = b**2 - 4*a*c
    if discriminant < 0:
        return {'error': 'Sin solucion real', 'validation_passed': False}

    RL = (-b - math.sqrt(discriminant)) / (2*a)
    L_free = L_total - RL
    R_free = R_total - RL
    occupancy = RL / R_total if R_total > 0 else 0

    return {
        'hormone': hormone,
        'Kd': float(Kd),
        'ligand_total': float(L_total),
        'receptor_total': float(R_total),
        'ligand_bound': float(RL),
        'ligand_free': float(L_free),
        'receptor_free': float(R_free),
        'fraction_occupied': float(occupancy),
        'validation_passed': True,
    }


def _dose_response(params):
    """Modelo de Hill: E = Emax * L^n / (EC50^n + L^n)."""
    hormone = params.get('hormone', '').lower()
    EC50 = params.get('EC50', 1e-9)
    Hill_n = params.get('Hill_coefficient', 1.0)
    dose_min = params.get('dose_min', -12)
    dose_max = params.get('dose_max', -6)
    n_points = params.get('n_points', 50)
    Emax = params.get('Emax', 100)

    doses = np.logspace(dose_min, dose_max, n_points)
    response = Emax * (doses**Hill_n) / (EC50**Hill_n + doses**Hill_n)

    def find_ec(percent):
        target = percent * Emax / 100
        idx = np.argmin(np.abs(response - target))
        return doses[idx]

    EC10 = find_ec(10)
    EC90 = find_ec(90)

    return {
        'hormone': hormone,
        'EC50': float(EC50),
        'Hill_coefficient': float(Hill_n),
        'Emax': float(Emax),
        'EC10': float(EC10),
        'EC90': float(EC90),
        'therapeutic_window': float(EC90 / EC10) if EC10 > 0 else None,
        'dose_response': {'doses': doses.tolist(), 'response': response.tolist()},
        'validation_passed': True,
    }


def _binding_kinetics(params):
    hormone = params.get('hormone', '').lower()
    kon = params.get('kon', None)
    koff = params.get('koff', None)
    time_max = params.get('time', 300)

    receptor_name = HORMONE_DB.get(hormone, {}).get('receptor', '')
    receptor_data = RECEPTOR_DB.get(receptor_name, {})
    if kon is None:
        kon = receptor_data.get('kon', 1e6)
    if koff is None:
        koff = receptor_data.get('koff', 0.001)

    Kd = koff / kon
    L0 = params.get('ligand_initial', 1e-9)
    R0 = params.get('receptor_initial', 1e-10)

    t = np.linspace(0, time_max, 200)
    k_obs = kon * L0 + koff
    RL_ss = (L0 * R0) / (Kd + L0)
    RL_t = RL_ss * (1 - np.exp(-k_obs * t))
    t_half = math.log(2) / k_obs

    return {
        'hormone': hormone,
        'kon': float(kon),
        'koff': float(koff),
        'Kd': float(Kd),
        't_half_sec': float(t_half),
        'binding_curve': {'time': t.tolist(), 'bound_complex': RL_t.tolist()},
        'validation_passed': True,
    }


def _receptor_saturation(params):
    hormone = params.get('hormone', '').lower()
    Kd = params.get('Kd', None)
    Bmax = params.get('Bmax', None)

    receptor_name = HORMONE_DB.get(hormone, {}).get('receptor', '')
    receptor_data = RECEPTOR_DB.get(receptor_name, {})
    if Kd is None:
        Kd = receptor_data.get('Kd', 1e-9)
    if Bmax is None:
        Bmax = receptor_data.get('Bmax', 10000)

    L_range = np.logspace(-12, -6, 30)
    B_specific = (Bmax * L_range) / (Kd + L_range)
    B_over_L = B_specific / L_range

    return {
        'hormone': hormone,
        'Kd': float(Kd),
        'Bmax': float(Bmax),
        'scatchard_plot': {'bound': B_specific.tolist(), 'bound_over_free': B_over_L.tolist()},
        'validation_passed': True,
    }


def _downregulation(params):
    """dR/dt = k_syn - k_dest*R - k_int*[H]*R -- solucion analitica exacta (EDO lineal)."""
    hormone = params.get('hormone', '').lower()
    k_dest = params.get('k_dest', 0.05)
    k_syn = params.get('k_syn', 100)
    R0 = params.get('initial_receptors', 10000)
    time_max = params.get('time', 24)
    H_conc = params.get('hormone_concentration', 1e-9)
    k_int = params.get('k_internalization', 1e-6)

    t = np.linspace(0, time_max, 100)
    k_total = k_dest + k_int * H_conc
    R_ss = k_syn / k_total
    R_t = R_ss + (R0 - R_ss) * np.exp(-k_total * t)

    R_half = (R0 + R_ss) / 2
    if R0 != R_ss:
        t_half = -math.log((R_half - R_ss) / (R0 - R_ss)) / k_total
    else:
        t_half = None

    return {
        'hormone': hormone,
        'initial_receptors': float(R0),
        'steady_state_receptors': float(R_ss),
        'receptor_reduction_pct': float((R0 - R_ss) / R0 * 100) if R0 else None,
        'time_to_half_hr': float(t_half) if t_half is not None else None,
        'downregulation_curve': {'time': t.tolist(), 'receptors': R_t.tolist()},
        'validation_passed': True,
    }


def _signal_transduction(params):
    """
    Cascada de amplificacion determinista: cada paso multiplica la senal
    por un factor de amplificacion fijo. (Version original tenia ruido
    np.random.uniform sin seed -- se saco para que validate() sea
    reproducible; si se quiere variabilidad biologica, pasarla como
    parametro explicito con seed, no implicita.)
    """
    hormone = params.get('hormone', '').lower()
    pathway = params.get('pathway', '')
    n_steps = params.get('steps', 3)
    amplification = params.get('amplification', 10)

    receptor_name = HORMONE_DB.get(hormone, {}).get('receptor', '')
    if not pathway:
        pathway = RECEPTOR_DB.get(receptor_name, {}).get('signal_pathway', 'unknown')

    initial_signal = params.get('hormone_concentration', 1e-9)
    signal_levels = [initial_signal]
    for _ in range(n_steps):
        signal_levels.append(signal_levels[-1] * amplification)

    step_time = params.get('step_time', 0.1)
    times = [i * step_time for i in range(n_steps + 1)]

    return {
        'hormone': hormone,
        'pathway': pathway,
        'steps': n_steps,
        'amplification_factor': amplification,
        'final_signal_amplitude': float(signal_levels[-1]),
        'total_amplification': float(amplification ** n_steps),
        'signal_propagation': {'time': times, 'signal': signal_levels},
        'validation_passed': True,
    }


def _hormone_metabolism(params):
    hormone = params.get('hormone', '').lower()
    t1_2 = params.get('half_life', None)

    if t1_2 is None:
        t1_2 = HORMONE_DB.get(hormone, {}).get('half_life', 60)

    k_el = math.log(2) / t1_2
    time_max = 5 * t1_2
    t = np.linspace(0, time_max, 100)

    C0 = params.get('initial_concentration', 100)
    C_t = C0 * np.exp(-k_el * t)
    AUC = float(_trapz_compat(C_t, t))

    return {
        'hormone': hormone,
        'half_life_min': float(t1_2),
        'elimination_rate_min': float(k_el),
        'initial_concentration': float(C0),
        'AUC': AUC,
        'concentration_curve': {'time': t.tolist(), 'concentration': C_t.tolist()},
        'validation_passed': True,
    }


def _validate_hormone():
    checks = []

    # 1. MW de insulina (cadena A) cae en el rango real conocido (~2384 Da)
    insulin = _peptide_hormone_analysis({'hormone': 'insulin'})
    checks.append(('insulin_mw_rango_real', 2300 < insulin.get('molecular_weight', 0) < 2450))

    # 2. Union hormona-receptor: ocupacion fraccional entre 0 y 1
    binding = _hormone_receptor_binding({'hormone': 'insulin', 'ligand_concentration': 1e-8, 'receptor_concentration': 1e-9})
    checks.append(('receptor_binding_ocupacion_valida', 0 < binding.get('fraction_occupied', -1) < 1))

    # 3. Balance de masa en union: bound + free debe reconstruir el total
    checks.append(('balance_masa_ligando', abs((binding['ligand_bound'] + binding['ligand_free']) - binding['ligand_total']) < 1e-15))

    # 4. Dosis-respuesta: EC10 < EC50 < EC90 (monotonicidad de Hill)
    dose = _dose_response({'hormone': 'insulin', 'EC50': 1e-9, 'Hill_coefficient': 1.5})
    checks.append(('dose_response_monotonica', dose['EC10'] < dose['EC50'] < dose['EC90']))

    # 5. Cinetica de union: Kd = koff/kon exacto
    kin = _binding_kinetics({'hormone': 'insulin', 'kon': 1e6, 'koff': 0.002})
    checks.append(('kinetics_Kd_exacto', abs(kin['Kd'] - (0.002 / 1e6)) < 1e-15))

    # 6. Downregulation: estado estacionario correcto (k_syn / k_total)
    down = _downregulation({'k_syn': 100, 'k_dest': 0.05, 'hormone_concentration': 0, 'initial_receptors': 10000})
    checks.append(('downregulation_steady_state_exacto', abs(down['steady_state_receptors'] - (100 / 0.05)) < 1e-6))

    # 7. Signal transduction determinista: misma llamada da mismo resultado
    s1 = _signal_transduction({'hormone': 'insulin', 'steps': 3, 'amplification': 10})
    s2 = _signal_transduction({'hormone': 'insulin', 'steps': 3, 'amplification': 10})
    checks.append(('signal_transduction_deterministico', s1['final_signal_amplitude'] == s2['final_signal_amplitude']))

    # 8. Steroide: masa de cortisol (C21H30O5) cae cerca del valor real ~362.46
    cortisol = _steroid_hormone_analysis({'hormone': 'cortisol'})
    checks.append(('cortisol_mw_referencia_real', abs(cortisol['molecular_weight'] - 362.46) < 0.5))

    # 9. Metabolismo: decaimiento exacto tras una vida media (C = C0/2)
    metab = _hormone_metabolism({'hormone': 'insulin', 'half_life': 5, 'initial_concentration': 100})
    t_arr = np.array(metab['concentration_curve']['time'])
    idx_half = int(np.argmin(np.abs(t_arr - 5)))
    C_at_half = metab['concentration_curve']['concentration'][idx_half]
    checks.append(('metabolismo_decaimiento_media_vida', abs(C_at_half - 50) < 2))

    return {
        'validation_passed': all(c[1] for c in checks),
        'checks': [{'name': c[0], 'passed': c[1]} for c in checks],
    }


HORMONE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": [
                "peptide_hormone", "steroid_hormone", "hormone_receptor",
                "dose_response", "binding_kinetics", "receptor_saturation",
                "downregulation", "signal_transduction", "hormone_metabolism",
                "validate",
            ],
            "description": "Modo de operacion de la tool.",
        },
        "hormone": {
            "type": "string",
            "description": "Nombre de hormona conocida (insulin, glucagon, cortisol, "
                            "testosterone, estradiol, adrenaline). Opcional si se pasa "
                            "sequence/formula custom.",
        },
        "sequence": {"type": "string", "description": "Solo peptide_hormone: secuencia custom de una letra."},
        "formula": {"type": "string", "description": "Solo steroid_hormone: formula quimica custom (ej. 'C21H30O5')."},
        "detailed": {"type": "boolean", "description": "Solo peptide_hormone: incluir composicion detallada. Default true."},
        "ligand_concentration": {"type": "number", "description": "Solo hormone_receptor: [L] total en M."},
        "receptor_concentration": {"type": "number", "description": "Solo hormone_receptor: [R] total en M."},
        "Kd": {"type": "number", "description": "Constante de disociacion en M (hormone_receptor, receptor_saturation)."},
        "EC50": {"type": "number", "description": "Solo dose_response: concentracion efectiva media en M."},
        "Hill_coefficient": {"type": "number", "description": "Solo dose_response: coeficiente de Hill (n)."},
        "Emax": {"type": "number", "description": "Solo dose_response: respuesta maxima (%). Default 100."},
        "dose_min": {"type": "number", "description": "Solo dose_response: log10 de la dosis minima. Default -12."},
        "dose_max": {"type": "number", "description": "Solo dose_response: log10 de la dosis maxima. Default -6."},
        "n_points": {"type": "integer", "description": "Numero de puntos en la curva (dose_response/otros)."},
        "kon": {"type": "number", "description": "Constante de asociacion M-1 s-1 (binding_kinetics)."},
        "koff": {"type": "number", "description": "Constante de disociacion s-1 (binding_kinetics)."},
        "time": {"type": "number", "description": "Tiempo de simulacion, segundos en binding_kinetics, horas en downregulation."},
        "ligand_initial": {"type": "number", "description": "Solo binding_kinetics: [L]0 en M."},
        "receptor_initial": {"type": "number", "description": "Solo binding_kinetics: [R]0 en M."},
        "Bmax": {"type": "number", "description": "Solo receptor_saturation: numero maximo de sitios de union."},
        "k_dest": {"type": "number", "description": "Solo downregulation: tasa de degradacion de receptores (h-1)."},
        "k_syn": {"type": "number", "description": "Solo downregulation: tasa de sintesis de receptores (receptores/h)."},
        "initial_receptors": {"type": "number", "description": "Solo downregulation: numero inicial de receptores."},
        "hormone_concentration": {"type": "number", "description": "Concentracion de hormona en M (downregulation, signal_transduction)."},
        "k_internalization": {"type": "number", "description": "Solo downregulation: tasa de internalizacion M-1 h-1."},
        "pathway": {"type": "string", "description": "Solo signal_transduction: via de senalizacion (si no se da, se infiere del receptor)."},
        "steps": {"type": "integer", "description": "Solo signal_transduction: pasos de la cascada."},
        "amplification": {"type": "number", "description": "Solo signal_transduction: factor de amplificacion por paso."},
        "step_time": {"type": "number", "description": "Solo signal_transduction: tiempo caracteristico por paso (s)."},
        "half_life": {"type": "number", "description": "Solo hormone_metabolism: vida media en minutos."},
        "initial_concentration": {"type": "number", "description": "Solo hormone_metabolism: concentracion inicial (unidades arbitrarias)."},
    },
    "required": ["mode"],
}


try:
    from tool_registry import register_tool
    register_tool(
        name="hormone_tool",
        schema={
            "name": "hormone_tool",
            "description": (
                "Matematicas de hormonas y senalizacion celular: hormonas peptidicas "
                "(composicion, MW, pI via aminoacid_tool), hormonas esteroides (masa "
                "desde formula), union hormona-receptor (equilibrio de Langmuir exacto), "
                "dosis-respuesta (modelo de Hill), cinetica de union kon/koff, saturacion "
                "de receptores (Scatchard), downregulation (EDO lineal con solucion "
                "analitica exacta), cascada de transduccion de senal (deterministica), "
                "y metabolismo/clearance hormonal (decaimiento exponencial, AUC)."
            ),
            "inputSchema": HORMONE_TOOL_SCHEMA,
        },
        handler=lambda args: hormone_tool(args.get("mode"), args),
    )
except ImportError:
    pass


if __name__ == '__main__':
    import json
    print(json.dumps(_validate_hormone(), indent=2))
