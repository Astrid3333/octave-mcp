# tools/aminoacid_tool.py
"""
aminoacid_tool - Matematicas de aminoacidos y peptidos

Modos:
- composition: Formula, peso molecular y composicion elemental
- isoelectric_point: Punto isoelectrico (pI) de aminoacidos/peptidos
- charge_at_ph: Carga neta a un pH dado
- titration_curve: Curva de titulacion (pH vs. moles de OH-)
- hydrophobicity: Indice de hidrofobicidad (Kyte-Doolittle, Hopp-Woods)
- molar_extinction: Coeficiente de extincion molar (A280)
- sequence_analysis: Analisis de secuencia (frecuencia, masa, cargas)
- peptide_mass: Masa de peptidos (monoisotopica y promedio)
- digestion: Digestion teorica (tripsina, quimotripsina, pepsina, lysc)
- validate: Autoverificacion

Patron de registro: register_tool(TOOL_NAME, _dispatch, modes=TOOL_MODES) al
final del archivo, consistente con ion_chemistry_tool.py y hormone_tool.py.
"""

import re
import numpy as np

TOOL_NAME = "aminoacid_tool"
TOOL_MODES = [
    "composition", "isoelectric_point", "charge_at_ph", "titration_curve",
    "hydrophobicity", "molar_extinction", "sequence_analysis",
    "peptide_mass", "digestion", "validate",
]

# --- Base de datos de aminoacidos ---
AMINO_ACIDS = {
    'A': {'name': 'Alanine', 'formula': 'C3H7NO2', 'mw': 89.09, 'pKa1': 2.34, 'pKa2': 9.69, 'pKaR': None, 'charge': 0, 'hydrophobicity': 1.8},
    'R': {'name': 'Arginine', 'formula': 'C6H14N4O2', 'mw': 174.20, 'pKa1': 2.17, 'pKa2': 9.04, 'pKaR': 12.48, 'charge': 1, 'hydrophobicity': -4.5},
    'N': {'name': 'Asparagine', 'formula': 'C4H8N2O3', 'mw': 132.12, 'pKa1': 2.02, 'pKa2': 8.80, 'pKaR': None, 'charge': 0, 'hydrophobicity': -3.5},
    'D': {'name': 'Aspartic Acid', 'formula': 'C4H7NO4', 'mw': 133.10, 'pKa1': 2.09, 'pKa2': 9.82, 'pKaR': 3.86, 'charge': -1, 'hydrophobicity': -3.5},
    'C': {'name': 'Cysteine', 'formula': 'C3H7NO2S', 'mw': 121.16, 'pKa1': 1.96, 'pKa2': 10.28, 'pKaR': 8.18, 'charge': 0, 'hydrophobicity': 2.5},
    'E': {'name': 'Glutamic Acid', 'formula': 'C5H9NO4', 'mw': 147.13, 'pKa1': 2.19, 'pKa2': 9.67, 'pKaR': 4.25, 'charge': -1, 'hydrophobicity': -3.5},
    'Q': {'name': 'Glutamine', 'formula': 'C5H10N2O3', 'mw': 146.15, 'pKa1': 2.17, 'pKa2': 9.13, 'pKaR': None, 'charge': 0, 'hydrophobicity': -3.5},
    'G': {'name': 'Glycine', 'formula': 'C2H5NO2', 'mw': 75.07, 'pKa1': 2.34, 'pKa2': 9.60, 'pKaR': None, 'charge': 0, 'hydrophobicity': -0.4},
    'H': {'name': 'Histidine', 'formula': 'C6H9N3O2', 'mw': 155.16, 'pKa1': 1.82, 'pKa2': 9.17, 'pKaR': 6.00, 'charge': 0.5, 'hydrophobicity': -3.2},
    'I': {'name': 'Isoleucine', 'formula': 'C6H13NO2', 'mw': 131.17, 'pKa1': 2.36, 'pKa2': 9.60, 'pKaR': None, 'charge': 0, 'hydrophobicity': 4.5},
    'L': {'name': 'Leucine', 'formula': 'C6H13NO2', 'mw': 131.17, 'pKa1': 2.36, 'pKa2': 9.60, 'pKaR': None, 'charge': 0, 'hydrophobicity': 3.8},
    'K': {'name': 'Lysine', 'formula': 'C6H14N2O2', 'mw': 146.19, 'pKa1': 2.18, 'pKa2': 8.95, 'pKaR': 10.53, 'charge': 1, 'hydrophobicity': -3.9},
    'M': {'name': 'Methionine', 'formula': 'C5H11NO2S', 'mw': 149.21, 'pKa1': 2.28, 'pKa2': 9.21, 'pKaR': None, 'charge': 0, 'hydrophobicity': 1.9},
    'F': {'name': 'Phenylalanine', 'formula': 'C9H11NO2', 'mw': 165.19, 'pKa1': 1.83, 'pKa2': 9.13, 'pKaR': None, 'charge': 0, 'hydrophobicity': 2.8},
    'P': {'name': 'Proline', 'formula': 'C5H9NO2', 'mw': 115.13, 'pKa1': 1.99, 'pKa2': 10.60, 'pKaR': None, 'charge': 0, 'hydrophobicity': -1.6},
    'S': {'name': 'Serine', 'formula': 'C3H7NO3', 'mw': 105.09, 'pKa1': 2.21, 'pKa2': 9.15, 'pKaR': None, 'charge': 0, 'hydrophobicity': -0.8},
    'T': {'name': 'Threonine', 'formula': 'C4H9NO3', 'mw': 119.12, 'pKa1': 2.09, 'pKa2': 9.10, 'pKaR': None, 'charge': 0, 'hydrophobicity': -0.7},
    'W': {'name': 'Tryptophan', 'formula': 'C11H12N2O2', 'mw': 204.23, 'pKa1': 2.38, 'pKa2': 9.39, 'pKaR': None, 'charge': 0, 'hydrophobicity': -0.9},
    'Y': {'name': 'Tyrosine', 'formula': 'C9H11NO3', 'mw': 181.19, 'pKa1': 2.20, 'pKa2': 9.11, 'pKaR': 10.07, 'charge': 0, 'hydrophobicity': -1.3},
    'V': {'name': 'Valine', 'formula': 'C5H11NO2', 'mw': 117.15, 'pKa1': 2.32, 'pKa2': 9.62, 'pKaR': None, 'charge': 0, 'hydrophobicity': 4.2},
}

MASS_DATA = {
    'A': (71.03711, 71.0788), 'R': (156.10111, 156.1875),
    'N': (114.04293, 114.1038), 'D': (115.02694, 115.0886),
    'C': (103.00919, 103.1388), 'E': (129.04259, 129.1155),
    'Q': (128.05858, 128.1307), 'G': (57.02146, 57.0519),
    'H': (137.05891, 137.1411), 'I': (113.08406, 113.1594),
    'L': (113.08406, 113.1594), 'K': (128.09496, 128.1741),
    'M': (131.04049, 131.1926), 'F': (147.06841, 147.1766),
    'P': (97.05276, 97.1167), 'S': (87.03203, 87.0782),
    'T': (101.04768, 101.1051), 'W': (186.07931, 186.2132),
    'Y': (163.06333, 163.1760), 'V': (99.06841, 99.1326),
}


def _dispatch(mode=None, **params):
    if mode == 'composition':
        return _aminoacid_composition(params)
    elif mode == 'isoelectric_point':
        return _isoelectric_point(params)
    elif mode == 'charge_at_ph':
        return _charge_at_ph(params)
    elif mode == 'titration_curve':
        return _titration_curve(params)
    elif mode == 'hydrophobicity':
        return _hydrophobicity(params)
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
    return {'error': f'Modo no reconocido: {mode}', 'validation_passed': False}


def _aminoacid_composition(params):
    sequence = params.get('sequence', '').upper()
    detailed = params.get('detailed', False)

    if not sequence:
        return {'error': 'Secuencia vacia', 'validation_passed': False}

    invalid = [aa for aa in sequence if aa not in AMINO_ACIDS]
    if invalid:
        return {'error': f'Aminoacidos no reconocidos: {invalid}', 'validation_passed': False}

    total_mw = sum(AMINO_ACIDS[aa]['mw'] for aa in sequence)
    peptide_bonds = len(sequence) - 1
    total_mw -= peptide_bonds * 18.015

    elements = {'C': 0, 'H': 0, 'N': 0, 'O': 0, 'S': 0}
    pattern = r'([A-Z][a-z]?)(\d*)'
    for aa in sequence:
        formula = AMINO_ACIDS[aa]['formula']
        matches = re.findall(pattern, formula)
        for elem, count in matches:
            if not elem:
                continue
            count = int(count) if count else 1
            elements[elem] = elements.get(elem, 0) + count

    elements['H'] -= peptide_bonds * 2
    elements['O'] -= peptide_bonds

    charge = _calculate_charge(sequence, 7.0)
    hydrophobicity_total = sum(AMINO_ACIDS[aa]['hydrophobicity'] for aa in sequence)
    avg_hydrophobicity = hydrophobicity_total / len(sequence) if sequence else 0

    result = {
        'sequence': sequence,
        'length': len(sequence),
        'molecular_weight': float(total_mw),
        'formula': ''.join([f'{e}{elements[e]}' for e in ['C', 'H', 'N', 'O', 'S'] if elements[e] > 0]),
        'composition': elements,
        'charge_at_ph7': float(charge),
        'avg_hydrophobicity': float(avg_hydrophobicity),
        'validation_passed': True,
    }

    if detailed:
        aa_freq = {}
        for aa in sequence:
            aa_freq[aa] = aa_freq.get(aa, 0) + 1
        result['frequency'] = aa_freq
        result['isoelectric_point'] = _calculate_pI(sequence)

    return result


def _isoelectric_point(params):
    sequence = params.get('sequence', '').upper()
    if not sequence:
        return {'error': 'Secuencia vacia', 'validation_passed': False}
    invalid = [aa for aa in sequence if aa not in AMINO_ACIDS]
    if invalid:
        return {'error': f'Aminoacidos no reconocidos: {invalid}', 'validation_passed': False}

    pI = _calculate_pI(sequence)
    return {
        'sequence': sequence,
        'isoelectric_point': float(pI),
        'charge_at_pI': float(_calculate_charge(sequence, pI)),
        'validation_passed': True,
    }


def _calculate_pI(sequence):
    if len(sequence) == 1:
        aa = sequence[0]
        data = AMINO_ACIDS[aa]
        pKas = [data['pKa1'], data['pKa2']]
        if data['pKaR'] is not None:
            pKas.append(data['pKaR'])
        pKas.sort()
        if len(pKas) == 2:
            return (pKas[0] + pKas[1]) / 2
        elif len(pKas) == 3:
            if data['charge'] == 1:
                return (pKas[1] + pKas[2]) / 2
            else:
                return (pKas[0] + pKas[1]) / 2

    def net_charge(pH):
        return _calculate_charge(sequence, pH)

    pH_values = np.linspace(0, 14, 1400)
    charges = [net_charge(pH) for pH in pH_values]

    pI = None
    for i in range(len(charges) - 1):
        if charges[i] * charges[i + 1] <= 0 and charges[i] != charges[i + 1]:
            pI = pH_values[i] - charges[i] * (pH_values[i + 1] - pH_values[i]) / (charges[i + 1] - charges[i])
            break

    return pI if pI is not None else 7.0


def _calculate_charge(sequence, pH):
    charge = 0.0
    for aa in sequence:
        data = AMINO_ACIDS[aa]
        charge += 1 / (1 + 10 ** (pH - data['pKa2']))
        charge -= 1 / (1 + 10 ** (data['pKa1'] - pH))
        if data['pKaR'] is not None:
            if data['charge'] == 1:
                charge += 1 / (1 + 10 ** (pH - data['pKaR']))
            elif data['charge'] == -1:
                charge -= 1 / (1 + 10 ** (data['pKaR'] - pH))
    return charge


def _charge_at_ph(params):
    sequence = params.get('sequence', '').upper()
    pH = params.get('pH', 7.0)
    if not sequence:
        return {'error': 'Secuencia vacia', 'validation_passed': False}
    invalid = [aa for aa in sequence if aa not in AMINO_ACIDS]
    if invalid:
        return {'error': f'Aminoacidos no reconocidos: {invalid}', 'validation_passed': False}

    charge = _calculate_charge(sequence, pH)
    return {
        'sequence': sequence,
        'pH': float(pH),
        'net_charge': float(charge),
        'charge_type': 'positivo' if charge > 0.5 else 'negativo' if charge < -0.5 else 'neutro',
        'validation_passed': True,
    }


def _titration_curve(params):
    sequence = params.get('sequence', '').upper()
    n_points = params.get('n_points', 100)
    if not sequence:
        return {'error': 'Secuencia vacia', 'validation_passed': False}
    invalid = [aa for aa in sequence if aa not in AMINO_ACIDS]
    if invalid:
        return {'error': f'Aminoacidos no reconocidos: {invalid}', 'validation_passed': False}

    pH_range = np.linspace(0, 14, n_points)
    charges = [_calculate_charge(sequence, pH) for pH in pH_range]

    mid_idx = n_points // 2
    oh_added = np.array(charges) - charges[mid_idx]

    return {
        'sequence': sequence,
        'titration_curve': {'pH': pH_range.tolist(), 'OH_moles': oh_added.tolist()},
        'validation_passed': True,
    }


def _hydrophobicity(params):
    sequence = params.get('sequence', '').upper()
    scale = params.get('scale', 'kyte_doolittle')
    window = params.get('window_size', 7)
    if not sequence:
        return {'error': 'Secuencia vacia', 'validation_passed': False}
    invalid = [aa for aa in sequence if aa not in AMINO_ACIDS]
    if invalid:
        return {'error': f'Aminoacidos no reconocidos: {invalid}', 'validation_passed': False}

    hydrophobicity_scales = {
        'kyte_doolittle': {aa: AMINO_ACIDS[aa]['hydrophobicity'] for aa in AMINO_ACIDS},
        'hopp_woods': {
            'A': 0.3, 'R': -1.8, 'N': -1.6, 'D': -1.6, 'C': 1.0,
            'E': -1.6, 'Q': -1.6, 'G': 0.0, 'H': -0.5, 'I': 1.8,
            'L': 1.8, 'K': -1.8, 'M': 1.3, 'F': 2.1, 'P': -0.2,
            'S': -0.2, 'T': -0.4, 'W': 1.9, 'Y': 1.3, 'V': 1.5,
        },
    }

    scale_data = hydrophobicity_scales.get(scale, hydrophobicity_scales['kyte_doolittle'])
    hydrophobicity_values = [scale_data.get(aa, 0) for aa in sequence]

    window = max(1, min(window, len(sequence)))
    moving_avg = []
    for i in range(len(sequence) - window + 1):
        moving_avg.append(float(np.mean(hydrophobicity_values[i:i + window])))

    return {
        'sequence': sequence,
        'scale': scale,
        'values': hydrophobicity_values,
        'window_size': window,
        'moving_average': moving_avg,
        'overall_hydrophobicity': float(np.mean(hydrophobicity_values)),
        'validation_passed': True,
    }


def _molar_extinction(params):
    sequence = params.get('sequence', '').upper()
    cystine = params.get('cystine', False)
    if not sequence:
        return {'error': 'Secuencia vacia', 'validation_passed': False}
    invalid = [aa for aa in sequence if aa not in AMINO_ACIDS]
    if invalid:
        return {'error': f'Aminoacidos no reconocidos: {invalid}', 'validation_passed': False}

    nW = sequence.count('W')
    nY = sequence.count('Y')
    nC = sequence.count('C')

    if cystine:
        extinction = (nW * 5500) + (nY * 1490) + (nC * 125)
    else:
        extinction = (nW * 5500) + (nY * 1490)

    return {
        'sequence': sequence,
        'extinction_coefficient_280nm': float(extinction),
        'units': 'M-1 cm-1',
        'validation_passed': True,
    }


def _sequence_analysis(params):
    sequence = params.get('sequence', '').upper()
    if not sequence:
        return {'error': 'Secuencia vacia', 'validation_passed': False}
    invalid = [aa for aa in sequence if aa not in AMINO_ACIDS]
    if invalid:
        return {'error': f'Aminoacidos no reconocidos: {invalid}', 'validation_passed': False}

    freq = {}
    for aa in sequence:
        freq[aa] = freq.get(aa, 0) + 1

    total = len(sequence)
    percentages = {aa: (count / total) * 100 for aa, count in freq.items()}

    hydrophobic = sum(AMINO_ACIDS[aa]['hydrophobicity'] > 0 for aa in sequence)
    charged = sum(AMINO_ACIDS[aa]['charge'] != 0 for aa in sequence)
    polar = sum(AMINO_ACIDS[aa]['hydrophobicity'] < 0 for aa in sequence)

    return {
        'sequence': sequence,
        'length': total,
        'frequency': freq,
        'percentages': percentages,
        'hydrophobic_count': hydrophobic,
        'charged_count': charged,
        'polar_count': polar,
        'validation_passed': True,
    }


def _peptide_mass(params):
    sequence = params.get('sequence', '').upper()
    mass_type = params.get('mass_type', 'both')
    if not sequence:
        return {'error': 'Secuencia vacia', 'validation_passed': False}
    invalid = [aa for aa in sequence if aa not in AMINO_ACIDS]
    if invalid:
        return {'error': f'Aminoacidos no reconocidos: {invalid}', 'validation_passed': False}

    mass_mono = sum(MASS_DATA[aa][0] for aa in sequence)
    mass_avg = sum(MASS_DATA[aa][1] for aa in sequence)

    peptide_bonds = len(sequence) - 1
    mass_mono -= peptide_bonds * 18.01056
    mass_avg -= peptide_bonds * 18.01528

    result = {'sequence': sequence, 'monoisotopic_mass': float(mass_mono), 'average_mass': float(mass_avg)}

    if mass_type == 'monoisotopic':
        result.pop('average_mass')
    elif mass_type == 'average':
        result.pop('monoisotopic_mass')

    result['validation_passed'] = True
    return result


def _digestion(params):
    sequence = params.get('sequence', '').upper()
    enzyme = params.get('enzyme', 'trypsin')
    missed = params.get('missed_cleavages', 0)
    if not sequence:
        return {'error': 'Secuencia vacia', 'validation_passed': False}
    invalid = [aa for aa in sequence if aa not in AMINO_ACIDS]
    if invalid:
        return {'error': f'Aminoacidos no reconocidos: {invalid}', 'validation_passed': False}

    cleavage_rules = {
        'trypsin': {'after': ['R', 'K'], 'avoid_before': 'P'},
        'chymotrypsin': {'after': ['F', 'W', 'Y'], 'avoid_before': None},
        'pepsin': {'after': ['F', 'L', 'W', 'Y', 'E', 'Q'], 'avoid_before': None},
        'lysc': {'after': ['K'], 'avoid_before': None},
    }

    rule = cleavage_rules.get(enzyme, cleavage_rules['trypsin'])

    cut_positions = []
    for i, aa in enumerate(sequence):
        if aa in rule['after']:
            if rule['avoid_before']:
                if i < len(sequence) - 1 and sequence[i + 1] == rule['avoid_before']:
                    continue
            cut_positions.append(i + 1)

    peptides = []
    if not cut_positions:
        peptides = [sequence]
    else:
        start = 0
        for pos in cut_positions:
            if start < len(sequence):
                peptides.append(sequence[start:pos])
                start = pos
        if start < len(sequence):
            peptides.append(sequence[start:])

    return {
        'sequence': sequence,
        'enzyme': enzyme,
        'missed_cleavages': missed,
        'peptides': peptides,
        'n_peptides': len(peptides),
        'validation_passed': True,
    }


def _validate_aminoacid():
    checks = []

    # Check 1: Composicion de Alanina (peso molecular conocido)
    comp = _aminoacid_composition({'sequence': 'A'})
    checks.append(('alanine_composition_mw', abs(comp['molecular_weight'] - 89.09) < 0.1))

    # Check 2: pI de Alanina debe caer entre pKa1 y pKa2 (2.34, 9.69)
    pI_ala = _isoelectric_point({'sequence': 'A'})
    checks.append(('alanine_pI_range', 2.34 < pI_ala['isoelectric_point'] < 9.69))

    # Check 3: carga en el pI debe ser ~0
    checks.append(('alanine_pI_zero_charge', abs(pI_ala['charge_at_pI']) < 0.01))

    # Check 4: peptido acido (DE) debe tener carga negativa a pH 7
    charge_de = _charge_at_ph({'sequence': 'DE', 'pH': 7.0})
    checks.append(('DE_charge_negative_at_ph7', charge_de['net_charge'] < -1))

    # Check 5: peptido basico (KR) debe tener carga positiva a pH 7
    charge_kr = _charge_at_ph({'sequence': 'KR', 'pH': 7.0})
    checks.append(('KR_charge_positive_at_ph7', charge_kr['net_charge'] > 1))

    # Check 6: extincion molar de un Trp solo debe ser 5500
    ext_w = _molar_extinction({'sequence': 'W'})
    checks.append(('single_trp_extinction', abs(ext_w['extinction_coefficient_280nm'] - 5500) < 1e-6))

    # Check 7: digestion tripsina de 'AKAR' corta despues de K y R -> AK, AR
    dig = _digestion({'sequence': 'AKAR', 'enzyme': 'trypsin'})
    checks.append(('trypsin_AKAR_cuts', dig['peptides'] == ['AK', 'AR']))

    # Check 8: tripsina NO corta antes de Prolina (regla avoid_before)
    dig_p = _digestion({'sequence': 'AKPAR', 'enzyme': 'trypsin'})
    checks.append(('trypsin_avoids_before_proline', 'AKP' in ''.join(dig_p['peptides']) and dig_p['peptides'][0] != 'AK'))

    # Check 9: masa peptidica de un solo residuo == su masa monoisotopica de tabla (sin restar agua)
    mass_a = _peptide_mass({'sequence': 'A'})
    checks.append(('single_residue_mass_no_water_subtracted', abs(mass_a['monoisotopic_mass'] - MASS_DATA['A'][0]) < 1e-6))

    # Check 10: composicion elemental de Glicina (C2H5NO2) coincide con formula
    comp_g = _aminoacid_composition({'sequence': 'G'})
    checks.append(('glycine_elements', comp_g['composition']['C'] == 2 and comp_g['composition']['N'] == 1 and comp_g['composition']['O'] == 2))

    return {
        'validation_passed': all(c[1] for c in checks),
        'checks': [{'name': c[0], 'passed': c[1]} for c in checks],
    }


try:
    from tool_registry import register_tool
    register_tool(TOOL_NAME, _dispatch, modes=TOOL_MODES)
except ImportError:
    pass
