"""
fungal_morphology_tool.py

Matematica de formas del cuerpo fungico (carpoforo): perfil del pileo
(sombrero), geometria del estipite (pie), patron de doblamiento de
laminillas, y empaquetamiento de poros en superficie.

Modos:
  - pileus_profile     : superficie de revolucion tipo "domo generalizado"
                          z(r) = h*(1-(r/R)^p)^(1/q). Validado contra el
                          caso cerrado exacto (hemisferio, p=q=2, h=R).
  - stipe_frustum       : tronco de cono (frustum). Formulas cerradas
                          exactas, validadas por integracion numerica
                          independiente del perfil r(z).
  - gill_doubling       : doblamiento jerarquico de laminillas/laminulas
                          (NO filotaxis de angulo dorado -- eso es de
                          hojas/semillas, no del patron real documentado
                          de gills fungicos de ordenes 1/2/3). Valida
                          contra la propiedad de auto-consistencia del
                          algoritmo (espaciado maximo respetado y minimo
                          necesario).
  - pore_packing        : empaquetamiento hexagonal de poros en la
                          superficie (poliporos). Validado contra la
                          fraccion de empaquetamiento exacta pi/(2*sqrt(3)).
  - validate             : autochequeo de los 4 modos anteriores.
"""

import numpy as np
import sys
import json

TOOL_SCHEMA = {
    "name": "fungal_morphology_tool",
    "description": (
        "Matematica de formas del cuerpo fungico (carpoforo): perfil del "
        "pileo (sombrero) como domo generalizado, geometria del estipite "
        "(frustum), doblamiento jerarquico de laminillas, y empaquetamiento "
        "hexagonal de poros en superficie. Modos: pileus_profile, "
        "stipe_frustum, gill_doubling, pore_packing, self_test, validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["pileus_profile", "stipe_frustum", "gill_doubling",
                         "pore_packing", "self_test", "validate"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "R": {"type": "number", "description": "radio del pileo (pileus_profile)"},
                    "h": {"type": "number", "description": "altura del domo (pileus_profile)"},
                    "p": {"type": "number", "description": "exponente radial (pileus_profile)"},
                    "q": {"type": "number", "description": "exponente de altura (pileus_profile)"},
                    "n_r": {"type": "integer", "description": "puntos radiales (pileus_profile)"},
                    "r_top": {"type": "number", "description": "radio superior del estipite (stipe_frustum)"},
                    "r_bottom": {"type": "number", "description": "radio inferior del estipite (stipe_frustum)"},
                    "H": {"type": "number", "description": "altura del estipite (stipe_frustum)"},
                    "n_z": {"type": "integer", "description": "puntos axiales (stipe_frustum)"},
                    "R_cap": {"type": "number", "description": "radio del sombrero (gill_doubling)"},
                    "r_stipe": {"type": "number", "description": "radio del estipite (gill_doubling)"},
                    "s_max": {"type": "number", "description": "espaciado angular maximo (gill_doubling)"},
                    "N0": {"type": "integer", "description": "n gills iniciales (gill_doubling)"},
                    "max_orders": {"type": "integer", "description": "ordenes maximos de duplicacion (gill_doubling)"},
                    "pore_diameter": {"type": "number", "description": "diametro de poro (pore_packing)"},
                    "domain_side": {"type": "number", "description": "lado del dominio (pore_packing)"},
                    "n_cells_side": {"type": "integer", "description": "celdas por lado (pore_packing)"},
                },
            },
        },
        "required": ["mode"],
    },
}


# --------------------------------------------------------------------------
# 1. Perfil del pileo (domo generalizado, superficie de revolucion)
# --------------------------------------------------------------------------

def _pileus_profile(R=5.0, h=3.0, p=2.0, q=2.0, n_r=400):
    """
    z(r) = h * (1 - (r/R)^p)^(1/q),  r en [0, R]

    p=q=2, h=R  -> hemisferio exacto (caso de validacion):
        area lateral = 2*pi*R^2
        volumen       = (2/3)*pi*R^3
    p=1, q=1            -> perfil conico (piramidal)
    p,q > 2              -> perfil mas aplanado/umbonado (tipico de
                             sombreros maduros extendidos)
    """
    r = np.linspace(1e-9, R, n_r)  # evitar r=0 exacto en derivada
    base = np.clip(1.0 - (r / R) ** p, 0.0, None)
    z = h * base ** (1.0 / q)

    dzdr = np.gradient(z, r)
    area_integrand = 2.0 * np.pi * r * np.sqrt(1.0 + dzdr ** 2)
    vol_integrand = 2.0 * np.pi * r * z

    surface_area = float(np.trapezoid(area_integrand, r))
    volume = float(np.trapezoid(vol_integrand, r))

    return {
        "mode": "pileus_profile",
        "r": r.tolist(),
        "z": z.tolist(),
        "surface_area_m2": surface_area,
        "volume_m3": volume,
        "params": {"R": R, "h": h, "p": p, "q": q},
    }


# --------------------------------------------------------------------------
# 2. Estipite como frustum (tronco de cono)
# --------------------------------------------------------------------------

def _stipe_frustum(r_top=0.5, r_bottom=0.8, H=6.0, n_z=300):
    """
    Formulas cerradas exactas:
      V = (pi*H/3) * (r_top^2 + r_top*r_bottom + r_bottom^2)
      A_lateral = pi*(r_top+r_bottom)*slant,  slant = sqrt(H^2+(r_bottom-r_top)^2)

    Se valida por integracion numerica independiente del perfil lineal
    r(z) = r_bottom + (r_top-r_bottom)*(z/H):
      V_num = integral( pi*r(z)^2 dz )        (metodo de discos)
      A_num = integral( 2*pi*r(z)*sqrt(1+(dr/dz)^2) dz )
    """
    slant = np.sqrt(H ** 2 + (r_bottom - r_top) ** 2)
    V_exact = (np.pi * H / 3.0) * (r_top ** 2 + r_top * r_bottom + r_bottom ** 2)
    A_exact = np.pi * (r_top + r_bottom) * slant

    z = np.linspace(0.0, H, n_z)
    r_z = r_bottom + (r_top - r_bottom) * (z / H)
    drdz = (r_top - r_bottom) / H

    V_num = float(np.trapezoid(np.pi * r_z ** 2, z))
    A_num = float(np.trapezoid(2.0 * np.pi * r_z * np.sqrt(1.0 + drdz ** 2), z))

    return {
        "mode": "stipe_frustum",
        "z": z.tolist(),
        "r_z": r_z.tolist(),
        "volume_exact_m3": float(V_exact),
        "volume_numeric_m3": V_num,
        "lateral_area_exact_m2": float(A_exact),
        "lateral_area_numeric_m2": A_num,
        "volume_abs_error": abs(V_num - V_exact),
        "area_abs_error": abs(A_num - A_exact),
        "params": {"r_top": r_top, "r_bottom": r_bottom, "H": H},
    }


# --------------------------------------------------------------------------
# 3. Doblamiento jerarquico de laminillas (lamelas / lamelulas)
# --------------------------------------------------------------------------

def _gill_doubling(R_cap=4.0, r_stipe=0.3, s_max=0.5, N0=4, max_orders=12):
    """
    Modelo del patron real de laminillas fungicas: gills primarios (orden 1)
    van del estipite al margen; cuando el espaciado angular entre gills
    adyacentes supera un umbral s_max (arco maximo tolerado), se inserta
    un gill secundario (laminula) mas corto en cada hueco, DUPLICANDO el
    conteo desde ese radio hacia el margen. El proceso se repite en
    ordenes sucesivos (2, 3, ...) -- esto es taxonomicamente lo que se
    observa (L = lamelas, l = lamelulas de 1er/2do orden), y es distinto
    de la filotaxis de angulo dorado (137.5 grados), que es un modelo
    para disposicion de hojas/semillas y no aplica aca.

    radio de bifurcacion para pasar de N a 2N gills:
        r_bifurcacion = s_max * N / (2*pi)

    Se itera mientras r_bifurcacion < R_cap.
    """
    N = N0
    r_current = r_stipe
    orders = [{"order": 1, "r_start": r_stipe, "n_gills": N0}]

    for order in range(2, max_orders + 2):
        r_bif = s_max * N / (2.0 * np.pi)
        if r_bif >= R_cap or r_bif <= r_current:
            break
        N_new = 2 * N
        orders.append({"order": order, "r_start": float(r_bif), "n_gills": N_new})
        r_current = r_bif
        N = N_new

    N_final = orders[-1]["n_gills"]
    spacing_at_margin = 2.0 * np.pi * R_cap / N_final
    # espaciado que habria SIN la ultima duplicacion (para probar que era necesaria)
    N_without_last = N_final // 2 if len(orders) > 1 else N_final
    spacing_without_last = 2.0 * np.pi * R_cap / N_without_last

    return {
        "mode": "gill_doubling",
        "orders": orders,
        "n_gills_final": N_final,
        "spacing_at_margin_m": spacing_at_margin,
        "spacing_without_last_doubling_m": spacing_without_last,
        "s_max": s_max,
        "constraint_satisfied": bool(spacing_at_margin <= s_max * 1e-9 + s_max),
        "last_doubling_was_necessary": bool(spacing_without_last > s_max),
        "params": {"R_cap": R_cap, "r_stipe": r_stipe, "s_max": s_max, "N0": N0},
    }


# --------------------------------------------------------------------------
# 4. Empaquetamiento hexagonal de poros
# --------------------------------------------------------------------------

def _pore_packing(pore_diameter=0.2, domain_side=None, n_cells_side=40):
    """
    Reticula triangular (empaquetamiento hexagonal) de circulos de diametro
    d en contacto: espaciado de red = d.

    Fraccion de empaquetamiento exacta (limite infinito):
        phi = pi / (2*sqrt(3))  ~= 0.9069

    Se genera una reticula finita (n_cells_side x n_cells_side celdas) y
    se compara la fraccion empirica contra el valor exacto -- el dominio
    se elige grande respecto de d para que el efecto de borde sea chico.
    """
    d = pore_diameter
    dx = d
    dy = d * np.sqrt(3.0) / 2.0

    if domain_side is None:
        domain_side = n_cells_side * d

    xs, ys = [], []
    row = 0
    y = 0.0
    while y <= domain_side:
        x_offset = (dx / 2.0) if (row % 2 == 1) else 0.0
        x = x_offset
        while x <= domain_side:
            xs.append(x)
            ys.append(y)
            x += dx
        y += dy
        row += 1

    n_pores = len(xs)
    domain_area = domain_side ** 2
    pore_area = n_pores * np.pi * (d / 2.0) ** 2
    packing_fraction_empirical = pore_area / domain_area
    packing_fraction_exact = np.pi / (2.0 * np.sqrt(3.0))

    return {
        "mode": "pore_packing",
        "n_pores": n_pores,
        "domain_side_m": domain_side,
        "packing_fraction_empirical": float(packing_fraction_empirical),
        "packing_fraction_exact": float(packing_fraction_exact),
        "abs_error": abs(packing_fraction_empirical - packing_fraction_exact),
        "params": {"pore_diameter": d, "n_cells_side": n_cells_side},
    }


# --------------------------------------------------------------------------
# 5. self_test / run / registro
# --------------------------------------------------------------------------

def run_self_test():
    checks = []

    def check(name, cond, detail=""):
        checks.append({"name": name, "passed": bool(cond), "detail": detail})

    R = 5.0
    out = _pileus_profile(R=R, h=R, p=2.0, q=2.0, n_r=2000)
    area_exact = 2.0 * np.pi * R ** 2
    vol_exact = (2.0 / 3.0) * np.pi * R ** 3
    area_err = abs(out["surface_area_m2"] - area_exact) / area_exact
    vol_err = abs(out["volume_m3"] - vol_exact) / vol_exact
    check("pileus_profile vs hemisferio (area)", area_err < 1e-3, f"rel err={area_err:.2e}")
    check("pileus_profile vs hemisferio (volumen)", vol_err < 1e-3, f"rel err={vol_err:.2e}")

    out = _stipe_frustum(r_top=0.5, r_bottom=0.8, H=6.0, n_z=2000)
    check("stipe_frustum: volumen numerico vs cerrado",
          out["volume_abs_error"] < 1e-4, f"err={out['volume_abs_error']:.2e}")
    check("stipe_frustum: area numerica vs cerrada",
          out["area_abs_error"] < 1e-4, f"err={out['area_abs_error']:.2e}")

    out = _gill_doubling(R_cap=4.0, r_stipe=0.3, s_max=0.5, N0=4)
    check("gill_doubling: auto-consistencia",
          out["constraint_satisfied"] and out["last_doubling_was_necessary"],
          f"spacing_margin={out['spacing_at_margin_m']:.4f}")

    out = _pore_packing(pore_diameter=0.2, n_cells_side=200)
    check("pore_packing vs fraccion hexagonal exacta",
          out["abs_error"] < 0.01, f"err={out['abs_error']:.2e}")

    total = len(checks)
    passed = sum(1 for c in checks if c["passed"])
    return {"total": total, "passed": passed, "all_passed": passed == total, "checks": checks}


def run(mode, params=None):
    params = params or {}
    if mode == "validate":
        r = run_self_test()
        return {"checks": r["checks"], "validation_passed": r["all_passed"], "n_checks": r["total"]}
    elif mode == "self_test":
        return run_self_test()
    elif mode == "pileus_profile":
        return _pileus_profile(**params)
    elif mode == "stipe_frustum":
        return _stipe_frustum(**params)
    elif mode == "gill_doubling":
        return _gill_doubling(**params)
    elif mode == "pore_packing":
        return _pore_packing(**params)
    else:
        raise ValueError(
            f"modo desconocido: {mode} "
            "(usar pileus_profile/stipe_frustum/gill_doubling/pore_packing/self_test)"
        )


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

        tool_registry.register_tool("fungal_morphology_tool", TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()
