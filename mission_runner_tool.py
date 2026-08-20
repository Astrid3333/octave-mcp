"""
mission_runner_tool: envoltorio narrativo que encadena plague_sir_tool[fit_beta]
con disaster_economics_tool[direct_loss]. No agrega fisica ni economia nueva --
solo mapea la salida real de una tool al input real de la otra, y arma un texto
narrativo a partir de los NUMEROS REALES devueltos (no un cuento fijo).

Mapeo: R0_reproductivo_basico (de fit_beta) se usa como 'intensity' en
direct_loss, con intensity_50=1.0 (umbral epidemiologico clasico: R0=1 es el
punto de quiebre entre epidemia que se apaga o crece). exposed_value y k los
aporta el usuario -- no salen de ninguna API, mismo criterio que
disaster_early_warning_tool con channel_geometry/fuel.
"""
from plague_sir_tool import compute_plague_sir
from disaster_economics_tool import compute_disaster_economics
from tool_registry import register_tool


def _mode_mission_plague_economics(params):
    text_data = params.get("text_data")
    preset = params.get("preset")
    gamma = params.get("gamma", 0.4)
    poblacion_estimada = params.get("poblacion_estimada", 2000.0)
    exposed_value = params.get("exposed_value")
    k = params.get("k", 1.5)

    if exposed_value is None:
        return {"error": "hay que pasar 'exposed_value' -- no sale de ninguna API, es conocimiento local del usuario sobre el valor economico expuesto"}

    sir_result = compute_plague_sir(
        mode="fit_beta", text_data=text_data, preset=preset,
        gamma=gamma, poblacion_estimada=poblacion_estimada,
    )
    if "error" in sir_result:
        return {"stage": "plague_sir_tool.fit_beta", "error": sir_result["error"]}

    R0 = sir_result["R0_reproductivo_basico"]

    econ_params = {
        "exposed_value": float(exposed_value),
        "intensity": R0,
        "intensity_50": 1.0,
        "k": k,
    }
    econ_result = compute_disaster_economics("direct_loss", econ_params)
    if "error" in econ_result:
        return {"stage": "disaster_economics_tool.direct_loss", "error": econ_result["error"]}

    if R0 > 1.0:
        veredicto = f"R0={R0:.2f} > 1 -- la plaga se esta propagando. Cada infectado contagia a mas de una persona en promedio."
    else:
        veredicto = f"R0={R0:.2f} <= 1 -- la plaga se esta apagando sola. Cada infectado contagia a menos de una persona en promedio."

    narrative = (
        f"Ajustaste el modelo contra {sir_result['n_semanas']} semanas de reportes reales "
        f"(r2={sir_result['r2_ajuste']:.3f} de ajuste). {veredicto} "
        f"Con un valor expuesto de {exposed_value:,.0f}, la perdida directa estimada es "
        f"{econ_result['direct_loss']:,.0f} (damage_ratio={econ_result['damage_ratio']:.3f})."
    )

    return {
        "narrative": narrative,
        "plague_sir_result": sir_result,
        "disaster_economics_result": econ_result,
        "caveat": sir_result.get("nota"),
    }


def _validate():
    r = _mode_mission_plague_economics({
        "preset": "peste_demo",
        "exposed_value": 1_000_000.0,
        "k": 1.5,
    })
    checks = [{
        "check": "mission_plague_economics_preset_corre_sin_error",
        "passed": "error" not in r and "narrative" in r,
    }]
    if "disaster_economics_result" in r:
        checks.append({
            "check": "direct_loss_no_negativo",
            "passed": r["disaster_economics_result"]["direct_loss"] >= 0,
        })
    return {"validation_passed": all(c["passed"] for c in checks), "checks": checks}


def compute_mission_runner(mode, params=None):
    params = params or {}
    if mode == "validate":
        return _validate()
    if mode == "mission_plague_economics":
        return _mode_mission_plague_economics(params)
    return {"error": f"modo desconocido: {mode}. Modos validos: mission_plague_economics, validate"}


MISSION_RUNNER_TOOL_SCHEMA = {
    "name": "mission_runner_tool",
    "description": (
        "Orquestador narrativo/educativo: encadena plague_sir_tool[fit_beta] con "
        "disaster_economics_tool[direct_loss], mapeando R0_reproductivo_basico como "
        "intensity (umbral intensity_50=1.0). Devuelve un texto narrativo generado a "
        "partir de los numeros reales de ambas tools, no un guion fijo. Requiere "
        "'exposed_value' (conocimiento local del usuario, no sale de ninguna API)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["mission_plague_economics", "validate"]},
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}

register_tool(
    name="mission_runner_tool",
    schema=MISSION_RUNNER_TOOL_SCHEMA,
    handler=lambda args: compute_mission_runner(args.get("mode"), args.get("params")),
)
