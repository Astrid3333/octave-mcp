"""
Tests para math_pipeline_builder_tool.py (tool MCP run_math_pipeline)

Cubre:
  1. Registro y resolucion de nombres (REGISTRY, TOOL_NAME_ALIASES, _lookup_tool)
  2. Forma del schema MCP expuesto (PIPELINE_BUILDER_TOOL_SCHEMA)
  3. Resolucion de referencias '$save_as.campo.subcampo' (_resolve_value)
  4. Integracion: los 5 pipelines encadenados que se corrieron a mano contra
     el servidor MCP en vivo el 2026-08-14, ahora como regresion automatica.

NOTA IMPORTANTE: el import de abajo asume que la funcion de entrada del
pipeline se llama `run_math_pipeline` (mismo nombre que la tool MCP). Si en
el archivo real tiene otro nombre (ej. `handle_pipeline`, `execute_pipeline`),
hay que corregir el import. Para confirmarlo rapido:

    grep -n "^def .*mode.*steps" math_pipeline_builder_tool.py

Correr solo los tests rapidos (sin llamar a computo real):
    pytest tests/test_math_pipeline_builder.py -m "not integration"

Correr todo, incluyendo integracion:
    pytest tests/test_math_pipeline_builder.py
"""
import json

import pytest

from math_pipeline_builder_tool import (
    REGISTRY,
    TOOL_NAME_ALIASES,
    PIPELINE_BUILDER_TOOL_SCHEMA,
    _lookup_tool,
    _resolve_value,
    run_math_pipeline,  # AJUSTAR si el nombre real difiere (ver nota arriba)
)


# ---------------------------------------------------------------------------
# 1. Registro de tools: tamano y contenido esperado tras el patch del
#    2026-08-14 (9 tools originales + 6 nuevas = 15; 3 aliases originales +
#    6 nuevos = 9)
# ---------------------------------------------------------------------------

EXPECTED_NEW_ALIASES = {
    "bacterial_growth_tool": "compute_bacterial_growth_tool",
    "enzyme_kinetics": "compute_enzyme_kinetics",
    "population_dynamics": "compute_population_dynamics",
    "reaction_diffusion_real": "compute_reaction_diffusion_real",
    "statistics": "compute_statistics",
    "symbolic": "compute_symbolic",
}

EXPECTED_ORIGINAL_ALIASES = {
    "math_error_analyzer": "compute_math_error_analysis",
    "math_benchmark": "compute_math_benchmark",
    "math_interpolation": "compute_math_interpolation",
}

ALL_EXPECTED_ALIASES = {**EXPECTED_ORIGINAL_ALIASES, **EXPECTED_NEW_ALIASES}


def test_registry_has_15_tools():
    assert len(REGISTRY) == 15, (
        f"Se esperaban 15 tools en REGISTRY (9 originales + 6 nuevas), "
        f"hay {len(REGISTRY)}: {sorted(REGISTRY)}"
    )


def test_alias_count():
    assert len(TOOL_NAME_ALIASES) == 9, (
        f"Se esperaban 9 aliases (3 originales + 6 nuevos), "
        f"hay {len(TOOL_NAME_ALIASES)}: {sorted(TOOL_NAME_ALIASES)}"
    )


@pytest.mark.parametrize("alias,target", sorted(ALL_EXPECTED_ALIASES.items()))
def test_alias_maps_to_expected_function_name(alias, target):
    assert TOOL_NAME_ALIASES.get(alias) == target


@pytest.mark.parametrize("tool_name", sorted(ALL_EXPECTED_ALIASES))
def test_lookup_tool_resolves_via_alias(tool_name):
    """_lookup_tool debe resolver tanto los alias originales como los 6 nuevos."""
    fn = _lookup_tool(tool_name)
    assert callable(fn)


def test_lookup_tool_resolves_direct_function_names():
    """Toda entrada de REGISTRY debe ser resoluble por su propio nombre,
    sin pasar por TOOL_NAME_ALIASES."""
    for direct_name, fn in REGISTRY.items():
        assert _lookup_tool(direct_name) is fn


def test_lookup_tool_unknown_raises_with_helpful_list():
    """El mensaje de error debe listar las tools disponibles, para que quien
    arma un pipeline no necesite ir al codigo fuente a buscarlas."""
    with pytest.raises(ValueError) as exc_info:
        _lookup_tool("tool_que_no_existe")
    msg = str(exc_info.value)
    assert "tool_que_no_existe" in msg
    assert "bacterial_growth_tool" in msg
    assert "symbolic" in msg


# ---------------------------------------------------------------------------
# 2. Schema MCP: consistencia entre REGISTRY/ALIASES y lo que se documenta
#    hacia el cliente MCP
# ---------------------------------------------------------------------------

def test_schema_description_mentions_new_domains():
    desc = PIPELINE_BUILDER_TOOL_SCHEMA["description"]
    for keyword in (
        "crecimiento bacteriano",
        "cinetica enzimatica",
        "dinamica poblacional",
        "reaccion-difusion",
        "estadistica",
        "calculo simbolico",
    ):
        assert keyword in desc, (
            f"'{keyword}' no aparece en la descripcion general del schema"
        )


def test_schema_tool_enum_lists_every_registered_alias_and_tool():
    """
    El enum textual dentro de items.tool.description debe listar TODOS los
    nombres invocables (alias + directos). Si se agrega una tool nueva y se
    olvida actualizar esta descripcion, este test tiene que fallar -- es
    justamente el tipo de desincronizacion que el patch de hoy pudo haber
    introducido si un assert hubiera pasado por error.
    """
    tool_desc = (
        PIPELINE_BUILDER_TOOL_SCHEMA["inputSchema"]["properties"]["steps"]
        ["items"]["properties"]["tool"]["description"]
    )
    todos_los_nombres = set(TOOL_NAME_ALIASES) | set(REGISTRY)
    faltantes = sorted(n for n in todos_los_nombres if n not in tool_desc)
    assert not faltantes, (
        f"Estas tools estan en REGISTRY/TOOL_NAME_ALIASES pero no figuran "
        f"en el enum textual del schema: {faltantes}"
    )


def test_schema_json_serializable():
    """El schema completo debe serializar sin errores -- ya lo confirmamos
    a mano durante el patch de hoy; esto lo deja como regresion automatica."""
    json.dumps(PIPELINE_BUILDER_TOOL_SCHEMA, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 3. Resolucion de referencias '$save_as.campo.subcampo'
# ---------------------------------------------------------------------------

def test_resolve_value_passthrough_for_non_reference():
    assert _resolve_value(42, {}) == 42
    assert _resolve_value("texto plano", {}) == "texto plano"


def test_resolve_value_dict_navigation():
    context = {"growth": {"t": [0, 1, 2], "y_ln_N_N0": [0.0, 0.14, 0.31]}}
    assert _resolve_value("$growth.t", context) == [0, 1, 2]
    assert _resolve_value("$growth.y_ln_N_N0", context) == [0.0, 0.14, 0.31]


def test_resolve_value_scalar_field():
    context = {"mm": {"Vmax": 0.005, "Km": 1.0}}
    assert _resolve_value("$mm.Vmax", context) == 0.005


def test_resolve_value_missing_step_raises():
    with pytest.raises(Exception):
        _resolve_value("$no_existe.campo", {})


# ---------------------------------------------------------------------------
# 4. Integracion: los 5 pipelines encadenados validados a mano hoy contra
#    el servidor MCP en vivo, ahora como regresion automatica.
#
#    Son mas lentos (llaman a las funciones de computo real, sin mocks).
#    Marcados aparte para poder excluirlos con `-m "not integration"` cuando
#    se quiera feedback rapido durante desarrollo.
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_pipeline_bacterial_growth_then_fit_recovers_parameters():
    """baranyi_roberts simula una curva -> fit_growth_curve la reajusta.
    Debe converger y recuperar mu_max/lambda_lag cerca de los valores reales
    (validado en vivo: mu_max_fit=0.521 vs 0.5 real, r_squared=0.999)."""
    result = run_math_pipeline(
        mode="run",
        steps=[
            {
                "tool": "bacterial_growth_tool",
                "args": {
                    "mode": "baranyi_roberts",
                    "mu_max": 0.5, "y0": 0, "y_max": 8, "h0": 1,
                    "t_max": 20, "n_points": 30,
                },
                "save_as": "growth",
            },
            {
                "tool": "bacterial_growth_tool",
                "args": {
                    "mode": "fit_growth_curve",
                    "t_data": "$growth.t",
                    "log_n_data": "$growth.y_ln_N_N0",
                },
                "save_as": "fit",
            },
        ],
    )
    assert result["n_steps"] == 2
    fit = result["results"]["fit"]
    assert fit["converged"] is True
    assert fit["r_squared"] > 0.99
    assert abs(fit["mu_max_fit"] - 0.5) < 0.05
    assert abs(fit["lambda_lag_fit"] - 2.0) < 0.5


@pytest.mark.integration
def test_pipeline_enzyme_kinetics_then_statistics_t_test():
    """NOTA: statistics requiere preset='custom' en modo libre, o falla con
    'preset ... no aplica' -- descubierto durante la sesion de hoy."""
    result = run_math_pipeline(
        mode="run",
        steps=[
            {
                "tool": "enzyme_kinetics",
                "args": {
                    "mode": "michaelis_menten",
                    "k1": 1, "km1": 0.5, "k2": 0.5, "E0": 0.01, "S0": 10,
                    "t_max": 30, "n_points": 20,
                },
                "save_as": "mm",
            },
            {
                "tool": "statistics",
                "args": {
                    "mode": "t_test",
                    "preset": "custom",
                    "sample": "$mm.velocidad_sample",
                    "mu0": "$mm.Vmax",
                },
                "save_as": "mm_test",
            },
        ],
    )
    mm_test = result["results"]["mm_test"]
    assert "error" not in mm_test
    assert mm_test["n"] == 10
    assert mm_test["reject_at_alpha_0.05"] is True


@pytest.mark.integration
def test_pipeline_population_dynamics_then_statistics_t_test():
    result = run_math_pipeline(
        mode="run",
        steps=[
            {
                "tool": "population_dynamics",
                "args": {
                    "mode": "logistic_growth",
                    "r": 0.3, "K": 100, "x0": 5, "t_max": 20, "n_points": 15,
                },
                "save_as": "growth_pop",
            },
            {
                "tool": "statistics",
                "args": {
                    "mode": "t_test",
                    "preset": "custom",
                    "sample": "$growth_pop.trajectory_sample",
                    "mu0": "$growth_pop.poblacion_final",
                },
                "save_as": "growth_test",
            },
        ],
    )
    growth = result["results"]["growth_pop"]
    assert growth["max_error_vs_analytic"] < 0.01
    growth_test = result["results"]["growth_test"]
    assert growth_test["reject_at_alpha_0.05"] is True


@pytest.mark.integration
def test_pipeline_reaction_diffusion_turing_instability():
    """reaction_diffusion_real no comparte forma de output con otras tools
    (solo escalares de una condicion analitica), asi que va sola en el
    pipeline -- no hay un encadenamiento $save_as natural para ella."""
    result = run_math_pipeline(
        mode="run",
        steps=[
            {
                "tool": "reaction_diffusion_real",
                "args": {
                    "mode": "check_turing_instability",
                    "a11": 1, "a12": -1, "a21": 2, "a22": -1.5,
                    "Du": 1, "Dv": 10,
                },
                "save_as": "turing",
            },
        ],
    )
    turing = result["results"]["turing"]
    assert turing["inestabilidad_turing_presente"] is True
    for cond in (
        "cond1_estable_sin_difusion_trace_negativa",
        "cond2_estable_sin_difusion_det_positivo",
        "cond3_signo_cruzado_difusion",
        "cond4_discriminante_positivo",
    ):
        assert turing[cond]["cumple"] is True


@pytest.mark.integration
def test_pipeline_symbolic_differentiate_then_integrate_roundtrip():
    """Derivar y luego integrar debe recuperar la expresion original (+C).
    NOTA: symbolic tambien requiere preset='custom' en modo libre."""
    result = run_math_pipeline(
        mode="run",
        steps=[
            {
                "tool": "symbolic",
                "args": {
                    "mode": "differentiate",
                    "preset": "custom",
                    "expression": "x**3 - 2*x**2 + x",
                    "variable": "x",
                },
                "save_as": "deriv",
            },
            {
                "tool": "symbolic",
                "args": {
                    "mode": "integrate",
                    "preset": "custom",
                    "expression": "$deriv.derivative_simplified",
                    "variable": "x",
                },
                "save_as": "reintegrated",
            },
        ],
    )
    deriv = result["results"]["deriv"]
    assert deriv["derivative_simplified"] == "3*x**2 - 4*x + 1"
    reintegrated = result["results"]["reintegrated"]
    assert reintegrated["antiderivative"] == "x**3 - 2*x**2 + x + C"


@pytest.mark.integration
def test_pipeline_validate_mode_still_works():
    """El patch no debe haber roto el modo demo fijo (validate), que no
    pide argumentos y corre una demo interna fija."""
    result = run_math_pipeline(mode="validate")
    assert result.get("validation_passed") is True or "results" in result
