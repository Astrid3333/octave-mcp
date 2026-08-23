"""
joukowski_schwarz_christoffel_tool.py

Mapeos conformes clasicos, cierra el gap #2 del roadmap de geometria
(distinto de projective_geometry_tool, que cubre Mobius/P2/P3):

1. Joukowski: w = z + a^2/z. Mapea circulos en el plano z a perfiles
   aerodinamicos (airfoils) en el plano w. Un circulo centrado en el
   origen de radio a se degenera a una placa plana [-2a, 2a]; un circulo
   offset que pasa por z=a produce un perfil con cuspide en el borde de
   fuga (dw/dz=0 en z=a).

2. Schwarz-Christoffel: mapea el semiplano superior a un poligono.
   f(z) = A + C * integral prod_k (t - x_k)^(alpha_k - 1) dt
   donde x_k son las preimagenes reales ("prevertices") y alpha_k*pi es
   el angulo interior en el vertice k.

   - triangle: caso cerrado con formula conocida (funcion Beta) -- dos
     prevertices finitos en 0 y 1, tercer vertice en el infinito.
     Longitud del lado finito = B(alpha1, alpha2), sin resolver el
     "parameter problem" (que para n>=4 vertices requiere shooting
     numerico y queda fuera de este tool).
   - polygon: n prevertices finitos dados por el usuario (sin vertice en
     el infinito). Calcula cada lado por integracion compleja con offset
     imaginario chico (evita las singularidades sobre el eje real, rama
     continua acercandose desde el semiplano superior, Im>0).

Mismo patron que las otras tools del server: TOOL_SCHEMA, run(mode, **params),
validate() -> {"checks","all_passed","total","validation_passed"}, __main__
con sys.argv, _register() via tool_registry.register_tool(TOOL_SCHEMA["name"],
TOOL_SCHEMA, _handler).
"""

import json
import sys

import numpy as np
from scipy import special
from scipy.integrate import quad


# ---------------------------------------------------------------------
# 1. Joukowski
# ---------------------------------------------------------------------

def _joukowski_forward(z, a):
    return z + (a ** 2) / z


def _joukowski_derivative(z, a):
    return 1.0 - (a ** 2) / (z ** 2)


def joukowski_map(center=(-0.1, 0.1), radius=None, a=1.0, n_points=180):
    xc, yc = center
    if radius is None:
        # radio minimo para que el circulo pase por z=a (cuspide en el borde de fuga)
        radius = float(np.hypot(a - xc, -yc))
    thetas = np.linspace(0, 2 * np.pi, n_points, endpoint=False)
    z_circle = (xc + 1j * yc) + radius * np.exp(1j * thetas)
    w_airfoil = _joukowski_forward(z_circle, a)
    dwdz = _joukowski_derivative(z_circle, a)

    circle_pts = [{"re": float(z.real), "im": float(z.imag)} for z in z_circle]
    airfoil_pts = [{"re": float(w.real), "im": float(w.imag)} for w in w_airfoil]
    min_idx = int(np.argmin(np.abs(dwdz)))

    return {
        "center": {"re": xc, "im": yc},
        "radius": radius,
        "a": a,
        "circle_points": circle_pts,
        "airfoil_points": airfoil_pts,
        "min_abs_derivative": float(np.abs(dwdz[min_idx])),
        "min_derivative_at_circle_point": circle_pts[min_idx],
        "trailing_edge_cusp": bool(np.abs(dwdz[min_idx]) < 1e-2),
    }


def joukowski_inverse(w_re, w_im, a=1.0):
    w = complex(w_re, w_im)
    # z^2 - w z + a^2 = 0
    disc = w ** 2 - 4 * a ** 2
    sq = np.sqrt(disc)
    z1 = (w + sq) / 2
    z2 = (w - sq) / 2
    # la raiz "fisica" (exterior del circulo unitario escalado) es la de mayor modulo
    z_phys = z1 if abs(z1) >= abs(z2) else z2
    return {
        "w": {"re": w_re, "im": w_im},
        "z_roots": [
            {"re": float(z1.real), "im": float(z1.imag)},
            {"re": float(z2.real), "im": float(z2.imag)},
        ],
        "z_physical": {"re": float(z_phys.real), "im": float(z_phys.imag)},
    }


# ---------------------------------------------------------------------
# 2. Schwarz-Christoffel -- triangulo (formula Beta cerrada)
# ---------------------------------------------------------------------

def sc_triangle(alpha1, alpha2):
    alpha3 = 1.0 - alpha1 - alpha2
    if not (0 < alpha1 < 1 and 0 < alpha2 < 1 and 0 < alpha3 < 1):
        raise ValueError(
            f"Angulos invalidos: alpha1={alpha1}, alpha2={alpha2}, "
            f"alpha3(implicito)={alpha3} -- los 3 deben estar en (0,1)"
        )

    def integrand(t):
        return t ** (alpha1 - 1) * (1 - t) ** (alpha2 - 1)

    side_len, err_est = quad(integrand, 0.0, 1.0)
    beta_closed_form = float(special.beta(alpha1, alpha2))

    return {
        "angles_over_pi": {"alpha1": alpha1, "alpha2": alpha2, "alpha3": alpha3},
        "angles_deg": {"v1": alpha1 * 180, "v2": alpha2 * 180, "v3": alpha3 * 180},
        "finite_side_length_numeric": float(side_len),
        "finite_side_length_beta_closed_form": beta_closed_form,
        "quad_error_estimate": float(err_est),
        "relative_error_vs_closed_form": abs(side_len - beta_closed_form) / abs(beta_closed_form),
    }


# ---------------------------------------------------------------------
# 3. Schwarz-Christoffel -- poligono general (n vertices finitos)
# ---------------------------------------------------------------------

def _sc_integrand_complex(t, eps, prevertices, exps):
    z = t + 1j * eps
    val = 1.0 + 0.0j
    for x, e in zip(prevertices, exps):
        val *= (z - x) ** e
    return val


def _complex_quad(func, a, b):
    real_part, _ = quad(lambda t: func(t).real, a, b, limit=200)
    imag_part, _ = quad(lambda t: func(t).imag, a, b, limit=200)
    return complex(real_part, imag_part)


def sc_polygon(prevertices, angles_over_pi, eps=1e-6):
    n = len(prevertices)
    if len(angles_over_pi) != n:
        raise ValueError("prevertices y angles_over_pi deben tener el mismo largo")
    order = np.argsort(prevertices)
    prevertices = [float(prevertices[i]) for i in order]
    angles_over_pi = [float(angles_over_pi[i]) for i in order]
    exps = [a - 1.0 for a in angles_over_pi]

    angle_sum = sum(angles_over_pi)
    expected = n - 2
    if abs(angle_sum - expected) > 1e-6:
        raise ValueError(
            f"suma de angulos/pi = {angle_sum}, debe ser n-2 = {expected} "
            f"para un poligono cerrado de {n} vertices"
        )

    def integrand(t):
        return _sc_integrand_complex(t, eps, prevertices, exps)

    sides = []
    for k in range(n - 1):
        side = _complex_quad(integrand, prevertices[k], prevertices[k + 1])
        sides.append(side)

    vertices = [0j]
    for side in sides:
        vertices.append(vertices[-1] + side)

    turning_angles_deg = []
    for k in range(len(sides) - 1):
        s1, s2 = sides[k], sides[k + 1]
        turn = np.angle(s2 / s1)
        turning_angles_deg.append(float(np.degrees(turn)))

    return {
        "prevertices": prevertices,
        "angles_over_pi": angles_over_pi,
        "angle_sum_check": {"sum": angle_sum, "expected_n_minus_2": expected},
        "side_vectors": [{"re": float(s.real), "im": float(s.imag)} for s in sides],
        "side_lengths": [float(abs(s)) for s in sides],
        "vertices": [{"re": float(v.real), "im": float(v.imag)} for v in vertices],
        "turning_angles_deg_between_consecutive_sides": turning_angles_deg,
    }


# ---------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------

def _validate():
    checks = []

    # 1) Joukowski: circulo centrado en el origen radio a -> placa plana [-2a,2a]
    a = 1.0
    res_flat = joukowski_map(center=(0.0, 0.0), radius=a, a=a, n_points=361)
    re_vals = [p["re"] for p in res_flat["airfoil_points"]]
    im_vals = [p["im"] for p in res_flat["airfoil_points"]]
    checks.append({
        "name": "joukowski circulo z0=0,R=a -> placa plana [-2a,2a] (im~0, re en rango)",
        "passed": bool(max(abs(v) for v in im_vals) < 1e-6
                        and max(re_vals) - 2 * a < 1e-6
                        and min(re_vals) + 2 * a > -1e-6),
        "got": {"max_abs_im": max(abs(v) for v in im_vals),
                "re_range": [min(re_vals), max(re_vals)]},
    })

    # 2) Joukowski: circulo que pasa por z=a -> cuspide (derivada ~0) en ese punto
    res_cusp = joukowski_map(center=(-0.08, 0.08), a=a, n_points=721)
    checks.append({
        "name": "joukowski circulo offset por z=a -> cuspide de borde de fuga (dw/dz~0)",
        "passed": res_cusp["trailing_edge_cusp"],
        "got": res_cusp["min_abs_derivative"],
    })

    # 3) Joukowski: forward + inverse recupera z original
    z0 = 1.7 + 0.9j
    w0 = _joukowski_forward(z0, a)
    inv = joukowski_inverse(w0.real, w0.imag, a=a)
    zp = complex(inv["z_physical"]["re"], inv["z_physical"]["im"])
    checks.append({
        "name": "joukowski forward+inverse recupera z original",
        "passed": bool(abs(zp - z0) < 1e-8 or abs(zp - (a ** 2 / z0)) < 1e-8),
        "got": {"z_original": [z0.real, z0.imag], "z_recovered": inv["z_physical"]},
    })

    # 4) Schwarz-Christoffel triangulo equilatero: lado = Gamma(1/3)^2/Gamma(2/3)
    tri = sc_triangle(1 / 3, 1 / 3)
    checks.append({
        "name": "SC triangulo equilatero: integral numerica == funcion Beta cerrada",
        "passed": tri["relative_error_vs_closed_form"] < 1e-6,
        "got": tri,
    })

    # 5) Schwarz-Christoffel triangulo (90,45,45)
    tri2 = sc_triangle(0.5, 0.25)
    checks.append({
        "name": "SC triangulo (90,45,45): integral numerica == funcion Beta cerrada",
        "passed": tri2["relative_error_vs_closed_form"] < 1e-6,
        "got": tri2,
    })

    # 6) Schwarz-Christoffel poligono (rectangulo simetrico, 4 vertices, angulos pi/2):
    #    el giro entre lados consecutivos debe ser ~90 grados (todos los angulos
    #    interiores rectos => giro exterior de +-90 en cada vertice)
    rect = sc_polygon([-2, -1, 1, 2], [0.5, 0.5, 0.5, 0.5])
    turns = rect["turning_angles_deg_between_consecutive_sides"]
    checks.append({
        "name": "SC poligono rectangular: giro ~90 grados entre lados consecutivos",
        "passed": all(abs(abs(t) - 90) < 1.0 for t in turns),
        "got": turns,
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "all_passed": all_passed, "total": len(checks),
            "validation_passed": all_passed}


# ---------------------------------------------------------------------
# schema + dispatcher
# ---------------------------------------------------------------------

TOOL_SCHEMA = {
    "name": "joukowski_schwarz_christoffel",
    "description": (
        "Mapeos conformes clasicos. mode='joukowski_map': w=z+a^2/z aplicado "
        "a un circulo (center, radius opcional -- si se omite usa el radio "
        "minimo que pasa por z=a, dando cuspide de borde de fuga), devuelve "
        "puntos del circulo y del perfil resultante mas la derivada dw/dz "
        "(cero => cuspide). mode='joukowski_inverse': dado w=(w_re,w_im) y a, "
        "resuelve z^2-wz+a^2=0 y devuelve ambas raices mas la 'fisica' (mayor "
        "modulo). mode='schwarz_christoffel_triangle': mapea semiplano "
        "superior a un triangulo via formula Beta cerrada (alpha1,alpha2 en "
        "unidades de pi, alpha3=1-alpha1-alpha2 implicito), sin resolver "
        "parameter problem. mode='schwarz_christoffel_polygon': dado "
        "prevertices (reales, n de ellos) y angles_over_pi (n angulos "
        "interiores/pi, deben sumar n-2), integra el mapeo SC completo "
        "(offset imaginario eps para evitar singularidades del eje real) y "
        "devuelve vertices, lados, y angulos de giro entre lados consecutivos. "
        "mode='validate': 6 auto-chequeos (placa plana degenerada, cuspide "
        "de Joukowski, forward+inverse, 2 triangulos vs funcion Beta, "
        "poligono rectangular con giros de 90 grados)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "joukowski_map", "joukowski_inverse",
                    "schwarz_christoffel_triangle", "schwarz_christoffel_polygon",
                    "validate",
                ],
                "default": "validate",
            },
            "center": {"type": "array", "items": {"type": "number"},
                       "description": "[re,im] del centro del circulo. joukowski_map."},
            "radius": {"type": "number", "description": "Radio del circulo. joukowski_map (opcional)."},
            "a": {"type": "number", "default": 1.0, "description": "Parametro a de Joukowski."},
            "n_points": {"type": "integer", "default": 180},
            "w_re": {"type": "number", "description": "joukowski_inverse."},
            "w_im": {"type": "number", "description": "joukowski_inverse."},
            "alpha1": {"type": "number", "description": "schwarz_christoffel_triangle."},
            "alpha2": {"type": "number", "description": "schwarz_christoffel_triangle."},
            "prevertices": {"type": "array", "items": {"type": "number"},
                             "description": "schwarz_christoffel_polygon."},
            "angles_over_pi": {"type": "array", "items": {"type": "number"},
                                "description": "schwarz_christoffel_polygon."},
            "eps": {"type": "number", "default": 1e-6, "description": "schwarz_christoffel_polygon."},
        },
    },
}


def run(mode="validate", **params):
    try:
        if mode == "joukowski_map":
            center = tuple(params.get("center", (-0.1, 0.1)))
            return {"result": joukowski_map(
                center=center, radius=params.get("radius"),
                a=params.get("a", 1.0), n_points=params.get("n_points", 180),
            )}
        elif mode == "joukowski_inverse":
            return {"result": joukowski_inverse(
                params["w_re"], params["w_im"], a=params.get("a", 1.0),
            )}
        elif mode == "schwarz_christoffel_triangle":
            return {"result": sc_triangle(params["alpha1"], params["alpha2"])}
        elif mode == "schwarz_christoffel_polygon":
            return {"result": sc_polygon(
                params["prevertices"], params["angles_over_pi"],
                eps=params.get("eps", 1e-6),
            )}
        elif mode == "validate":
            return _validate()
        else:
            raise ValueError(f"mode desconocido: {mode}")
    except Exception as e:
        return {"error": str(e)}


def joukowski_schwarz_christoffel(mode="validate", **params):
    return run(mode=mode, **params)


def _handler(args):
    return run(**(args or {}))


try:
    import tool_registry
    tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler)
except ImportError:
    pass


if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "validate"
    if mode_arg == "validate":
        print(json.dumps(_validate(), indent=2))
    else:
        params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        print(json.dumps(run(mode=mode_arg, **params_arg), indent=2))
