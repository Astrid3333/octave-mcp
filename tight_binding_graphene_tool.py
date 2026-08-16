"""
tight_binding_graphene_tool
============================

Nearest-neighbor tight-binding model for a graphene (honeycomb) lattice.
Complementa dft_tool (que hoy solo cubre moleculas pequenas) permitiendo
estructura de bandas de sistemas periodicos 2D tipo grafeno.

Modelo:
  - Lattice honeycomb, 2 atomos por celda (sublattices A/B).
  - Solo hopping a primeros vecinos, energia on-site = 0 (particle-hole
    simetrico), parametro de hopping t (default 2.7 eV, valor estandar
    de literatura para grafeno).
  - Hamiltoniano k-espacio 2x2:
        H(k) = [[0, f(k)], [f(k)*, 0]]
        f(k) = -t * sum_j exp(i k . delta_j)
    con delta_j los 3 vectores a primeros vecinos.
  - Autovalores: E_+-(k) = +-|f(k)|  (bandas pi y pi*).

Convencion de dispatch: el tool_registry invoca al handler pasando el
diccionario completo de argumentos como UN SOLO parametro posicional
(no expandido como **kwargs). Firma correcta: _handler(args).
"""

import cmath
import math

import tool_registry


# ----------------------------------------------------------------------
# Constantes de la red
# ----------------------------------------------------------------------

A_CC = 1.42          # distancia carbono-carbono (Angstrom)
A_LATTICE = A_CC * math.sqrt(3)   # constante de red (Angstrom)
T_DEFAULT = 2.7       # hopping a primeros vecinos (eV)

# Vectores a los 3 primeros vecinos (sublattice A -> B)
DELTAS = [
    (A_CC * 0.0, A_CC * 1.0),
    (A_CC * math.sqrt(3) / 2.0, -A_CC * 0.5),
    (-A_CC * math.sqrt(3) / 2.0, -A_CC * 0.5),
]

# Vectores de red reciproca
B1 = (2 * math.pi / (A_LATTICE), 2 * math.pi / (A_LATTICE * math.sqrt(3)))
B2 = (2 * math.pi / (A_LATTICE), -2 * math.pi / (A_LATTICE * math.sqrt(3)))

# Puntos de alta simetria (coordenadas cartesianas, 1/Angstrom)
GAMMA = (0.0, 0.0)
K_POINT = (2 * math.pi / (3 * A_CC * math.sqrt(3)), 2 * math.pi / (3 * A_CC))
M_POINT = (2 * math.pi / (3 * A_CC * math.sqrt(3)) * 1.5 / 1.0, 0.0)
# M como punto medio entre dos K adyacentes en el borde de la BZ
M_POINT = (2 * math.pi / (A_LATTICE * math.sqrt(3)), 0.0)


def f_k(kx, ky, t=T_DEFAULT):
    """f(k) = -t * sum_j exp(i k . delta_j)"""
    acc = 0j
    for dx, dy in DELTAS:
        acc += cmath.exp(1j * (kx * dx + ky * dy))
    return -t * acc


def bands_at(kx, ky, t=T_DEFAULT):
    """Devuelve (E_menos, E_mas) = (-|f(k)|, +|f(k)|)."""
    mag = abs(f_k(kx, ky, t))
    return (-mag, mag)


def _linspace_path(p0, p1, n):
    x0, y0 = p0
    x1, y1 = p1
    pts = []
    for i in range(n):
        s = i / max(n - 1, 1)
        pts.append((x0 + s * (x1 - x0), y0 + s * (y1 - y0)))
    return pts


def band_structure(t=T_DEFAULT, points_per_segment=60):
    """
    Estructura de bandas a lo largo del camino Gamma -> K -> M -> Gamma.
    Devuelve lista de dicts: {segment, k_index, kx, ky, E_minus, E_plus}
    """
    path_segments = [
        ("Gamma-K", GAMMA, K_POINT),
        ("K-M", K_POINT, M_POINT),
        ("M-Gamma", M_POINT, GAMMA),
    ]
    out = []
    idx = 0
    for name, p0, p1 in path_segments:
        pts = _linspace_path(p0, p1, points_per_segment)
        for kx, ky in pts:
            e_minus, e_plus = bands_at(kx, ky, t)
            out.append({
                "segment": name,
                "k_index": idx,
                "kx": kx,
                "ky": ky,
                "E_minus": e_minus,
                "E_plus": e_plus,
            })
            idx += 1
    return out


def density_of_states(t=T_DEFAULT, n_side=120, n_bins=200):
    """
    DOS aproximado por muestreo uniforme de la primera zona de Brillouin
    (aproximada como un rectangulo alrededor de Gamma acotado por |b1|,|b2|)
    y binning de los autovalores de ambas bandas.
    """
    energies = []
    kx_max = max(abs(B1[0]), abs(B2[0]))
    ky_max = max(abs(B1[1]), abs(B2[1]))
    for i in range(n_side):
        kx = -kx_max + 2 * kx_max * i / (n_side - 1)
        for j in range(n_side):
            ky = -ky_max + 2 * ky_max * j / (n_side - 1)
            e_minus, e_plus = bands_at(kx, ky, t)
            energies.append(e_minus)
            energies.append(e_plus)

    if not energies:
        return {"bin_edges": [], "counts": []}

    e_min, e_max = min(energies), max(energies)
    if e_min == e_max:
        e_min -= 0.5
        e_max += 0.5
    width = (e_max - e_min) / n_bins
    counts = [0] * n_bins
    for e in energies:
        b = int((e - e_min) / width)
        if b == n_bins:
            b -= 1
        counts[b] += 1
    bin_edges = [e_min + i * width for i in range(n_bins + 1)]
    return {"bin_edges": bin_edges, "counts": counts}


# ----------------------------------------------------------------------
# Validacion
# ----------------------------------------------------------------------

def _validate(t=T_DEFAULT):
    checks = []

    # Check 1: en el punto K (punto de Dirac), f(K) debe anularse y por
    # lo tanto E_+ = E_- = 0 (bandas pi/pi* se tocan, gap cero).
    e_minus_k, e_plus_k = bands_at(K_POINT[0], K_POINT[1], t)
    ok1 = abs(e_minus_k) < 1e-8 and abs(e_plus_k) < 1e-8
    checks.append({
        "name": "dirac_point_gapless_at_K",
        "passed": bool(ok1),
        "detail": f"E-(K)={e_minus_k:.3e} eV, E+(K)={e_plus_k:.3e} eV",
    })

    # Check 2: simetria particula-hueco (bipartite lattice, on-site=0):
    # para cualquier k, E_+(k) = -E_-(k).
    import random
    random.seed(0)
    max_asym = 0.0
    for _ in range(200):
        kx = random.uniform(-3.0, 3.0)
        ky = random.uniform(-3.0, 3.0)
        e_minus, e_plus = bands_at(kx, ky, t)
        max_asym = max(max_asym, abs(e_plus + e_minus))
    ok2 = max_asym < 1e-9
    checks.append({
        "name": "particle_hole_symmetry",
        "passed": bool(ok2),
        "detail": f"max |E+(k)+E-(k)| sobre 200 puntos k aleatorios = {max_asym:.3e} eV",
    })

    # Check 3: en Gamma, coordinacion completa -> |f(Gamma)| = 3t
    # (los 3 vectores delta contribuyen en fase), banda de mayor
    # amplitud absoluta esperada en la trayectoria Gamma-K-M-Gamma.
    e_minus_g, e_plus_g = bands_at(GAMMA[0], GAMMA[1], t)
    ok3 = abs(abs(e_plus_g) - 3 * t) < 1e-8
    checks.append({
        "name": "gamma_point_bandwidth_3t",
        "passed": bool(ok3),
        "detail": f"E+(Gamma)={e_plus_g:.6f} eV, esperado 3t={3*t:.6f} eV",
    })

    passed_count = sum(1 for c in checks if c["passed"])
    return {
        "all_passed": passed_count == len(checks),
        "passed": passed_count,
        "total": len(checks),
        "checks": checks,
    }


# ----------------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------------

def validate(t=T_DEFAULT):
    return _validate(t=t)


def compute_tight_binding_graphene(mode="validate", **kwargs):
    if mode == "validate":
        return validate(t=kwargs.get("t", T_DEFAULT))
    elif mode == "band_structure":
        return {
            "t_eV": kwargs.get("t", T_DEFAULT),
            "path": "Gamma-K-M-Gamma",
            "points": band_structure(
                t=kwargs.get("t", T_DEFAULT),
                points_per_segment=kwargs.get("points_per_segment", 60),
            ),
        }
    elif mode == "dos":
        return density_of_states(
            t=kwargs.get("t", T_DEFAULT),
            n_side=kwargs.get("n_side", 120),
            n_bins=kwargs.get("n_bins", 200),
        )
    else:
        raise ValueError(f"mode desconocido: {mode}")


TIGHT_BINDING_GRAPHENE_TOOL_SCHEMA = {
    "name": "tight_binding_graphene_tool",
    "description": (
        "Estructura de bandas tight-binding a primeros vecinos para grafeno "
        "(red honeycomb, 2 atomos por celda). Modos: validate (chequeo del "
        "punto de Dirac, simetria particula-hueco y ancho de banda en Gamma), "
        "band_structure (camino Gamma-K-M-Gamma), dos (densidad de estados "
        "aproximada por muestreo de la zona de Brillouin). Complementa "
        "dft_tool, que hoy solo cubre moleculas pequenas, con sistemas "
        "periodicos 2D."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["validate", "band_structure", "dos"]},
            "t": {"type": "number", "description": "parametro de hopping a primeros vecinos, en eV (default 2.7)"},
            "points_per_segment": {"type": "integer", "description": "puntos k por segmento del camino Gamma-K-M-Gamma (band_structure)"},
            "n_side": {"type": "integer", "description": "muestras por lado de la grilla de la BZ (dos)"},
            "n_bins": {"type": "integer", "description": "numero de bins de energia para el histograma (dos)"},
        },
        "required": ["mode"],
    },
}


def _handler(args):
    args = dict(args or {})
    mode = args.pop("mode", "validate")
    params = args.pop("params", None) or {}
    merged = {**params, **args}
    return compute_tight_binding_graphene(mode=mode, **merged)


tool_registry.register_tool(
    "tight_binding_graphene_tool", TIGHT_BINDING_GRAPHENE_TOOL_SCHEMA, _handler
)


if __name__ == "__main__":
    import json
    print(json.dumps(validate(), indent=2, ensure_ascii=False))
