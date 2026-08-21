"""
color_math_tool.py

Matematica del color: conversion entre espacios (RGB/HSL/XYZ/Lab),
contraste WCAG, distancia perceptual (CIE76) y generacion de paletas
armonicas via rotacion de matiz. 100% numpy puro, sin dependencias de
color externas (sin colormath/colour-science), mismo patron que el
resto de la suite octave-mcp: dispatcher run(mode, params), self_test
con checks booleanos, ValueError en modo/parametros invalidos.

Convenciones de rango:
  - rgb: [r, g, b] en 0-255 (float u int)
  - hsl: [h, s, l] con h en grados 0-360, s y l en 0-100
  - xyz: [x, y, z] escala D65 0-100 (Y=100 para blanco)
  - lab: [L, a, b] con L en 0-100, a/b aprox -128..127

Referencia: sRGB D65, matrices IEC 61966-2-1 estandar. WCAG 2.x usa el
mismo par de coeficientes de luminancia relativa (0.2126/0.7152/0.0722)
que la fila Y de la matriz sRGB->XYZ, aplicados a canales linealizados.
"""

import numpy as np

_VALID_SPACES = {"rgb", "hsl", "xyz", "lab"}

# Matriz sRGB (linear) -> XYZ, D65, escala 0-100
_RGB_TO_XYZ = np.array([
    [41.24564, 35.75761, 18.04375],
    [21.26729, 71.51522, 7.21750],
    [1.93339, 11.91920, 95.03041],
])
_XYZ_TO_RGB = np.linalg.inv(_RGB_TO_XYZ)

_D65_WHITE = (95.047, 100.0, 108.883)
_LAB_DELTA = 6.0 / 29.0


# ---------------------------------------------------------------------------
# helpers de bajo nivel (todas trabajan en floats puros, sin condicionar
# sobre arrays de numpy directamente para evitar el gotcha de numpy.bool_
# filtrandose a la serializacion JSON-RPC)
# ---------------------------------------------------------------------------

def _srgb_to_linear(c):
    c = float(c)
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c):
    c = float(max(0.0, min(1.0, c)))
    if c <= 0.0031308:
        return c * 12.92
    return 1.055 * (c ** (1.0 / 2.4)) - 0.055


def _lab_f(t):
    if t > _LAB_DELTA ** 3:
        return t ** (1.0 / 3.0)
    return t / (3.0 * _LAB_DELTA ** 2) + 4.0 / 29.0


def _lab_f_inv(t):
    if t > _LAB_DELTA:
        return t ** 3
    return 3.0 * _LAB_DELTA ** 2 * (t - 4.0 / 29.0)


def _validate_rgb(rgb):
    if not (isinstance(rgb, (list, tuple)) and len(rgb) == 3):
        raise ValueError("rgb debe ser una lista de 3 componentes [r, g, b]")
    for c in rgb:
        if not (0 <= float(c) <= 255):
            raise ValueError(f"componente rgb fuera de rango 0-255: {c!r}")
    return [float(c) for c in rgb]


# ---------------------------------------------------------------------------
# conversiones RGB <-> XYZ <-> Lab
# ---------------------------------------------------------------------------

def rgb_to_xyz(rgb):
    r, g, b = _validate_rgb(rgb)
    lin = np.array([_srgb_to_linear(r / 255.0), _srgb_to_linear(g / 255.0), _srgb_to_linear(b / 255.0)])
    xyz = _RGB_TO_XYZ @ lin
    return [float(v) for v in xyz]


def xyz_to_rgb(xyz):
    if not (isinstance(xyz, (list, tuple)) and len(xyz) == 3):
        raise ValueError("xyz debe ser una lista de 3 componentes [x, y, z]")
    xyz_arr = np.array([float(v) for v in xyz])
    lin = _XYZ_TO_RGB @ xyz_arr
    rgb = [round(_linear_to_srgb(v) * 255.0, 6) for v in lin]
    return rgb


def xyz_to_lab(xyz):
    if not (isinstance(xyz, (list, tuple)) and len(xyz) == 3):
        raise ValueError("xyz debe ser una lista de 3 componentes [x, y, z]")
    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    fx = _lab_f(x / _D65_WHITE[0])
    fy = _lab_f(y / _D65_WHITE[1])
    fz = _lab_f(z / _D65_WHITE[2])
    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)
    return [L, a, b]


def lab_to_xyz(lab):
    if not (isinstance(lab, (list, tuple)) and len(lab) == 3):
        raise ValueError("lab debe ser una lista de 3 componentes [L, a, b]")
    L, a, b = float(lab[0]), float(lab[1]), float(lab[2])
    fy = (L + 16.0) / 116.0
    fx = fy + a / 500.0
    fz = fy - b / 200.0
    x = _D65_WHITE[0] * _lab_f_inv(fx)
    y = _D65_WHITE[1] * _lab_f_inv(fy)
    z = _D65_WHITE[2] * _lab_f_inv(fz)
    return [x, y, z]


def rgb_to_lab(rgb):
    return xyz_to_lab(rgb_to_xyz(rgb))


def lab_to_rgb(lab):
    return xyz_to_rgb(lab_to_xyz(lab))


# ---------------------------------------------------------------------------
# conversiones RGB <-> HSL
# ---------------------------------------------------------------------------

def rgb_to_hsl(rgb):
    r, g, b = [c / 255.0 for c in _validate_rgb(rgb)]
    maxc, minc = max(r, g, b), min(r, g, b)
    l = (maxc + minc) / 2.0

    if maxc == minc:
        h = s = 0.0
    else:
        d = maxc - minc
        s = d / (2.0 - maxc - minc) if l > 0.5 else d / (maxc + minc)
        if maxc == r:
            h = ((g - b) / d) + (6.0 if g < b else 0.0)
        elif maxc == g:
            h = (b - r) / d + 2.0
        else:
            h = (r - g) / d + 4.0
        h *= 60.0

    return [h % 360.0, s * 100.0, l * 100.0]


def _hue_to_rgb_component(p, q, t):
    if t < 0:
        t += 1.0
    if t > 1:
        t -= 1.0
    if t < 1.0 / 6.0:
        return p + (q - p) * 6.0 * t
    if t < 1.0 / 2.0:
        return q
    if t < 2.0 / 3.0:
        return p + (q - p) * (2.0 / 3.0 - t) * 6.0
    return p


def hsl_to_rgb(hsl):
    if not (isinstance(hsl, (list, tuple)) and len(hsl) == 3):
        raise ValueError("hsl debe ser una lista de 3 componentes [h, s, l]")
    h, s, l = float(hsl[0]) / 360.0, float(hsl[1]) / 100.0, float(hsl[2]) / 100.0

    if s == 0:
        r = g = b = l
    else:
        q = l * (1.0 + s) if l < 0.5 else l + s - l * s
        p = 2.0 * l - q
        r = _hue_to_rgb_component(p, q, h + 1.0 / 3.0)
        g = _hue_to_rgb_component(p, q, h)
        b = _hue_to_rgb_component(p, q, h - 1.0 / 3.0)

    return [round(r * 255.0, 6), round(g * 255.0, 6), round(b * 255.0, 6)]


# ---------------------------------------------------------------------------
# conversion generica entre cualquier par de espacios soportados
# ---------------------------------------------------------------------------

def _to_rgb(color, space):
    if space == "rgb":
        return _validate_rgb(color)
    if space == "hsl":
        return hsl_to_rgb(color)
    if space == "xyz":
        return xyz_to_rgb(color)
    if space == "lab":
        return lab_to_rgb(color)
    raise ValueError(f"espacio de color desconocido: {space!r} (validos: {sorted(_VALID_SPACES)})")


def _from_rgb(rgb, space):
    if space == "rgb":
        return rgb
    if space == "hsl":
        return rgb_to_hsl(rgb)
    if space == "xyz":
        return rgb_to_xyz(rgb)
    if space == "lab":
        return rgb_to_lab(rgb)
    raise ValueError(f"espacio de color desconocido: {space!r} (validos: {sorted(_VALID_SPACES)})")


def compute_convert(params):
    color = params.get("color")
    from_space = params.get("from")
    to_space = params.get("to")
    if from_space not in _VALID_SPACES:
        raise ValueError(f"'from' invalido: {from_space!r} (validos: {sorted(_VALID_SPACES)})")
    if to_space not in _VALID_SPACES:
        raise ValueError(f"'to' invalido: {to_space!r} (validos: {sorted(_VALID_SPACES)})")
    if color is None:
        raise ValueError("falta 'color'")

    rgb = _to_rgb(color, from_space)
    result = _from_rgb(rgb, to_space)
    return {
        "mode": "convert",
        "from": from_space,
        "to": to_space,
        "input": color,
        "result": result,
    }


# ---------------------------------------------------------------------------
# contraste WCAG
# ---------------------------------------------------------------------------

def _relative_luminance(rgb):
    r, g, b = [c / 255.0 for c in _validate_rgb(rgb)]

    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def compute_contrast_ratio(params):
    c1 = params.get("color1")
    c2 = params.get("color2")
    if c1 is None or c2 is None:
        raise ValueError("faltan 'color1' y/o 'color2'")

    l1 = _relative_luminance(c1)
    l2 = _relative_luminance(c2)
    lighter, darker = max(l1, l2), min(l1, l2)
    ratio = (lighter + 0.05) / (darker + 0.05)

    return {
        "mode": "contrast_ratio",
        "ratio": round(ratio, 4),
        "luminance_color1": round(l1, 6),
        "luminance_color2": round(l2, 6),
        "passes_aa_normal_text": bool(ratio >= 4.5),
        "passes_aa_large_text": bool(ratio >= 3.0),
        "passes_aaa_normal_text": bool(ratio >= 7.0),
        "passes_aaa_large_text": bool(ratio >= 4.5),
    }


# ---------------------------------------------------------------------------
# distancia perceptual
# ---------------------------------------------------------------------------

def compute_perceptual_distance(params):
    c1 = params.get("color1")
    c2 = params.get("color2")
    metric = params.get("metric", "cie76")
    if c1 is None or c2 is None:
        raise ValueError("faltan 'color1' y/o 'color2'")
    if metric != "cie76":
        raise ValueError(f"metrica no soportada: {metric!r} (por ahora solo 'cie76')")

    lab1 = np.array(rgb_to_lab(c1))
    lab2 = np.array(rgb_to_lab(c2))
    delta_e = float(np.linalg.norm(lab1 - lab2))

    return {
        "mode": "perceptual_distance",
        "metric": "cie76",
        "delta_e": round(delta_e, 6),
        "lab_color1": [round(v, 4) for v in lab1.tolist()],
        "lab_color2": [round(v, 4) for v in lab2.tolist()],
    }


# ---------------------------------------------------------------------------
# armonia cromatica
# ---------------------------------------------------------------------------

_HARMONY_OFFSETS = {
    "complementary": [180.0],
    "triadic": [120.0, 240.0],
    "tetradic": [90.0, 180.0, 270.0],
    "split_complementary": [150.0, 210.0],
}


def compute_harmony(params):
    base_color = params.get("base_color")
    space = params.get("space", "rgb")
    scheme = params.get("scheme")
    angle = params.get("angle", 30.0)

    if base_color is None:
        raise ValueError("falta 'base_color'")
    if space not in _VALID_SPACES:
        raise ValueError(f"'space' invalido: {space!r}")

    base_rgb = _to_rgb(base_color, space)
    base_hsl = rgb_to_hsl(base_rgb)

    if scheme == "analogous":
        offsets = [-float(angle), float(angle)]
    elif scheme in _HARMONY_OFFSETS:
        offsets = _HARMONY_OFFSETS[scheme]
    else:
        raise ValueError(
            f"scheme desconocido: {scheme!r} "
            f"(validos: analogous, {sorted(_HARMONY_OFFSETS)})"
        )

    palette = [{"hsl": base_hsl, "rgb": base_rgb}]
    for off in offsets:
        h = (base_hsl[0] + off) % 360.0
        hsl = [h, base_hsl[1], base_hsl[2]]
        palette.append({"hsl": hsl, "rgb": hsl_to_rgb(hsl)})

    return {
        "mode": "harmony",
        "scheme": scheme,
        "base": {"hsl": base_hsl, "rgb": base_rgb},
        "palette": palette,
    }


# ---------------------------------------------------------------------------
# self_test
# ---------------------------------------------------------------------------

def run_self_test():
    checks = []

    def check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    # 1) blanco RGB -> Lab ~ (100, 0, 0)
    lab_white = rgb_to_lab([255, 255, 255])
    ok = abs(lab_white[0] - 100.0) < 1e-3 and abs(lab_white[1]) < 1e-3 and abs(lab_white[2]) < 1e-3
    check("rgb_blanco_a_lab_100_0_0", ok, f"lab={[round(v, 4) for v in lab_white]}")

    # 2) negro RGB -> Lab (0, 0, 0)
    lab_black = rgb_to_lab([0, 0, 0])
    ok = all(abs(v) < 1e-6 for v in lab_black)
    check("rgb_negro_a_lab_0_0_0", ok, f"lab={lab_black}")

    # 3) round-trip RGB -> XYZ -> RGB
    original = [123.0, 45.0, 200.0]
    recovered = xyz_to_rgb(rgb_to_xyz(original))
    max_err = max(abs(a - b) for a, b in zip(original, recovered))
    check("roundtrip_rgb_xyz_rgb", max_err < 1e-3, f"max_err={max_err:.2e}")

    # 4) round-trip RGB -> Lab -> RGB
    recovered_lab = lab_to_rgb(rgb_to_lab(original))
    max_err_lab = max(abs(a - b) for a, b in zip(original, recovered_lab))
    check("roundtrip_rgb_lab_rgb", max_err_lab < 1e-2, f"max_err={max_err_lab:.2e}")

    # 5) round-trip RGB -> HSL -> RGB
    recovered_hsl = hsl_to_rgb(rgb_to_hsl(original))
    max_err_hsl = max(abs(a - b) for a, b in zip(original, recovered_hsl))
    check("roundtrip_rgb_hsl_rgb", max_err_hsl < 1e-3, f"max_err={max_err_hsl:.2e}")

    # 6) contraste negro/blanco = 21:1 (maximo posible en WCAG)
    r = compute_contrast_ratio({"color1": [0, 0, 0], "color2": [255, 255, 255]})
    check("contraste_negro_blanco_21_a_1", abs(r["ratio"] - 21.0) < 1e-2, f"ratio={r['ratio']}")

    # 7) contraste mismo color = 1:1
    r_same = compute_contrast_ratio({"color1": [100, 150, 200], "color2": [100, 150, 200]})
    check("contraste_mismo_color_1_a_1", abs(r_same["ratio"] - 1.0) < 1e-6, f"ratio={r_same['ratio']}")

    # 8) negro/blanco pasa AAA normal text (umbral 7:1)
    check("negro_blanco_pasa_aaa", r["passes_aaa_normal_text"] is True, f"ratio={r['ratio']}")

    # 9) distancia perceptual entre el mismo color es 0
    d_same = compute_perceptual_distance({"color1": [10, 20, 30], "color2": [10, 20, 30]})
    check("distancia_mismo_color_es_cero", d_same["delta_e"] < 1e-9, f"delta_e={d_same['delta_e']}")

    # 10) distancia rojo-verde > distancia rojo-rojo_similar
    d_far = compute_perceptual_distance({"color1": [255, 0, 0], "color2": [0, 255, 0]})
    d_near = compute_perceptual_distance({"color1": [255, 0, 0], "color2": [250, 5, 5]})
    check(
        "distancia_perceptual_monotonica",
        d_far["delta_e"] > d_near["delta_e"],
        f"far={d_far['delta_e']:.2f} near={d_near['delta_e']:.2f}",
    )

    # 11) armonia complementaria: diferencia de matiz es 180 grados
    h = compute_harmony({"base_color": [200, 50, 50], "scheme": "complementary"})
    base_h = h["base"]["hsl"][0]
    comp_h = h["palette"][1]["hsl"][0]
    circular_diff = (comp_h - base_h) % 360
    diff = abs(circular_diff - 180.0)
    check("armonia_complementaria_180_grados", diff < 1e-6, f"diff={circular_diff:.6f}")

    # 12) armonia triadica: 3 colores en la paleta (base + 2), separados 120
    h_tri = compute_harmony({"base_color": [200, 50, 50], "scheme": "triadic"})
    check(
        "armonia_triadica_tres_colores",
        len(h_tri["palette"]) == 3,
        f"n={len(h_tri['palette'])}",
    )

    # 13) ValueError con espacio invalido en convert
    try:
        compute_convert({"color": [1, 2, 3], "from": "rgb", "to": "cmyk"})
        check("valueerror_espacio_invalido_en_convert", False, "no se levanto excepcion")
    except ValueError:
        check("valueerror_espacio_invalido_en_convert", True, "")

    # 14) ValueError con scheme desconocido en harmony
    try:
        compute_harmony({"base_color": [1, 2, 3], "scheme": "no_existe"})
        check("valueerror_scheme_invalido_en_harmony", False, "no se levanto excepcion")
    except ValueError:
        check("valueerror_scheme_invalido_en_harmony", True, "")

    # 15) ValueError con modo desconocido en run()
    try:
        run("modo_inexistente", {})
        check("valueerror_modo_desconocido_en_run", False, "no se levanto excepcion")
    except ValueError:
        check("valueerror_modo_desconocido_en_run", True, "")

    total = len(checks)
    passed = sum(1 for c in checks if c["passed"])
    return {"total": total, "passed": passed, "all_passed": passed == total, "checks": checks}


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def run(mode, params=None):
    params = params or {}
    if mode == "convert":
        return compute_convert(params)
    elif mode == "contrast_ratio":
        return compute_contrast_ratio(params)
    elif mode == "perceptual_distance":
        return compute_perceptual_distance(params)
    elif mode == "harmony":
        return compute_harmony(params)
    elif mode == "self_test":
        return run_self_test()
    else:
        raise ValueError(f"modo desconocido: {mode!r}")


COLOR_MATH_TOOL_SCHEMA = {
    "name": "color_math_tool",
    "description": (
        "Matematica del color: conversion entre espacios RGB/HSL/XYZ/Lab "
        "(matrices sRGB D65 estandar), calculo de ratio de contraste WCAG "
        "2.x, distancia perceptual CIE76 (Lab) y generacion de paletas "
        "armonicas (complementaria/triadica/tetradica/analoga/split-complementaria) "
        "via rotacion de matiz en HSL."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["convert", "contrast_ratio", "perceptual_distance", "harmony", "self_test"],
            },
            "params": {
                "type": "object",
                "properties": {
                    "color": {"type": "array", "description": "color de entrada para convert, formato segun 'from'"},
                    "from": {"type": "string", "enum": sorted(_VALID_SPACES), "description": "espacio de origen (mode=convert)"},
                    "to": {"type": "string", "enum": sorted(_VALID_SPACES), "description": "espacio de destino (mode=convert)"},
                    "color1": {"type": "array", "description": "[r,g,b] 0-255 (mode=contrast_ratio, perceptual_distance)"},
                    "color2": {"type": "array", "description": "[r,g,b] 0-255 (mode=contrast_ratio, perceptual_distance)"},
                    "metric": {"type": "string", "enum": ["cie76"], "default": "cie76", "description": "mode=perceptual_distance"},
                    "base_color": {"type": "array", "description": "color base para la paleta (mode=harmony)"},
                    "space": {"type": "string", "enum": sorted(_VALID_SPACES), "default": "rgb", "description": "espacio de base_color (mode=harmony)"},
                    "scheme": {
                        "type": "string",
                        "enum": ["analogous", "complementary", "triadic", "tetradic", "split_complementary"],
                        "description": "mode=harmony",
                    },
                    "angle": {"type": "number", "default": 30.0, "description": "grados de separacion para scheme=analogous (mode=harmony)"},
                },
            },
        },
        "required": ["mode"],
    },
}


try:
    from tool_registry import register_tool
    register_tool(
        name="color_math_tool",
        schema=COLOR_MATH_TOOL_SCHEMA,
        handler=lambda args: run(args.get("mode"), args.get("params")),
    )
except ImportError:
    pass


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "self_test":
        print(json.dumps(run_self_test(), indent=2, ensure_ascii=False))
    else:
        print("uso: python3 color_math_tool.py self_test")
