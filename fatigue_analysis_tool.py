"""
fatigue_analysis_tool.py

Fatiga ciclica de componentes mecanicos via ecuacion de Basquin (curva S-N
en el regimen de alto ciclo), correccion de tension media de Goodman
modificado, y regla de Miner de dano acumulado lineal. Motivada por la
necesidad de validar piezas de protesis (tibia/pylon, pie) sometidas a
carga ciclica de marcha -- ver Doberti Martinez, A. "Diseno de una protesis
de pierna para amputados transtibiales" (U. Chile, 2015), fase 3 del
trabajo (respuesta estatica y resistencia a la fatiga).

No trae una base de datos de parametros de fatiga por material: sigma_f'
(coeficiente de resistencia a la fatiga) y b (exponente de Basquin) varian
mucho segun proceso de fabricacion (impreso 3D, waterjet, forjado, etc.) y
deben ser provistos por quien llama la tool, tipicamente de una norma o
ensayo -- no se inventan valores por material aca.

Patron: compute_fatigue_analysis_tool(mode, **kwargs) + SCHEMA
Auto-registro via register_tool.

Ecuacion de Basquin (alto ciclo, S-N): sigma_a = sigma_f' * (2N)^b
  sigma_a  : amplitud de tension [MPa]
  sigma_f' : coeficiente de resistencia a la fatiga [MPa]
  N        : ciclos hasta falla
  b        : exponente de Basquin (tipicamente -0.05 a -0.15, material-dependiente)

Correccion de Goodman modificado (tension media != 0):
  sigma_a_eq = sigma_a / (1 - sigma_m / sigma_u)
  sigma_m : tension media del ciclo [MPa]
  sigma_u : resistencia ultima a la traccion [MPa]

Regla de Miner (dano lineal acumulado):
  D = sum(n_i / N_i)   -- falla predicha cuando D >= 1

Modos:
  - basquin_life      : ciclos a falla N dado sigma_a, sigma_f', b
  - goodman_equivalent : tension amplitud equivalente (R=-1) dado sigma_a, sigma_m, sigma_u
  - miner_damage        : dano acumulado D dado un espectro de bloques de carga
  - validate              : autotest
"""

try:
    from tool_registry import register_tool
except ImportError:
    register_tool = None


def _basquin_life(sigma_a_mpa, sigma_f_prime_mpa, b):
    if sigma_a_mpa <= 0 or sigma_f_prime_mpa <= 0:
        raise ValueError("sigma_a_mpa y sigma_f_prime_mpa deben ser > 0")
    if b >= 0:
        raise ValueError("b (exponente de Basquin) debe ser negativo")
    if sigma_a_mpa >= sigma_f_prime_mpa:
        # (2N)^b con base cerca de 1 y N grande -> igual matematicamente valido,
        # pero fuera del rango tipico de validez del modelo de alto ciclo
        note = "sigma_a >= sigma_f': el resultado cae fuera del rango tipico de validez de Basquin (regimen de bajo ciclo)"
    else:
        note = None
    two_N = (sigma_a_mpa / sigma_f_prime_mpa) ** (1.0 / b)
    N = 0.5 * two_N
    return {
        "sigma_a_mpa": sigma_a_mpa,
        "sigma_f_prime_mpa": sigma_f_prime_mpa,
        "b": b,
        "cycles_to_failure": N,
        "note": note,
    }


def _goodman_equivalent(sigma_a_mpa, sigma_m_mpa, sigma_u_mpa):
    if sigma_a_mpa <= 0:
        raise ValueError("sigma_a_mpa debe ser > 0")
    if sigma_u_mpa <= 0:
        raise ValueError("sigma_u_mpa debe ser > 0")
    if sigma_m_mpa >= sigma_u_mpa:
        raise ValueError("sigma_m_mpa debe ser < sigma_u_mpa (Goodman no valido mas alla de la resistencia ultima)")
    sigma_a_eq = sigma_a_mpa / (1.0 - (sigma_m_mpa / sigma_u_mpa))
    return {
        "sigma_a_mpa": sigma_a_mpa,
        "sigma_m_mpa": sigma_m_mpa,
        "sigma_u_mpa": sigma_u_mpa,
        "sigma_a_equivalent_mpa": sigma_a_eq,
    }


def _miner_damage(blocks, sigma_f_prime_mpa, b, sigma_u_mpa=None):
    if not blocks:
        raise ValueError("blocks no puede estar vacio")
    details = []
    total_D = 0.0
    for i, blk in enumerate(blocks):
        sigma_a = blk.get("stress_amplitude_mpa")
        n_i = blk.get("cycles_applied")
        sigma_m = blk.get("mean_stress_mpa", 0.0)
        if sigma_a is None or n_i is None:
            raise ValueError(f"block[{i}] requiere 'stress_amplitude_mpa' y 'cycles_applied'")
        if n_i < 0:
            raise ValueError(f"block[{i}]: cycles_applied debe ser >= 0")

        if sigma_m and sigma_m != 0.0:
            if sigma_u_mpa is None:
                raise ValueError(f"block[{i}] tiene mean_stress_mpa != 0 pero no se paso 'sigma_u_mpa' para la correccion de Goodman")
            g = _goodman_equivalent(sigma_a, sigma_m, sigma_u_mpa)
            sigma_a_eff = g["sigma_a_equivalent_mpa"]
        else:
            sigma_a_eff = sigma_a

        life = _basquin_life(sigma_a_eff, sigma_f_prime_mpa, b)
        N_i = life["cycles_to_failure"]
        d_i = n_i / N_i
        total_D += d_i
        details.append({
            "block_index": i,
            "stress_amplitude_mpa": sigma_a,
            "mean_stress_mpa": sigma_m,
            "effective_stress_amplitude_mpa": sigma_a_eff,
            "cycles_applied": n_i,
            "cycles_to_failure_N_i": N_i,
            "damage_fraction": d_i,
        })

    return {
        "blocks": details,
        "total_damage_D": total_D,
        "failure_predicted": total_D >= 1.0,
        "repeats_to_failure": (1.0 / total_D) if total_D > 0 else float("inf"),
        "note": "regla de Miner: dano lineal acumulado, no captura efectos de secuencia de carga (orden de los bloques)",
    }


def _validate():
    checks = []

    # Caso 1: round-trip Basquin -- forward (N->sigma_a) e inverso (sigma_a->N) consistentes
    sigma_f_prime, b = 900.0, -0.09
    N_target = 1e5
    sigma_a_fwd = sigma_f_prime * ((2 * N_target) ** b)
    r1 = _basquin_life(sigma_a_fwd, sigma_f_prime, b)
    ok1 = abs(r1["cycles_to_failure"] - N_target) / N_target < 1e-6
    checks.append(("basquin_roundtrip_consistency", ok1))

    # Caso 2: sigma_a mas alto -> menos ciclos a falla (monotonia)
    r2a = _basquin_life(200.0, sigma_f_prime, b)
    r2b = _basquin_life(400.0, sigma_f_prime, b)
    ok2 = r2b["cycles_to_failure"] < r2a["cycles_to_failure"]
    checks.append(("basquin_higher_stress_fewer_cycles", ok2))

    # Caso 3: Goodman con sigma_m=0 -> sigma_a_eq == sigma_a (sin correccion)
    r3 = _goodman_equivalent(100.0, 0.0, 500.0)
    ok3 = abs(r3["sigma_a_equivalent_mpa"] - 100.0) < 1e-9
    checks.append(("goodman_zero_mean_no_correction", ok3))

    # Caso 4: Goodman con sigma_m>0 -> sigma_a_eq > sigma_a (correccion penaliza)
    r4 = _goodman_equivalent(100.0, 200.0, 500.0)
    ok4 = r4["sigma_a_equivalent_mpa"] > 100.0
    checks.append(("goodman_positive_mean_increases_equivalent", ok4))

    # Caso 5: Miner con un solo bloque, n_i == N_i -> D == 1 (falla justo en el limite)
    life5 = _basquin_life(150.0, sigma_f_prime, b)
    r5 = _miner_damage([{"stress_amplitude_mpa": 150.0, "cycles_applied": life5["cycles_to_failure"]}], sigma_f_prime, b)
    ok5 = abs(r5["total_damage_D"] - 1.0) < 1e-6 and r5["failure_predicted"] is True
    checks.append(("miner_single_block_D_eq_1_at_life", ok5))

    # Caso 6: Miner con dos bloques -- D es la suma de las fracciones individuales
    blocks6 = [
        {"stress_amplitude_mpa": 150.0, "cycles_applied": life5["cycles_to_failure"] / 4.0},
        {"stress_amplitude_mpa": 150.0, "cycles_applied": life5["cycles_to_failure"] / 4.0},
    ]
    r6 = _miner_damage(blocks6, sigma_f_prime, b)
    ok6 = abs(r6["total_damage_D"] - 0.5) < 1e-6 and r6["failure_predicted"] is False
    checks.append(("miner_two_blocks_sum_damage", ok6))

    # Caso 7: Miner con mean_stress != 0 y sin sigma_u_mpa -> debe fallar con ValueError
    ok7 = False
    try:
        _miner_damage([{"stress_amplitude_mpa": 100.0, "mean_stress_mpa": 50.0, "cycles_applied": 1000}], sigma_f_prime, b)
    except ValueError:
        ok7 = True
    checks.append(("miner_missing_sigma_u_raises", ok7))

    passed = sum(1 for _, ok in checks if ok)
    return {
        "mode": "validate",
        "checks": [{"name": n, "passed": ok} for n, ok in checks],
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks),
    }


FATIGUE_ANALYSIS_TOOL_SCHEMA = {
    "name": "fatigue_analysis_tool",
    "description": (
        "Fatiga ciclica de componentes mecanicos (ej. tibia/pylon o pie protesico bajo carga "
        "repetida de marcha): basquin_life calcula ciclos a falla via la ecuacion de Basquin "
        "(sigma_a = sigma_f' * (2N)^b, regimen de alto ciclo); goodman_equivalent aplica la "
        "correccion de tension media de Goodman modificado; miner_damage acumula dano lineal "
        "(regla de Miner, D=sum(n_i/N_i)) sobre un espectro de bloques de carga con distinta "
        "amplitud/tension media/ciclos aplicados, y predice si D>=1 (falla). No incluye base de "
        "datos de parametros por material -- sigma_f', b y sigma_u deben proveerse (dependen del "
        "proceso de fabricacion, no solo del material nominal)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["basquin_life", "goodman_equivalent", "miner_damage", "validate"],
                "description": "Operacion a realizar, o 'validate' para autotest",
            },
            "sigma_a_mpa": {"type": "number", "description": "basquin_life/goodman_equivalent: amplitud de tension del ciclo, MPa"},
            "sigma_f_prime_mpa": {"type": "number", "description": "basquin_life/miner_damage: coeficiente de resistencia a la fatiga del material/proceso, MPa"},
            "b": {"type": "number", "description": "basquin_life/miner_damage: exponente de Basquin (negativo, tipicamente -0.05 a -0.15)"},
            "sigma_m_mpa": {"type": "number", "description": "goodman_equivalent: tension media del ciclo, MPa"},
            "sigma_u_mpa": {"type": "number", "description": "goodman_equivalent/miner_damage: resistencia ultima a la traccion, MPa (requerida solo si algun bloque tiene mean_stress_mpa != 0)"},
            "blocks": {
                "type": "array",
                "description": "miner_damage: espectro de bloques de carga, cada uno {stress_amplitude_mpa, cycles_applied, mean_stress_mpa? (default 0)}",
                "items": {"type": "object"},
            },
        },
        "required": ["mode"],
    },
}


def compute_fatigue_analysis_tool(mode, **kwargs):
    if mode == "validate":
        return _validate()
    elif mode == "basquin_life":
        req = ["sigma_a_mpa", "sigma_f_prime_mpa", "b"]
        missing = [k for k in req if kwargs.get(k) is None]
        if missing:
            raise ValueError(f"basquin_life requiere: {missing}")
        return {"mode": mode, **_basquin_life(*(float(kwargs[k]) for k in req))}
    elif mode == "goodman_equivalent":
        req = ["sigma_a_mpa", "sigma_m_mpa", "sigma_u_mpa"]
        missing = [k for k in req if kwargs.get(k) is None]
        if missing:
            raise ValueError(f"goodman_equivalent requiere: {missing}")
        return {"mode": mode, **_goodman_equivalent(*(float(kwargs[k]) for k in req))}
    elif mode == "miner_damage":
        blocks = kwargs.get("blocks")
        sigma_f_prime = kwargs.get("sigma_f_prime_mpa")
        b = kwargs.get("b")
        if not blocks or sigma_f_prime is None or b is None:
            raise ValueError("miner_damage requiere 'blocks', 'sigma_f_prime_mpa' y 'b'")
        sigma_u = kwargs.get("sigma_u_mpa")
        return {"mode": mode, **_miner_damage(blocks, float(sigma_f_prime), float(b), float(sigma_u) if sigma_u is not None else None)}
    else:
        raise ValueError(f"Modo desconocido: {mode}")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_fatigue_analysis_tool(mode="validate"), indent=2, ensure_ascii=False))


try:
    from tool_registry import register_tool as _register_tool_real
    _register_tool_real(
        name="fatigue_analysis_tool",
        schema=FATIGUE_ANALYSIS_TOOL_SCHEMA,
        handler=lambda args: compute_fatigue_analysis_tool(
            args.get("mode"),
            **{k: v for k, v in args.items() if k != "mode"}
        ),
    )
except ImportError:
    pass
