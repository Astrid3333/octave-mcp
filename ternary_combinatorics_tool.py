"""
ternary_combinatorics_tool.py

Diseños Ternarios Balanceados (BTD, "Balanced Ternary Designs"): arreglos
combinatorios de V puntos en B bloques (multiconjuntos), donde cada punto
puede aparecer 0, 1 o 2 veces en un bloque dado. Notacion estandar de la
literatura (Billington et al.): BTD(V, B; rho1, rho2, R; K, Lambda), donde:

  - rho1[v] = # de bloques en los que el punto v aparece exactamente 1 vez
  - rho2[v] = # de bloques en los que el punto v aparece exactamente 2 veces
  - R[v]    = rho1[v] + 2*rho2[v]  (replicacion total del punto v)
  - K[b]    = suma de multiplicidades en el bloque b (tamano del bloque)
  - Lambda[{x,y}] = suma sobre bloques de (mult_x_en_bloque * mult_y_en_bloque)

Un diseno es una BTD regular si rho1, rho2, K y Lambda son constantes a
traves de todos los puntos/bloques/pares respectivamente.

Referencia de la condicion usada en validate(): V ≡ 0 (mod 3) es condicion
necesaria y suficiente para la existencia de una BTD regular de bloque 3,
indice 2, con rho2=1 (Billington, "Balanced ternary designs with block
size three"). El ejemplo de validate() es una construccion propia (no una
tabla citada de un paper) que se verifica aritmeticamente en tiempo de
ejecucion y satisface esa condicion.
"""

from itertools import combinations


def _develop_cyclic(V, base_block):
    """
    Desarrolla un bloque base ciclicamente modulo V: genera V bloques,
    cada uno el bloque base desplazado por 0..V-1.

    base_block: dict {offset_int: multiplicidad_int (1 o 2)}
    Devuelve: lista de V dicts {punto_int: multiplicidad_int}
    """
    blocks = []
    for shift in range(V):
        blk = {}
        for off, m in base_block.items():
            p = (off + shift) % V
            blk[p] = m
        blocks.append(blk)
    return blocks


def _verify_btd(V, blocks):
    """
    Calcula rho1/rho2/R por punto, K por bloque, y Lambda por par de
    puntos distintos. Lanza ValueError si algun punto esta fuera de
    rango [0,V) o si alguna multiplicidad no es 1 o 2.
    """
    rho1 = [0] * V
    rho2 = [0] * V
    K_list = []

    for blk in blocks:
        k = 0
        for p, m in blk.items():
            if not (0 <= p < V):
                raise ValueError(f"punto {p} fuera de rango [0,{V})")
            if m == 1:
                rho1[p] += 1
            elif m == 2:
                rho2[p] += 1
            else:
                raise ValueError(f"multiplicidad invalida {m} para punto {p} (debe ser 1 o 2)")
            k += m
        K_list.append(k)

    R_list = [rho1[p] + 2 * rho2[p] for p in range(V)]

    lam = {}
    for a, b in combinations(range(V), 2):
        total = 0
        for blk in blocks:
            total += blk.get(a, 0) * blk.get(b, 0)
        lam[(a, b)] = total

    rho1_values = set(rho1)
    rho2_values = set(rho2)
    K_values = set(K_list)
    lambda_values = set(lam.values())

    regular = len(rho1_values) == 1 and len(rho2_values) == 1
    constant_block_size = len(K_values) == 1
    balanced_pairs = len(lambda_values) == 1
    is_btd = regular and constant_block_size and balanced_pairs

    return {
        "V": V,
        "B": len(blocks),
        "rho1": rho1,
        "rho2": rho2,
        "R": R_list,
        "K": K_list,
        "Lambda_pairs": {f"{a}-{b}": v for (a, b), v in lam.items()},
        "regular": regular,
        "constant_block_size": constant_block_size,
        "balanced_pairs": balanced_pairs,
        "is_btd": is_btd,
        "rho1_value": rho1[0] if regular else None,
        "rho2_value": rho2[0] if regular else None,
        "R_value": R_list[0] if regular else None,
        "K_value": K_list[0] if constant_block_size else None,
        "Lambda_value": next(iter(lambda_values)) if balanced_pairs else None,
    }


def compute_ternary_combinatorics(mode="validate", V=None, base_block=None, blocks=None):
    """
    mode:
      - "generate_cyclic": requiere V y base_block (dict offset(str)->
        multiplicidad(1 o 2)). Desarrolla el bloque base ciclicamente mod
        V y devuelve el diseno generado junto con su reporte de verify.
      - "verify": requiere V y blocks (lista de dicts point(str)->
        multiplicidad(1 o 2)). Calcula rho1/rho2/R/K/Lambda y confirma si
        es una BTD regular.
      - "validate": autochequeos internos (ver _validate_ternary_combinatorics).
    """
    if mode == "generate_cyclic":
        if V is None or base_block is None:
            return {"error": "mode='generate_cyclic' requiere 'V' y 'base_block' (dict offset->multiplicidad 1 o 2)"}
        try:
            base = {int(k): int(v) for k, v in base_block.items()}
            developed = _develop_cyclic(V, base)
            report = _verify_btd(V, developed)
        except (ValueError, TypeError) as e:
            return {"error": str(e)}
        blocks_out = [{str(p): m for p, m in blk.items()} for blk in developed]
        return {"base_block": {str(k): v for k, v in base.items()}, "blocks": blocks_out, **report}

    if mode == "verify":
        if V is None or blocks is None:
            return {"error": "mode='verify' requiere 'V' y 'blocks' (lista de dicts point->multiplicidad)"}
        try:
            parsed_blocks = [{int(k): int(v) for k, v in blk.items()} for blk in blocks]
            return _verify_btd(V, parsed_blocks)
        except (ValueError, TypeError) as e:
            return {"error": str(e)}

    if mode == "validate":
        return _validate_ternary_combinatorics()

    return {"error": f"modo desconocido: {mode!r} (validos: generate_cyclic, verify, validate)"}


def _validate_ternary_combinatorics():
    checks = []

    # --- construccion ciclica autoconsistente: V=3, bloque base {0:1, 1:2} ---
    # Cumple la condicion necesaria y suficiente V ≡ 0 (mod 3) para una BTD
    # regular de bloque 3, indice 2, rho2=1 (Billington). No es una tabla
    # citada de un paper -- se verifica aritmeticamente aca mismo.
    base = {0: 1, 1: 2}
    developed = _develop_cyclic(3, base)
    report = _verify_btd(3, developed)
    ok_valid_btd = (
        report["is_btd"] is True
        and report["rho1_value"] == 1
        and report["rho2_value"] == 1
        and report["R_value"] == 3
        and report["K_value"] == 3
        and report["Lambda_value"] == 2
    )
    checks.append({
        "name": "generate_cyclic_V3_produce_btd_regular_rho1_1_rho2_1_R3_K3_L2",
        "passed": bool(ok_valid_btd),
        "detail": (
            f"is_btd={report['is_btd']} rho1={report['rho1_value']} "
            f"rho2={report['rho2_value']} R={report['R_value']} "
            f"K={report['K_value']} Lambda={report['Lambda_value']}"
        ),
    })

    # --- verify() standalone sobre el mismo diseno, no solo via generate_cyclic ---
    blocks_str = [{str(p): m for p, m in blk.items()} for blk in developed]
    report2 = compute_ternary_combinatorics(mode="verify", V=3, blocks=blocks_str)
    checks.append({
        "name": "verify_standalone_coincide_con_generate_cyclic",
        "passed": bool(report2.get("is_btd") is True and report2.get("Lambda_value") == 2),
    })

    # --- diseno incompleto (se quita un bloque) debe detectarse como no balanceado ---
    broken_blocks_str = blocks_str[:2]
    broken_report = compute_ternary_combinatorics(mode="verify", V=3, blocks=broken_blocks_str)
    ok_detects_broken = broken_report.get("is_btd") is False
    checks.append({
        "name": "diseno_incompleto_detectado_como_no_balanceado",
        "passed": bool(ok_detects_broken),
        "detail": f"is_btd={broken_report.get('is_btd')} (se esperaba False)",
    })

    # --- multiplicidad invalida (3 repeticiones) debe dar error, no crash ---
    bad = compute_ternary_combinatorics(mode="verify", V=3, blocks=[{"0": 3, "1": 1}])
    checks.append({
        "name": "multiplicidad_invalida_mayor_a_2_da_error_no_crash",
        "passed": "error" in bad,
    })

    # --- punto fuera de rango debe dar error, no crash ---
    bad_range = compute_ternary_combinatorics(mode="verify", V=3, blocks=[{"5": 1}])
    checks.append({
        "name": "punto_fuera_de_rango_da_error_no_crash",
        "passed": "error" in bad_range,
    })

    # --- modo desconocido debe dar error, no crash ---
    bad_mode = compute_ternary_combinatorics(mode="modo_que_no_existe")
    checks.append({
        "name": "modo_desconocido_da_error_no_crash",
        "passed": "error" in bad_mode,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"validation_passed": all_passed, "n_checks": len(checks), "checks": checks}


TERNARY_COMBINATORICS_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["generate_cyclic", "verify", "validate"],
            "default": "validate",
        },
        "V": {"type": "integer", "description": "Numero de puntos del diseno"},
        "base_block": {
            "type": "object",
            "description": (
                "Solo generate_cyclic: dict offset(str)->multiplicidad(1 o 2), "
                "se desarrolla ciclicamente modulo V"
            ),
        },
        "blocks": {
            "type": "array",
            "description": (
                "Solo verify: lista de bloques, cada uno un dict point(str)->"
                "multiplicidad(1 o 2)"
            ),
        },
    },
    "required": ["mode"],
}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_ternary_combinatorics(mode="validate"), indent=2, ensure_ascii=False))


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass


def _ternary_combinatorics_handler(args):
    return compute_ternary_combinatorics(**args)


register_tool(
    name="ternary_combinatorics_tool",
    schema={
        "name": "ternary_combinatorics_tool",
        "description": (
            "Disenos Ternarios Balanceados (BTD): generate_cyclic construye un "
            "diseno por desarrollo ciclico de un bloque base modulo V y lo "
            "verifica; verify calcula rho1/rho2/R/K/Lambda de un diseno dado "
            "(bloques como multiconjuntos, cada punto aparece 0/1/2 veces) y "
            "confirma si es una BTD regular (replicacion constante por punto, "
            "tamano de bloque constante, cada par de puntos co-ocurre Lambda "
            "veces contando multiplicidad); validate corre autochequeos contra "
            "una construccion ciclica autoconsistente (V=3, deteccion de "
            "disenos rotos/invalidos)."
        ),
        "inputSchema": TERNARY_COMBINATORICS_SCHEMA,
    },
    handler=_ternary_combinatorics_handler,
)
