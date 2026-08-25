"""
aminoacid_tool: composición, carga, pI, hidrofobicidad, digestión y masa de
péptidos/proteínas a partir de secuencia de una letra.

Datos: pKa de grupos ionizables (escala EMBOSS/Lehninger), hidrofobicidad
Kyte-Doolittle (1982), masas residuales promedio y monoisotópicas estándar.
"""
import math

# --- Tabla de aminoácidos ---
# mw_residue: masa del residuo en cadena (masa libre - agua), promedio
# mw_mono: masa monoisotópica residual
# hydrophobicity: escala Kyte-Doolittle
# pKa_side: pKa del grupo lateral ionizable (None si no ionizable)
# side_type: 'acidic' (se desprotona, queda negativo) o 'basic' (se protona, queda positivo)
AMINO_ACIDS = {
    'A': {'name': 'Alanine',       'mw_residue': 71.0788,  'mw_mono': 71.03711,  'hydrophobicity': 1.8,  'pKa_side': None, 'side_type': None},
    'R': {'name': 'Arginine',      'mw_residue': 156.1875, 'mw_mono': 156.10111, 'hydrophobicity': -4.5, 'pKa_side': 12.48, 'side_type': 'basic'},
    'N': {'name': 'Asparagine',    'mw_residue': 114.1038, 'mw_mono': 114.04293, 'hydrophobicity': -3.5, 'pKa_side': None, 'side_type': None},
    'D': {'name': 'Aspartate',     'mw_residue': 115.0886, 'mw_mono': 115.02694, 'hydrophobicity': -3.5, 'pKa_side': 3.65,  'side_type': 'acidic'},
    'C': {'name': 'Cysteine',      'mw_residue': 103.1388, 'mw_mono': 103.00919, 'hydrophobicity': 2.5,  'pKa_side': 8.33,  'side_type': 'acidic'},
    'Q': {'name': 'Glutamine',     'mw_residue': 128.1307, 'mw_mono': 128.05858, 'hydrophobicity': -3.5, 'pKa_side': None, 'side_type': None},
    'E': {'name': 'Glutamate',     'mw_residue': 129.1155, 'mw_mono': 129.04259, 'hydrophobicity': -3.5, 'pKa_side': 4.25,  'side_type': 'acidic'},
    'G': {'name': 'Glycine',       'mw_residue': 57.0519,  'mw_mono': 57.02146,  'hydrophobicity': -0.4, 'pKa_side': None, 'side_type': None},
    'H': {'name': 'Histidine',     'mw_residue': 137.1411, 'mw_mono': 137.05891, 'hydrophobicity': -3.2, 'pKa_side': 6.00,  'side_type': 'basic'},
    'I': {'name': 'Isoleucine',    'mw_residue': 113.1594, 'mw_mono': 113.08406, 'hydrophobicity': 4.5,  'pKa_side': None, 'side_type': None},
    'L': {'name': 'Leucine',       'mw_residue': 113.1594, 'mw_mono': 113.08406, 'hydrophobicity': 3.8,  'pKa_side': None, 'side_type': None},
    'K': {'name': 'Lysine',        'mw_residue': 128.1741, 'mw_mono': 128.09496, 'hydrophobicity': -3.9, 'pKa_side': 10.53, 'side_type': 'basic'},
    'M': {'name': 'Methionine',    'mw_residue': 131.1926, 'mw_mono': 131.04049, 'hydrophobicity': 1.9,  'pKa_side': None, 'side_type': None},
    'F': {'name': 'Phenylalanine', 'mw_residue': 147.1766, 'mw_mono': 147.06841, 'hydrophobicity': 2.8,  'pKa_side': None, 'side_type': None},
    'P': {'name': 'Proline',       'mw_residue': 97.1167,  'mw_mono': 97.05276,  'hydrophobicity': -1.6, 'pKa_side': None, 'side_type': None},
    'S': {'name': 'Serine',        'mw_residue': 87.0782,  'mw_mono': 87.03203,  'hydrophobicity': -0.8, 'pKa_side': None, 'side_type': None},
    'T': {'name': 'Threonine',     'mw_residue': 101.1051, 'mw_mono': 101.04768, 'hydrophobicity': -0.7, 'pKa_side': None, 'side_type': None},
    'W': {'name': 'Tryptophan',    'mw_residue': 186.2132, 'mw_mono': 186.07931, 'hydrophobicity': -0.9, 'pKa_side': None, 'side_type': None},
    'Y': {'name': 'Tyrosine',      'mw_residue': 163.1760, 'mw_mono': 163.06333, 'hydrophobicity': -1.3, 'pKa_side': 10.07, 'side_type': 'acidic'},
    'V': {'name': 'Valine',        'mw_residue': 99.1326,  'mw_mono': 99.06841,  'hydrophobicity': 4.2,  'pKa_side': None, 'side_type': None},
}

WATER_MW = 18.0153
WATER_MONO = 18.01056
PKA_NTERM = 9.69
PKA_CTERM = 2.34

# Coeficientes de extinción molar a 280nm (M-1 cm-1), Pace et al. 1995
EXT_COEF = {'W': 5500, 'Y': 1490, 'C_cystine': 125}


def aminoacid_tool(mode, params):
    """
    Análisis de aminoácidos y péptidos a partir de secuencia de una letra.

    mode: string, uno de los modos listados abajo.
    params: dict con los argumentos de tools/call (incluye 'mode' y el resto).

    Modos:
    - composition: composición, frecuencia, peso molecular
    - isoelectric_point: pI vía bisección sobre carga neta
    - charge_at_ph: carga neta a un pH dado
    - titration_curve: carga neta en función de pH (0-14)
    - hydrophobicity: perfil e índice promedio (Kyte-Doolittle)
    - molar_extinction: coeficiente de extinción a 280nm (reducido/oxidado)
    - sequence_analysis: composición + fracciones aromática/alifática/cargada/polar
    - peptide_mass: masa promedio y monoisotópica
    - digestion: digestión in-silico con tripsina (corta tras K/R, no antes de P)
    - validate: autoverificación
    """
    if mode == 'composition':
        return _aminoacid_composition(params)
    elif mode == 'isoelectric_point':
        seq = _clean_seq(params.get('sequence', ''))
        return {'sequence': seq, 'isoelectric_point': _calculate_pI(seq), 'validation_passed': True}
    elif mode == 'charge_at_ph':
        seq = _clean_seq(params.get('sequence', ''))
        pH = params.get('pH', 7.0)
        return {'sequence': seq, 'pH': pH, 'net_charge': _calculate_charge(seq, pH), 'validation_passed': True}
    elif mode == 'titration_curve':
        return _titration_curve(params)
    elif mode == 'hydrophobicity':
        return _hydrophobicity_profile(params)
    elif mode == 'molar_extinction':
        return _molar_extinction(params)
    elif mode == 'sequence_analysis':
        return _sequence_analysis(params)
    elif mode == 'peptide_mass':
        return _peptide_mass(params)
    elif mode == 'digestion':
        return _digestion(params)
    elif mode == 'validate':
        return _validate_aminoacid()
    else:
        return {'error': f'Modo desconocido: {mode}', 'validation_passed': False}


def _clean_seq(seq):
    return ''.join(c for c in seq.upper() if c in AMINO_ACIDS)


def _calculate_charge(seq, pH):
    """Carga neta a un pH dado (modelo Henderson-Hasselbalch, grupos independientes)."""
    if not seq:
        return 0.0
    charge = 0.0
    # N-terminal (básico)
    charge += 1.0 / (1.0 + 10 ** (pH - PKA_NTERM))
    # C-terminal (ácido)
    charge -= 1.0 / (1.0 + 10 ** (PKA_CTERM - pH))
    for aa in seq:
        info = AMINO_ACIDS.get(aa)
        if not info or info['pKa_side'] is None:
            continue
        pKa = info['pKa_side']
        if info['side_type'] == 'basic':
            charge += 1.0 / (1.0 + 10 ** (pH - pKa))
        elif info['side_type'] == 'acidic':
            charge -= 1.0 / (1.0 + 10 ** (pKa - pH))
    return float(charge)


def _calculate_pI(seq, tol=1e-4):
    """pI vía bisección: pH donde la carga neta cruza 0."""
    if not seq:
        return None
    lo, hi = 0.0, 14.0
    # signo de la carga en lo debe ser positivo, en hi negativo
    if _calculate_charge(seq, lo) < 0 or _calculate_charge(seq, hi) > 0:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        c = _calculate_charge(seq, mid)
        if abs(c) < tol:
            return float(mid)
        if c > 0:
            lo = mid
        else:
            hi = mid
    return float((lo + hi) / 2)


def _aminoacid_composition(params):
    seq = _clean_seq(params.get('sequence', ''))
    detailed = params.get('detailed', True)
    if not seq:
        return {'error': 'Secuencia vacía o inválida', 'validation_passed': False}
    n = len(seq)
    composition = {}
    for aa in seq:
        composition[aa] = composition.get(aa, 0) + 1
    frequency = {aa: c / n for aa, c in composition.items()}
    mw = sum(AMINO_ACIDS[aa]['mw_residue'] for aa in seq) + WATER_MW
    result = {
        'sequence': seq,
        'length': n,
        'molecular_weight': float(mw),
        'validation_passed': True,
    }
    if detailed:
        result['composition'] = composition
        result['frequency'] = frequency
    return result


def _titration_curve(params):
    seq = _clean_seq(params.get('sequence', ''))
    n_points = params.get('n_points', 71)
    if not seq:
        return {'error': 'Secuencia vacía o inválida', 'validation_passed': False}
    pHs = [14.0 * i / (n_points - 1) for i in range(n_points)]
    charges = [_calculate_charge(seq, pH) for pH in pHs]
    return {
        'sequence': seq,
        'isoelectric_point': _calculate_pI(seq),
        'titration_curve': {'pH': pHs, 'net_charge': charges},
        'validation_passed': True,
    }


def _hydrophobicity_profile(params):
    seq = _clean_seq(params.get('sequence', ''))
    window = params.get('window', 9)
    if not seq:
        return {'error': 'Secuencia vacía o inválida', 'validation_passed': False}
    values = [AMINO_ACIDS[aa]['hydrophobicity'] for aa in seq]
    avg = sum(values) / len(values)
    profile = []
    half = window // 2
    if len(seq) >= window:
        for i in range(half, len(seq) - half):
            w = values[i - half:i + half + 1]
            profile.append(sum(w) / len(w))
    return {
        'sequence': seq,
        'avg_hydrophobicity': float(avg),
        'per_residue': values,
        'sliding_window_profile': profile,
        'window': window,
        'validation_passed': True,
    }


def _molar_extinction(params):
    seq = _clean_seq(params.get('sequence', ''))
    assume_all_disulfide = params.get('assume_all_disulfide', False)
    if not seq:
        return {'error': 'Secuencia vacía o inválida', 'validation_passed': False}
    nW = seq.count('W')
    nY = seq.count('Y')
    nC = seq.count('C')
    ext_reduced = nW * EXT_COEF['W'] + nY * EXT_COEF['Y']
    n_cystine = nC // 2 if assume_all_disulfide else 0
    ext_oxidized = ext_reduced + n_cystine * EXT_COEF['C_cystine']
    return {
        'sequence': seq,
        'n_trp': nW, 'n_tyr': nY, 'n_cys': nC,
        'extinction_coefficient_reduced': int(ext_reduced),
        'extinction_coefficient_oxidized_estimate': int(ext_oxidized),
        'validation_passed': True,
    }


def _sequence_analysis(params):
    seq = _clean_seq(params.get('sequence', ''))
    if not seq:
        return {'error': 'Secuencia vacía o inválida', 'validation_passed': False}
    n = len(seq)
    aromatic = sum(seq.count(a) for a in 'FWY')
    aliphatic = sum(seq.count(a) for a in 'AILV')
    polar = sum(seq.count(a) for a in 'STNQCY')
    charged_pos = sum(seq.count(a) for a in 'KRH')
    charged_neg = sum(seq.count(a) for a in 'DE')
    return {
        'sequence': seq,
        'length': n,
        'molecular_weight': _aminoacid_composition({'sequence': seq, 'detailed': False})['molecular_weight'],
        'isoelectric_point': _calculate_pI(seq),
        'net_charge_ph7': _calculate_charge(seq, 7.0),
        'fraction_aromatic': aromatic / n,
        'fraction_aliphatic': aliphatic / n,
        'fraction_polar': polar / n,
        'fraction_charged_positive': charged_pos / n,
        'fraction_charged_negative': charged_neg / n,
        'validation_passed': True,
    }


def _peptide_mass(params):
    seq = _clean_seq(params.get('sequence', ''))
    if not seq:
        return {'error': 'Secuencia vacía o inválida', 'validation_passed': False}
    mw_avg = sum(AMINO_ACIDS[aa]['mw_residue'] for aa in seq) + WATER_MW
    mw_mono = sum(AMINO_ACIDS[aa]['mw_mono'] for aa in seq) + WATER_MONO
    return {
        'sequence': seq,
        'length': len(seq),
        'average_mass': float(mw_avg),
        'monoisotopic_mass': float(mw_mono),
        'validation_passed': True,
    }


def _digestion(params):
    """Digestión con tripsina: corta después de K/R salvo que siga P."""
    seq = _clean_seq(params.get('sequence', ''))
    if not seq:
        return {'error': 'Secuencia vacía o inválida', 'validation_passed': False}
    fragments = []
    current = ''
    for i, aa in enumerate(seq):
        current += aa
        next_aa = seq[i + 1] if i + 1 < len(seq) else None
        if aa in ('K', 'R') and next_aa != 'P':
            fragments.append(current)
            current = ''
    if current:
        fragments.append(current)
    frag_info = [{'peptide': f, 'length': len(f),
                   'mass': sum(AMINO_ACIDS[a]['mw_residue'] for a in f) + WATER_MW}
                  for f in fragments]
    return {
        'sequence': seq,
        'enzyme': 'trypsin',
        'n_fragments': len(fragments),
        'fragments': frag_info,
        'validation_passed': True,
    }


def _validate_aminoacid():
    checks = []

    # 1. pI de glicina como aminoácido aislado (pI teórico ~5.97, Lehninger)
    pI_gly = _calculate_pI('G')
    checks.append(('pI_glicina_referencia', abs(pI_gly - 5.97) < 0.3))

    # 2. pI de lisina aislada (pI teórico ~9.74) — debe dar básico
    pI_lys = _calculate_pI('K')
    checks.append(('pI_lisina_basica', pI_lys > 9.0))

    # 3. pI de aspartato aislado (pI teórico ~2.77-2.98) — debe dar ácido
    pI_asp = _calculate_pI('D')
    checks.append(('pI_aspartato_acida', pI_asp < 3.5))

    # 4. Carga neta a pH muy bajo debe ser positiva, a pH muy alto negativa
    seq_test = 'ACDEFGHIKLMNPQRSTVWY'  # los 20 aminoácidos
    c_low = _calculate_charge(seq_test, 0.5)
    c_high = _calculate_charge(seq_test, 13.5)
    checks.append(('carga_extremos_signo_correcto', c_low > 0 and c_high < 0))

    # 5. Insulina cadena A: MW conocido ~2384 Da para la secuencia real de 21 residuos
    insulin_a = 'GIVEQCCTSICSLYQLENYCN'
    mw = _aminoacid_composition({'sequence': insulin_a, 'detailed': False})['molecular_weight']
    checks.append(('mw_insulina_cadena_A_rango_real', 2300 < mw < 2450))

    # 6. Digestión tripsina no corta antes de P (caso KP)
    dig = _digestion({'sequence': 'AAKPAAKAA'})
    checks.append(('tripsina_respeta_regla_KP', dig['fragments'][0]['peptide'] == 'AAKPAAK'))

    # 7. Extinción molar: 1 Trp + 1 Tyr = 5500+1490
    ext = _molar_extinction({'sequence': 'AWAYA'})
    checks.append(('extincion_molar_suma_correcta', ext['extinction_coefficient_reduced'] == 5500 + 1490))

    return {
        'validation_passed': all(c[1] for c in checks),
        'checks': [{'name': c[0], 'passed': c[1]} for c in checks],
    }


AMINOACID_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": [
                "composition", "isoelectric_point", "charge_at_ph",
                "titration_curve", "hydrophobicity", "molar_extinction",
                "sequence_analysis", "peptide_mass", "digestion", "validate",
            ],
            "description": "Modo de operacion de la tool.",
        },
        "sequence": {
            "type": "string",
            "description": "Secuencia de aminoacidos en codigo de una letra "
                            "(mayus/minus, se filtran caracteres invalidos).",
        },
        "pH": {
            "type": "number",
            "description": "Solo charge_at_ph: pH al que se calcula la carga neta.",
        },
        "n_points": {
            "type": "integer",
            "description": "Solo titration_curve: cantidad de puntos de pH entre 0 y 14. Default=71.",
        },
        "window": {
            "type": "integer",
            "description": "Solo hydrophobicity: tamano de ventana deslizante (impar recomendado). Default=9.",
        },
        "assume_all_disulfide": {
            "type": "boolean",
            "description": "Solo molar_extinction: si True, asume que todas las cisteinas forman "
                            "puentes disulfuro (n_cistina = n_cys//2) para el coeficiente oxidado.",
        },
        "detailed": {
            "type": "boolean",
            "description": "Solo composition: si True (default) incluye composicion y frecuencia por residuo.",
        },
    },
    "required": ["mode"],
}


try:
    from tool_registry import register_tool
    register_tool(
        name="aminoacid_tool",
        schema={
            "name": "aminoacid_tool",
            "description": (
                "Analisis de aminoacidos y peptidos a partir de secuencia de una letra: "
                "composicion, peso molecular (promedio y monoisotopico), carga neta y punto "
                "isoelectrico (Henderson-Hasselbalch sobre pKa reales de grupos ionizables, "
                "escala EMBOSS/Lehninger), curva de titulacion, perfil de hidrofobicidad "
                "(Kyte-Doolittle), coeficiente de extincion molar a 280nm (Pace et al. 1995), "
                "y digestion in-silico con tripsina."
            ),
            "inputSchema": AMINOACID_TOOL_SCHEMA,
        },
        handler=lambda args: aminoacid_tool(args.get("mode"), args),
    )
except ImportError:
    pass


if __name__ == '__main__':
    import json
    print(json.dumps(_validate_aminoacid(), indent=2))
