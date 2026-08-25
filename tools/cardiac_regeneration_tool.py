"""
cardiac_regeneration_tool.py

Modelo de EDOs de regeneracion cardiaca post-infarto: competencia entre la
rama regenerativa (cardiomiocitos dediferenciados -> proliferantes ->
re-diferenciados/maduros) y la rama fibrotica (fibroblasto -> miofibroblasto
-> cicatriz), ambas consumiendo el mismo territorio de tejido lesionado.

Compartimentos (7), todos como fraccion del territorio lesionado total
(injury_fraction), que es la cantidad conservada exacta en todo momento:

    W  Wound        -- tejido lesionado aun no comprometido a ninguna rama
    D  CM_dediff     -- cardiomiocitos dediferenciados, competentes p/ ciclo
    P  CM_prolif     -- cardiomiocitos en division activa
    R  CM_regen      -- cardiomiocitos re-diferenciados/maduros (regenerado)
    F  Fibroblast    -- fibroblastos activados por la lesion
    M  Myofibroblast -- miofibroblastos (fenotipo contractil/secretor)
    S  Scar          -- cicatriz fibrotica madura

Invariante exacto en todo t: W+D+P+R+F+M+S = injury_fraction
(se cumple por construccion: cada termino que sale de un compartimento
entra exactamente al siguiente, sin fuentes ni sumideros externos).

Biologia codificada (simplificada, orden de magnitud, NO calibrada contra
un dataset cuantitativo real -- ver validate() y las notas de cada preset):

- La rama regenerativa depende de una "ventana regenerativa" k_regen(t) que
  puede ser sostenida (pez cebra, capacidad regenerativa de por vida) o
  decaer exponencialmente con constante de tiempo tau_window (mamiferos:
  la ventana se cierra en los primeros dias de vida postnatal en raton, y
  es casi nula en el adulto).
- La rama fibrotica tiene un feedback autocatalitico: los miofibroblastos
  secretan TGF-beta, que promueve la transdiferenciacion de mas
  fibroblastos a miofibroblastos (circuito bien documentado en fibrosis
  cardiaca). Sin ese feedback (fibro_feedback_gain=0) el sistema es lineal
  y el resultado final no depende de injury_fraction; con el feedback
  activo, aparece una dependencia real de la salida final con la
  intensidad relativa de cada rama -- es lo que permite un barrido de
  bifurcation con un umbral, no una curva plana.
"""

import numpy as np
from scipy.integrate import odeint
from typing import Dict, Any, List
from tool_registry import register_tool


# ----------------------------------------------------------------------------
# Presets de especie / contexto (aproximados, orden de magnitud -- no
# calibrados contra un dataset cuantitativo real; pensados para capturar el
# ORDEN correcto de capacidad regenerativa entre especies/edades, no valores
# absolutos publicables)
# ----------------------------------------------------------------------------
PRESETS = {
    "zebrafish": {
        "k_regen0": 0.15,          # 1/dia, tasa dediferenciacion inicial
        "tau_window": None,        # ventana sostenida, no decae (regen. de por vida)
        "k_fibro": 0.02,           # 1/dia, tasa activacion fibroblastica (baja)
        "k_dediff_to_prolif": 0.30,
        "k_prolif_to_mature": 0.10,
        "k_fibro_to_myo": 0.10,
        "k_myo_to_scar": 0.05,
        "fibro_feedback_gain": 0.5,
        "K_myo": 0.05,
        "regen_suppression_gain": 0.3,
        "K_suppress": 0.05,
    },
    "neonatal_mouse": {
        "k_regen0": 0.10,
        "tau_window": 7.0,         # dias -- ventana se cierra ~P7
        "k_fibro": 0.08,
        "k_dediff_to_prolif": 0.30,
        "k_prolif_to_mature": 0.10,
        "k_fibro_to_myo": 0.10,
        "k_myo_to_scar": 0.05,
        "fibro_feedback_gain": 1.0,
        "K_myo": 0.05,
        "regen_suppression_gain": 0.6,
        "K_suppress": 0.05,
    },
    "adult_mouse": {
        "k_regen0": 0.01,
        "tau_window": 2.0,
        "k_fibro": 0.15,
        "k_dediff_to_prolif": 0.30,
        "k_prolif_to_mature": 0.10,
        "k_fibro_to_myo": 0.10,
        "k_myo_to_scar": 0.05,
        "fibro_feedback_gain": 1.5,
        "K_myo": 0.05,
        "regen_suppression_gain": 1.0,
        "K_suppress": 0.05,
    },
    "adult_human": {
        "k_regen0": 0.002,
        "tau_window": 1.0,
        "k_fibro": 0.15,
        "k_dediff_to_prolif": 0.30,
        "k_prolif_to_mature": 0.10,
        "k_fibro_to_myo": 0.10,
        "k_myo_to_scar": 0.05,
        "fibro_feedback_gain": 2.0,
        "K_myo": 0.05,
        "regen_suppression_gain": 1.5,
        "K_suppress": 0.05,
    },
}

COMPARTMENTS = ["W", "D", "P", "R", "F", "M", "S"]


class CardiacRegenerationModel:
    def __init__(self, species: str = "adult_mouse", custom: Dict[str, Any] = None,
                 injury_fraction: float = 0.3):
        if custom is not None:
            self.params = dict(custom)
            self.species = "custom"
        else:
            if species not in PRESETS:
                raise ValueError(f"species desconocida: {species}. Opciones: {list(PRESETS)}")
            self.params = dict(PRESETS[species])
            self.species = species
        self.injury_fraction = float(injury_fraction)

    # -- tasa de dediferenciacion dependiente del tiempo (ventana regenerativa) --
    def k_regen(self, t: float) -> float:
        k0 = self.params["k_regen0"]
        tau = self.params.get("tau_window")
        if tau is None:
            return float(k0)
        return float(k0 * np.exp(-t / tau))

    def odes(self, y: np.ndarray, t: float) -> np.ndarray:
        W, D, P, R, F, M, S = y
        p = self.params

        kr_base = self.k_regen(t)
        kf = p["k_fibro"]

        # feedback autocatalitico en la rama fibrotica: mas miofibroblasto
        # -> mas conversion fibroblasto->miofibroblasto (TGF-beta autocrino).
        # Saturacion tipo Hill con K_myo FIJO (constante absoluta, no
        # proporcional a injury_fraction).
        feedback = 1.0 + p["fibro_feedback_gain"] * (M / (M + p["K_myo"]))
        k_f2m_eff = p["k_fibro_to_myo"] * feedback

        # acoplamiento de vuelta hacia la rama regenerativa: el
        # microambiente miofibroblastico (rigidez de matriz + TGF-beta)
        # suprime la ventana regenerativa. Sin este termino, dW/dt depende
        # solo de kr(t) y kf (constantes), y el resultado final queda
        # desacoplado de todo lo que pase en la rama fibrotica -- el
        # feedback de arriba nunca podria alterar el desenlace, solo la
        # velocidad. Con la supresion, ambas ramas compiten de verdad.
        suppression = 1.0 + p["regen_suppression_gain"] * (M / (M + p["K_suppress"]))
        kr = kr_base / suppression

        dW = -(kr + kf) * W
        dD = kr * W - p["k_dediff_to_prolif"] * D
        dP = p["k_dediff_to_prolif"] * D - p["k_prolif_to_mature"] * P
        dR = p["k_prolif_to_mature"] * P
        dF = kf * W - k_f2m_eff * F
        dM = k_f2m_eff * F - p["k_myo_to_scar"] * M
        dS = p["k_myo_to_scar"] * M

        return np.array([dW, dD, dP, dR, dF, dM, dS])

    def _y0(self) -> np.ndarray:
        # t=0: todo el territorio lesionado empieza como "wound" sin comprometer
        y0 = np.zeros(7)
        y0[0] = self.injury_fraction
        return y0

    def simulate(self, t_end: float = 60.0, num_points: int = 300) -> Dict[str, Any]:
        t = np.linspace(0.0, t_end, num_points)
        sol = odeint(self.odes, self._y0(), t)
        traj = {name: sol[:, i].tolist() for i, name in enumerate(COMPARTMENTS)}
        conservation = (sol.sum(axis=1) - self.injury_fraction)
        return {
            "species": self.species,
            "injury_fraction": self.injury_fraction,
            "t": t.tolist(),
            "trajectory": traj,
            "max_conservation_error": float(np.max(np.abs(conservation))),
        }

    def outcome(self, t_end: float = 200.0) -> Dict[str, Any]:
        """Fracciones finales (asintoticas) de regenerado vs cicatriz."""
        t = np.linspace(0.0, t_end, 400)
        sol = odeint(self.odes, self._y0(), t)
        final = sol[-1]
        regen_frac = float(final[3] / self.injury_fraction)   # R
        scar_frac = float(final[6] / self.injury_fraction)    # S
        residual = float((final[0] + final[1] + final[2] + final[4] + final[5]) / self.injury_fraction)
        return {
            "species": self.species,
            "injury_fraction": self.injury_fraction,
            "t_end": t_end,
            "regen_fraction": regen_frac,
            "scar_fraction": scar_frac,
            "residual_fraction": residual,   # deberia ser ~0 si t_end alcanza para converger
            "conservation_check": float(np.sum(final) - self.injury_fraction),
        }

    def bifurcation(self, param_name: str = "k_regen0", param_range=(0.001, 0.15),
                     num_points: int = 12, t_end: float = 200.0) -> Dict[str, Any]:
        lo, hi = param_range
        values = np.linspace(lo, hi, num_points)
        regen_fracs = []
        scar_fracs = []
        for v in values:
            custom = dict(self.params)
            custom[param_name] = float(v)
            m = CardiacRegenerationModel(custom=custom, injury_fraction=self.injury_fraction)
            out = m.outcome(t_end=t_end)
            regen_fracs.append(out["regen_fraction"])
            scar_fracs.append(out["scar_fraction"])
        return {
            "param_name": param_name,
            "param_values": values.tolist(),
            "regen_fraction": regen_fracs,
            "scar_fraction": scar_fracs,
        }

    # ------------------------------------------------------------------
    def validate(self) -> Dict[str, Any]:
        checks = {}

        # 1. conservacion exacta a lo largo de una trayectoria (adult_mouse, injury=0.3)
        m1 = CardiacRegenerationModel(species="adult_mouse", injury_fraction=0.3)
        r1 = m1.simulate(t_end=60.0, num_points=200)
        checks["conservacion_trayectoria"] = {
            "passed": r1["max_conservation_error"] < 1e-8,
            "details": f"max|suma-injury_fraction| = {r1['max_conservation_error']:.2e}",
        }

        # 2. sin fibrosis (k_fibro=0) Y ventana sostenida (tau_window=None)
        #    -> 100% regenerado al final. OJO: con ventana que decae (tau
        #    finito), incluso sin fibrosis queda un residuo de Wound sin
        #    comprometer para siempre (la ventana se cierra antes de
        #    capturarlo todo) -- por eso este check usa tau_window=None
        #    explicitamente, no un preset con ventana que cierra.
        custom_no_fibro = dict(PRESETS["adult_mouse"])
        custom_no_fibro["k_fibro"] = 0.0
        custom_no_fibro["tau_window"] = None
        m2 = CardiacRegenerationModel(custom=custom_no_fibro, injury_fraction=0.3)
        o2 = m2.outcome(t_end=1500.0)
        checks["sin_fibrosis_ventana_sostenida_100pct_regenerado"] = {
            "passed": abs(o2["regen_fraction"] - 1.0) < 1e-3 and o2["scar_fraction"] < 1e-6,
            "details": f"regen_fraction={o2['regen_fraction']:.6f}, scar_fraction={o2['scar_fraction']:.2e}",
        }

        # 3. sin regeneracion (k_regen0=0) -> 100% cicatriz al final
        custom_no_regen = dict(PRESETS["adult_mouse"])
        custom_no_regen["k_regen0"] = 0.0
        m3 = CardiacRegenerationModel(custom=custom_no_regen, injury_fraction=0.3)
        o3 = m3.outcome(t_end=300.0)
        checks["sin_regeneracion_100pct_cicatriz"] = {
            "passed": abs(o3["scar_fraction"] - 1.0) < 1e-3 and o3["regen_fraction"] < 1e-6,
            "details": f"scar_fraction={o3['scar_fraction']:.6f}, regen_fraction={o3['regen_fraction']:.2e}",
        }

        # 4. orden biologico correcto entre especies: zebrafish > neonatal > adult_mouse > adult_human
        #    en fraccion final regenerada, mismo injury_fraction para las 4
        order = ["zebrafish", "neonatal_mouse", "adult_mouse", "adult_human"]
        fracs = []
        for sp in order:
            m = CardiacRegenerationModel(species=sp, injury_fraction=0.3)
            fracs.append(m.outcome(t_end=300.0)["regen_fraction"])
        monotonic = all(fracs[i] > fracs[i + 1] for i in range(len(fracs) - 1))
        checks["orden_capacidad_regenerativa_por_especie"] = {
            "passed": monotonic,
            "details": f"regen_fraction por especie {order} = {[round(f, 4) for f in fracs]}",
        }

        # 5. ventana regenerativa decae correctamente para presets con tau_window
        m5 = CardiacRegenerationModel(species="adult_mouse", injury_fraction=0.3)
        k_at_0 = m5.k_regen(0.0)
        k_at_10tau = m5.k_regen(10 * m5.params["tau_window"])
        checks["ventana_regenerativa_decae"] = {
            "passed": k_at_0 > 0 and k_at_10tau < 1e-3 * k_at_0,
            "details": f"k_regen(0)={k_at_0:.4f}, k_regen(10*tau)={k_at_10tau:.2e}",
        }

        # 6. zebrafish (tau_window=None) NO decae -- ventana sostenida
        m6 = CardiacRegenerationModel(species="zebrafish", injury_fraction=0.3)
        k_zf_0 = m6.k_regen(0.0)
        k_zf_1000 = m6.k_regen(1000.0)
        checks["ventana_sostenida_pez_cebra"] = {
            "passed": abs(k_zf_0 - k_zf_1000) < 1e-12,
            "details": f"k_regen(0)={k_zf_0:.4f}, k_regen(1000)={k_zf_1000:.4f}",
        }

        # 7. sin feedback autocatalitico (fibro_feedback_gain=0), el resultado
        #    final es independiente de injury_fraction (sistema lineal
        #    homogeneo); con feedback>0, si depende -- confirma que el
        #    feedback es lo que introduce la no-linealidad real
        custom_lin = dict(PRESETS["adult_mouse"])
        custom_lin["fibro_feedback_gain"] = 0.0
        custom_lin["regen_suppression_gain"] = 0.0
        fracs_lin = []
        for inj in (0.1, 0.3, 0.6):
            m = CardiacRegenerationModel(custom=custom_lin, injury_fraction=inj)
            fracs_lin.append(m.outcome(t_end=300.0)["regen_fraction"])
        fracs_nonlin = []
        for inj in (0.1, 0.3, 0.6):
            m = CardiacRegenerationModel(species="adult_mouse", injury_fraction=inj)
            fracs_nonlin.append(m.outcome(t_end=300.0)["regen_fraction"])
        checks["feedback_introduce_dependencia_de_injury_fraction"] = {
            "passed": (max(fracs_lin) - min(fracs_lin) < 1e-4) and (max(fracs_nonlin) - min(fracs_nonlin) > 1e-4),
            "details": (
                f"sin feedback regen_fraction(inj=0.1,0.3,0.6)={[round(f,4) for f in fracs_lin]} (deberia ser ~constante); "
                f"con feedback={[round(f,4) for f in fracs_nonlin]} (deberia variar)"
            ),
        }

        # 8. no negatividad: ningun compartimento negativo en toda la trayectoria
        min_val = min(min(v) for v in r1["trajectory"].values())
        checks["no_negatividad"] = {
            "passed": min_val > -1e-9,
            "details": f"valor minimo en toda la trayectoria = {min_val:.2e}",
        }

        # normaliza cada 'passed' a bool nativo de Python (defensa contra
        # numpy.bool_ u otros tipos no serializables a JSON colandose desde
        # cualquier comparacion que involucre un numpy.float64)
        for c in checks.values():
            c["passed"] = bool(c["passed"])

        total = len(checks)
        passed = sum(1 for c in checks.values() if c["passed"])
        return {
            "tool": "cardiac_regeneration_tool",
            "checks": checks,
            "total_passed": passed,
            "total_checks": total,
            "validation_passed": bool(passed == total),
        }

    # ------------------------------------------------------------------
    def run(self, mode: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if mode == "simulate":
            t_end = params.get("t_end", 60.0)
            num_points = params.get("num_points", 300)
            return self.simulate(t_end=t_end, num_points=num_points)

        elif mode == "outcome":
            t_end = params.get("t_end", 200.0)
            return self.outcome(t_end=t_end)

        elif mode == "bifurcation":
            param_name = params.get("param_name", "k_regen0")
            param_range = params.get("param_range", [0.001, 0.15])
            num_points = params.get("num_points", 12)
            t_end = params.get("t_end", 200.0)
            return self.bifurcation(param_name=param_name, param_range=tuple(param_range),
                                     num_points=num_points, t_end=t_end)

        elif mode == "validate":
            return self.validate()

        else:
            return {"status": "error", "error": f"Unknown mode: {mode}"}


def run(mode: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Global entry point.

    params:
      "species": zebrafish | neonatal_mouse | adult_mouse | adult_human | custom (default adult_mouse)
      "custom": dict de parametros -- requerido si species == "custom"
      "injury_fraction": fraccion de tejido lesionado, 0..1 (default 0.3)
      ... plus params especificos de cada modo (ver CardiacRegenerationModel.run)
    """
    species = params.get("species", "adult_mouse")
    custom = params.get("custom")
    injury_fraction = params.get("injury_fraction", 0.3)
    model = CardiacRegenerationModel(species=species, custom=custom, injury_fraction=injury_fraction)
    return model.run(mode, params)


CARDIAC_REGENERATION_TOOL_SCHEMA = {
    "name": "cardiac_regeneration_tool",
    "description": (
        "Modelo de EDOs de regeneracion cardiaca post-infarto: 7 compartimentos "
        "(Wound, CM_dediff, CM_prolif, CM_regen, Fibroblast, Myofibroblast, Scar) "
        "compitiendo por el mismo territorio de tejido lesionado (injury_fraction, "
        "invariante exacto). Rama regenerativa gobernada por una ventana temporal "
        "que decae segun especie (sostenida en pez cebra, se cierra en dias en "
        "raton neonato, casi nula en adulto). Rama fibrotica con feedback "
        "autocatalitico TGF-beta (miofibroblasto->mas miofibroblasto). Presets: "
        "zebrafish, neonatal_mouse, adult_mouse, adult_human, o custom. Modos: "
        "simulate (trayectoria temporal), outcome (fracciones finales regenerado "
        "vs cicatriz), bifurcation (barrido de un parametro, e.g. k_regen0 o "
        "fibro_feedback_gain), validate (8 self-checks)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["simulate", "outcome", "bifurcation", "validate"],
            },
            "params": {
                "type": "object",
                "description": (
                    "species (zebrafish|neonatal_mouse|adult_mouse|adult_human|custom), "
                    "custom (dict de rates si species=custom), injury_fraction (0..1, "
                    "default 0.3), y parametros especificos de cada modo (t_end, "
                    "num_points, param_name, param_range)."
                ),
            },
        },
        "required": ["mode"],
    },
}

register_tool(
    name="cardiac_regeneration_tool",
    schema=CARDIAC_REGENERATION_TOOL_SCHEMA,
    handler=lambda args: run(args.get("mode"), args.get("params") or {}),
)


if __name__ == "__main__":
    model = CardiacRegenerationModel()
    result = model.validate()

    print("=" * 70)
    print("CARDIAC REGENERATION - VALIDATE MODE (v1.0)")
    print("=" * 70)

    checks = result["checks"]
    for check_name in sorted(checks.keys()):
        check_info = checks[check_name]
        status = "OK" if check_info["passed"] else "FAIL"
        print(f"[{status}] {check_name:45s} | {check_info['details']}")

    print("=" * 70)
    print(f"Total: {result['total_passed']}/{result['total_checks']} PASSED")
    print(f"validation_passed: {result['validation_passed']}")
    print("=" * 70)
