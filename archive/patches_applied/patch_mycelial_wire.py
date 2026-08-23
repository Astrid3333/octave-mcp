import shutil
import datetime
import py_compile

FILE = "mycelial_network_tool.py"
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup = f"{FILE}.bak_{ts}"
shutil.copy(FILE, backup)
print(f"Backup creado: {backup}")

with open(FILE, "r", encoding="utf-8") as f:
    src = f.read()

# --- 1) TOOL_SCHEMA + imports sys/json, insertados antes de MODES ---
anchor1 = '''from scipy.stats import poisson as _poisson, nbinom as _nbinom, levy_stable

MODES = ['''

TOOL_SCHEMA_BLOCK = '''from scipy.stats import poisson as _poisson, nbinom as _nbinom, levy_stable
import sys
import json

TOOL_SCHEMA = {
    "name": "mycelial_network_tool",
    "description": (
        "Modelado micelial: crecimiento logistico, eyeccion balistica de "
        "esporas (gota-de-Buller + drag de Stokes), estadistica espacial "
        "de dispersion de esporas (poisson/neg_binomial/levy), y "
        "advection-difusion de esporas en el viento. Modos: "
        "growth_logistic, spore_ballistic, spore_statistical, "
        "spore_advection_diffusion, self_test, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["growth_logistic", "spore_ballistic",
                         "spore_statistical", "spore_advection_diffusion",
                         "self_test", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "r": {"type": "number", "description": "tasa de crecimiento (growth_logistic)"},
                    "K": {"type": "number", "description": "capacidad de carga (growth_logistic)"},
                    "B0": {"type": "number", "description": "biomasa inicial (growth_logistic)"},
                    "t_max": {"type": "number", "description": "tiempo final (growth_logistic, spore_ballistic)"},
                    "n_points": {"type": "integer", "description": "cantidad de puntos"},
                    "drop_radius_um": {"type": "number", "description": "radio de la gota en micrones (spore_ballistic)"},
                    "launch_angle_deg": {"type": "number", "description": "angulo de lanzamiento en grados (spore_ballistic)"},
                    "distribution": {"type": "string", "enum": ["poisson", "neg_binomial", "levy"], "description": "distribucion espacial (spore_statistical)"},
                    "n_spores": {"type": "integer", "description": "cantidad de esporas simuladas (spore_statistical)"},
                    "area_size_m": {"type": "number", "description": "lado del area de estudio en metros (spore_statistical)"},
                    "levy_alpha": {"type": "number", "description": "indice de cola para distribution=levy (spore_statistical)"},
                    "seed": {"type": "integer", "description": "semilla aleatoria (spore_statistical)"},
                    "D": {"type": "number", "description": "coeficiente de difusion (spore_advection_diffusion)"},
                    "v_wind": {"type": "number", "description": "velocidad del viento (spore_advection_diffusion)"},
                    "source_mass": {"type": "number", "description": "masa de la fuente puntual (spore_advection_diffusion)"},
                    "x_max": {"type": "number", "description": "extension espacial del dominio (spore_advection_diffusion)"},
                    "nx": {"type": "integer", "description": "cantidad de celdas espaciales (spore_advection_diffusion)"},
                    "t_snapshot": {"type": "number", "description": "instante de la foto de concentracion (spore_advection_diffusion)"},
                },
            },
        },
        "required": ["mode"],
    },
}

MODES = ['''

assert src.count(anchor1) == 1, "anchor1 (TOOL_SCHEMA) no es unico"
src = src.replace(anchor1, TOOL_SCHEMA_BLOCK, 1)

# --- 2) compute_mycelial_network: la rama validate ahora llama a run_self_test ---
anchor2 = '''def compute_mycelial_network(mode="growth_logistic", **kwargs):
    if mode == "validate":
        return _validate_mycelial_network()'''
new2 = '''def compute_mycelial_network(mode="growth_logistic", **kwargs):
    if mode == "validate":
        return run_self_test()'''
assert src.count(anchor2) == 1, "anchor2 (rama validate) no es unico"
src = src.replace(anchor2, new2, 1)

# --- 3) rename _validate_mycelial_network -> run_self_test ---
anchor3 = '''def _validate_mycelial_network():
    checks = []
    all_passed = True'''
new3 = '''def run_self_test():
    checks = []
    all_passed = True'''
assert src.count(anchor3) == 1, "anchor3 (rename funcion) no es unico"
src = src.replace(anchor3, new3, 1)

# --- 4) return final + bloque NOTA DE INTEGRACION -> run()/__main__/_register() ---
anchor4 = '''    return {
        "mode": "validate",
        "validation_passed": bool(all_passed),
        "checks": checks,
    }


# --------------------------------------------------------------------------
# NOTA DE INTEGRACION (adaptar a tu server.py real):
#
# 1. Registro de schema: agregar "mycelial_network" con
#    mode enum = MODES (incluyendo "validate") -- esto es lo que
#    run_all_validations.py detecta automaticamente via
#    mode_to_call="validate" por default, sin necesitar tocar
#    ALTERNATE_VALIDATE_MODE / ALTERNATE_VALIDATE_PARAM_NAME /
#    FLAT_SIGNATURE_TOOLS.
#
# 2. Dispatch: sumar el elif tool_name=="mycelial_network" en el
#    bloque de despacho de server.py, siguiendo el mismo patron
#    (result=compute_mycelial_network(**args), resp={...}).
#
# 3. Si mycelial_network termina viviendo junto a un submotor Rust
#    (candidato: spore_statistical con muchos agentes, o el paso de
#    NN fuerza-bruta si area/n_spores crece -- ahi mismo patron que
#    fem_poisson2d: subprocess + JSON), dejar el wrapper Python tal
#    cual y solo reemplazar el cuerpo de _spore_statistical con la
#    llamada al binario.
# --------------------------------------------------------------------------'''

new4 = '''    total = len(checks)
    passed_n = sum(1 for c in checks if c["passed"])
    return {"total": total, "passed": passed_n, "all_passed": passed_n == total, "checks": checks}


def run(mode, params=None):
    params = params or {}
    if mode == "validate":
        r = run_self_test()
        return {"checks": r["checks"], "validation_passed": r["all_passed"], "n_checks": r["total"]}
    elif mode == "self_test":
        return run_self_test()
    else:
        return compute_mycelial_network(mode=mode, **params)


if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "self_test"
    params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    try:
        out = run(mode_arg, params_arg)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)


def _register():
    """
    Auto-registro estilo octave-mcp (patron self-registrante via
    tool_registry, register_tool(name, schema, handler)).
    """
    try:
        import tool_registry

        def _handler(args):
            return run(args.get("mode"), args.get("params"))

        tool_registry.register_tool("mycelial_network_tool", TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()'''

assert src.count(anchor4) == 1, "anchor4 (return final + NOTA) no es unico"
src = src.replace(anchor4, new4, 1)

with open(FILE, "w", encoding="utf-8") as f:
    f.write(src)

py_compile.compile(FILE, doraise=True)
print(f"{FILE} parcheado OK. py_compile OK.")
