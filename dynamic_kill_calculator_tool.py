"""
dynamic_kill_calculator_tool.py

Herramienta MCP para control de pozos: calcula la tasa de bombeo y densidad
de lodo necesarias para detener un influjo de yacimiento (kick/blowout)
mediante el metodo "Dynamic Kill", resuelto por interseccion IPR/VLP
(analisis nodal) con busqueda numerica.

Nivel: avanzado.
  - IPR seleccionable por tipo de fluido (Darcy lineal / Vogel / Backpressure /
    Fetkovich compuesto).
  - VLP multifasico seleccionable (Poettmann-Carpenter / Hagedorn-Brown con
    correccion de Griffith / Beggs-Brill).
  - Perdida de friccion calculada por tramo via numero de Reynolds
    generalizado (fluido ley de potencia) + factor de Fanning, no una
    constante.
  - Kick tolerance / MAASP.
  - Comparacion Driller's Method vs Wait-and-Weight.
  - mode=validate con casos de referencia tipo SPE + casos limite.

Este archivo define el schema, la validacion de entrada, el dispatch a las
funciones de Octave (engine) y el modo validate. El motor numerico pesado
(Reynolds/Fanning, Beggs-Brill, solver de interseccion) vive en un .m
separado (dynamic_kill_engine.m) para mantener la logica matematica en
Octave, consistente con el resto del repo.
"""

import json
import math
import subprocess
from typing import Any, Literal, Optional

# ---------------------------------------------------------------------------
# Constantes de unidades de campo (field units): psi, ft, ppg, bbl/min, cp
# ---------------------------------------------------------------------------
HYDROSTATIC_CONST = 0.052        # psi/ft por ppg
FANNING_CONST = 25.8             # constante de conversion para dP friccion en field units

FLUID_TYPES = ("oil_above_pb", "oil_below_pb", "gas", "composite")
VLP_METHODS = ("poettmann_carpenter", "hagedorn_brown", "beggs_brill")
KILL_METHODS = ("driller", "wait_and_weight")


class DynamicKillInputError(ValueError):
    """Error de validacion de entrada, antes de tocar el motor Octave."""


# ---------------------------------------------------------------------------
# Schema de entrada (lo que describe la tool ante el LLM / MCP client)
# ---------------------------------------------------------------------------
TOOL_SCHEMA: dict[str, Any] = {
    "name": "dynamic_kill_calculator_tool",
    "description": (
        "Calcula el kill dinamico (densidad de lodo y tasa de bombeo "
        "criticas) para detener un influjo de yacimiento no controlado, "
        "usando analisis nodal (interseccion IPR/VLP) con correlaciones "
        "multifasicas y perdida de friccion por Reynolds/Fanning. "
        "Incluye kick tolerance, MAASP y comparacion Driller vs "
        "Wait-and-Weight. No reemplaza software de simulacion transitoria "
        "certificado para operaciones reales; es un modelo de ingenieria "
        "de pozos en estado semi-estable para analisis y docencia avanzada."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["kill_design", "kick_tolerance", "compare_methods", "validate"],
                "description": (
                    "kill_design: calcula densidad de lodo y tasa critica. "
                    "kick_tolerance: maximo influjo tolerable antes de exceder MAASP. "
                    "compare_methods: Driller's Method vs Wait-and-Weight. "
                    "validate: corre casos de referencia y devuelve pass/fail."
                ),
            },
            "well_geometry": {
                "type": "object",
                "properties": {
                    "tvd_ft": {"type": "number", "description": "Profundidad vertical verdadera, ft"},
                    "md_ft": {"type": "number", "description": "Profundidad medida (si el pozo es desviado), ft"},
                    "drillpipe_od_in": {"type": "number"},
                    "drillpipe_id_in": {"type": "number"},
                    "casing_id_in": {"type": "number", "description": "Diametro interno del casing/riser, in"},
                    "openhole_diameter_in": {"type": "number"},
                    "shoe_tvd_ft": {"type": "number", "description": "Profundidad de zapata, para MAASP"},
                    "inclination_deg": {"type": "number", "default": 0, "description": "0 = pozo vertical"},
                },
                "required": ["tvd_ft", "drillpipe_od_in", "drillpipe_id_in", "casing_id_in"],
            },
            "reservoir": {
                "type": "object",
                "properties": {
                    "fluid_type": {"type": "string", "enum": list(FLUID_TYPES)},
                    "pr_psi": {"type": "number", "description": "Presion de yacimiento (estatica)"},
                    "productivity_index": {"type": "number", "description": "J, bbl/d/psi (si se conoce, Darcy/Vogel)"},
                    "permeability_md": {"type": "number"},
                    "net_pay_ft": {"type": "number"},
                    "reservoir_radius_ft": {"type": "number"},
                    "wellbore_radius_ft": {"type": "number"},
                    "skin": {"type": "number", "default": 0},
                    "backpressure_c": {"type": "number", "description": "Coeficiente C de Rawlins-Schellhardt (gas)"},
                    "backpressure_n": {"type": "number", "description": "Exponente n, 0.5-1.0 (gas)"},
                    "fracture_gradient_psi_ft": {"type": "number", "description": "Para MAASP/kick tolerance"},
                },
                "required": ["fluid_type", "pr_psi"],
            },
            "control_fluid": {
                "type": "object",
                "properties": {
                    "base_density_ppg": {"type": "number"},
                    "rheology_model": {"type": "string", "enum": ["power_law", "bingham"]},
                    "power_law_n": {"type": "number", "description": "Indice de comportamiento, ley de potencia"},
                    "power_law_k": {"type": "number", "description": "Indice de consistencia K, eq. cp"},
                    "plastic_viscosity_cp": {"type": "number", "description": "PV, si rheology_model=bingham"},
                    "yield_point_lbf_100ft2": {"type": "number", "description": "YP, si rheology_model=bingham"},
                },
                "required": ["base_density_ppg", "rheology_model"],
            },
            "kick_data": {
                "type": "object",
                "properties": {
                    "sidpp_psi": {"type": "number", "description": "Shut-in drillpipe pressure"},
                    "sicp_psi": {"type": "number", "description": "Shut-in casing pressure"},
                    "pit_gain_bbl": {"type": "number"},
                    "influx_type": {"type": "string", "enum": ["gas", "oil", "water", "unknown"]},
                },
            },
            "vlp_method": {
                "type": "string",
                "enum": list(VLP_METHODS),
                "default": "beggs_brill",
            },
            "kill_method": {
                "type": "string",
                "enum": list(KILL_METHODS),
                "default": "wait_and_weight",
            },
            "safety_margin_psi": {
                "type": "number",
                "default": 100,
                "description": "Margen sobre Pr que debe superar el BHP en la tasa critica",
            },
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# Validacion de entrada (antes de invocar Octave)
# ---------------------------------------------------------------------------
def _validate_kill_design_input(payload: dict[str, Any]) -> None:
    geom = payload.get("well_geometry")
    res = payload.get("reservoir")
    fluid = payload.get("control_fluid")

    if not geom or not res or not fluid:
        raise DynamicKillInputError(
            "kill_design requiere well_geometry, reservoir y control_fluid"
        )

    if res["fluid_type"] not in FLUID_TYPES:
        raise DynamicKillInputError(f"fluid_type invalido: {res['fluid_type']}")

    if res["fluid_type"] == "gas" and (
        "backpressure_c" not in res or "backpressure_n" not in res
    ):
        raise DynamicKillInputError(
            "fluid_type=gas requiere backpressure_c y backpressure_n "
            "(Rawlins-Schellhardt); si no se conocen, usar composite "
            "con productivity_index estimado."
        )

    if res["fluid_type"] in ("oil_above_pb", "oil_below_pb") and "productivity_index" not in res:
        raise DynamicKillInputError(
            f"fluid_type={res['fluid_type']} requiere productivity_index (J)"
        )

    if geom["drillpipe_id_in"] >= geom["casing_id_in"]:
        raise DynamicKillInputError(
            "drillpipe_id_in debe ser menor que casing_id_in (geometria invalida)"
        )

    if fluid["rheology_model"] == "power_law" and (
        "power_law_n" not in fluid or "power_law_k" not in fluid
    ):
        raise DynamicKillInputError(
            "rheology_model=power_law requiere power_law_n y power_law_k"
        )
    if fluid["rheology_model"] == "bingham" and (
        "plastic_viscosity_cp" not in fluid or "yield_point_lbf_100ft2" not in fluid
    ):
        raise DynamicKillInputError(
            "rheology_model=bingham requiere plastic_viscosity_cp y yield_point_lbf_100ft2"
        )


def _validate_kick_tolerance_input(payload: dict[str, Any]) -> None:
    geom = payload.get("well_geometry")
    res = payload.get("reservoir")
    if not geom or "shoe_tvd_ft" not in geom:
        raise DynamicKillInputError("kick_tolerance requiere well_geometry.shoe_tvd_ft")
    if not res or "fracture_gradient_psi_ft" not in res:
        raise DynamicKillInputError("kick_tolerance requiere reservoir.fracture_gradient_psi_ft")


# ---------------------------------------------------------------------------
# Dispatch a Octave (el motor numerico real vive en dynamic_kill_engine.m)
# ---------------------------------------------------------------------------
def _call_octave_engine(function_name: str, args_json: str) -> dict[str, Any]:
    """
    Invoca dynamic_kill_engine.m via octave-cli, pasando los argumentos
    como JSON (parseados del lado Octave con jsondecode) y recibiendo la
    salida tambien como JSON (jsonencode), igual que el resto de las tools
    del repo que delegan calculo pesado a .m.
    """
    cmd = [
        "octave-cli", "--no-gui", "--eval",
        f"addpath('.'); source('dynamic_kill_engine.m'); "
        f"disp(jsonencode({function_name}(jsondecode('{args_json}'))))",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"octave engine error: {proc.stderr.strip()}")
    return json.loads(proc.stdout.strip())


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------
def kill_design(payload: dict[str, Any]) -> dict[str, Any]:
    _validate_kill_design_input(payload)
    payload = {**payload, "vlp_method": payload.get("vlp_method", "beggs_brill")}
    return _call_octave_engine("dk_kill_design", json.dumps(payload))


def kick_tolerance(payload: dict[str, Any]) -> dict[str, Any]:
    _validate_kick_tolerance_input(payload)
    return _call_octave_engine("dk_kick_tolerance", json.dumps(payload))


def compare_methods(payload: dict[str, Any]) -> dict[str, Any]:
    _validate_kill_design_input(payload)
    return _call_octave_engine("dk_compare_methods", json.dumps(payload))


# ---------------------------------------------------------------------------
# mode=validate — casos de referencia + casos limite
# ---------------------------------------------------------------------------
def validate() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # Caso limite 1: q=0 -> BHP debe ser exactamente la hidrostatica pura
    # (sin termino de friccion), verificando que el modelo no inyecta
    # perdida de carga espuria a caudal nulo.
    zero_flow_case = {
        "well_geometry": {
            "tvd_ft": 10000, "drillpipe_od_in": 5.0, "drillpipe_id_in": 4.276,
            "casing_id_in": 8.535,
        },
        "reservoir": {"fluid_type": "oil_above_pb", "pr_psi": 5000, "productivity_index": 0.5},
        "control_fluid": {
            "base_density_ppg": 12.0, "rheology_model": "power_law",
            "power_law_n": 0.6, "power_law_k": 3.5,
        },
        "vlp_method": "beggs_brill",
        "flow_rate_bpm_override": 0,
    }
    try:
        result = _call_octave_engine("dk_bhp_at_rate", json.dumps(zero_flow_case))
        expected_hydrostatic = HYDROSTATIC_CONST * 12.0 * 10000
        ok = abs(result.get("bhp_psi", -1) - expected_hydrostatic) < 1.0
        checks.append({
            "case": "q=0 => BHP igual a hidrostatica pura (sin friccion espuria)",
            "got": result.get("bhp_psi"),
            "expected": expected_hydrostatic,
            "ok": ok,
        })
    except Exception as exc:  # noqa: BLE001
        checks.append({
            "case": "q=0 => BHP igual a hidrostatica pura (sin friccion espuria)",
            "got": f"error: {exc}", "expected": "sin error", "ok": False,
        })

    # Caso limite 2: selector de IPR por fluid_type — gas no debe usar Vogel
    for fluid_type, must_use in (
        ("gas", "backpressure"),
        ("oil_below_pb", "vogel"),
        ("oil_above_pb", "darcy_lineal"),
    ):
        try:
            r = _call_octave_engine(
                "dk_select_ipr_method", json.dumps({"reservoir": {"fluid_type": fluid_type}})
            )
            ok = r.get("ipr_method") == must_use
            checks.append({
                "case": f"selector IPR para fluid_type={fluid_type}",
                "got": r.get("ipr_method"), "expected": must_use, "ok": ok,
            })
        except Exception as exc:  # noqa: BLE001
            checks.append({
                "case": f"selector IPR para fluid_type={fluid_type}",
                "got": f"error: {exc}", "expected": must_use, "ok": False,
            })

    # Caso de referencia 3: ejemplo tipo SPE de kill sheet (valores de
    # manual de control de pozos, kill mud weight por formula estandar).
    # TODO: reemplazar por un caso publicado con solucion verificada antes
    # de confiar en este check para produccion.
    spe_reference_case = {
        "well_geometry": {"tvd_ft": 8000, "drillpipe_od_in": 5.0, "drillpipe_id_in": 4.276, "casing_id_in": 8.535},
        "kick_data": {"sidpp_psi": 200, "pit_gain_bbl": 15, "influx_type": "gas"},
        "control_fluid": {"base_density_ppg": 9.6, "rheology_model": "bingham",
                           "plastic_viscosity_cp": 20, "yield_point_lbf_100ft2": 15},
    }
    try:
        r = _call_octave_engine("dk_kill_mud_weight", json.dumps(spe_reference_case))
        expected_kmw = 9.6 + (200 / (HYDROSTATIC_CONST * 8000))
        ok = abs(r.get("kill_mud_weight_ppg", -1) - expected_kmw) < 0.05
        checks.append({
            "case": "kill mud weight = original_mw + SIDPP/(0.052*TVD) (formula estandar kill sheet)",
            "got": r.get("kill_mud_weight_ppg"), "expected": round(expected_kmw, 3), "ok": ok,
        })
    except Exception as exc:  # noqa: BLE001
        checks.append({
            "case": "kill mud weight = original_mw + SIDPP/(0.052*TVD)",
            "got": f"error: {exc}", "expected": "ver formula", "ok": False,
        })

    all_passed = all(c["ok"] for c in checks)
    return {"validate": True, "all_passed": all_passed, "checks": checks}


# ---------------------------------------------------------------------------
# Entry point de la tool (siguiendo la convencion mode-dispatch del repo)
# ---------------------------------------------------------------------------
def dynamic_kill_calculator_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    mode = arguments.get("mode")
    if mode == "kill_design":
        return kill_design(arguments)
    if mode == "kick_tolerance":
        return kick_tolerance(arguments)
    if mode == "compare_methods":
        return compare_methods(arguments)
    if mode == "validate":
        return validate()
    raise DynamicKillInputError(f"mode desconocido: {mode}")


if __name__ == "__main__":
    import json
    print(json.dumps(dynamic_kill_calculator_tool({"mode": "validate"}), indent=2, ensure_ascii=False))


try:
    from tool_registry import register_tool as _register_tool_real
    _register_tool_real(
        name="dynamic_kill_calculator_tool",
        schema=TOOL_SCHEMA,
        handler=dynamic_kill_calculator_tool,
    )
except ImportError:
    pass
