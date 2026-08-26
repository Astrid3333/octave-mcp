"""
perceptual_scale_tool.py

Escala perceptual del color:
- color_difference_scale: distancia perceptual entre dos colores Lab,
  usando CIE76 (euclidiana simple) y CIEDE2000 (perceptualmente ajustada)
- contrast_scale: relacion de contraste WCAG entre dos colores sRGB y su
  nivel de legibilidad (AA/AAA)
- harmony_scale: distancia angular en el circulo cromatico (HSL hue) entre
  dos colores, e identificacion de relaciones de armonia conocidas
"""

import math


# ---------------------------------------------------------------------------
# CIE76 y CIEDE2000
# ---------------------------------------------------------------------------
def cie76(lab1, lab2):
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    return math.sqrt((L2 - L1) ** 2 + (a2 - a1) ** 2 + (b2 - b1) ** 2)


def ciede2000(lab1, lab2):
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    C1 = math.sqrt(a1 ** 2 + b1 ** 2)
    C2 = math.sqrt(a2 ** 2 + b2 ** 2)
    Cbar = (C1 + C2) / 2.0

    G = 0.5 * (1 - math.sqrt((Cbar ** 7) / (Cbar ** 7 + 25.0 ** 7)))
    a1p = (1 + G) * a1
    a2p = (1 + G) * a2

    C1p = math.sqrt(a1p ** 2 + b1 ** 2)
    C2p = math.sqrt(a2p ** 2 + b2 ** 2)

    def _hue(a, b):
        if a == 0 and b == 0:
            return 0.0
        h = math.degrees(math.atan2(b, a))
        return h + 360.0 if h < 0 else h

    h1p = _hue(a1p, b1)
    h2p = _hue(a2p, b2)

    dLp = L2 - L1
    dCp = C2p - C1p

    if C1p * C2p == 0:
        dhp = 0.0
    else:
        dh = h2p - h1p
        if dh > 180:
            dh -= 360
        elif dh < -180:
            dh += 360
        dhp = dh
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2.0))

    Lbarp = (L1 + L2) / 2.0
    Cbarp = (C1p + C2p) / 2.0

    if C1p * C2p == 0:
        hbarp = h1p + h2p
    else:
        if abs(h1p - h2p) > 180:
            hbarp = (h1p + h2p + 360) / 2.0 if (h1p + h2p) < 360 else (h1p + h2p - 360) / 2.0
        else:
            hbarp = (h1p + h2p) / 2.0

    T = (
        1
        - 0.17 * math.cos(math.radians(hbarp - 30))
        + 0.24 * math.cos(math.radians(2 * hbarp))
        + 0.32 * math.cos(math.radians(3 * hbarp + 6))
        - 0.20 * math.cos(math.radians(4 * hbarp - 63))
    )

    d_theta = 30 * math.exp(-(((hbarp - 275) / 25.0) ** 2))
    Rc = 2 * math.sqrt((Cbarp ** 7) / (Cbarp ** 7 + 25.0 ** 7))
    Sl = 1 + (0.015 * (Lbarp - 50) ** 2) / math.sqrt(20 + (Lbarp - 50) ** 2)
    Sc = 1 + 0.045 * Cbarp
    Sh = 1 + 0.015 * Cbarp * T
    Rt = -math.sin(math.radians(2 * d_theta)) * Rc

    dE = math.sqrt(
        (dLp / Sl) ** 2
        + (dCp / Sc) ** 2
        + (dHp / Sh) ** 2
        + Rt * (dCp / Sc) * (dHp / Sh)
    )
    return dE


def color_difference_scale(params):
    lab1 = (params["L1"], params["a1"], params["b1"])
    lab2 = (params["L2"], params["a2"], params["b2"])

    d76 = cie76(lab1, lab2)
    d00 = ciede2000(lab1, lab2)

    return {
        "cie76_distance": d76,
        "ciede2000_distance": d00,
        "note": (
            "CIE76 es euclidiana simple en Lab; CIEDE2000 ajusta por "
            "no-uniformidad perceptual (mismo delta numerico percibido "
            "distinto segun zona del espacio de color)."
        ),
    }


# ---------------------------------------------------------------------------
# Contraste WCAG
# ---------------------------------------------------------------------------
def _srgb_to_linear(c):
    c = c / 255.0
    if c <= 0.03928:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb):
    r, g, b = rgb
    R = _srgb_to_linear(r)
    G = _srgb_to_linear(g)
    B = _srgb_to_linear(b)
    return 0.2126 * R + 0.7152 * G + 0.0722 * B


def contrast_ratio(rgb1, rgb2):
    L1 = relative_luminance(rgb1)
    L2 = relative_luminance(rgb2)
    lighter, darker = max(L1, L2), min(L1, L2)
    return (lighter + 0.05) / (darker + 0.05)


def contrast_scale(params):
    rgb1 = (params["r1"], params["g1"], params["b1"])
    rgb2 = (params["r2"], params["g2"], params["b2"])
    large_text = params.get("large_text", False)

    ratio = contrast_ratio(rgb1, rgb2)

    if large_text:
        aa_pass = ratio >= 3.0
        aaa_pass = ratio >= 4.5
    else:
        aa_pass = ratio >= 4.5
        aaa_pass = ratio >= 7.0

    return {
        "contrast_ratio": ratio,
        "wcag_aa_pass": aa_pass,
        "wcag_aaa_pass": aaa_pass,
        "large_text": large_text,
    }


# ---------------------------------------------------------------------------
# Armonias cromaticas (circulo de matiz HSL, 0-360 grados)
# ---------------------------------------------------------------------------
HARMONY_ANGLES = {
    "complementary": 180.0,
    "triadic": 120.0,
    "split_complementary": 150.0,
    "analogous": 30.0,
    "square": 90.0,
}


def harmony_scale(params):
    hue1 = params["hue1"] % 360.0
    hue2 = params["hue2"] % 360.0
    tolerance_deg = params.get("tolerance_deg", 10.0)

    diff = abs(hue1 - hue2)
    diff = min(diff, 360.0 - diff)

    matches = []
    for name, angle in HARMONY_ANGLES.items():
        if abs(diff - angle) <= tolerance_deg:
            matches.append(name)

    return {
        "hue_distance_deg": diff,
        "matched_harmonies": matches,
    }


def perceptual_scale_tool(params: dict) -> dict:
    mode = params.get("mode", "color_difference_scale")

    if mode == "color_difference_scale":
        return color_difference_scale(params)
    elif mode == "contrast_scale":
        return contrast_scale(params)
    elif mode == "harmony_scale":
        return harmony_scale(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(
            "mode invalido. Opciones: color_difference_scale, contrast_scale, "
            "harmony_scale, validate"
        )


def _validate():
    checks = []

    # 1) Identidad: mismo color -> distancia 0 (CIE76 y CIEDE2000)
    same = color_difference_scale({"L1": 50.0, "a1": 20.0, "b1": -10.0, "L2": 50.0, "a2": 20.0, "b2": -10.0})
    checks.append({
        "name": "identity_zero_distance",
        "passed": abs(same["cie76_distance"]) < 1e-9 and abs(same["ciede2000_distance"]) < 1e-9,
        "result": same,
    })

    # 2) CIE76: distancia euclidiana directa conocida (3-4-0 -> 5)
    known = color_difference_scale({"L1": 0.0, "a1": 0.0, "b1": 0.0, "L2": 3.0, "a2": 4.0, "b2": 0.0})
    checks.append({
        "name": "cie76_known_euclidean_distance",
        "passed": abs(known["cie76_distance"] - 5.0) < 1e-9,
        "cie76_distance": known["cie76_distance"],
    })

    # 3) Simetria: d(A,B) == d(B,A) para ambas metricas
    d_ab = color_difference_scale({"L1": 40.0, "a1": 10.0, "b1": 5.0, "L2": 60.0, "a2": -5.0, "b2": 15.0})
    d_ba = color_difference_scale({"L1": 60.0, "a1": -5.0, "b1": 15.0, "L2": 40.0, "a2": 10.0, "b2": 5.0})
    checks.append({
        "name": "symmetry",
        "passed": abs(d_ab["cie76_distance"] - d_ba["cie76_distance"]) < 1e-9
        and abs(d_ab["ciede2000_distance"] - d_ba["ciede2000_distance"]) < 1e-6,
        "d_ab": d_ab, "d_ba": d_ba,
    })

    # 4) Contraste WCAG: blanco sobre negro -> ratio 21:1 (maximo posible)
    r4 = contrast_scale({"r1": 255, "g1": 255, "b1": 255, "r2": 0, "g2": 0, "b2": 0})
    checks.append({
        "name": "max_contrast_white_black",
        "passed": abs(r4["contrast_ratio"] - 21.0) < 0.01 and r4["wcag_aaa_pass"],
        "contrast_ratio": r4["contrast_ratio"],
    })

    # 5) Contraste WCAG: mismo color -> ratio 1:1, falla AA
    r5 = contrast_scale({"r1": 128, "g1": 128, "b1": 128, "r2": 128, "g2": 128, "b2": 128})
    checks.append({
        "name": "min_contrast_same_color",
        "passed": abs(r5["contrast_ratio"] - 1.0) < 1e-6 and not r5["wcag_aa_pass"],
        "contrast_ratio": r5["contrast_ratio"],
    })

    # 6) Armonia: 180 grados exactos -> complementary detectado
    r6 = harmony_scale({"hue1": 0.0, "hue2": 180.0})
    checks.append({
        "name": "complementary_detected",
        "passed": "complementary" in r6["matched_harmonies"],
        "result": r6,
    })

    # 7) Armonia: 120 grados exactos -> triadic detectado
    r7 = harmony_scale({"hue1": 40.0, "hue2": 160.0})
    checks.append({
        "name": "triadic_detected",
        "passed": "triadic" in r7["matched_harmonies"],
        "result": r7,
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "mode": "validate",
        "tool": "perceptual_scale_tool",
        "all_passed": all_passed,
        "checks": checks,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(perceptual_scale_tool({"mode": "validate"}), indent=2))
