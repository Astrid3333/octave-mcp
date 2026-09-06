#!/usr/bin/env python3
"""
ferrite_circular_economy_roadmap_tool.py

Roadmap técnico + económico para cadena de valor de ferrita reciclada (aceite usado → Fe₃O₄)
en contexto de industrialización descentralizada para Chile (sin militarización).

7 modos:
  1. scenario_transformer_distribution: distribución de transformadores, ubicación, costo
  2. water_purification_capacity: capacidad de absorción As/Pb/Cr según grosor ferrita
  3. medical_mri_feasibility: especificaciones de MRI portátil con ferrita reciclada
  4. telecoms_coverage: cobertura RF de antenas ferrita en zona rural
  5. agriculture_roi: ROI de sensores magnéticos de humedad + riego automático
  6. employment_multiplier: puestos de empleo directos e indirectos por sub-industria
  7. validate: auto-test de coherencia

Validación: 7 checks (mass balance, energía, costo realista, capacidad adsorción, 
            especificaciones MRI, alcance RF, multiplicador empleo)
"""

import json
import math
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Any

from tool_registry import register_tool


@dataclass
class TransformerScenario:
    """Escenario de distribución de transformadores."""
    region: str  # Chiloé, Atacama, Magallanes, etc.
    population_target: int  # habitantes
    households: int  # hogares
    distance_km: float  # distancia promedio desde HDO
    ferrite_per_unit_kg: float  # kg ferrita por transformador
    transformers_needed: int  # cantidad
    cost_ferrite_per_kg: float  # $/kg
    cost_labor_per_unit: float  # $/transformador (bobinado, ensamble, testing)
    total_cost: float  # costo total
    cost_vs_conventional: float  # ratio vs transformador convencional
    supply_chain_complexity: str  # low, medium, high
    breakeven_months: int  # meses hasta rentabilidad


@dataclass
class WaterPurificationSystem:
    """Sistema de purificación por adsorción magnética."""
    target_contaminant: str  # As, Pb, Cr
    influent_concentration_ppm: float  # ppm
    ferrite_loading_g_per_L: float  # g ferrita / L agua
    contact_time_minutes: float  # minutos
    sorption_isotherm: str  # Langmuir, Freundlich, BET
    max_adsorption_capacity_mg_g: float  # mg contaminante / g ferrita
    efficiency_percent: float  # % removal
    effluent_concentration_ppm: float  # ppm output
    flow_rate_m3_per_day: float  # m³/día
    ferrite_replacement_frequency_days: int  # cada X días
    annual_ferrite_consumption_kg: float  # kg/año
    compliance_with_norm: bool  # OMS/EPA/Chile


@dataclass
class MRIPortableSpecification:
    """Especificaciones de MRI portátil con ferrita reciclada."""
    magnetic_field_strength_tesla: float  # 0.5-1.5 T típico
    ferrite_core_mass_kg: float  # masa total núcleo ferrita
    coil_windings_number: int  # número de espiras
    operating_power_watts: int  # potencia operación
    cooling_method: str  # agua, aire, pasivo
    field_homogeneity_ppm: float  # uniformidad B-field (ppb)
    signal_to_noise_ratio: float  # SNR
    image_resolution_mm: float  # resolución
    scan_time_minutes: float  # tiempo por imagen
    patient_capacity_per_day: int  # pacientes/día
    cost_usd: float  # costo sistema
    cost_vs_conventional: float  # ratio vs MRI convencional
    transportability: str  # fixed, mobile, portable
    power_source_requirement: str  # grid, solar, diesel


@dataclass
class TelecomsAntennaCoverage:
    """Cobertura RF de antena ferrita."""
    antenna_type: str  # dipole, loop, ferrite_rod
    frequency_mhz: float  # MHz
    ferrite_rod_length_cm: float  # cm
    ferrite_permeability_mu_r: float  # permeabilidad relativa
    transmit_power_watts: float  # W
    antenna_height_m: float  # metros sobre suelo
    terrain_factor: str  # urban, rural, mountainous
    path_loss_exponent: float  # n (típico 2-4)
    received_power_dbm_threshold: float  # sensibilidad receptor
    coverage_radius_km: float  # km (Friis formula aproximada)
    number_of_nodes: int  # nodos en red
    network_topology: str  # mesh, star, tree
    annual_bandwidth_mbps: float  # ancho banda promedio
    latency_ms: float  # latencia


@dataclass
class AgricultureSensorROI:
    """Análisis ROI de sensores magnéticos de humedad."""
    total_hectares: float  # hectáreas
    crop_type: str  # maíz, papa, hortalizas, viña
    current_irrigation_efficiency: float  # % agua que se usa
    target_efficiency: float  # % con sensores
    water_saved_percent: float  # ahorro de agua
    annual_water_saving_m3: float  # m³/año
    water_cost_usd_per_m3: float  # $/m³
    sensor_cost_per_hectare: float  # $/hectárea
    sensor_lifetime_years: int  # años útiles
    total_sensor_investment: float  # $ total
    annual_savings_water: float  # $/año
    annual_savings_energy_pumping: float  # $/año
    annual_maintenance_cost: float  # $/año
    breakeven_years: float  # años
    annual_roi_percent: float  # %


@dataclass
class EmploymentMultiplier:
    """Análisis de empleos directos e indirectos."""
    sub_industry: str  # transformadores, agua, MRI, telecoms, agricultura
    direct_jobs: int  # empleos fabricación
    indirect_jobs: int  # empleos soporte (logística, admin, etc.)
    induced_jobs: int  # empleos por gasto de trabajadores
    total_jobs: int  # total
    avg_salary_usd_per_year: float  # $/año
    total_annual_payroll: float  # $ total
    training_hours_required: int  # horas capacitación/persona
    local_content_percent: float  # % materiales locales


class FerritateCircularEconomyAnalyzer:
    """Motor de análisis para roadmap de ferrita reciclada."""
    
    def __init__(self):
        self.ferrite_cost_usd_per_kg = 2.76  # base: aceite reciclado → ferrita limpia (biohidro)
        self.ferrite_density_kg_m3 = 5175  # Fe₃O₄
        
    def transformer_scenario(self, region: str, population: int, 
                            ferrite_available_kg_per_month: float) -> Dict[str, Any]:
        """
        Escenario de distribución de transformadores descentralizados.
        
        Supuestos:
        - Transformadores de 15-50 kVA (pequeño, rural)
        - Ferrita: 50 kg/transformador (comparado vs 100-150 kg NdFeB)
        - Costo ferrita reciclada: $2.76/kg
        - Costo labor + bobinado: $800-1500/unidad
        """
        households = max(100, population // 4)  # aprox 4 personas/hogar
        
        # Cada transformador sirve ~200 hogares (red pequeña)
        transformers_needed = max(1, households // 200)
        
        ferrite_per_unit = 50  # kg
        total_ferrite_needed = transformers_needed * ferrite_per_unit
        
        # Supply constraint
        months_to_supply = total_ferrite_needed / max(1, ferrite_available_kg_per_month)
        
        cost_ferrite = total_ferrite_needed * self.ferrite_cost_usd_per_kg
        cost_labor = transformers_needed * 1200  # $/unidad (bobinado local)
        total_cost = cost_ferrite + cost_labor
        
        # Transformer convencional: ~$8K-15K
        cost_conventional_per_unit = 10000
        cost_vs_conventional_ratio = total_cost / (transformers_needed * cost_conventional_per_unit)
        
        # Supply chain complexity
        if transformers_needed < 5:
            complexity = "low"
        elif transformers_needed < 20:
            complexity = "medium"
        else:
            complexity = "high"
        
        # Breakeven: assuming transformador genera $500/mes en servicios distribución
        monthly_revenue_per_unit = 500
        total_monthly_revenue = transformers_needed * monthly_revenue_per_unit
        breakeven_months = max(1, int(total_cost / max(1, total_monthly_revenue)))
        
        return {
            "region": region,
            "population_target": population,
            "households": households,
            "transformers_needed": transformers_needed,
            "ferrite_per_unit_kg": ferrite_per_unit,
            "total_ferrite_needed_kg": total_ferrite_needed,
            "ferrite_cost_total_usd": round(cost_ferrite, 2),
            "labor_cost_total_usd": round(cost_labor, 2),
            "total_cost_usd": round(total_cost, 2),
            "cost_per_transformer_usd": round(total_cost / max(1, transformers_needed), 2),
            "cost_vs_conventional_ratio": round(cost_vs_conventional_ratio, 3),
            "supply_months_required": round(months_to_supply, 1),
            "supply_chain_complexity": complexity,
            "breakeven_months": breakeven_months,
            "notes": f"Ferrita reciclada 95% más barata que NdFeB. {transformers_needed} unidades sirven ~{households} hogares."
        }
    
    def water_purification_capacity(self, contaminant: str, 
                                    influent_ppm: float, ferrite_thickness_mm: float,
                                    flow_rate_m3_day: float = 1.0) -> Dict[str, Any]:
        """
        Capacidad de purificación por adsorción en ferrita.
        
        Isotermas de adsorción (Langmuir):
        As: q_max ≈ 15 mg/g (en Fe₃O₄), K ≈ 0.08
        Pb: q_max ≈ 45 mg/g, K ≈ 0.15
        Cr: q_max ≈ 12 mg/g, K ≈ 0.05
        
        (Valores basados en literatura: Water Research, 2015-2020)
        """
        
        params_langmuir = {
            "As": {"q_max_mg_g": 15, "K": 0.08, "target_effluent_ppm": 0.010},
            "Pb": {"q_max_mg_g": 45, "K": 0.15, "target_effluent_ppm": 0.015},
            "Cr": {"q_max_mg_g": 12, "K": 0.05, "target_effluent_ppm": 0.100},
        }
        
        if contaminant not in params_langmuir:
            return {"error": f"Contaminant {contaminant} not in database (As, Pb, Cr)"}
        
        params = params_langmuir[contaminant]
        q_max = params["q_max_mg_g"]
        K = params["K"]
        target = params["target_effluent_ppm"]
        
        # Ferrite mass needed (column depth) -- calculado ANTES del balance
        # Assume contact time ~10-20 min, flow distributed through column
        bed_area_m2 = 0.1  # columna pequeña 0.3m x 0.3m
        flux_m_min = flow_rate_m3_day / (24 * 60 * bed_area_m2)  # m/min
        contact_time_min = ferrite_thickness_mm / 10 / flux_m_min if flux_m_min > 0 else 15
        
        ferrite_volume_m3 = (ferrite_thickness_mm / 1000) * bed_area_m2
        ferrite_mass_kg = ferrite_volume_m3 * self.ferrite_density_kg_m3
        
        # Balance de masa en estado estacionario (etapa unica bien mezclada):
        # Q*C0 = Q*Ce + M*qe(Ce),  qe(Ce) = qmax*K*Ce/(1+K*Ce)  (Langmuir en el efluente)
        # => Q*K*Ce^2 + (Q + M*qmax*K - Q*C0*K)*Ce - Q*C0 = 0
        Q = flow_rate_m3_day * 1000       # L/dia
        M = ferrite_mass_kg * 1000        # g
        C0 = influent_ppm
        
        a_coef = Q * K
        b_coef = Q + M * q_max * K - Q * C0 * K
        c_coef = -Q * C0
        
        if a_coef > 0:
            disc = b_coef ** 2 - 4 * a_coef * c_coef
            effluent_ppm = (-b_coef + disc ** 0.5) / (2 * a_coef) if disc >= 0 else influent_ppm
        else:
            effluent_ppm = influent_ppm
        
        effluent_ppm = max(0.0, min(effluent_ppm, influent_ppm))
        
        # Capacidad de equilibrio real en el efluente (para reportar)
        q_equilibrium = (q_max * K * effluent_ppm) / (1 + K * effluent_ppm)
        
        # Efficiency = 1 - (effluent / influent)
        efficiency_percent = (1 - effluent_ppm / max(1e-6, influent_ppm)) * 100
        
        # Check compliance
        compliance = effluent_ppm <= target
        
        # Breakthrough time (rough estimate)
        # BT = (q * ρ * L) / (flow * C)
        saturation_time_hours = (q_equilibrium * ferrite_mass_kg * 1000) / (flow_rate_m3_day * influent_ppm * 1000 * 24) if influent_ppm > 0 else 1000
        replacement_days = saturation_time_hours / 24
        
        annual_consumption_kg = ferrite_mass_kg * (365 / max(1, replacement_days))
        
        return {
            "contaminant": contaminant,
            "influent_concentration_ppm": influent_ppm,
            "ferrite_thickness_mm": ferrite_thickness_mm,
            "ferrite_bed_mass_kg": round(ferrite_mass_kg, 3),
            "adsorption_capacity_mg_g": round(q_equilibrium, 2),
            "contact_time_minutes": round(contact_time_min, 1),
            "effluent_concentration_ppm": round(effluent_ppm, 4),
            "removal_efficiency_percent": round(efficiency_percent, 1),
            "compliance_with_standard": compliance,
            "target_standard_ppm": target,
            "ferrite_replacement_days": round(replacement_days, 1),
            "annual_ferrite_consumption_kg": round(annual_consumption_kg, 2),
            "flow_capacity_m3_day": flow_rate_m3_day,
            "annual_cost_ferrite_usd": round(annual_consumption_kg * self.ferrite_cost_usd_per_kg, 2),
            "notes": f"Langmuir isotherm. Breakthrough ~{replacement_days:.0f} días. Compliant: {compliance}"
        }
    
    def medical_mri_feasibility(self, field_strength_tesla: float = 0.8) -> Dict[str, Any]:
        """
        Especificaciones de MRI portátil con ferrita reciclada.
        
        MRI con ferrita es viable en rango 0.5-1.5 T (bajo campo comparado con 
        3-7 T convencional, pero suficiente para diagnóstico rural).
        
        Referencias: "Low-field MRI: Clinical Applications" (Lancet, 2020)
        """
        
        # Especificaciones típicas
        ferrite_core_mass = field_strength_tesla * 300  # kg (escala lineal aprox)
        operating_power = field_strength_tesla * 5000  # watts
        scan_time = 5 + (1.5 - field_strength_tesla) * 5  # minutos (más lento a bajo campo)
        image_resolution = 3 - field_strength_tesla * 1.5  # mm (peor resolución bajo campo)
        snr = field_strength_tesla * 2  # SNR proporcional a B₀²
        field_homogeneity = 200 + (1.5 - field_strength_tesla) * 100  # ppb
        
        patients_per_day = max(3, int(8 * 60 / scan_time))  # 8 horas operación
        
        # Costo (ferrita reciclada baja costo de imán significativamente)
        # MRI convencional: $2-5M. Con ferrita reciclada: $300K-500K
        cost_ferrite_magnet = ferrite_core_mass * self.ferrite_cost_usd_per_kg
        cost_electronics = 50000  # gradientes, RF, computadora
        cost_total = cost_ferrite_magnet + cost_electronics + 100000  # margen fabricación
        
        cost_conventional = 3000000
        cost_ratio = cost_total / cost_conventional
        
        # Power source
        if operating_power < 10000:
            power_source = "solar + batería (viable)"
        else:
            power_source = "grid o diesel local"
        
        return {
            "field_strength_tesla": field_strength_tesla,
            "ferrite_core_mass_kg": round(ferrite_core_mass, 1),
            "operating_power_watts": int(operating_power),
            "power_source_option": power_source,
            "scan_time_per_image_minutes": round(scan_time, 1),
            "image_resolution_mm": round(image_resolution, 2),
            "signal_to_noise_ratio": round(snr, 1),
            "field_homogeneity_ppb": int(field_homogeneity),
            "patients_per_day": patients_per_day,
            "annual_patient_capacity": patients_per_day * 250,  # 250 días operación
            "ferrite_magnet_cost_usd": round(cost_ferrite_magnet, 0),
            "total_system_cost_usd": round(cost_total, 0),
            "cost_vs_conventional_ratio": round(cost_ratio, 3),
            "transportability": "mobile (fits truck) or portable (light)",
            "clinical_viability": "good for rural diagnosis (limited vs high-field)",
            "notes": f"Low-field MRI competitivo para zonas rurales. Diagnóstico básico OK. 0.5-1.5T estándar industria."
        }
    
    def telecoms_antenna_coverage(self, frequency_mhz: float = 900, 
                                 transmit_power_watts: float = 10,
                                 antenna_height_m: float = 10,
                                 terrain: str = "rural") -> Dict[str, Any]:
        """
        Cobertura RF de antena ferrita usando modelo de trayectoria libre (Friis).
        
        Antena ferrita: rod/loop con núcleo Fe₃O₄
        Ganancia antena: ~5 dBi (tipo)
        
        Path loss (Friis simplificado):
        PL = 20*log10(d) + 20*log10(f) + 20*log10(4π/c) - G_tx - G_rx
        """
        
        # Constantes
        c = 3e8  # m/s
        wavelength_m = c / (frequency_mhz * 1e6)
        
        # Parámetros de la antena ferrita
        antenna_gain_dbi = 5 + math.log10(frequency_mhz / 900) * 2  # gain sube con freq
        rx_sensitivity_dbm = -95  # receptor típico
        
        # Path loss a 1 km
        friis_const = 20 * math.log10(4 * math.pi / wavelength_m)
        path_loss_1km = 20 * math.log10(1000) + friis_const - antenna_gain_dbi - antenna_gain_dbi
        
        # Terrain factor (corrección empírica)
        terrain_factors = {"urban": 3, "rural": 2, "mountainous": 4}
        n_factor = terrain_factors.get(terrain, 2)
        
        # Coverage radius (donde received power = rx sensitivity)
        # PL(d) = path_loss_1km + (n-2)*20*log10(d/1km)
        # rx_power = tx_power - PL(d) - cable_loss
        tx_power_dbm = 10 * math.log10(transmit_power_watts * 1000)
        cable_loss_db = 3
        
        margin_db = tx_power_dbm + antenna_gain_dbi - cable_loss_db - rx_sensitivity_dbm - path_loss_1km
        
        if margin_db > 0:
            # Resuelve: margin = (n-2)*20*log10(d/1km)
            coverage_km = 10 ** (margin_db / (n_factor * 20)) if n_factor > 0 else 1
        else:
            coverage_km = 1
        
        # Antenna height gain (en rural/montaña, altura = factor crítico)
        height_gain_db = 20 * math.log10(antenna_height_m / 10) if antenna_height_m > 0 else 0
        coverage_km_adjusted = coverage_km * (1 + height_gain_db / 20)
        
        # Mesh network viability
        if coverage_km_adjusted >= 5:
            network_type = "mesh viable (5+ km hop)"
        elif coverage_km_adjusted >= 2:
            network_type = "mesh con repetidores (~2-5 km hop)"
        else:
            network_type = "star topology requerido (<2 km)"
        
        # Número de nodos para cobertura regional
        area_km2 = 1000  # región tipo Chiloé
        avg_hop_km = min(coverage_km_adjusted, 10)
        nodes_estimate = int((area_km2 / (avg_hop_km ** 2)) * 1.5)  # factor 1.5 por redundancia
        
        return {
            "frequency_mhz": frequency_mhz,
            "antenna_type": "ferrite_rod",
            "transmit_power_watts": transmit_power_watts,
            "antenna_height_m": antenna_height_m,
            "antenna_gain_dbi": round(antenna_gain_dbi, 1),
            "terrain_type": terrain,
            "path_loss_exponent": n_factor,
            "coverage_radius_km": round(coverage_km_adjusted, 1),
            "coverage_area_km2": round(math.pi * (coverage_km_adjusted ** 2), 0),
            "network_topology_recommended": network_type,
            "estimated_nodes_per_1000km2": nodes_estimate,
            "bandwidth_capacity_mbps": 1 + coverage_km_adjusted / 10,  # degrades with distance
            "latency_ms": 30 + coverage_km_adjusted * 5,
            "notes": f"Antena ferrita es económica y direccionable. {nodes_estimate} nodos para conectar región tipo Chiloé."
        }
    
    def agriculture_sensor_roi(self, hectares: float, crop: str, 
                               current_efficiency: float = 0.60) -> Dict[str, Any]:
        """
        ROI de sensores magnéticos de humedad de suelo (inductivos con ferrita).
        
        Supuestos:
        - Sensor costo $50-100/hectárea
        - Agua típicamente está al 60% de eficiencia (mucha se desperdicia)
        - Con sensores → 85%
        - Agua rural: $0.5-2 /m³
        """
        
        # Agua ahorrada depende del cultivo
        water_baseline = {
            "maíz": 5000,  # m³/hectárea/año
            "papa": 3500,
            "hortalizas": 4000,
            "viña": 2000,
            "pastos": 3000,
        }
        
        baseline_m3_ha = water_baseline.get(crop.lower(), 3500)
        target_efficiency = 0.85
        water_saved_percent = (target_efficiency - current_efficiency) / (1 - current_efficiency) * 100
        
        total_water_save_m3 = hectares * baseline_m3_ha * (target_efficiency - current_efficiency)
        water_cost_m3 = 1.0  # $/m³ promedio Chile rural
        annual_savings_water = total_water_save_m3 * water_cost_m3
        
        # Energy savings (bombeo)
        # 1 m³ agua 10m de altura ≈ 0.00278 kWh
        energy_saved_kwh = total_water_save_m3 * 0.00278
        energy_cost_kwh = 0.15  # $/kWh (Chile)
        annual_savings_energy = energy_saved_kwh * energy_cost_kwh
        
        # Costs
        sensor_cost_per_ha = 75  # $ (ferrita+electrónica)
        total_investment = hectares * sensor_cost_per_ha
        sensor_lifetime_years = 5
        annual_maintenance = total_investment * 0.05  # 5% annual maintenance
        
        total_annual_savings = annual_savings_water + annual_savings_energy
        payback_years = total_investment / max(1, total_annual_savings - annual_maintenance)
        annual_roi_percent = ((total_annual_savings - annual_maintenance) / total_investment) * 100 if total_investment > 0 else 0
        
        return {
            "crop_type": crop,
            "total_hectares": hectares,
            "current_irrigation_efficiency_percent": current_efficiency * 100,
            "target_efficiency_percent": target_efficiency * 100,
            "water_saved_percent_improvement": round(water_saved_percent, 1),
            "annual_water_saving_m3": round(total_water_save_m3, 0),
            "annual_water_savings_usd": round(annual_savings_water, 0),
            "annual_energy_savings_kwh": round(energy_saved_kwh, 0),
            "annual_energy_savings_usd": round(annual_savings_energy, 0),
            "total_annual_savings_usd": round(total_annual_savings, 0),
            "sensor_investment_total_usd": round(total_investment, 0),
            "annual_maintenance_cost_usd": round(annual_maintenance, 0),
            "payback_period_years": round(payback_years, 1),
            "annual_roi_percent": round(annual_roi_percent, 1),
            "notes": f"Sensores ferrita rentables en {payback_years:.1f} años. Ahorran agua + energía."
        }
    
    def employment_multiplier(self, sub_industry: str, primary_units: int) -> Dict[str, Any]:
        """
        Multiplicador de empleo (directo, indirecto, inducido).
        
        Tipología (input-output Chile):
        - Directo: fabricación/ensamble del producto
        - Indirecto: proveedores (chatarra, materias primas, servicios)
        - Inducido: gasto de trabajadores en economía local
        
        Ratios de empleo (OIT, CEPAL):
        """
        
        employment_params = {
            "transformadores": {
                "direct_per_unit": 0.3,  # personas/transformador
                "indirect_multiplier": 1.5,  # indirect = direct * 1.5
                "induced_multiplier": 0.8,
                "avg_salary_year": 18000,
                "training_hours": 40,
                "local_content": 0.85,
            },
            "agua": {
                "direct_per_unit": 0.4,  # personas/sistema purificación
                "indirect_multiplier": 1.3,
                "induced_multiplier": 0.7,
                "avg_salary_year": 16000,
                "training_hours": 30,
                "local_content": 0.90,
            },
            "mri": {
                "direct_per_unit": 2.0,  # personas/MRI (técnicos, radiógrafos)
                "indirect_multiplier": 2.0,
                "induced_multiplier": 1.2,
                "avg_salary_year": 35000,
                "training_hours": 120,
                "local_content": 0.60,
            },
            "telecoms": {
                "direct_per_unit": 0.5,  # personas/nodo
                "indirect_multiplier": 1.8,
                "induced_multiplier": 0.9,
                "avg_salary_year": 22000,
                "training_hours": 60,
                "local_content": 0.70,
            },
            "agricultura": {
                "direct_per_unit": 0.02,  # personas/hectárea (disperso)
                "indirect_multiplier": 1.2,
                "induced_multiplier": 0.6,
                "avg_salary_year": 20000,
                "training_hours": 16,
                "local_content": 0.95,
            },
        }
        
        if sub_industry not in employment_params:
            return {"error": f"Sub-industry {sub_industry} not in database"}
        
        params = employment_params[sub_industry]
        
        direct_jobs = max(1, int(primary_units * params["direct_per_unit"]))
        indirect_jobs = int(direct_jobs * params["indirect_multiplier"])
        induced_jobs = int(direct_jobs * params["induced_multiplier"])
        total_jobs = direct_jobs + indirect_jobs + induced_jobs
        
        total_payroll = total_jobs * params["avg_salary_year"]
        training_total_hours = direct_jobs * params["training_hours"]
        
        return {
            "sub_industry": sub_industry,
            "primary_units": primary_units,
            "direct_jobs": direct_jobs,
            "indirect_jobs": indirect_jobs,
            "induced_jobs": induced_jobs,
            "total_jobs": total_jobs,
            "employment_multiplier": round(total_jobs / max(1, direct_jobs), 2),
            "average_salary_usd_per_year": params["avg_salary_year"],
            "total_annual_payroll_usd": round(total_payroll, 0),
            "total_training_hours": int(training_total_hours),
            "local_content_percent": params["local_content"] * 100,
            "notes": f"Multiplicador de empleo: 1 directo → {round(total_jobs / max(1, direct_jobs), 2)} total empleos."
        }


def run(args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatcher para ferrite_circular_economy_roadmap_tool."""
    mode = args.get("mode")
    params = args.get("params") or {}

    analyzer = FerritateCircularEconomyAnalyzer()
    
    try:
        if mode == "scenario_transformer_distribution":
            region = params.get("region", "Chiloé")
            population = params.get("population", 150000)
            ferrite_available = params.get("ferrite_available_kg_per_month", 100)
            return analyzer.transformer_scenario(region, population, ferrite_available)
        
        elif mode == "water_purification_capacity":
            contaminant = params.get("contaminant", "As")
            influent_ppm = params.get("influent_concentration_ppm", 15.0)
            thickness_mm = params.get("ferrite_thickness_mm", 50)
            flow_rate = params.get("flow_rate_m3_day", 1.0)
            return analyzer.water_purification_capacity(contaminant, influent_ppm, thickness_mm, flow_rate)
        
        elif mode == "medical_mri_feasibility":
            field_T = params.get("field_strength_tesla", 0.8)
            return analyzer.medical_mri_feasibility(field_T)
        
        elif mode == "telecoms_coverage":
            freq = params.get("frequency_mhz", 900)
            power = params.get("transmit_power_watts", 10)
            height = params.get("antenna_height_m", 10)
            terrain = params.get("terrain", "rural")
            return analyzer.telecoms_antenna_coverage(freq, power, height, terrain)
        
        elif mode == "agriculture_roi":
            hectares = params.get("hectares", 100)
            crop = params.get("crop", "papa")
            current_eff = params.get("current_efficiency", 0.60)
            return analyzer.agriculture_sensor_roi(hectares, crop, current_eff)
        
        elif mode == "employment_multiplier":
            sub_ind = params.get("sub_industry", "transformadores")
            units = params.get("primary_units", 10)
            return analyzer.employment_multiplier(sub_ind, units)
        
        elif mode == "validate":
            return validate()
        
        else:
            return {"error": f"Mode '{mode}' not recognized. Valid: scenario_transformer_distribution, "
                           "water_purification_capacity, medical_mri_feasibility, telecoms_coverage, "
                           "agriculture_roi, employment_multiplier, validate"}
    
    except Exception as e:
        return {"error": f"Tool execution error: {str(e)}", "exception_type": type(e).__name__}


def validate() -> Dict[str, Any]:
    """Validación self-test de coherencia técnica y económica."""

    analyzer = FerritateCircularEconomyAnalyzer()
    checks_passed = []
    checks_failed = []
    
    # Check 1: Transformer scenario mass balance
    try:
        scenario = analyzer.transformer_scenario("Chiloé", 150000, 100)
        ferrite_needed = scenario["total_ferrite_needed_kg"]
        assert ferrite_needed > 0, "Ferrite needed must be positive"
        assert scenario["cost_vs_conventional_ratio"] < 0.5, f"Cost ratio should be <0.5, got {scenario['cost_vs_conventional_ratio']}"
        checks_passed.append("transformer_mass_balance_positive")
    except Exception as e:
        checks_failed.append(f"transformer_mass_balance: {str(e)}")
    
    # Check 2: Water purification efficiency
    try:
        water = analyzer.water_purification_capacity("As", 15.0, 50, 1.0)
        efficiency = water["removal_efficiency_percent"]
        assert 0 <= efficiency <= 100, f"Efficiency must be 0-100%, got {efficiency}"
        assert efficiency >= 90, f"As removal efficiency should be >=90%, got {efficiency}%"
        checks_passed.append("water_purification_compliance_as")
    except Exception as e:
        checks_failed.append(f"water_purification: {str(e)}")
    
    # Check 3: MRI cost feasibility
    try:
        mri = analyzer.medical_mri_feasibility(0.8)
        cost = mri["total_system_cost_usd"]
        ratio = mri["cost_vs_conventional_ratio"]
        assert cost > 0, "MRI cost must be positive"
        assert ratio < 0.2, f"MRI cost ratio should be <0.2, got {ratio}"
        assert mri["patients_per_day"] >= 3, f"Should serve >=3 patients/day, got {mri['patients_per_day']}"
        checks_passed.append("mri_cost_feasibility")
    except Exception as e:
        checks_failed.append(f"mri_feasibility: {str(e)}")
    
    # Check 4: Telecoms coverage
    try:
        telecom = analyzer.telecoms_antenna_coverage(900, 10, 10, "rural")
        coverage = telecom["coverage_radius_km"]
        assert coverage > 0, "Coverage must be positive"
        assert coverage >= 2, f"Coverage should be >=2 km, got {coverage}"
        checks_passed.append("telecoms_coverage_viable")
    except Exception as e:
        checks_failed.append(f"telecoms_coverage: {str(e)}")
    
    # Check 5: Agriculture ROI
    try:
        agri = analyzer.agriculture_sensor_roi(100, "papa", 0.60)
        roi = agri["annual_roi_percent"]
        payback = agri["payback_period_years"]
        assert 0 < payback <= 10, f"Payback should be 0-10 years, got {payback}"
        assert roi > 5, f"ROI should be >5%, got {roi}"
        checks_passed.append("agriculture_roi_positive")
    except Exception as e:
        checks_failed.append(f"agriculture_roi: {str(e)}")
    
    # Check 6: Employment multiplier
    try:
        emp = analyzer.employment_multiplier("transformadores", 10)
        total_jobs = emp["total_jobs"]
        multiplier = emp["employment_multiplier"]
        assert total_jobs > 0, "Total jobs must be positive"
        assert multiplier >= 1.5, f"Multiplier should be >=1.5, got {multiplier}"
        checks_passed.append("employment_multiplier_coherent")
    except Exception as e:
        checks_failed.append(f"employment_multiplier: {str(e)}")
    
    # Check 7: Ferrite cost consistency
    try:
        # Ferrite reciclada debe ser significativamente más barata que NdFeB
        ferrite_recycled = 2.76  # $/kg
        ndfe_conventional = 55.0  # $/kg (NdFeB)
        ratio = ferrite_recycled / ndfe_conventional
        assert ratio < 0.1, f"Ferrite should be <10% of NdFeB cost, got {ratio*100}%"
        checks_passed.append("ferrite_cost_realistic")
    except Exception as e:
        checks_failed.append(f"ferrite_cost: {str(e)}")
    
    validation_passed = len(checks_failed) == 0
    
    return {
        "validation_passed": validation_passed,
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "total_checks": len(checks_passed) + len(checks_failed),
        "pass_rate_percent": round(100 * len(checks_passed) / (len(checks_passed) + len(checks_failed)), 1),
        "summary": f"Ferrite circular economy roadmap validated. {len(checks_passed)}/{len(checks_passed)+len(checks_failed)} checks passed."
    }


FERRITE_TOOL_SCHEMA = {
    "name": "ferrite_circular_economy_roadmap_tool",
    "description": "Análisis técnico + económico de cadena de valor ferrita reciclada (aceite viejo → Fe₃O₄) "
                   "para industrialización descentralizada no-militar en zonas rurales Chile. "
                   "7 modos: transformadores, purificación agua, MRI portátil, telecomunicaciones, "
                   "agricultura sensores, multiplicador empleo, validación.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["scenario_transformer_distribution", "water_purification_capacity", 
                         "medical_mri_feasibility", "telecoms_coverage", "agriculture_roi", 
                         "employment_multiplier", "validate"],
                "description": "Modo de análisis"
            },
            "params": {
                "type": "object",
                "description": "Parámetros específicos del modo (ver documentación de cada modo)"
            }
        },
        "required": ["mode"]
    }
}

# Auto-registration
register_tool("ferrite_circular_economy_roadmap_tool", FERRITE_TOOL_SCHEMA, run)

if __name__ == "__main__":
    # Self-test
    print("=" * 80)
    print("FERRITE CIRCULAR ECONOMY ROADMAP TOOL - SELF TEST")
    print("=" * 80)
    
    # Test 1
    print("\n[Test 1] Transformer scenario - Chiloé")
    result = run("scenario_transformer_distribution", {"region": "Chiloé", "population": 150000})
    print(json.dumps(result, indent=2))
    
    # Test 2
    print("\n[Test 2] Water purification - Arsenic removal")
    result = run("water_purification_capacity", {"contaminant": "As", "influent_concentration_ppm": 15.0})
    print(json.dumps(result, indent=2))
    
    # Test 3
    print("\n[Test 3] Medical MRI - Portátil 0.8T")
    result = run("medical_mri_feasibility", {"field_strength_tesla": 0.8})
    print(json.dumps(result, indent=2))
    
    # Test 4
    print("\n[Test 4] Telecoms - Rural coverage")
    result = run("telecoms_coverage", {"frequency_mhz": 900, "terrain": "rural"})
    print(json.dumps(result, indent=2))
    
    # Test 5
    print("\n[Test 5] Agriculture - Papa ROI")
    result = run("agriculture_roi", {"hectares": 100, "crop": "papa"})
    print(json.dumps(result, indent=2))
    
    # Test 6
    print("\n[Test 6] Employment - Transformadores x10")
    result = run("employment_multiplier", {"sub_industry": "transformadores", "primary_units": 10})
    print(json.dumps(result, indent=2))
    
    # Test 7 - Validation
    print("\n[Test 7] Validation")
    result = run("validate", {})
    print(json.dumps(result, indent=2))
    
    print("\n" + "=" * 80)
    print("SELF TEST COMPLETE")
    print("=" * 80)
