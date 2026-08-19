"""
public_data_ingest_tool.py

Herramientas de calidad e ingesta de datos publicos: deteccion de outliers,
score de calidad de registros, y estimacion de duplicados exactos/difusos.

Modos:
  - outlier_detection_zscore: deteccion via z-score (media/std), con nota
    documentada sobre el efecto de "masking" (un outlier extremo infla el
    std y puede terminar enmascarando su propio z-score).
  - outlier_detection_iqr: deteccion via rango intercuartil (Q1/Q3), mas
    robusto que z-score ante outliers extremos porque no depende de la
    media ni el desvio estandar.
  - data_quality_score: completeness (fraccion de celdas no vacias),
    uniqueness (1 - fraccion de duplicados exactos), validity (fraccion de
    valores que pasan validadores opcionales), combinadas en score compuesto
    ponderado.
  - deduplication_estimate: duplicados exactos por clave y duplicados
    difusos por similitud Jaccard sobre tokens de los campos clave.
  - validate: suite de 10 checks.

confidence_flag: "alta" en zscore/IQR/completeness (formulas estandar
cerradas); "media" en deduplicacion difusa (el umbral Jaccard es heuristico,
no hay ground truth de "duplicado real" sin revision humana).
"""

import json
import sys


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

def _outlier_detection_zscore(params):
    values = [float(v) for v in params["values"]]
    threshold = float(params.get("threshold", 3.0))
    n = len(values)
    if n == 0:
        raise ValueError("values no puede estar vacio")
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / n
    std = var ** 0.5
    if std == 0:
        zscores = [0.0] * n
    else:
        zscores = [(x - mean) / std for x in values]
    outlier_indices = [i for i, z in enumerate(zscores) if abs(z) > threshold]
    return {
        "n": n,
        "mean": round(mean, 6),
        "std": round(std, 6),
        "threshold": threshold,
        "zscores": [round(z, 6) for z in zscores],
        "outlier_indices": outlier_indices,
        "n_outliers": len(outlier_indices),
        "note": (
            "El z-score puede sufrir 'masking': un outlier extremo infla el std "
            "y puede terminar enmascarando su propio z-score (quedar por debajo "
            "del umbral). Para datasets con outliers severos o multiples, "
            "preferir outlier_detection_iqr."
        ),
    }


def _outlier_detection_iqr(params):
    original_values = [float(v) for v in params["values"]]
    if not original_values:
        raise ValueError("values no puede estar vacio")
    k = float(params.get("k", 1.5))
    sorted_values = sorted(original_values)

    def percentile(sorted_vals, p):
        idx = p * (len(sorted_vals) - 1)
        lo = int(idx)
        hi = min(lo + 1, len(sorted_vals) - 1)
        frac = idx - lo
        return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac

    q1 = percentile(sorted_values, 0.25)
    q3 = percentile(sorted_values, 0.75)
    iqr = q3 - q1
    lower_bound = q1 - k * iqr
    upper_bound = q3 + k * iqr
    outlier_indices = [
        i for i, v in enumerate(original_values) if v < lower_bound or v > upper_bound
    ]
    return {
        "n": len(original_values),
        "q1": round(q1, 6),
        "q3": round(q3, 6),
        "iqr": round(iqr, 6),
        "k": k,
        "lower_bound": round(lower_bound, 6),
        "upper_bound": round(upper_bound, 6),
        "outlier_indices": outlier_indices,
        "n_outliers": len(outlier_indices),
    }


def _data_quality_score(params):
    records = params["records"]
    if not records:
        raise ValueError("records no puede estar vacio")
    required_fields = params.get("required_fields") or list(records[0].keys())
    n = len(records)

    total_cells = n * len(required_fields)
    filled = sum(
        1 for r in records for f in required_fields if r.get(f) not in (None, "", [])
    )
    completeness = filled / total_cells if total_cells else 1.0

    seen = set()
    duplicates = 0
    for r in records:
        key = tuple(sorted((k, str(v)) for k, v in r.items()))
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    uniqueness = 1 - duplicates / n

    validators = params.get("validators", {})
    if validators:
        valid_count = 0
        total_checks = 0
        for r in records:
            for f, rule in validators.items():
                total_checks += 1
                v = r.get(f)
                ok = True
                if rule.get("type") == "numeric":
                    try:
                        fv = float(v)
                        if "min" in rule and fv < rule["min"]:
                            ok = False
                        if "max" in rule and fv > rule["max"]:
                            ok = False
                    except (TypeError, ValueError):
                        ok = False
                elif rule.get("type") == "nonempty":
                    ok = v not in (None, "")
                if ok:
                    valid_count += 1
        validity = valid_count / total_checks if total_checks else 1.0
    else:
        validity = 1.0

    weights = params.get("weights", {"completeness": 0.4, "uniqueness": 0.3, "validity": 0.3})
    composite = (
        completeness * weights.get("completeness", 0.4)
        + uniqueness * weights.get("uniqueness", 0.3)
        + validity * weights.get("validity", 0.3)
    )

    return {
        "n_records": n,
        "completeness": round(completeness, 6),
        "uniqueness": round(uniqueness, 6),
        "validity": round(validity, 6),
        "composite_score": round(composite, 6),
        "n_duplicates": duplicates,
    }


def _deduplication_estimate(params):
    records = params["records"]
    if not records:
        raise ValueError("records no puede estar vacio")
    key_fields = params.get("key_fields")
    fuzzy_threshold = float(params.get("fuzzy_threshold", 0.85))
    n = len(records)

    def keyset(r):
        if key_fields:
            return tuple(str(r.get(f, "")).strip().lower() for f in key_fields)
        return tuple(sorted((k, str(v).strip().lower()) for k, v in r.items()))

    exact_groups = {}
    for i, r in enumerate(records):
        k = keyset(r)
        exact_groups.setdefault(k, []).append(i)
    exact_duplicates = sum(len(v) - 1 for v in exact_groups.values() if len(v) > 1)

    def tokenize(r):
        text = " ".join(str(r.get(f, "")) for f in (key_fields or r.keys()))
        return set(text.lower().split())

    reps = list(exact_groups.items())
    fuzzy_pairs = []
    for i in range(len(reps)):
        for j in range(i + 1, len(reps)):
            ridx_i = reps[i][1][0]
            ridx_j = reps[j][1][0]
            ti = tokenize(records[ridx_i])
            tj = tokenize(records[ridx_j])
            if not ti or not tj:
                continue
            jacc = len(ti & tj) / len(ti | tj)
            if jacc >= fuzzy_threshold:
                fuzzy_pairs.append({"i": ridx_i, "j": ridx_j, "jaccard": round(jacc, 4)})

    return {
        "n_records": n,
        "n_exact_groups": len(exact_groups),
        "exact_duplicates": exact_duplicates,
        "fuzzy_duplicate_pairs": fuzzy_pairs,
        "n_fuzzy_pairs": len(fuzzy_pairs),
        "estimated_total_duplicates": exact_duplicates + len(fuzzy_pairs),
    }


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

def _check(name, passed, **extra):
    return {"name": name, "passed": bool(passed), **extra}


def _validate():
    checks = []

    # z-score: media/std recuperados sobre datos generados manualmente
    values = [10.0, 12.0, 11.0, 13.0, 9.0, 10.0, 11.0, 12.0, 10.0, 50.0]
    z = _outlier_detection_zscore({"values": values, "threshold": 2.0})
    checks.append(_check(
        "zscore_flags_extreme_value_as_outlier",
        9 in z["outlier_indices"] or z["n_outliers"] >= 1,
        outlier_indices=z["outlier_indices"],
    ))
    checks.append(_check(
        "zscore_no_std_gives_zero_zscores",
        all(s == 0.0 for s in _outlier_detection_zscore({"values": [5.0] * 5})["zscores"]),
    ))

    # IQR: caso de masking conocido -- un outlier extremo aislado infla tanto el std
    # que su propio z-score puede quedar por debajo del umbral, mientras que IQR
    # (basado en cuartiles, no en media/std) sigue detectandolo con normalidad.
    masking_values = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 1000.0]
    iqr_result = _outlier_detection_iqr({"values": masking_values})
    checks.append(_check(
        "iqr_detects_extreme_outlier_robust_to_masking",
        9 in iqr_result["outlier_indices"],
        outlier_indices=iqr_result["outlier_indices"],
    ))
    checks.append(_check(
        "iqr_bounds_are_ordered",
        iqr_result["lower_bound"] <= iqr_result["q1"] <= iqr_result["q3"] <= iqr_result["upper_bound"],
        lower=iqr_result["lower_bound"], upper=iqr_result["upper_bound"],
    ))

    # Symmetric data: sin outliers, ni z-score ni IQR deberian marcar nada
    symmetric = [8.0, 9.0, 10.0, 11.0, 12.0, 9.0, 10.0, 11.0, 10.0, 10.0]
    z_sym = _outlier_detection_zscore({"values": symmetric})
    iqr_sym = _outlier_detection_iqr({"values": symmetric})
    checks.append(_check(
        "symmetric_data_no_outliers_flagged",
        z_sym["n_outliers"] == 0 and iqr_sym["n_outliers"] == 0,
        zscore_outliers=z_sym["n_outliers"], iqr_outliers=iqr_sym["n_outliers"],
    ))

    # Data quality: dataset completo, sin duplicados, sin validadores -> composite alto
    clean_records = [
        {"id": 1, "name": "a", "value": 10},
        {"id": 2, "name": "b", "value": 20},
        {"id": 3, "name": "c", "value": 30},
    ]
    dq_clean = _data_quality_score({"records": clean_records})
    checks.append(_check(
        "clean_dataset_gets_perfect_completeness_and_uniqueness",
        dq_clean["completeness"] == 1.0 and dq_clean["uniqueness"] == 1.0,
        completeness=dq_clean["completeness"], uniqueness=dq_clean["uniqueness"],
    ))

    # Data quality: con un duplicado exacto y un campo faltante -> composite baja
    dirty_records = [
        {"id": 1, "name": "a", "value": 10},
        {"id": 1, "name": "a", "value": 10},  # duplicado exacto
        {"id": 3, "name": "", "value": 30},   # campo faltante
    ]
    dq_dirty = _data_quality_score({"records": dirty_records})
    checks.append(_check(
        "dirty_dataset_scores_lower_than_clean",
        dq_dirty["composite_score"] < dq_clean["composite_score"],
        dirty_composite=dq_dirty["composite_score"], clean_composite=dq_clean["composite_score"],
    ))
    checks.append(_check(
        "dirty_dataset_detects_one_duplicate",
        dq_dirty["n_duplicates"] == 1,
        n_duplicates=dq_dirty["n_duplicates"],
    ))

    # Deduplicacion: exacta
    dedup_records = [
        {"id": 1, "email": "a@x.com", "name": "Ana Perez"},
        {"id": 2, "email": "a@x.com", "name": "Ana Perez"},
        {"id": 3, "email": "b@x.com", "name": "Bruno Diaz"},
    ]
    dedup = _deduplication_estimate({"records": dedup_records, "key_fields": ["email", "name"]})
    checks.append(_check(
        "deduplication_detects_exact_duplicate",
        dedup["exact_duplicates"] == 1,
        exact_duplicates=dedup["exact_duplicates"],
    ))

    # invalid_mode_raises
    try:
        compute_public_data_ingest("modo_inexistente", {})
        invalid_ok = False
    except ValueError:
        invalid_ok = True
    checks.append(_check("invalid_mode_raises", invalid_ok))

    return {"checks": checks, "validation_passed": all(c["passed"] for c in checks)}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def compute_public_data_ingest(mode, params):
    params = params or {}
    if mode == "outlier_detection_zscore":
        return _outlier_detection_zscore(params)
    elif mode == "outlier_detection_iqr":
        return _outlier_detection_iqr(params)
    elif mode == "data_quality_score":
        return _data_quality_score(params)
    elif mode == "deduplication_estimate":
        return _deduplication_estimate(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"modo desconocido: {mode}")


PUBLIC_DATA_INGEST_TOOL_SCHEMA = {
    "name": "public_data_ingest_tool",
    "description": (
        "Calidad e ingesta de datos publicos: outlier_detection_zscore (media/std, "
        "documenta el efecto de masking donde un outlier extremo infla el std y puede "
        "enmascarar su propio z-score), outlier_detection_iqr (rango intercuartil, "
        "robusto ante masking porque no depende de media/std), data_quality_score "
        "(completeness + uniqueness + validity combinadas en score compuesto ponderado), "
        "deduplication_estimate (duplicados exactos por clave y duplicados difusos por "
        "similitud Jaccard sobre tokens), validate (suite de 10 checks). confidence_flag "
        "'alta' en zscore/IQR/completeness (formulas cerradas), 'media' en deduplicacion "
        "difusa (umbral Jaccard heuristico, sin ground truth de duplicado real)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"mode": {"type": "string"}, "params": {"type": "object"}},
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        result = compute_public_data_ingest(req.get("mode", "validate"), req.get("params", {}))
        print(json.dumps(result, ensure_ascii=False, indent=2))


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

def _handle(args):
    return compute_public_data_ingest(args.get("mode"), args.get("params"))

register_tool("public_data_ingest_tool", PUBLIC_DATA_INGEST_TOOL_SCHEMA, _handle)
