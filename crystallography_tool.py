"""
crystallography_tool -- geometria de red cristalina, difraccion de Bragg,
y factor de estructura para las redes de Bravais cubicas comunes.

Patron: standalone (sin reenvolver otras tools), autocontenido, con su
propio mode="validate" al estilo del resto del repo.

Modos:
  - lattice_geometry: dado (a,b,c,alpha,beta,gamma) en el sistema cristalino
    mas general (triclinico), calcula el volumen de la celda unitaria y el
    espaciado interplanar d(hkl) via la formula general del tensor metrico
    reciproco. Los 7 sistemas cristalinos son casos particulares de esta
    misma formula (cubico: alpha=beta=gamma=90, a=b=c; etc.), asi que no
    hace falta una formula hardcodeada por sistema.
  - bragg_diffraction: ley de Bragg n*lambda = 2*d*sin(theta). Modo directo
    (d,lambda -> 2theta) o inverso (2theta,lambda -> d).
  - structure_factor: factor de estructura F(hkl) para simple cubica, BCC,
    FCC y diamante, con las reglas de extincion sistematica.
  - validate: casos de libro de texto (NaCl FCC con Cu-Ka, reglas de
    extincion exactas de BCC/FCC/diamante).
"""

import cmath
import math


# ---------------------------------------------------------------------
# 1. lattice_geometry
# ---------------------------------------------------------------------

def _cell_volume(a, b, c, alpha_deg, beta_deg, gamma_deg):
    al, be, ga = map(math.radians, (alpha_deg, beta_deg, gamma_deg))
    ca, cb, cg = math.cos(al), math.cos(be), math.cos(ga)
    factor = 1 - ca**2 - cb**2 - cg**2 + 2 * ca * cb * cg
    if factor <= 0:
        raise ValueError(
            f"parametros de red no fisicos: 1 - cos^2(alpha) - cos^2(beta) - cos^2(gamma) "
            f"+ 2*cos(alpha)*cos(beta)*cos(gamma) = {factor:.6f} <= 0 (celda degenerada)"
        )
    return a * b * c * math.sqrt(factor)


def _d_spacing(h, k, l, a, b, c, alpha_deg, beta_deg, gamma_deg):
    """Formula general (triclinica) del espaciado interplanar via el
    tensor metrico reciproco. Se reduce exactamente a las formulas
    especiales de cada sistema cristalino como caso particular
    (ej. cubico: 1/d^2 = (h^2+k^2+l^2)/a^2).
    """
    al, be, ga = map(math.radians, (alpha_deg, beta_deg, gamma_deg))
    ca, cb, cg = math.cos(al), math.cos(be), math.cos(ga)
    sa, sb, sg = math.sin(al), math.sin(be), math.sin(ga)

    V = _cell_volume(a, b, c, alpha_deg, beta_deg, gamma_deg)

    S11 = b**2 * c**2 * sa**2
    S22 = a**2 * c**2 * sb**2
    S33 = a**2 * b**2 * sg**2
    S12 = a * b * c**2 * (ca * cb - cg)
    S23 = a**2 * b * c * (cb * cg - ca)
    S13 = a * b**2 * c * (cg * ca - cb)

    inv_d2 = (
        S11 * h**2 + S22 * k**2 + S33 * l**2
        + 2 * S12 * h * k + 2 * S23 * k * l + 2 * S13 * h * l
    ) / V**2

    if inv_d2 <= 0:
        raise ValueError(f"1/d^2 = {inv_d2:.6e} <= 0 -- hkl=({h},{k},{l}) no da un plano fisico con esta celda")

    return 1.0 / math.sqrt(inv_d2), V


def _lattice_geometry(params):
    a = params["a"]
    b = params.get("b", a)
    c = params.get("c", a)
    alpha = params.get("alpha", 90.0)
    beta = params.get("beta", 90.0)
    gamma = params.get("gamma", 90.0)
    hkl_list = params.get("hkl", [[1, 0, 0], [1, 1, 0], [1, 1, 1]])

    V = _cell_volume(a, b, c, alpha, beta, gamma)

    planes = []
    for h, k, l in hkl_list:
        d, _ = _d_spacing(h, k, l, a, b, c, alpha, beta, gamma)
        planes.append({"hkl": [h, k, l], "d_angstrom": round(d, 6)})

    return {
        "mode": "lattice_geometry",
        "params_used": {"a": a, "b": b, "c": c, "alpha": alpha, "beta": beta, "gamma": gamma},
        "volumen_celda_A3": round(V, 6),
        "planos": planes,
        "nota": "formula general triclinica -- cubico/tetragonal/ortorrombico/hexagonal/monoclinico son casos particulares (alpha=beta=gamma=90 y/o a=b=c segun corresponda; hexagonal usa gamma=120)",
    }


# ---------------------------------------------------------------------
# 2. bragg_diffraction
# ---------------------------------------------------------------------

def _bragg_diffraction(params):
    wavelength = params["wavelength_angstrom"]
    n = params.get("n", 1)

    if "d_angstrom" in params:
        d = params["d_angstrom"]
        sin_theta = n * wavelength / (2 * d)
        if not (-1.0 <= sin_theta <= 1.0):
            return {
                "mode": "bragg_diffraction",
                "error": f"sin(theta) = {sin_theta:.6f} fuera de [-1,1] -- no hay reflexion posible con estos d/lambda/n (d demasiado chico o lambda/n demasiado grande)",
            }
        theta_deg = math.degrees(math.asin(sin_theta))
        return {
            "mode": "bragg_diffraction",
            "direccion": "d,lambda -> 2theta",
            "d_angstrom": d,
            "wavelength_angstrom": wavelength,
            "n": n,
            "theta_deg": round(theta_deg, 6),
            "two_theta_deg": round(2 * theta_deg, 6),
        }
    elif "two_theta_deg" in params:
        two_theta = params["two_theta_deg"]
        theta_rad = math.radians(two_theta / 2)
        d = n * wavelength / (2 * math.sin(theta_rad))
        return {
            "mode": "bragg_diffraction",
            "direccion": "2theta,lambda -> d",
            "two_theta_deg": two_theta,
            "wavelength_angstrom": wavelength,
            "n": n,
            "d_angstrom": round(d, 6),
        }
    else:
        raise ValueError("bragg_diffraction requiere 'd_angstrom' (modo directo) o 'two_theta_deg' (modo inverso)")


# ---------------------------------------------------------------------
# 3. structure_factor
# ---------------------------------------------------------------------

_BASIS = {
    "simple_cubic": [(0.0, 0.0, 0.0)],
    "bcc": [(0.0, 0.0, 0.0), (0.5, 0.5, 0.5)],
    "fcc": [(0.0, 0.0, 0.0), (0.5, 0.5, 0.0), (0.5, 0.0, 0.5), (0.0, 0.5, 0.5)],
    "diamond": [
        (0.0, 0.0, 0.0), (0.5, 0.5, 0.0), (0.5, 0.0, 0.5), (0.0, 0.5, 0.5),
        (0.25, 0.25, 0.25), (0.75, 0.75, 0.25), (0.75, 0.25, 0.75), (0.25, 0.75, 0.75),
    ],
}


def _structure_factor_single(h, k, l, lattice_type):
    basis = _BASIS[lattice_type]
    F = sum(cmath.exp(2j * math.pi * (h * x + k * y + l * z)) for x, y, z in basis)
    mag = abs(F)
    allowed = mag > 1e-6
    return F, mag, allowed


def _structure_factor(params):
    lattice_type = params.get("lattice_type", "fcc")
    if lattice_type not in _BASIS:
        raise ValueError(f"lattice_type desconocido: {lattice_type!r}. Usar: {list(_BASIS.keys())}")
    hkl_list = params.get("hkl", [[1, 0, 0], [1, 1, 0], [1, 1, 1], [2, 0, 0]])

    results = []
    for h, k, l in hkl_list:
        F, mag, allowed = _structure_factor_single(h, k, l, lattice_type)
        results.append({
            "hkl": [h, k, l],
            "F_real": round(F.real, 6),
            "F_imag": round(F.imag, 6),
            "magnitud": round(mag, 6),
            "reflexion_permitida": allowed,
        })

    return {
        "mode": "structure_factor",
        "lattice_type": lattice_type,
        "resultados": results,
        "nota": "factor de forma atomico f_j=1 para todos los atomos de la base (factor de estructura geometrico puro) -- reglas de extincion sistematica exactas, independientes de la especie atomica",
    }


# ---------------------------------------------------------------------
# 4. validate
# ---------------------------------------------------------------------

def _validate():
    checks = {}

    # (a) NaCl: FCC, a=5.64 A, plano (200), Cu-Ka lambda=1.5406 A
    # d(200) para cubico = a / sqrt(h^2+k^2+l^2) = 5.64/2 = 2.82 A
    d200, V = _d_spacing(2, 0, 0, 5.64, 5.64, 5.64, 90, 90, 90)
    checks["NaCl_d200_esperado_2.82A"] = {
        "cumple": abs(d200 - 2.82) < 1e-6,
        "valor": round(d200, 6),
    }
    checks["NaCl_volumen_esperado_a_cubo"] = {
        "cumple": abs(V - 5.64**3) < 1e-6,
        "valor": round(V, 6),
    }

    # (b) Bragg con ese d200 y Cu-Ka -> 2theta conocido (~31.7 grados, tabulado)
    br = _bragg_diffraction({"d_angstrom": d200, "wavelength_angstrom": 1.5406, "n": 1})
    checks["NaCl_200_two_theta_cerca_de_31.7deg"] = {
        "cumple": abs(br["two_theta_deg"] - 31.7) < 0.5,
        "valor": br["two_theta_deg"],
    }

    # (c) Roundtrip Bragg: d -> 2theta -> d debe ser identidad
    br2 = _bragg_diffraction({"two_theta_deg": br["two_theta_deg"], "wavelength_angstrom": 1.5406, "n": 1})
    checks["bragg_roundtrip_d_identidad"] = {
        "cumple": abs(br2["d_angstrom"] - d200) < 1e-6,
        "valor": br2["d_angstrom"],
    }

    # (d) Reglas de extincion BCC: (100) prohibido (h+k+l impar), (110) permitido (par)
    _, mag100_bcc, allowed100_bcc = _structure_factor_single(1, 0, 0, "bcc")
    _, mag110_bcc, allowed110_bcc = _structure_factor_single(1, 1, 0, "bcc")
    checks["BCC_100_prohibido"] = {"cumple": not allowed100_bcc, "valor": round(mag100_bcc, 6)}
    checks["BCC_110_permitido"] = {"cumple": allowed110_bcc, "valor": round(mag110_bcc, 6)}

    # (e) Reglas de extincion FCC: (100) prohibido (paridad mixta), (111) permitido (todos impares), (200) permitido (todos pares)
    _, mag100_fcc, allowed100_fcc = _structure_factor_single(1, 0, 0, "fcc")
    _, mag111_fcc, allowed111_fcc = _structure_factor_single(1, 1, 1, "fcc")
    _, mag200_fcc, allowed200_fcc = _structure_factor_single(2, 0, 0, "fcc")
    checks["FCC_100_prohibido"] = {"cumple": not allowed100_fcc, "valor": round(mag100_fcc, 6)}
    checks["FCC_111_permitido"] = {"cumple": allowed111_fcc, "valor": round(mag111_fcc, 6)}
    checks["FCC_200_permitido"] = {"cumple": allowed200_fcc, "valor": round(mag200_fcc, 6)}

    # (f) Reglas de extincion diamante: (200) prohibido (todos pares pero h+k+l=2 no divisible por 4), (111) permitido, (400) permitido (todos pares, h+k+l=4 divisible por 4)
    _, mag200_dia, allowed200_dia = _structure_factor_single(2, 0, 0, "diamond")
    _, mag111_dia, allowed111_dia = _structure_factor_single(1, 1, 1, "diamond")
    _, mag400_dia, allowed400_dia = _structure_factor_single(4, 0, 0, "diamond")
    checks["diamante_200_prohibido"] = {"cumple": not allowed200_dia, "valor": round(mag200_dia, 6)}
    checks["diamante_111_permitido"] = {"cumple": allowed111_dia, "valor": round(mag111_dia, 6)}
    checks["diamante_400_permitido"] = {"cumple": allowed400_dia, "valor": round(mag400_dia, 6)}

    # (g) Simple cubica: ninguna extincion, todo permitido
    _, mag100_sc, allowed100_sc = _structure_factor_single(1, 0, 0, "simple_cubic")
    checks["simple_cubica_100_permitido"] = {"cumple": allowed100_sc, "valor": round(mag100_sc, 6)}

    all_pass = all(c["cumple"] for c in checks.values())
    return {"mode": "validate", "checks": checks, "validation_passed": all_pass}


# ---------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------

def compute_crystallography(mode="lattice_geometry", params=None):
    params = params or {}
    if mode == "lattice_geometry":
        return _lattice_geometry(params)
    elif mode == "bragg_diffraction":
        return _bragg_diffraction(params)
    elif mode == "structure_factor":
        return _structure_factor(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode!r}. Usar: lattice_geometry | bragg_diffraction | structure_factor | validate")


CRYSTALLOGRAPHY_TOOL_SCHEMA = {
    "name": "crystallography_tool",
    "description": (
        "Geometria de red cristalina (volumen de celda, espaciado interplanar d(hkl) "
        "via formula general triclinica valida para los 7 sistemas cristalinos), "
        "ley de Bragg (d,lambda <-> 2theta), y factor de estructura geometrico con "
        "reglas de extincion sistematica para simple_cubic/bcc/fcc/diamond. "
        "mode='lattice_geometry': params={a,b,c,alpha,beta,gamma,hkl:[[h,k,l],...]} "
        "(b,c,alpha,beta,gamma opcionales, default cubico). "
        "mode='bragg_diffraction': params={wavelength_angstrom,n,d_angstrom} o "
        "{wavelength_angstrom,n,two_theta_deg}. "
        "mode='structure_factor': params={lattice_type,hkl:[[h,k,l],...]}."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["lattice_geometry", "bragg_diffraction", "structure_factor", "validate"],
                "default": "lattice_geometry",
            },
            "params": {"type": "object"},
        },
    },
}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_crystallography("validate"), indent=2, ensure_ascii=False))


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool(
    "crystallography_tool",
    CRYSTALLOGRAPHY_TOOL_SCHEMA,
    lambda args: compute_crystallography(args.get("mode", "lattice_geometry"), args.get("params")),
)
