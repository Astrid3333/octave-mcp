"""
abstract_algebra_tool.py -- algebra abstracta sobre estructuras finitas
CHICAS (pensado para orden <= ~8, por el costo combinatorio de
verificar isomorfismos por fuerza bruta). Base de casi cualquier curso
de algebra abstracta: tablas de Cayley, verificacion de axiomas de
grupo/anillo/cuerpo, e isomorfismos entre estructuras del mismo orden.

Todo por fuerza bruta sobre tablas explicitas (listas de listas), sin
libreria de teoria de grupos externa -- transparente y facil de
auditar a mano para un elemento de orden 4 u 8, que es el uso tipico
(verificar la tarea, generar contraejemplos, chequear una construccion
antes de generalizarla).

Modes:

1. cayley_table -- genera la tabla de Cayley de una estructura preset
   (suma o multiplicacion modular Z_n, grupo simetrico S_n via
   permutaciones, grupo diedral D_n) o valida una tabla explicita dada
   por el usuario.

2. verify_group_axioms -- dado 'elementos' y 'tabla' (tabla de Cayley
   NxN, table[i][j] = indice del elemento resultado de elementos[i]*elementos[j]),
   verifica cerradura, asociatividad (O(n^3), fuerza bruta), existencia
   de identidad, y existencia de inverso para cada elemento. Si todo
   pasa, es un grupo; reporta ademas si es abeliano (tabla simetrica).

3. verify_ring_field_axioms -- dado 'elementos', 'tabla_suma' y
   'tabla_mult', verifica axiomas de anillo (grupo abeliano bajo suma,
   monoide asociativo bajo multiplicacion, distributividad en ambos
   lados) y, si ademas hay inverso multiplicativo para todo elemento
   no-cero y la multiplicacion es conmutativa, confirma que es cuerpo.

4. check_isomorphism -- dadas dos tablas de Cayley del mismo orden,
   busca por fuerza bruta (sobre todas las permutaciones -- por eso el
   limite de orden chico) un isomorfismo de grupo. Si lo encuentra,
   devuelve el mapeo; si no, confirma que NO son isomorfos (para orden
   chico la busqueda es exhaustiva, asi que la respuesta negativa es
   definitiva, no una sospecha).
"""
from itertools import permutations, product


MAX_ORDEN_ISOMORFISMO = 8


def _tabla_modular(n, op):
    if op == "add":
        return [[(i + j) % n for j in range(n)] for i in range(n)]
    if op == "mult":
        return [[(i * j) % n for j in range(n)] for i in range(n)]
    raise ValueError(f"op debe ser 'add' o 'mult', recibido {op!r}")


def _tabla_simetrico(n):
    elems = list(permutations(range(n)))
    idx = {e: i for i, e in enumerate(elems)}
    tabla = []
    for a in elems:
        fila = []
        for b in elems:
            comp = tuple(a[b[x]] for x in range(n))
            fila.append(idx[comp])
        tabla.append(fila)
    nombres = ["".join(str(x) for x in e) for e in elems]
    return nombres, tabla


def _tabla_diedral(n):
    elems = [(0, k) for k in range(n)] + [(1, k) for k in range(n)]
    idx = {e: i for i, e in enumerate(elems)}

    def compone(a, b):
        ta, ka = a
        tb, kb = b
        if ta == 0 and tb == 0:
            return (0, (ka + kb) % n)
        if ta == 0 and tb == 1:
            return (1, (ka + kb) % n)
        if ta == 1 and tb == 0:
            return (1, (ka - kb) % n)
        return (0, (ka - kb) % n)

    tabla = [[idx[compone(a, b)] for b in elems] for a in elems]
    nombres = [("r%d" % k if t == 0 else "sr%d" % k) for (t, k) in elems]
    return nombres, tabla


def _preset_cayley_table(preset, n):
    if preset == "Zn_add":
        elementos = [str(i) for i in range(n)]
        return elementos, _tabla_modular(n, "add")
    if preset == "Zn_mult":
        elementos = [str(i) for i in range(n)]
        return elementos, _tabla_modular(n, "mult")
    if preset == "Sn":
        return _tabla_simetrico(n)
    if preset == "Dn":
        return _tabla_diedral(n)
    return None, None


def _es_cerrada(elementos, tabla):
    n = len(elementos)
    if len(tabla) != n:
        return False, f"la tabla tiene {len(tabla)} filas, se esperaban {n}"
    for i, fila in enumerate(tabla):
        if len(fila) != n:
            return False, f"fila {i} tiene {len(fila)} columnas, se esperaban {n}"
        for j, v in enumerate(fila):
            if not isinstance(v, int) or v < 0 or v >= n:
                return False, f"tabla[{i}][{j}]={v!r} no es un indice valido de elemento (0..{n - 1})"
    return True, None


def _es_asociativa(tabla):
    n = len(tabla)
    for a, b, c in product(range(n), repeat=3):
        ab = tabla[a][b]
        bc = tabla[b][c]
        if tabla[ab][c] != tabla[a][bc]:
            return False, [a, b, c]
    return True, None


def _encontrar_identidad(tabla):
    n = len(tabla)
    for e in range(n):
        if all(tabla[e][a] == a and tabla[a][e] == a for a in range(n)):
            return e
    return None


def _encontrar_inversos(tabla, identidad):
    n = len(tabla)
    inversos = {}
    for a in range(n):
        inv = None
        for b in range(n):
            if tabla[a][b] == identidad and tabla[b][a] == identidad:
                inv = b
                break
        if inv is None:
            return None, a
        inversos[a] = inv
    return inversos, None


def _es_conmutativa(tabla):
    n = len(tabla)
    return all(tabla[i][j] == tabla[j][i] for i in range(n) for j in range(n))


def _verify_group_axioms(elementos, tabla):
    n = len(elementos)
    ok_cerrada, razon_cerrada = _es_cerrada(elementos, tabla)
    if not ok_cerrada:
        return {"es_grupo": False, "fallo_en": "cerradura", "detalle": razon_cerrada}

    ok_asoc, contraejemplo = _es_asociativa(tabla)
    if not ok_asoc:
        a, b, c = contraejemplo
        return {"es_grupo": False, "fallo_en": "asociatividad",
                "contraejemplo": {"a": elementos[a], "b": elementos[b], "c": elementos[c]}}

    identidad = _encontrar_identidad(tabla)
    if identidad is None:
        return {"es_grupo": False, "fallo_en": "identidad", "detalle": "ningun elemento actua como identidad de dos lados"}

    inversos, elem_sin_inverso = _encontrar_inversos(tabla, identidad)
    if inversos is None:
        return {"es_grupo": False, "fallo_en": "inverso",
                "detalle": f"el elemento {elementos[elem_sin_inverso]!r} no tiene inverso"}

    return {
        "es_grupo": True,
        "orden": n,
        "identidad": elementos[identidad],
        "abeliano": _es_conmutativa(tabla),
        "inversos": {elementos[a]: elementos[b] for a, b in inversos.items()},
    }


def _verify_ring_field_axioms(elementos, tabla_suma, tabla_mult):
    n = len(elementos)
    grupo_suma = _verify_group_axioms(elementos, tabla_suma)
    if not grupo_suma["es_grupo"]:
        return {"es_anillo": False, "fallo_en": f"suma no forma grupo ({grupo_suma['fallo_en']})", "detalle_suma": grupo_suma}
    if not grupo_suma["abeliano"]:
        return {"es_anillo": False, "fallo_en": "suma no es conmutativa (se requiere grupo abeliano bajo suma)"}

    ok_cerrada, razon = _es_cerrada(elementos, tabla_mult)
    if not ok_cerrada:
        return {"es_anillo": False, "fallo_en": "multiplicacion no cerrada", "detalle": razon}
    ok_asoc, contraejemplo = _es_asociativa(tabla_mult)
    if not ok_asoc:
        a, b, c = contraejemplo
        return {"es_anillo": False, "fallo_en": "multiplicacion no asociativa",
                 "contraejemplo": {"a": elementos[a], "b": elementos[b], "c": elementos[c]}}

    cero = _encontrar_identidad(tabla_suma)
    for a, b, c in product(range(n), repeat=3):
        izq = tabla_mult[a][tabla_suma[b][c]]
        der = tabla_suma[tabla_mult[a][b]][tabla_mult[a][c]]
        if izq != der:
            return {"es_anillo": False, "fallo_en": "distributividad por izquierda",
                     "contraejemplo": {"a": elementos[a], "b": elementos[b], "c": elementos[c]}}
        izq2 = tabla_mult[tabla_suma[a][b]][c]
        der2 = tabla_suma[tabla_mult[a][c]][tabla_mult[b][c]]
        if izq2 != der2:
            return {"es_anillo": False, "fallo_en": "distributividad por derecha",
                     "contraejemplo": {"a": elementos[a], "b": elementos[b], "c": elementos[c]}}

    resultado = {
        "es_anillo": True,
        "orden": n,
        "cero": elementos[cero],
        "mult_conmutativa": _es_conmutativa(tabla_mult),
    }

    identidad_mult = _encontrar_identidad(tabla_mult)
    resultado["tiene_identidad_multiplicativa"] = identidad_mult is not None
    if identidad_mult is not None:
        resultado["uno"] = elementos[identidad_mult]

    if resultado["mult_conmutativa"] and identidad_mult is not None:
        no_cero = [a for a in range(n) if a != cero]
        todos_invertibles = True
        for a in no_cero:
            tiene_inverso = any(tabla_mult[a][b] == identidad_mult for b in no_cero)
            if not tiene_inverso:
                todos_invertibles = False
                break
        resultado["es_cuerpo"] = todos_invertibles
    else:
        resultado["es_cuerpo"] = False

    return resultado


def _check_isomorphism(elementos_a, tabla_a, elementos_b, tabla_b):
    n = len(elementos_a)
    if len(elementos_b) != n:
        return {"isomorfos": False, "razon": f"ordenes distintos ({n} vs {len(elementos_b)}) -- no pueden ser isomorfos"}
    if n > MAX_ORDEN_ISOMORFISMO:
        return {"error": f"orden {n} excede el maximo {MAX_ORDEN_ISOMORFISMO} para busqueda por fuerza bruta sobre permutaciones"}

    ga = _verify_group_axioms(elementos_a, tabla_a)
    gb = _verify_group_axioms(elementos_b, tabla_b)
    if not ga["es_grupo"] or not gb["es_grupo"]:
        return {"isomorfos": False, "razon": "al menos una de las dos estructuras no es un grupo, isomorfismo de grupo no aplica",
                "grupo_a": ga, "grupo_b": gb}

    if ga["abeliano"] != gb["abeliano"]:
        return {"isomorfos": False, "razon": "un grupo es abeliano y el otro no -- propiedad invariante bajo isomorfismo, no pueden ser isomorfos"}

    for perm in permutations(range(n)):
        ok = True
        for i in range(n):
            for j in range(n):
                if perm[tabla_a[i][j]] != tabla_b[perm[i]][perm[j]]:
                    ok = False
                    break
            if not ok:
                break
        if ok:
            mapeo = {elementos_a[i]: elementos_b[perm[i]] for i in range(n)}
            return {"isomorfos": True, "mapeo": mapeo}

    return {"isomorfos": False, "razon": "busqueda exhaustiva sobre todas las permutaciones no encontro ningun isomorfismo -- respuesta definitiva para este orden, no una sospecha"}


def compute_abstract_algebra(mode="validate", preset=None, n=None,
                              elementos=None, tabla=None,
                              tabla_suma=None, tabla_mult=None,
                              elementos_a=None, tabla_a=None,
                              elementos_b=None, tabla_b=None):

    if mode == "validate":
        elems4, tabla4 = _preset_cayley_table("Zn_add", 4)
        g4 = _verify_group_axioms(elems4, tabla4)
        ok_z4 = g4["es_grupo"] and g4["abeliano"] and g4["orden"] == 4

        elems_v4 = ["e", "a", "b", "c"]
        tabla_v4 = [
            [0, 1, 2, 3],
            [1, 0, 3, 2],
            [2, 3, 0, 1],
            [3, 2, 1, 0],
        ]
        gv4 = _verify_group_axioms(elems_v4, tabla_v4)
        ok_v4 = gv4["es_grupo"] and gv4["abeliano"] and gv4["orden"] == 4

        iso_z4_v4 = _check_isomorphism(elems4, tabla4, elems_v4, tabla_v4)
        ok_no_iso = iso_z4_v4["isomorfos"] is False

        elems5add, tabla5add = _preset_cayley_table("Zn_add", 5)
        elems5mult, tabla5mult = _preset_cayley_table("Zn_mult", 5)
        cuerpo5 = _verify_ring_field_axioms(elems5add, tabla5add, tabla5mult)
        ok_cuerpo5 = cuerpo5.get("es_anillo") and cuerpo5.get("es_cuerpo") is True

        elems4add, tabla4add = _preset_cayley_table("Zn_add", 4)
        elems4mult, tabla4mult = _preset_cayley_table("Zn_mult", 4)
        anillo4 = _verify_ring_field_axioms(elems4add, tabla4add, tabla4mult)
        ok_anillo4_no_cuerpo = anillo4.get("es_anillo") and anillo4.get("es_cuerpo") is False

        nombres_s3, tabla_s3 = _preset_cayley_table("Sn", 3)
        g_s3 = _verify_group_axioms(nombres_s3, tabla_s3)
        ok_s3_no_abeliano = g_s3["es_grupo"] and g_s3["abeliano"] is False and g_s3["orden"] == 6

        nombres_d3, tabla_d3 = _preset_cayley_table("Dn", 3)
        iso_d3_s3 = _check_isomorphism(nombres_d3, tabla_d3, nombres_s3, tabla_s3)
        ok_d3_s3_iso = iso_d3_s3.get("isomorfos") is True

        ok = bool(ok_z4 and ok_v4 and ok_no_iso and ok_cuerpo5 and ok_anillo4_no_cuerpo and ok_s3_no_abeliano and ok_d3_s3_iso)
        return {
            "ok": ok,
            "checks": {
                "Z4_es_grupo_abeliano": bool(ok_z4),
                "Klein_V4_es_grupo_abeliano": bool(ok_v4),
                "Z4_no_isomorfo_a_V4": bool(ok_no_iso),
                "Z5_bajo_suma_y_mult_es_cuerpo": bool(ok_cuerpo5),
                "Z4_es_anillo_no_cuerpo": bool(ok_anillo4_no_cuerpo),
                "S3_es_grupo_no_abeliano_orden6": bool(ok_s3_no_abeliano),
                "D3_isomorfo_a_S3": bool(ok_d3_s3_iso),
            },
            "detalle_Z4_vs_V4": iso_z4_v4,
            "detalle_Z5_cuerpo": {k: v for k, v in cuerpo5.items() if k != "tabla"},
        }

    if mode == "cayley_table":
        if preset is None or n is None:
            return {"error": "mode='cayley_table' requiere 'preset' (Zn_add, Zn_mult, Sn, Dn) y 'n'"}
        elementos_out, tabla_out = _preset_cayley_table(preset, n)
        if elementos_out is None:
            return {"error": f"preset desconocido: {preset!r} (validos: Zn_add, Zn_mult, Sn, Dn)"}
        return {"elementos": elementos_out, "tabla": tabla_out, "orden": len(elementos_out)}

    if mode == "verify_group_axioms":
        if elementos is None or tabla is None:
            return {"error": "mode='verify_group_axioms' requiere 'elementos' (lista de nombres) y 'tabla' (matriz NxN de indices)"}
        return _verify_group_axioms(elementos, tabla)

    if mode == "verify_ring_field_axioms":
        if elementos is None or tabla_suma is None or tabla_mult is None:
            return {"error": "mode='verify_ring_field_axioms' requiere 'elementos', 'tabla_suma' y 'tabla_mult'"}
        return _verify_ring_field_axioms(elementos, tabla_suma, tabla_mult)

    if mode == "check_isomorphism":
        if elementos_a is None or tabla_a is None or elementos_b is None or tabla_b is None:
            return {"error": "mode='check_isomorphism' requiere 'elementos_a', 'tabla_a', 'elementos_b', 'tabla_b'"}
        return _check_isomorphism(elementos_a, tabla_a, elementos_b, tabla_b)

    return {"error": f"modo desconocido: {mode!r} (validos: cayley_table, verify_group_axioms, verify_ring_field_axioms, check_isomorphism, validate)"}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_abstract_algebra(mode="validate"), indent=2, ensure_ascii=False))
