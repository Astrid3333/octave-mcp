"""
circular_economy_tool.py

Flujo de materiales con balance de masa (inputs/outputs/reciclaje/perdidas por etapa).
Patron: compute_circular_economy_tool(mode, **kwargs) + CIRCULAR_ECONOMY_TOOL_SCHEMA
Auto-registro via @register_tool (mismo patron que biorefinery_tool).

Invariante de validacion: conservacion de masa en cada etapa
    input_mass = output_mass + recycled_mass + loss_mass  (+/- tolerancia numerica)

Modos:
  - stage_balance   : balance de masa de una sola etapa
  - chain_balance   : balance encadenado sobre una lista de etapas
  - circularity_index : Material Circularity Indicator simplificado (MCI, Ellen MacArthur-like)
  - validate        : autotest con casos donde la conservacion de masa es exacta
"""

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(schema):
        def _decorator(fn):
            return fn
        return _decorator


def _stage_balance(input_mass, output_mass, recycled_mass, loss_mass=None, tol=1e-6):
    input_mass = float(input_mass)
    output_mass = float(output_mass)
    recycled_mass = float(recycled_mass)

    if loss_mass is None:
        # Se infiere la perdida para cerrar el balance
        loss_mass = input_mass - output_mass - recycled_mass
    else:
        loss_mass = float(loss_mass)

    balance_residual = input_mass - (output_mass + recycled_mass + loss_mass)
    mass_conserved = abs(balance_residual) <= tol

    recycling_rate = (recycled_mass / input_mass) if input_mass > 0 else 0.0
    loss_rate = (loss_mass / input_mass) if input_mass > 0 else 0.0

    return {
        "input_mass": input_mass,
        "output_mass": output_mass,
        "recycled_mass": recycled_mass,
        "loss_mass": loss_mass,
        "balance_residual": balance_residual,
        "mass_conserved": mass_conserved,
        "recycling_rate": recycling_rate,
        "loss_rate": loss_rate,
    }


def _chain_balance(stages, tol=1e-6):
    """
    stages: lista de dicts con al menos {input_mass, output_mass, recycled_mass, loss_mass?}
    El output de una etapa se espera que alimente el input de la siguiente
    (no se fuerza, solo se reporta si hay discontinuidad).
    """
    results = []
    total_input = 0.0
    total_recycled = 0.0
    total_loss = 0.0

    prev_output = None
    for i, stage in enumerate(stages):
        r = _stage_balance(
            stage["input_mass"],
            stage["output_mass"],
            stage.get("recycled_mass", 0.0),
            stage.get("loss_mass"),
            tol=tol,
        )
        r["stage_index"] = i
        r["stage_name"] = stage.get("name", f"etapa_{i}")

        if prev_output is not None:
            r["input_output_discontinuity"] = r["input_mass"] - prev_output
        else:
            r["input_output_discontinuity"] = None

        prev_output = r["output_mass"]
        total_input += r["input_mass"]
        total_recycled += r["recycled_mass"]
        total_loss += r["loss_mass"]
        results.append(r)

    all_conserved = all(r["mass_conserved"] for r in results)

    return {
        "stages": results,
        "total_input_mass": total_input,
        "total_recycled_mass": total_recycled,
        "total_loss_mass": total_loss,
        "overall_recycling_rate": (total_recycled / total_input) if total_input > 0 else 0.0,
        "all_stages_mass_conserved": all_conserved,
    }


def _circularity_index(virgin_mass_input, recycled_mass_input, product_mass, waste_mass):
    """
    Version simplificada del Material Circularity Indicator (MCI):
    MCI = 1 - (masa lineal / masa total de referencia)
    donde masa lineal ~ (virgin_input + waste_no_reciclado) normalizado por la masa del producto.
    """
    virgin_mass_input = float(virgin_mass_input)
    recycled_mass_input = float(recycled_mass_input)
    product_mass = float(product_mass)
    waste_mass = float(waste_mass)

    total_input = virgin_mass_input + recycled_mass_input
    if total_input <= 0 or product_mass <= 0:
        raise ValueError("virgin+recycled input y product_mass deben ser > 0")

    linear_flow_index = (virgin_mass_input + waste_mass) / (2.0 * product_mass) \
        if product_mass > 0 else 1.0
    linear_flow_index = min(max(linear_flow_index, 0.0), 1.0)
    mci = max(0.0, 1.0 - linear_flow_index)

    recycled_input_fraction = recycled_mass_input / total_input

    return {
        "virgin_mass_input": virgin_mass_input,
        "recycled_mass_input": recycled_mass_input,
        "product_mass": product_mass,
        "waste_mass": waste_mass,
        "recycled_input_fraction": recycled_input_fraction,
        "linear_flow_index": linear_flow_index,
        "material_circularity_indicator": mci,
    }


def _validate():
    checks = []

    # Caso 1: balance exacto, sin inferir perdida -> residual = 0
    r1 = _stage_balance(input_mass=100, output_mass=70, recycled_mass=20, loss_mass=10)
    ok1 = abs(r1["balance_residual"]) < 1e-9 and r1["mass_conserved"]
    checks.append(("stage_balance_exact_conservation", ok1))

    # Caso 2: perdida inferida automaticamente -> debe cerrar exacto por construccion
    r2 = _stage_balance(input_mass=50, output_mass=40, recycled_mass=5, loss_mass=None)
    ok2 = abs(r2["loss_mass"] - 5.0) < 1e-9 and r2["mass_conserved"]
    checks.append(("stage_balance_inferred_loss", ok2))

    # Caso 3: balance roto a proposito -> mass_conserved debe ser False
    r3 = _stage_balance(input_mass=100, output_mass=70, recycled_mass=20, loss_mass=5)
    # 70+20+5=95 != 100 -> residual=5, no conservado
    ok3 = (not r3["mass_conserved"]) and abs(r3["balance_residual"] - 5.0) < 1e-9
    checks.append(("stage_balance_detects_violation", ok3))

    # Caso 4: cadena de 2 etapas, todas conservadas
    stages = [
        {"name": "recoleccion", "input_mass": 100, "output_mass": 80, "recycled_mass": 15, "loss_mass": 5},
        {"name": "reprocesamiento", "input_mass": 80, "output_mass": 60, "recycled_mass": 10, "loss_mass": 10},
    ]
    r4 = _chain_balance(stages)
    ok4 = r4["all_stages_mass_conserved"] and abs(r4["total_input_mass"] - 180.0) < 1e-9
    checks.append(("chain_balance_two_stages", ok4))

    # Caso 5: MCI = 0 para sistema 100% lineal (todo virgen, todo residuo, nada reciclado)
    # linear_flow_index = (V + W)/(2P); con V=P, W=P -> LFI=1 -> MCI=0
    r5 = _circularity_index(virgin_mass_input=100, recycled_mass_input=0, product_mass=100, waste_mass=100)
    ok5 = abs(r5["material_circularity_indicator"] - 0.0) < 1e-9
    checks.append(("mci_fully_linear_system_is_zero", ok5))

    # Caso 6: MCI mejora (sube) cuando baja el input virgen y el waste, a paridad de producto
    r6a = _circularity_index(virgin_mass_input=100, recycled_mass_input=0, product_mass=100, waste_mass=100)
    r6b = _circularity_index(virgin_mass_input=20, recycled_mass_input=80, product_mass=100, waste_mass=20)
    ok6 = r6b["material_circularity_indicator"] > r6a["material_circularity_indicator"]
    checks.append(("mci_increases_with_more_recycling", ok6))

    passed = sum(1 for _, ok in checks if ok)
    return {
        "mode": "validate",
        "checks": [{"name": n, "passed": ok} for n, ok in checks],
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks),
    }


CIRCULAR_ECONOMY_TOOL_SCHEMA = {
    "name": "circular_economy_tool",
    "description": (
        "Flujo de materiales con balance de masa por etapa (input/output/reciclaje/perdidas), "
        "encadenamiento multi-etapa, y un Material Circularity Indicator (MCI) simplificado. "
        "Conservacion de masa se usa como invariante de validacion."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["stage_balance", "chain_balance", "circularity_index", "validate"],
                "description": "Operacion a realizar, o 'validate' para autotest",
            },
            "input_mass": {"type": "number"},
            "output_mass": {"type": "number"},
            "recycled_mass": {"type": "number"},
            "loss_mass": {"type": "number", "description": "Opcional; si se omite se infiere para cerrar el balance"},
            "stages": {
                "type": "array",
                "description": "Para mode=chain_balance: lista de {name?, input_mass, output_mass, recycled_mass, loss_mass?}",
                "items": {"type": "object"},
            },
            "virgin_mass_input": {"type": "number"},
            "recycled_mass_input": {"type": "number"},
            "product_mass": {"type": "number"},
            "waste_mass": {"type": "number"},
        },
        "required": ["mode"],
    },
}


@register_tool(CIRCULAR_ECONOMY_TOOL_SCHEMA)
def compute_circular_economy_tool(mode, **kwargs):
    if mode == "validate":
        return _validate()

    if mode == "stage_balance":
        return {
            "mode": mode,
            **_stage_balance(
                kwargs["input_mass"],
                kwargs["output_mass"],
                kwargs.get("recycled_mass", 0.0),
                kwargs.get("loss_mass"),
            ),
        }
    elif mode == "chain_balance":
        stages = kwargs.get("stages")
        if not stages:
            raise ValueError("Se requiere 'stages' (lista de etapas)")
        return {"mode": mode, **_chain_balance(stages)}
    elif mode == "circularity_index":
        return {
            "mode": mode,
            **_circularity_index(
                kwargs["virgin_mass_input"],
                kwargs["recycled_mass_input"],
                kwargs["product_mass"],
                kwargs["waste_mass"],
            ),
        }
    else:
        raise ValueError(f"Modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_circular_economy_tool(mode="validate"), indent=2, ensure_ascii=False))
