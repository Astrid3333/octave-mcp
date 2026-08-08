import re
import math

# Vocabularios de unidades historicas (castellano colonial/peninsular), sin solape entre categorias
UNIDADES = {
    "capacidad": ["fanega", "fanegas", "celemin", "celemines", "cahiz", "cahices",
                  "cantara", "cantaras", "cuartillo", "cuartillos", "arroba", "arrobas"],
    "longitud": ["vara", "varas", "legua", "leguas", "pie", "pies", "braza", "brazas",
                 "aranzada", "aranzadas", "estadal", "estadales"],
    "peso": ["libra", "libras", "arrelde", "arreldes", "quintal", "quintales",
             "onza", "onzas", "marco", "marcos"],
}

# Normaliza plural -> forma canonica singular para agrupar conteos
CANON = {
    "fanegas": "fanega", "celemines": "celemin", "cahices": "cahiz",
    "cantaras": "cantara", "cuartillos": "cuartillo", "arrobas": "arroba",
    "varas": "vara", "leguas": "legua", "pies": "pie", "brazas": "braza",
    "aranzadas": "aranzada", "estadales": "estadal",
    "libras": "libra", "arreldes": "arrelde", "quintales": "quintal",
    "onzas": "onza", "marcos": "marco",
}

def _strip_accents(s):
    repl = {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ñ":"n"}
    for a,b in repl.items():
        s = s.replace(a,b)
    return s

def _canon(word):
    w = _strip_accents(word.lower())
    return CANON.get(w, w)

def extract_unit_counts(text_data, min_mentions=3):
    """Cuenta menciones de unidades historicas por categoria. Devuelve
    counts crudos por categoria y por unidad canonica."""
    text_norm = _strip_accents(text_data.lower())
    resultado = {}
    for categoria, unidades in UNIDADES.items():
        counts = {}
        for u in unidades:
            u_norm = _strip_accents(u)
            pattern = r'\b' + re.escape(u_norm) + r'\b'
            n = len(re.findall(pattern, text_norm))
            if n > 0:
                canon = _canon(u)
                counts[canon] = counts.get(canon, 0) + n
        resultado[categoria] = counts
    return resultado

def shannon_entropy_normalized(counts: dict):
    """H de Shannon (base 2) sobre la distribucion de unidades, normalizada
    por H_max = log2(k). Devuelve (H, H_max, homogeneidad_pct, k, total)."""
    total = sum(counts.values())
    k = len(counts)
    if k == 0 or total == 0:
        return None
    if k == 1:
        return {"H": 0.0, "H_max": 0.0, "homogeneidad_pct": 100.0, "k": 1, "total": total}
    probs = [c / total for c in counts.values()]
    H = -sum(p * math.log2(p) for p in probs if p > 0)
    H_max = math.log2(k)
    homogeneidad = (1 - H / H_max) * 100.0
    return {"H": H, "H_max": H_max, "homogeneidad_pct": homogeneidad, "k": k, "total": total}

def analyze_units_entropy(text_data, min_mentions=3):
    raw = extract_unit_counts(text_data, min_mentions=min_mentions)
    out = {}
    for categoria, counts in raw.items():
        total = sum(counts.values())
        if total < min_mentions:
            out[categoria] = {
                "ok": False,
                "warning": f"solo {total} menciones extraidas (<{min_mentions}), se muestra crudo en vez de estimar homogeneidad",
                "counts": counts,
            }
            continue
        stats = shannon_entropy_normalized(counts)
        out[categoria] = {
            "ok": True,
            "counts": counts,
            "unidad_dominante": max(counts, key=counts.get),
            **stats,
        }
    return out
