"""
crisprzip_energy_tool.py

Modelo CRISPRzip: energía libre de unión ARN-ADN para predecir eficiencia de corte.
Integra biofísica molecular con predicción de on-target y off-target.

Aplicación: diseño de guías CRISPR, predicción de especificidad.
"""

import numpy as np
import json

# Schema
CRISPRZIP_ENERGY_SCHEMA = {
    "name": "crisprzip_energy_tool",
    "type": "object",
    "description": "CRISPRzip: modelo de energía libre para eficiencia de corte CRISPR-Cas9",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["binding_energy", "cutting_efficiency", "off_target_search", "specificity_score", "validate"],
                "description": "binding_energy: ΔG | cutting_efficiency: predicción | off_target_search: búsqueda | specificity_score: especificidad | validate: self-test"
            },
            "guide_sequence": {
                "type": "string",
                "description": "Secuencia guía ARN (20bp típico)"
            },
            "target_sequence": {
                "type": "string",
                "description": "Secuencia ADN objetivo (incluyendo PAM NGG)"
            },
            "genome_sequence": {
                "type": "string",
                "description": "Secuencia genómica para búsqueda off-target (opcional)"
            },
            "temperature": {
                "type": "number",
                "description": "Temperatura en °C, default 37"
            },
            "cas9_concentration": {
                "type": "number",
                "description": "Concentración de Cas9 en nM, default 100"
            }
        },
        "required": ["mode", "guide_sequence", "target_sequence"]
    }
}

# Parámetros termodinámicos (kcal/mol) para Watson-Crick + wobble
THERMODYNAMIC_PARAMS = {
    "AA": -1.9, "AT": -1.5, "AG": -1.3, "AC": -1.8,
    "TA": -1.6, "TT": -1.9, "TG": -1.5, "TC": -1.3,
    "GA": -1.3, "GT": -1.5, "GG": -2.3, "GC": -2.1,
    "CA": -1.8, "CT": -1.3, "CG": -2.1, "CC": -2.0,
    # Wobble G-U (permitido en CRISPR con penalidad)
    "GU": -1.2, "UG": -1.2
}

def calculate_binding_energy(guide_seq, target_seq, temperature=37):
    """
    Calcula ΔG de unión para ARN guía-ADN objetivo.
    Retorna energía libre (kcal/mol) y melting temperature.
    
    Fórmula simplificada: ΔG = ΔH - T*ΔS
    ΔH: entalpia (suma de stacking + basepairs)
    ΔS: entropía (aproximado)
    """
    # Alinear guía y objetivo
    guide_seq = guide_seq.upper().replace("U", "T")
    target_seq = target_seq.upper()
    
    if len(guide_seq) > len(target_seq):
        return {"error": "Guide longer than target"}
    
    # Calcular entalpia (sum de pares base)
    enthalpy = 0.0
    mismatches = 0
    
    for i in range(len(guide_seq)):
        guide_base = guide_seq[i]
        target_base = target_seq[i]
        
        pair = guide_base + target_base
        if pair in THERMODYNAMIC_PARAMS:
            enthalpy += THERMODYNAMIC_PARAMS[pair]
        else:
            # Mismatch penalidad
            enthalpy -= 2.5  # penalidad fuerte
            mismatches += 1
    
    # Stacking energies (interacción entre pares consecutivos)
    stacking = 0.0
    for i in range(len(guide_seq) - 1):
        # Penalidad general para stacking en mismatches
        if guide_seq[i] != target_seq[i]:
            stacking -= 0.5
    
    enthalpy += stacking
    
    # Entropía (aproximación): -ΔS ≈ 0.017 * len(seq)
    entropy_term = 0.017 * len(guide_seq)
    
    # ΔG = ΔH - T*ΔS (T en Kelvin)
    temp_kelvin = temperature + 273.15
    delta_g = enthalpy - (temp_kelvin * entropy_term)
    
    # Melting temperature (Tm) cuando ΔG = 0
    # ΔG = 0 => T_m = ΔH / ΔS
    if entropy_term > 0:
        tm = enthalpy / entropy_term - 273.15
    else:
        tm = 0
    
    return {
        "guide_sequence": guide_seq,
        "target_sequence": target_seq[:len(guide_seq)],
        "delta_g_kcal_mol": float(delta_g),
        "melting_temperature_c": float(tm),
        "mismatches": mismatches,
        "binding_strength": "Strong" if delta_g < -25 else "Moderate" if delta_g < -15 else "Weak"
    }

def predict_cutting_efficiency(guide_seq, target_seq, temperature=37, cas9_conc=100):
    """
    Predice eficiencia de corte basada en ΔG y concentración de Cas9.
    
    Efficiency = 1 / (1 + K_d / [Cas9])
    donde K_d ∝ exp(ΔG / RT)
    """
    energy = calculate_binding_energy(guide_seq, target_seq, temperature)
    
    if "error" in energy:
        return energy
    
    delta_g = energy["delta_g_kcal_mol"]
    
    # Constante de disociación
    R = 0.00198  # kcal/(mol·K)
    temp_k = temperature + 273.15
    
    # K_d = exp(ΔG / RT)
    try:
        kd = np.exp(delta_g / (R * temp_k))
    except:
        kd = 1e6  # Unión muy débil
    
    # Eficiencia (Hill equation con n=1)
    # Asumiendo [Cas9] disponible
    efficiency = cas9_conc / (kd + cas9_conc)
    efficiency = max(0, min(1, efficiency))  # Clamp [0,1]
    
    return {
        "binding_energy": energy,
        "kd_nm": float(kd),
        "cutting_efficiency": float(efficiency),
        "efficiency_percent": float(efficiency * 100),
        "prediction_confidence": "High" if abs(delta_g) > 20 else "Medium" if abs(delta_g) > 10 else "Low"
    }

def find_off_targets(guide_seq, genome_seq, max_mismatches=3, window_size=20):
    """
    Busca sitios off-target permitiendo hasta max_mismatches.
    """
    guide_seq = guide_seq.upper()
    genome_seq = genome_seq.upper()
    
    off_targets = []
    
    for i in range(len(genome_seq) - window_size + 1):
        window = genome_seq[i:i + window_size]
        
        mismatches = sum(1 for j in range(len(guide_seq)) if guide_seq[j] != window[j])
        
        if mismatches <= max_mismatches:
            off_targets.append({
                "position": i,
                "sequence": window,
                "mismatches": mismatches,
                "energy": calculate_binding_energy(guide_seq, window)["delta_g_kcal_mol"]
            })
    
    # Ordenar por número de mismatches (menos es más probable)
    off_targets.sort(key=lambda x: x["mismatches"])
    
    return {
        "guide_sequence": guide_seq,
        "off_targets_found": len(off_targets),
        "off_targets": off_targets[:10],  # Top 10
        "specificity_risk": "High" if len(off_targets) > 50 else "Medium" if len(off_targets) > 20 else "Low"
    }

def calculate_specificity_score(guide_seq, target_energy, off_target_energies):
    """
    Calcula score de especificidad (0-100).
    Basado en ratio de energía on-target vs off-target.
    """
    if not off_target_energies:
        return 100  # Sin off-targets, score máximo
    
    # Energía promedio de off-targets (menos negativa = peor)
    avg_off_target = np.mean(off_target_energies)
    
    # Ratio on-target / off-target
    # Si on-target es mucho más negativa, ratio bajo, specificity alta
    if avg_off_target != 0:
        energy_ratio = target_energy / avg_off_target
    else:
        energy_ratio = 1
    
    # Especificidad: 100 * (1 - ratio)
    specificity = max(0, min(100, 100 * (1 - energy_ratio)))
    
    return {
        "specificity_score_0_100": float(specificity),
        "on_target_energy": float(target_energy),
        "avg_off_target_energy": float(avg_off_target),
        "specificity_level": "High" if specificity > 80 else "Medium" if specificity > 60 else "Low"
    }

def validate_crisprzip():
    """Validación de self-test."""
    tests = []
    
    # Test 1: Unión perfecta debería ser más negativa que con mismatches
    perfect = calculate_binding_energy("ATGCATGCATGCATGCATGC", "ATGCATGCATGCATGCATGC")
    mismatch = calculate_binding_energy("ATGCATGCATGCATGCATGC", "ATGCATGCATGCTAGCATGC")  # 1 mismatch
    tests.append({
        "name": "Unión perfecta < mismatch (energía más negativa)",
        "passed": int(perfect["delta_g_kcal_mol"] < mismatch["delta_g_kcal_mol"]),
        "perfect_dg": perfect["delta_g_kcal_mol"],
        "mismatch_dg": mismatch["delta_g_kcal_mol"]
    })
    
    # Test 2: Eficiencia debe estar en [0,1]
    eff = predict_cutting_efficiency("ATGCATGCATGCATGCATGC", "ATGCATGCATGCATGCATGC")
    tests.append({
        "name": "Eficiencia en rango [0,1]",
        "passed": int(0 <= eff["cutting_efficiency"] <= 1),
        "efficiency": eff["cutting_efficiency"]
    })
    
    # Test 3: Más mismatches = peor unión
    nomm = calculate_binding_energy("ATGCATGCATGCATGCATGC", "ATGCATGCATGCATGCATGC")  # 0 mm
    onemm = calculate_binding_energy("ATGCATGCATGCATGCATGC", "ATGCATGCATGCTAGCATGC")  # 1 mm
    twomm = calculate_binding_energy("ATGCATGCATGCATGCATGC", "ATGCATGCATGCTAGCTAGC")  # 2 mm
    tests.append({
        "name": "Energía degrada con mismatches: 0mm > 1mm > 2mm",
        "passed": int(nomm["delta_g_kcal_mol"] < onemm["delta_g_kcal_mol"] < twomm["delta_g_kcal_mol"]),
        "nomm": nomm["delta_g_kcal_mol"],
        "onemm": onemm["delta_g_kcal_mol"],
        "twomm": twomm["delta_g_kcal_mol"]
    })
    
    # Test 4: Off-targets sin mismatches debe encontrar sitio idéntico
    genome = "ATGCATGCATGCATGCATGCNNNATGCATGCATGCATGCATGCATGC"
    ot = find_off_targets("ATGCATGCATGCATGCATGC", genome, max_mismatches=0)
    tests.append({
        "name": "Off-target search encuentra sitio idéntico",
        "passed": int(ot["off_targets_found"] >= 2),  # Al menos 2 (inicio + dentro)
        "found": ot["off_targets_found"]
    })
    
    validation_passed = bool(all(t["passed"] for t in tests))
    return {
        "validation_passed": validation_passed,
        "tests": tests,
        "summary": f"{sum(1 for t in tests if t['passed'])}/{len(tests)} passed"
    }

def run_crisprzip_energy_tool(mode, guide_sequence=None, target_sequence=None, genome_sequence=None,
                               temperature=37, cas9_concentration=100):
    """Entry point."""
    try:
        if mode == "validate":
            return validate_crisprzip()
        elif mode == "binding_energy":
            return calculate_binding_energy(guide_sequence, target_sequence, temperature)
        elif mode == "cutting_efficiency":
            return predict_cutting_efficiency(guide_sequence, target_sequence, temperature, cas9_concentration)
        elif mode == "off_target_search":
            return find_off_targets(guide_sequence, genome_sequence or target_sequence)
        elif mode == "specificity_score":
            target_energy = calculate_binding_energy(guide_sequence, target_sequence)["delta_g_kcal_mol"]
            off_targets = find_off_targets(guide_sequence, genome_sequence or target_sequence)
            off_energies = [ot["energy"] for ot in off_targets["off_targets"]]
            return calculate_specificity_score(guide_sequence, target_energy, off_energies)
        else:
            return {"error": f"Unknown mode: {mode}"}
    except Exception as e:
        return {"error": str(e), "validation_passed": False}

if __name__ == "__main__":
    print("=== CRISPRzip Energy Tool ===\n")
    
    # Validate
    print("1. Validation:")
    val = validate_crisprzip()
    print(json.dumps(val, indent=2, ensure_ascii=False))
    
    # Binding energy
    print("\n2. Binding energy (perfect match):")
    be = calculate_binding_energy("ATGCATGCATGCATGCATGC", "ATGCATGCATGCATGCATGC")
    print(f"   ΔG = {be['delta_g_kcal_mol']:.2f} kcal/mol")
    print(f"   Tm = {be['melting_temperature_c']:.1f}°C")
    
    # Cutting efficiency
    print("\n3. Cutting efficiency:")
    ce = predict_cutting_efficiency("ATGCATGCATGCATGCATGC", "ATGCATGCATGCATGCATGC")
    print(f"   Efficiency = {ce['efficiency_percent']:.1f}%")
    
    # Off-target
    print("\n4. Off-target search (1 mismatch allowed):")
    ot = find_off_targets("ATGCATGCATGCATGCATGC", "ATGCATGCATGCATGCATGCNNNATGCATGCATGCTAGCATGC", max_mismatches=1)
    print(f"   Off-targets found: {ot['off_targets_found']}")

try:
    from tool_registry import register_tool
    register_tool(
        name="crisprzip_energy_tool",
        schema=CRISPRZIP_ENERGY_SCHEMA,
        handler=lambda args: run_crisprzip_energy_tool(
            args.get("mode"),
            args.get("guide_sequence"),
            args.get("target_sequence"),
            args.get("genome_sequence"),
            args.get("temperature", 37),
            args.get("cas9_concentration", 100)
        ),
    )
except ImportError:
    pass
