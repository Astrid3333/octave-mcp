"""
soil_erosion_tool.py

Modelado de erosion de suelo, complementario a land_use_change_tool
(mismo dominio conceptual: degradacion de la tierra). Dos ejes:

  1) rusle_projection: tasa de perdida de suelo vs. RUSLE (Revised
     Universal Soil Loss Equation, Renard et al. 1997):

         A = R * K * LS * C * P   [t/ha/anio, unidades SI de RUSLE2]

     donde R=erosividad de lluvia, K=erodibilidad del suelo,
     LS=factor topografico (longitud+pendiente, McCool et al. 1989),
     C=factor de cobertura/manejo, P=factor de practicas de soporte.

     Sobre esa tasa se corre una proyeccion multi-anio de profundidad
     de suelo, con un feedback opcional (C aumenta a medida que el
     suelo se adelgaza, i.e. menos cobertura vegetal posible sobre
     suelo degradado). Cuando el feedback esta apagado (alpha=0) la
     proyeccion tiene forma cerrada exacta (depletion lineal), lo que
     permite el mismo patron cerrado-vs-numerico que unified_dark_sector_tool
     y land_use_change_tool.

  2) hotspot_grid: grilla sintetica de pendiente/erodibilidad, score
     de riesgo celda a celda via LS*K, umbral, y deteccion de
     parches conexos de riesgo alto por flood-fill (4-conectividad,
     sin scipy) -- mismo patron que la fragmentacion de habitat en
     land_use_change_tool pero aplicado a riesgo de erosion.

Nota de honestidad de datos: el feedback C(t) es una acoplacion
cualitativa razonable (suelo mas delgado -> menos retencion de agua/
nutrientes -> cobertura vegetal mas dificil de sostener -> C sube)
pero la funcion exacta (exponencial, parametro alpha) es una eleccion
de modelado ilustrativa, NO calibrada contra datos de campo -- no
tratar alpha como una constante medida.

Modos: rusle_projection, hotspot_grid, validate.
"""

import numpy as np


# ---------------------------------------------------------------------------
# RUSLE: factor topografico LS (McCool et al. 1987/1989)
# ---------------------------------------------------------------------------

def _ls_factor(slope_percent, slope_length_m):
    """Factor topografico LS de RUSLE. slope_percent en %, slope_length_m
    en metros. Formula McCool: LS = (lambda/22.13)^m * (65.41*sin^2(theta)
    + 4.56*sin(theta) + 0.065), con m dependiente de la pendiente."""
    slope_percent = np.asarray(slope_percent, dtype=float)
    slope_length_m = np.asarray(slope_length_m, dtype=float)

    theta = np.arctan(slope_percent / 100.0)
    sin_theta = np.sin(theta)

    m = np.where(
        slope_percent >= 5.0, 0.5,
        np.where(slope_percent >= 3.5, 0.4,
                 np.where(slope_percent >= 1.0, 0.3, 0.2))
    )

    ls = (slope_length_m / 22.13) ** m * (
        65.41 * sin_theta ** 2 + 4.56 * sin_theta + 0.065
    )
    return ls


def _rusle_annual_loss(R, K, LS, C, P):
    """A = R*K*LS*C*P, t/ha/anio (unidades SI-RUSLE2 consistentes)."""
    return R * K * LS * C * P


# ---------------------------------------------------------------------------
# Proyeccion de profundidad de suelo: cerrada (sin feedback) vs numerica
# ---------------------------------------------------------------------------

def _depth_loss_mm_per_year(annual_loss_t_ha, bulk_density_t_m3):
    """Convierte perdida de masa (t/ha/anio) a perdida de profundidad
    (mm/anio). 1 mm de suelo sobre 1 ha con densidad rho (t/m3) pesa
    rho*10 toneladas (1 ha * 1 mm = 10 m3), asi que profundidad_mm =
    masa_t_ha / (10*rho)."""
    return annual_loss_t_ha / (10.0 * bulk_density_t_m3)


def _soil_depth_closed_form(D0_mm, R, K, LS, C0, P, n_years, bulk_density_t_m3):
    """Forma cerrada exacta valida solo cuando C es constante (sin
    feedback): depletion lineal en el tiempo, con piso en 0."""
    A0 = _rusle_annual_loss(R, K, LS, C0, P)
    loss_per_year_mm = _depth_loss_mm_per_year(A0, bulk_density_t_m3)
    D_n = D0_mm - n_years * loss_per_year_mm
    return {
        "annual_loss_t_ha": float(A0),
        "depth_loss_mm_per_year": float(loss_per_year_mm),
        "final_depth_mm": float(max(D_n, 0.0)),
        "final_depth_mm_unclamped": float(D_n),
    }


def _soil_depth_numeric(D0_mm, R, K, LS, C0, P, n_years, bulk_density_t_m3,
                         feedback_alpha=0.0, C_max=1.0):
    """Proyeccion anio a anio. Si feedback_alpha=0, C se mantiene en C0
    todo el tiempo y el resultado debe coincidir con la forma cerrada
    (mientras la profundidad no toque el piso de 0). Si feedback_alpha>0,
    C sube a medida que D cae (suelo mas fino -> menos cobertura posible),
    acelerando la perdida."""
    D = float(D0_mm)
    C = float(C0)
    depths = [D]
    covers = [C]
    annual_losses = []

    for _ in range(int(n_years)):
        A_t = _rusle_annual_loss(R, K, LS, C, P)
        loss_mm = _depth_loss_mm_per_year(A_t, bulk_density_t_m3)
        annual_losses.append(float(A_t))
        D = max(D - loss_mm, 0.0)
        depths.append(D)

        if feedback_alpha != 0.0 and D0_mm > 0:
            frac_lost = 1.0 - (D / D0_mm)
            C = min(C0 * np.exp(feedback_alpha * frac_lost), C_max)
        covers.append(C)

    return {
        "depths_mm": depths,
        "cover_factors": covers,
        "annual_losses_t_ha": annual_losses,
        "final_depth_mm": float(depths[-1]),
        "cumulative_depth_loss_mm": float(D0_mm - depths[-1]),
    }


# ---------------------------------------------------------------------------
# Grilla de hotspots de riesgo de erosion (flood-fill sin scipy)
# ---------------------------------------------------------------------------

def _generate_risk_grid(rows, cols, seed, slope_length_m, cover_factor,
                         support_practice_factor,
                         slope_min=0.0, slope_max=45.0,
                         k_min=0.01, k_max=0.05):
    rng = np.random.default_rng(seed)
    slope_grid = rng.uniform(slope_min, slope_max, size=(rows, cols))
    k_grid = rng.uniform(k_min, k_max, size=(rows, cols))
    ls_grid = _ls_factor(slope_grid, slope_length_m)
    risk_grid = ls_grid * k_grid * cover_factor * support_practice_factor
    return risk_grid, slope_grid, k_grid


def _flood_fill_components(mask):
    """Componentes conexas de mask==True via 4-conectividad
    (flood-fill iterativo con pila, sin recursion ni scipy)."""
    rows, cols = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    components = []

    for i in range(rows):
        for j in range(cols):
            if mask[i, j] and not visited[i, j]:
                stack = [(i, j)]
                visited[i, j] = True
                comp = []
                while stack:
                    ci, cj = stack.pop()
                    comp.append((ci, cj))
                    for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        ni, nj = ci + di, cj + dj
                        if (0 <= ni < rows and 0 <= nj < cols
                                and mask[ni, nj] and not visited[ni, nj]):
                            visited[ni, nj] = True
                            stack.append((ni, nj))
                components.append(comp)
    return components


def _edge_density(mask):
    rows, cols = mask.shape
    edges = 0
    total_adjacent = 0
    for i in range(rows):
        for j in range(cols):
            if j + 1 < cols:
                total_adjacent += 1
                if mask[i, j] != mask[i, j + 1]:
                    edges += 1
            if i + 1 < rows:
                total_adjacent += 1
                if mask[i, j] != mask[i + 1, j]:
                    edges += 1
    return (edges / total_adjacent) if total_adjacent > 0 else 0.0


# ---------------------------------------------------------------------------
# Modos publicos
# ---------------------------------------------------------------------------

def _mode_rusle_projection(params):
    R = float(params.get("R", 2500.0))
    K = float(params.get("K", 0.03))
    slope_percent = float(params.get("slope_percent", 8.0))
    slope_length_m = float(params.get("slope_length_m", 20.0))
    C0 = float(params.get("cover_factor", 0.3))
    P = float(params.get("support_practice_factor", 1.0))
    D0_mm = float(params.get("initial_depth_mm", 300.0))
    n_years = int(params.get("n_years", 50))
    bulk_density = float(params.get("bulk_density_t_m3", 1.3))
    feedback_alpha = float(params.get("feedback_alpha", 0.02))

    LS = float(_ls_factor(slope_percent, slope_length_m))

    closed = _soil_depth_closed_form(D0_mm, R, K, LS, C0, P, n_years, bulk_density)
    numeric_no_feedback = _soil_depth_numeric(
        D0_mm, R, K, LS, C0, P, n_years, bulk_density, feedback_alpha=0.0)
    numeric_with_feedback = _soil_depth_numeric(
        D0_mm, R, K, LS, C0, P, n_years, bulk_density,
        feedback_alpha=feedback_alpha)

    return {
        "mode": "rusle_projection",
        "inputs": {
            "R": R, "K": K, "slope_percent": slope_percent,
            "slope_length_m": slope_length_m, "cover_factor_C0": C0,
            "support_practice_factor_P": P, "initial_depth_mm": D0_mm,
            "n_years": n_years, "bulk_density_t_m3": bulk_density,
            "feedback_alpha": feedback_alpha,
        },
        "ls_factor": LS,
        "annual_loss_year0_t_ha": closed["annual_loss_t_ha"],
        "closed_form_no_feedback": closed,
        "numeric_no_feedback_final_depth_mm": numeric_no_feedback["final_depth_mm"],
        "numeric_with_feedback": {
            "final_depth_mm": numeric_with_feedback["final_depth_mm"],
            "cumulative_depth_loss_mm": numeric_with_feedback["cumulative_depth_loss_mm"],
        },
        "note": ("El feedback (C sube a medida que el suelo se adelgaza) es "
                 "una acoplacion cualitativa ilustrativa, no calibrada contra "
                 "datos de campo -- no tratar feedback_alpha como constante medida."),
    }


def _mode_hotspot_grid(params):
    rows = int(params.get("rows", 20))
    cols = int(params.get("cols", 20))
    seed = int(params.get("seed", 42))
    slope_length_m = float(params.get("slope_length_m", 20.0))
    cover_factor = float(params.get("cover_factor", 0.3))
    support_practice_factor = float(params.get("support_practice_factor", 1.0))
    threshold_percentile = float(params.get("threshold_percentile", 75.0))

    risk_grid, slope_grid, k_grid = _generate_risk_grid(
        rows, cols, seed, slope_length_m, cover_factor, support_practice_factor)

    threshold = float(np.percentile(risk_grid, threshold_percentile))
    mask = risk_grid >= threshold
    components = _flood_fill_components(mask)
    sizes = sorted((len(c) for c in components), reverse=True)
    total_cells = rows * cols
    hotspot_cells = int(mask.sum())

    return {
        "mode": "hotspot_grid",
        "grid_shape": [rows, cols],
        "risk_stats": {
            "min": float(risk_grid.min()),
            "max": float(risk_grid.max()),
            "mean": float(risk_grid.mean()),
        },
        "threshold_percentile": threshold_percentile,
        "threshold_value": threshold,
        "hotspot_fraction": hotspot_cells / total_cells,
        "n_patches": len(components),
        "patch_sizes": sizes,
        "largest_patch_fraction": (sizes[0] / total_cells) if sizes else 0.0,
        "edge_density": _edge_density(mask),
    }


def _validate():
    errors = []
    checks = {}

    # 1) R=0 -> A=0
    a_zero_rain = _rusle_annual_loss(0.0, 0.03, 2.0, 0.3, 1.0)
    checks["rusle_zero_rainfall_gives_zero_loss"] = bool(a_zero_rain == 0.0)

    # 2) C=0 (cobertura total) -> A=0
    a_zero_cover = _rusle_annual_loss(2500.0, 0.03, 2.0, 0.0, 1.0)
    checks["rusle_zero_cover_gives_zero_loss"] = bool(a_zero_cover == 0.0)

    # 3) LS monotono creciente en pendiente (longitud fija)
    ls_low_slope = float(_ls_factor(5.0, 20.0))
    ls_high_slope = float(_ls_factor(30.0, 20.0))
    checks["ls_factor_monotonic_in_slope"] = bool(ls_high_slope > ls_low_slope)

    # 4) LS monotono creciente en longitud (pendiente fija)
    ls_short = float(_ls_factor(10.0, 5.0))
    ls_long = float(_ls_factor(10.0, 200.0))
    checks["ls_factor_monotonic_in_length"] = bool(ls_long > ls_short)

    # 5) orden de magnitud razonable para un caso cropland tipico
    #    (chequeo de plausibilidad, no un valor exacto de literatura)
    ls_typical = float(_ls_factor(8.0, 20.0))
    a_typical = _rusle_annual_loss(2500.0, 0.03, ls_typical, 0.3, 1.0)
    checks["rusle_typical_value"] = a_typical
    checks["rusle_typical_within_plausible_bounds"] = bool(0.1 <= a_typical <= 200.0)

    # 6) forma cerrada vs numerica (sin feedback), profundidad sin tocar el piso
    D0, n_years = 300.0, 20
    closed = _soil_depth_closed_form(D0, 2500.0, 0.03, ls_typical, 0.3, 1.0, n_years, 1.3)
    numeric = _soil_depth_numeric(D0, 2500.0, 0.03, ls_typical, 0.3, 1.0, n_years, 1.3,
                                   feedback_alpha=0.0)
    diff = abs(closed["final_depth_mm"] - numeric["final_depth_mm"])
    checks["closed_form_vs_numeric_max_diff"] = diff
    checks["closed_form_matches_numeric_no_feedback"] = bool(diff < 1e-9)

    # 7) el feedback nunca reduce la perdida acumulada frente a no-feedback
    numeric_fb = _soil_depth_numeric(D0, 2500.0, 0.03, ls_typical, 0.3, 1.0, n_years, 1.3,
                                      feedback_alpha=0.05)
    checks["feedback_increases_or_equals_cumulative_loss"] = bool(
        numeric_fb["cumulative_depth_loss_mm"] >= numeric["cumulative_depth_loss_mm"] - 1e-9
    )

    # 8) el piso de profundidad nunca se vuelve negativo (erosion extrema, largo plazo)
    extreme = _soil_depth_numeric(50.0, 20000.0, 0.05, 5.0, 0.9, 1.0, 200, 1.0,
                                   feedback_alpha=0.05)
    checks["depth_floor_never_negative"] = bool(min(extreme["depths_mm"]) >= 0.0)

    # 9-11) flood-fill sobre mascaras construidas a mano
    empty_mask = np.zeros((3, 3), dtype=bool)
    checks["flood_fill_empty_mask_gives_zero_patches"] = bool(
        len(_flood_fill_components(empty_mask)) == 0)

    full_mask = np.ones((3, 3), dtype=bool)
    full_components = _flood_fill_components(full_mask)
    checks["flood_fill_full_mask_gives_one_patch"] = bool(
        len(full_components) == 1 and len(full_components[0]) == 9)

    checker = np.zeros((4, 4), dtype=bool)
    checker[::2, ::2] = True
    checker[1::2, 1::2] = True
    checker_components = _flood_fill_components(checker)
    n_true_cells = int(checker.sum())
    checks["flood_fill_checkerboard_gives_isolated_singletons"] = bool(
        len(checker_components) == n_true_cells
        and all(len(c) == 1 for c in checker_components)
    )

    # 12) modo desconocido devuelve dict de error
    unknown_result = compute_soil_erosion_tool("bogus_mode", {})
    checks["unknown_mode_returns_error_dict"] = bool("error" in unknown_result)

    validation_passed = all(
        v for k, v in checks.items()
        if isinstance(v, bool)
    )

    return {
        "mode": "validate",
        "validation_passed": validation_passed,
        "checks": checks,
        "errors": errors,
    }


def compute_soil_erosion_tool(mode, params=None):
    if params is None:
        params = {}

    if mode == "rusle_projection":
        return _mode_rusle_projection(params)
    elif mode == "hotspot_grid":
        return _mode_hotspot_grid(params)
    elif mode == "validate":
        return _validate()
    else:
        return {
            "error": (
                f"Modo desconocido: {mode}. Modos validos: rusle_projection, "
                "hotspot_grid, validate."
            )
        }


SOIL_EROSION_TOOL_SCHEMA = {
    "name": "soil_erosion_tool",
    "description": (
        "Modelado de erosion de suelo, complementario a land_use_change_tool. "
        "mode=rusle_projection calcula la tasa de perdida de suelo via RUSLE "
        "(A=R*K*LS*C*P, LS de McCool) y proyecta profundidad de suelo a "
        "n_years, con verificacion cerrado-vs-numerico contra la solucion "
        "analitica exacta cuando el feedback de cobertura esta apagado. "
        "mode=hotspot_grid genera una grilla sintetica de pendiente/"
        "erodibilidad, calcula un score de riesgo celda a celda y detecta "
        "parches conexos de riesgo alto (4-conectividad, flood-fill) para "
        "distinguir hotspots concentrados de riesgo disperso."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["rusle_projection", "hotspot_grid", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "R": {"type": "number", "description": "Factor de erosividad de lluvia RUSLE (default 2500.0)"},
                    "K": {"type": "number", "description": "Factor de erodibilidad del suelo RUSLE (default 0.03)"},
                    "slope_percent": {"type": "number", "description": "Pendiente en % para rusle_projection (default 8.0)"},
                    "slope_length_m": {"type": "number", "description": "Longitud de pendiente en metros (default 20.0)"},
                    "cover_factor": {"type": "number", "description": "Factor de cobertura/manejo C0 (default 0.3)"},
                    "support_practice_factor": {"type": "number", "description": "Factor de practicas de soporte P (default 1.0)"},
                    "initial_depth_mm": {"type": "number", "description": "Profundidad inicial de suelo en mm, solo rusle_projection (default 300.0)"},
                    "n_years": {"type": "integer", "description": "Anios a proyectar en rusle_projection (default 50)"},
                    "bulk_density_t_m3": {"type": "number", "description": "Densidad aparente del suelo t/m3 (default 1.3)"},
                    "feedback_alpha": {"type": "number", "description": "Fuerza del feedback cobertura-profundidad, ilustrativo no calibrado (default 0.02)"},
                    "rows": {"type": "integer", "description": "Filas de la grilla en hotspot_grid (default 20)"},
                    "cols": {"type": "integer", "description": "Columnas de la grilla en hotspot_grid (default 20)"},
                    "threshold_percentile": {"type": "number", "description": "Percentil de riesgo para marcar celda como hotspot (default 75.0)"},
                    "seed": {"type": "integer", "description": "Semilla RNG (default 42)"},
                },
            },
        },
        "required": ["mode"],
    },
}

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool(
    "soil_erosion_tool",
    SOIL_EROSION_TOOL_SCHEMA,
    lambda args, _f=compute_soil_erosion_tool: _f(**args),
)
