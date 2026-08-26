"""
natural_scale_tool.py

Leyes de escala conocidas en fisica y biologia:
- physical_scaling: ley del inverso del cuadrado, Gutenberg-Richter,
  numero de Reynolds
- biological_scaling: ley de Kleiber (metabolismo vs masa), relacion
  depredador-presa (Lotka-Volterra, punto de equilibrio)
- fractal_nature: dimension fractal de autosimilitud (N copias a escala 1/s)
"""

import math


# ---------------------------------------------------------------------------
# physical_scaling
# ---------------------------------------------------------------------------
def inverse_square_law(params):
    intensity0 = params.get("intensity0", 100.0)
    distance0 = params.get("distance0", 1.0)
    distance = params["distance"]

    # I * d^2 = constante
    constant = intensity0 * distance0 ** 2
    intensity = constant / (distance ** 2)

    return {"intensity": intensity, "constant": constant, "distance": distance}


def gutenberg_richter(params):
    """
    log10(N) = a - b*M  =>  N = 10^(a - b*M)
    N: numero de terremotos con magnitud >= M
    """
    a = params.get("a", 7.0)
    b = params.get("b", 1.0)
    magnitude = params["magnitude"]

    log_n = a - b * magnitude
    n = 10 ** log_n

    return {"magnitude": magnitude, "expected_count_n": n, "log10_n": log_n, "a": a, "b": b}


def reynolds_number(params):
    density = params.get("density", 1000.0)  # kg/m^3, agua por defecto
    velocity = params["velocity"]
    length = params["length"]
    viscosity = params.get("dynamic_viscosity", 1.0e-3)  # Pa*s, agua ~1e-3

    re = density * velocity * length / viscosity
    regime = "laminar" if re < 2300 else ("transicional" if re < 4000 else "turbulento")

    return {"reynolds_number": re, "regime": regime}


def physical_scaling(params):
    law = params.get("law", "inverse_square")
    if law == "inverse_square":
        return inverse_square_law(params)
    elif law == "gutenberg_richter":
        return gutenberg_richter(params)
    elif law == "reynolds":
        return reynolds_number(params)
    else:
        raise ValueError("law invalida. Opciones: inverse_square, gutenberg_richter, reynolds")


# ---------------------------------------------------------------------------
# biological_scaling
# ---------------------------------------------------------------------------
def kleiber_law(params):
    """metabolismo = a * masa^0.75 (escala alometrica de Kleiber)"""
    mass = params["mass"]
    a = params.get("coefficient", 70.0)  # kcal/dia aprox para mamiferos, valor tipico

    metabolism = a * mass ** 0.75
    return {"mass": mass, "metabolic_rate": metabolism, "exponent": 0.75}


def predator_prey_equilibrium(params):
    """
    Punto de equilibrio no trivial del modelo Lotka-Volterra:
      dPrey/dt = alpha*Prey - beta*Prey*Predator
      dPredator/dt = delta*Prey*Predator - gamma*Predator
    Equilibrio: Prey* = gamma/delta, Predator* = alpha/beta
    """
    alpha = params.get("prey_growth_rate", 1.0)
    beta = params.get("predation_rate", 0.1)
    delta = params.get("predator_growth_efficiency", 0.075)
    gamma = params.get("predator_death_rate", 1.5)

    prey_eq = gamma / delta
    predator_eq = alpha / beta

    return {
        "prey_equilibrium": prey_eq,
        "predator_equilibrium": predator_eq,
    }


def biological_scaling(params):
    model = params.get("model", "kleiber")
    if model == "kleiber":
        return kleiber_law(params)
    elif model == "predator_prey":
        return predator_prey_equilibrium(params)
    else:
        raise ValueError("model invalido. Opciones: kleiber, predator_prey")


# ---------------------------------------------------------------------------
# fractal_nature
# ---------------------------------------------------------------------------
def fractal_dimension(params):
    """
    Dimension de autosimilitud: D = log(N) / log(1/s)
    N: numero de copias autosimilares
    s: factor de escala de cada copia (0 < s < 1)
    """
    n_copies = params["n_copies"]
    scale_factor = params["scale_factor"]

    if not (0 < scale_factor < 1):
        raise ValueError("scale_factor debe estar entre 0 y 1 (exclusivo)")

    dimension = math.log(n_copies) / math.log(1.0 / scale_factor)

    return {"n_copies": n_copies, "scale_factor": scale_factor, "fractal_dimension": dimension}


def fractal_nature(params):
    return fractal_dimension(params)


# ---------------------------------------------------------------------------
# Dispatch principal
# ---------------------------------------------------------------------------
def natural_scale_tool(params: dict) -> dict:
    mode = params.get("mode", "physical_scaling")

    if mode == "physical_scaling":
        return physical_scaling(params)
    elif mode == "biological_scaling":
        return biological_scaling(params)
    elif mode == "fractal_nature":
        return fractal_nature(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            "mode invalido. Opciones: physical_scaling, biological_scaling, "
            "fractal_nature, validate"
        )


# ---------------------------------------------------------------------------
# Modo validate
# ---------------------------------------------------------------------------
def _validate():
    checks = []

    # 1) Inverso del cuadrado: duplicar distancia -> intensidad a 1/4
    r1a = inverse_square_law({"intensity0": 100.0, "distance0": 1.0, "distance": 1.0})
    r1b = inverse_square_law({"intensity0": 100.0, "distance0": 1.0, "distance": 2.0})
    checks.append({
        "name": "inverse_square_quarter_at_double_distance",
        "passed": abs(r1a["intensity"] - 100.0) < 1e-9 and abs(r1b["intensity"] - 25.0) < 1e-9,
        "intensity_at_1": r1a["intensity"],
        "intensity_at_2": r1b["intensity"],
    })

    # 2) Gutenberg-Richter: relacion monotonica decreciente con magnitud;
    #    a magnitud+1, N cae a 1/10 (b=1)
    r2a = gutenberg_richter({"a": 7.0, "b": 1.0, "magnitude": 5.0})
    r2b = gutenberg_richter({"a": 7.0, "b": 1.0, "magnitude": 6.0})
    ratio = r2a["expected_count_n"] / r2b["expected_count_n"]
    checks.append({
        "name": "gutenberg_richter_decade_drop",
        "passed": abs(ratio - 10.0) < 1e-6,
        "ratio": ratio,
    })

    # 3) Reynolds: valores tipicos de flujo laminar en tuberia estrecha con agua
    r3 = reynolds_number({"density": 1000.0, "velocity": 0.001, "length": 0.01, "dynamic_viscosity": 1e-3})
    checks.append({
        "name": "reynolds_laminar_regime",
        "passed": r3["regime"] == "laminar",
        "reynolds_number": r3["reynolds_number"],
    })

    # 4) Reynolds: valores altos -> turbulento
    r4 = reynolds_number({"density": 1000.0, "velocity": 10.0, "length": 1.0, "dynamic_viscosity": 1e-3})
    checks.append({
        "name": "reynolds_turbulent_regime",
        "passed": r4["regime"] == "turbulento",
        "reynolds_number": r4["reynolds_number"],
    })

    # 5) Kleiber: exponente correcto y valor conocido para masa=1
    r5 = kleiber_law({"mass": 1.0, "coefficient": 70.0})
    checks.append({
        "name": "kleiber_exponent_and_base_value",
        "passed": r5["exponent"] == 0.75 and abs(r5["metabolic_rate"] - 70.0) < 1e-9,
        "result": r5,
    })

    # 6) Kleiber: masa mayor -> metabolismo mayor pero sub-lineal (menos que proporcional)
    r6a = kleiber_law({"mass": 1.0, "coefficient": 70.0})
    r6b = kleiber_law({"mass": 16.0, "coefficient": 70.0})
    # masa x16 -> metabolismo deberia escalar por 16^0.75 = 8, no por 16
    expected_ratio = 16.0 ** 0.75
    observed_ratio = r6b["metabolic_rate"] / r6a["metabolic_rate"]
    checks.append({
        "name": "kleiber_sublinear_scaling",
        "passed": abs(observed_ratio - expected_ratio) < 1e-6 and observed_ratio < 16.0,
        "observed_ratio": observed_ratio,
        "expected_ratio": expected_ratio,
    })

    # 7) predator_prey_equilibrium: calculo directo
    r7 = predator_prey_equilibrium({
        "prey_growth_rate": 1.0,
        "predation_rate": 0.1,
        "predator_growth_efficiency": 0.075,
        "predator_death_rate": 1.5,
    })
    expected_prey = 1.5 / 0.075  # 20
    expected_predator = 1.0 / 0.1  # 10
    checks.append({
        "name": "predator_prey_equilibrium_calculation",
        "passed": abs(r7["prey_equilibrium"] - expected_prey) < 1e-9
        and abs(r7["predator_equilibrium"] - expected_predator) < 1e-9,
        "result": r7,
    })

    # 8) fractal_dimension: curva de Koch (N=4, s=1/3) -> D ~ 1.2619
    r8 = fractal_dimension({"n_copies": 4, "scale_factor": 1.0 / 3.0})
    checks.append({
        "name": "koch_curve_dimension",
        "passed": abs(r8["fractal_dimension"] - 1.2619) < 0.001,
        "fractal_dimension": r8["fractal_dimension"],
    })

    # 9) fractal_dimension: triangulo de Sierpinski (N=3, s=1/2) -> D ~ 1.585
    r9 = fractal_dimension({"n_copies": 3, "scale_factor": 0.5})
    checks.append({
        "name": "sierpinski_triangle_dimension",
        "passed": abs(r9["fractal_dimension"] - 1.58496) < 0.001,
        "fractal_dimension": r9["fractal_dimension"],
    })

    # 10) fractal_dimension: caso trivial (linea, N=2, s=1/2) -> D = 1
    r10 = fractal_dimension({"n_copies": 2, "scale_factor": 0.5})
    checks.append({
        "name": "line_dimension_is_one",
        "passed": abs(r10["fractal_dimension"] - 1.0) < 1e-9,
        "fractal_dimension": r10["fractal_dimension"],
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "mode": "validate",
        "tool": "natural_scale_tool",
        "all_passed": all_passed,
        "checks": checks,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(natural_scale_tool({"mode": "validate"}), indent=2))
