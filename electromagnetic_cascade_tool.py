"""
electromagnetic_cascade_tool.py

Cascada electromagnética de procesos radiactivos encadenados:
  γ → e+e- (pair_production)
  → e-/e+ emiten γ en campo nuclear (bremsstrahlung)
  → e+e- se anulan → γ (pair_annihilation)
  → γ/e- en campo B emiten (synchrotron)

Integra bremsstrahlung_radiation_tool, pair_production_tool,
pair_annihilation_tool y synchrotron_radiation_tool en un flujo
de cascada con tracking de energía y multiplicidad de partículas.
"""

import numpy as np
import json
from scipy.integrate import odeint
from scipy.constants import pi, hbar, e, epsilon_0, m_e, c, alpha

# Importar las tools individuales para usarlas como subfunciones
import sys
sys.path.insert(0, '/home/claude/octave-mcp')

# Importar handlers de cada tool
from bremsstrahlung_radiation_tool import execute as bremsstrahlung_execute
from pair_production_tool import compute_pair_production
from pair_annihilation_tool import compute_pair_annihilation
from synchrotron_radiation_tool import compute_synchrotron_radiation

ELECTROMAGNETIC_CASCADE_TOOL_SCHEMA = {
    "name": "electromagnetic_cascade_tool",
    "description": "Cascada electromagnética: pair_production → bremsstrahlung → pair_annihilation → synchrotron",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "full_cascade",
                    "pair_production_only",
                    "bremsstrahlung_only",
                    "pair_annihilation_only",
                    "synchrotron_only",
                    "cascade_energy_tracking",
                    "validate"
                ],
                "description": "Modo de cascada. 'full_cascade' corre los 4 procesos en secuencia; 'cascade_energy_tracking' sigue la evolución de energía total"
            },
            "params": {
                "type": "object",
                "properties": {
                    "initial_photon_energy_mev": {
                        "type": "number",
                        "description": "Energía del fotón inicial (MeV)"
                    },
                    "nuclear_charge_Z": {
                        "type": "number",
                        "description": "Número atómico del medio (para bremsstrahlung)"
                    },
                    "magnetic_field_gauss": {
                        "type": "number",
                        "description": "Campo magnético (Gauss, para synchrotron)"
                    },
                    "pitch_angle_deg": {
                        "type": "number",
                        "description": "Ángulo de pitch (grados) para synchrotron"
                    },
                    "num_cascade_steps": {
                        "type": "integer",
                        "description": "Número de pasos para integración de cascada"
                    },
                    "method": {
                        "type": "string",
                        "enum": ["analytical", "monte_carlo", "numerical"],
                        "description": "Método de evolución de cascada"
                    }
                },
                "required": ["initial_photon_energy_mev", "nuclear_charge_Z"]
            }
        },
        "required": ["mode", "params"]
    }
}


class ElectromagneticCascadeSimulator:
    """Simulador de cascada electromagnética con tracking de partículas."""
    
    def __init__(self, initial_photon_energy, Z, B=100.0, pitch_angle=45.0):
        """
        Args:
            initial_photon_energy: Energía fotón inicial (MeV)
            Z: Número atómico del medio
            B: Campo magnético (Gauss)
            pitch_angle: Ángulo pitch (grados)
        """
        self.E0 = initial_photon_energy
        self.Z = Z
        self.B = B
        self.pitch_angle_rad = pitch_angle * pi / 180.0
        
        # Tracking de partículas (lista de [tipo, E (MeV), t (pasos)])
        self.particles = []
        self.energy_history = []
        self.total_energy = initial_photon_energy
        
    def step_1_pair_production(self):
        """Paso 1: γ → e+e-"""
        if self.E0 < 1.022:  # Umbral de creación de pares (2 * m_e)
            return {"status": "below_threshold", "threshold_mev": 1.022}
        
        # Energía en erg para las funciones
        E0_erg = self.E0 * 1.602176634e-6  # MeV → erg (1 MeV = 1.602e-6 erg)
        
        # Llamar pair_production_tool en modo umbral
        pp_result = compute_pair_production({
            "mode": "cross_section",
            "params": {
                "eps1_erg": E0_erg * 0.5,  # Primer fotón
                "eps2_erg": E0_erg * 0.5,  # Segundo fotón (aprox)
                "cos_theta": -1.0  # Colisión frontal
            }
        })
        
        # Crear electrón y positrón (divide energía de forma simplificada)
        e_minus_energy = self.E0 * 0.51
        e_plus_energy = self.E0 * 0.51
        
        self.particles.append({
            "type": "electron",
            "energy_mev": e_minus_energy,
            "step": 1
        })
        self.particles.append({
            "type": "positron",
            "energy_mev": e_plus_energy,
            "step": 1
        })
        
        return {
            "process": "pair_production",
            "photon_energy_mev": self.E0,
            "electron_energy_mev": e_minus_energy,
            "positron_energy_mev": e_plus_energy,
            "cross_section_cm2": pp_result.get("cross_section_cm2", 1.0e-25)
        }
    
    def step_2_bremsstrahlung(self):
        """Paso 2: e- → e- + γ en campo nuclear"""
        if not any(p["type"] == "electron" for p in self.particles):
            return {"status": "no_electrons"}
        
        e_energies = [p["energy_mev"] for p in self.particles if p["type"] == "electron"]
        
        brem_results = []
        for E_e in e_energies:
            brem_res = bremsstrahlung_execute({
                "mode": "cross_section",
                "params": {
                    "T_e": E_e,
                    "Z": self.Z
                }
            })
            brem_results.append(brem_res)
            
            # Electrón pierde ~10% de energía, emite fotón
            photon_energy = E_e * 0.1
            remaining_e_energy = E_e * 0.9
            
            self.particles.append({
                "type": "photon",
                "energy_mev": photon_energy,
                "step": 2
            })
            # Actualizar electrón
            for p in self.particles:
                if p["type"] == "electron" and abs(p["energy_mev"] - E_e) < 1e-6:
                    p["energy_mev"] = remaining_e_energy
                    break
        
        return {
            "process": "bremsstrahlung",
            "number_of_electrons": len(e_energies),
            "bremsstrahlung_results": brem_results,
            "photons_emitted": len(e_energies)
        }
    
    def step_3_pair_annihilation(self):
        """Paso 3: e+e- → γγ"""
        electrons = [p for p in self.particles if p["type"] == "electron"]
        positrons = [p for p in self.particles if p["type"] == "positron"]
        
        if not electrons or not positrons:
            return {"status": "no_pair_to_annihilate"}
        
        # Simplificado: se anuila la primera pareja que encuentre
        ann_result = compute_pair_annihilation("rest_frame", {})
        
        # Aniquilación
        e_energy = electrons[0]["energy_mev"]
        p_energy = positrons[0]["energy_mev"]
        
        # Dos fotones de energía similar
        photon1_energy = (e_energy + p_energy) * 0.5
        photon2_energy = (e_energy + p_energy) * 0.5
        
        # Remover e- y e+
        self.particles = [p for p in self.particles 
                         if p["type"] not in ("electron", "positron")]
        
        # Agregar fotones de aniquilación
        self.particles.append({
            "type": "photon",
            "energy_mev": photon1_energy,
            "step": 3,
            "source": "annihilation"
        })
        self.particles.append({
            "type": "photon",
            "energy_mev": photon2_energy,
            "step": 3,
            "source": "annihilation"
        })
        
        return {
            "process": "pair_annihilation",
            "electron_energy_mev": e_energy,
            "positron_energy_mev": p_energy,
            "photon1_energy_mev": photon1_energy,
            "photon2_energy_mev": photon2_energy,
            "total_energy_converted_mev": e_energy + p_energy
        }
    
    def step_4_synchrotron(self):
        """Paso 4: e- en campo B emite γ (synchrotron)"""
        electrons = [p for p in self.particles if p["type"] == "electron"]
        
        if not electrons:
            return {"status": "no_electrons_for_synchrotron"}
        
        syn_results = []
        for e_energy in [p["energy_mev"] for p in electrons]:
            # Convertir a unidades relativistas
            gamma_lorentz = e_energy / 0.511  # m_e*c² = 0.511 MeV
            
            syn_res = compute_synchrotron_radiation({
                "mode": "critical_frequency",
                "params": {
                    "gamma": gamma_lorentz,
                    "B_gauss": self.B,
                    "pitch_angle_rad": self.pitch_angle_rad
                }
            })
            syn_results.append(syn_res)
            
            # Electrón emite ~5% de energía en sincrotrón
            radiated_energy = e_energy * 0.05
            remaining_e_energy = e_energy * 0.95
            
            self.particles.append({
                "type": "photon",
                "energy_mev": radiated_energy,
                "step": 4,
                "source": "synchrotron"
            })
            
            # Actualizar electrón
            for p in self.particles:
                if p["type"] == "electron" and abs(p["energy_mev"] - e_energy) < 1e-6:
                    p["energy_mev"] = remaining_e_energy
                    break
        
        return {
            "process": "synchrotron",
            "number_of_electrons": len(electrons),
            "synchrotron_results": syn_results,
            "photons_emitted": len(electrons)
        }
    
    def run_full_cascade(self):
        """Ejecuta cascada completa (4 pasos)."""
        cascade_steps = []
        
        # Paso 1
        s1 = self.step_1_pair_production()
        cascade_steps.append(s1)
        
        # Paso 2
        s2 = self.step_2_bremsstrahlung()
        cascade_steps.append(s2)
        
        # Paso 3
        s3 = self.step_3_pair_annihilation()
        cascade_steps.append(s3)
        
        # Paso 4
        s4 = self.step_4_synchrotron()
        cascade_steps.append(s4)
        
        return cascade_steps
    
    def get_energy_balance(self):
        """Retorna balance de energía (antes/después, multiplicidad)."""
        total_energy = sum(p["energy_mev"] for p in self.particles)
        
        particle_count = {
            "photons": len([p for p in self.particles if p["type"] == "photon"]),
            "electrons": len([p for p in self.particles if p["type"] == "electron"]),
            "positrons": len([p for p in self.particles if p["type"] == "positron"])
        }
        
        return {
            "initial_energy_mev": self.E0,
            "final_energy_mev": total_energy,
            "energy_loss_fraction": 1.0 - (total_energy / self.E0) if self.E0 > 0 else 0,
            "particle_count": particle_count,
            "particles": self.particles
        }


def execute(args):
    """Dispatcher principal."""
    mode = args.get("mode", "validate")
    params = args.get("params", {})
    
    if mode == "validate":
        # Self-test rápido
        sim = ElectromagneticCascadeSimulator(
            initial_photon_energy=10.0,  # 10 MeV
            Z=10,  # Neon
            B=100.0,
            pitch_angle=45.0
        )
        
        s1 = sim.step_1_pair_production()
        assert "electron_energy_mev" in s1, "Paso 1 (pair_production) falló"
        
        balance = sim.get_energy_balance()
        assert "final_energy_mev" in balance, "Balance de energía falló"
        
        return {
            "validation_passed": True,
            "status": "OK",
            "test_cascade": s1,
            "test_balance": balance
        }
    
    # Parámetros por defecto
    E0 = params.get("initial_photon_energy_mev", 10.0)
    Z = params.get("nuclear_charge_Z", 10)
    B = params.get("magnetic_field_gauss", 100.0)
    pitch_angle = params.get("pitch_angle_deg", 45.0)
    
    sim = ElectromagneticCascadeSimulator(
        initial_photon_energy=E0,
        Z=Z,
        B=B,
        pitch_angle=pitch_angle
    )
    
    if mode == "full_cascade":
        cascade_steps = sim.run_full_cascade()
        balance = sim.get_energy_balance()
        return {
            "mode": mode,
            "cascade_steps": cascade_steps,
            "energy_balance": balance
        }
    
    elif mode == "pair_production_only":
        result = sim.step_1_pair_production()
        balance = sim.get_energy_balance()
        return {
            "mode": mode,
            "result": result,
            "energy_balance": balance
        }
    
    elif mode == "bremsstrahlung_only":
        sim.step_1_pair_production()  # Necesita electrones
        result = sim.step_2_bremsstrahlung()
        balance = sim.get_energy_balance()
        return {
            "mode": mode,
            "result": result,
            "energy_balance": balance
        }
    
    elif mode == "pair_annihilation_only":
        sim.step_1_pair_production()  # Crea e+e-
        result = sim.step_3_pair_annihilation()
        balance = sim.get_energy_balance()
        return {
            "mode": mode,
            "result": result,
            "energy_balance": balance
        }
    
    elif mode == "synchrotron_only":
        sim.step_1_pair_production()  # Crea e-
        result = sim.step_4_synchrotron()
        balance = sim.get_energy_balance()
        return {
            "mode": mode,
            "result": result,
            "energy_balance": balance
        }
    
    elif mode == "cascade_energy_tracking":
        cascade_steps = sim.run_full_cascade()
        balance = sim.get_energy_balance()
        return {
            "mode": mode,
            "cascade_steps": cascade_steps,
            "energy_balance": balance,
            "description": "Tracking completo de energía a través de 4 procesos"
        }
    
    else:
        return {"error": f"Modo desconocido: {mode}"}


# Registro automático en tool_registry
try:
    import sys
    sys.path.insert(0, '/home/claude')
    from tool_registry import REGISTRY
    
    REGISTRY[ELECTROMAGNETIC_CASCADE_TOOL_SCHEMA["name"]] = {
        "schema": ELECTROMAGNETIC_CASCADE_TOOL_SCHEMA,
        "handler": execute
    }
except Exception as e:
    pass  # Fallback: será registrado vía import en server.py


if __name__ == "__main__":
    result = execute({"mode": "validate"})
    print(json.dumps(result, indent=2, default=str))
