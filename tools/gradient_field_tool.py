"""
gradient_field_tool.py

Matematica de gradientes de campo magnetico en RM: seleccion de corte
(slice selection), codificacion de frecuencia (readout) y de fase, y
trayectoria en k-space generada por un gradiente. Complementa a
kspace_reconstruction_tool (que opera sobre los datos ya adquiridos)
calculando como el hardware de gradientes determina esos datos.

Convencion: gamma de proton (1H) = 42.5774e6 Hz/T. Gradientes en T/m,
campos de vision (FOV) en m, tiempos en s.

Modes:
  - slice_thickness: espesor de corte a partir del ancho de banda del
    pulso RF y la intensidad del gradiente de seleccion de corte
    (params: rf_bandwidth_hz, gz_tesla_per_m)
  - frequency_encoding: ancho de banda de lectura y ancho de banda por
    pixel a partir del gradiente de frecuencia y el FOV/matriz
    (params: gx_tesla_per_m, fov_x_m, nx)
  - phase_encode_steps: numero de pasos de codificacion de fase y el
    incremento de area de gradiente necesario, a partir del FOV y la
    resolucion deseada (params: fov_y_m, resolution_y_m)
  - kspace_position: posicion alcanzada en k-space bajo un gradiente
    constante durante un tiempo dado, k = gamma * G * t
    (params: g_tesla_per_m, t_s)
  - validate: auto-validacion contra casos con resultado conocido
"""
import json

import numpy as np

TOOL_NAME = "gradient_field_tool"

GAMMA_HZ = 42.5774e6  # Hz/T, proton (1H)


def slice_thickness(rf_bandwidth_hz, gz_tesla_per_m):
    if gz_tesla_per_m <= 0:
        return {"error": "gz_tesla_per_m debe ser > 0"}
    thickness_m = rf_bandwidth_hz / (GAMMA_HZ * gz_tesla_per_m)
    return {
        "rf_bandwidth_hz": rf_bandwidth_hz,
        "gz_tesla_per_m": gz_tesla_per_m,
        "slice_thickness_m": thickness_m,
        "slice_thickness_mm": thickness_m * 1000,
    }


def frequency_encoding(gx_tesla_per_m, fov_x_m, nx):
    total_bandwidth_hz = GAMMA_HZ * gx_tesla_per_m * fov_x_m
    bandwidth_per_pixel_hz = total_bandwidth_hz / nx
    return {
        "gx_tesla_per_m": gx_tesla_per_m,
        "fov_x_m": fov_x_m,
        "nx": nx,
        "total_bandwidth_hz": total_bandwidth_hz,
        "bandwidth_per_pixel_hz": bandwidth_per_pixel_hz,
    }


def phase_encode_steps(fov_y_m, resolution_y_m):
    if resolution_y_m <= 0 or fov_y_m <= 0:
        return {"error": "fov_y_m y resolution_y_m deben ser > 0"}
    ny = int(round(fov_y_m / resolution_y_m))
    delta_k_y = 1.0 / fov_y_m  # ciclos/m, paso en k-space
    return {
        "fov_y_m": fov_y_m,
        "resolution_y_m": resolution_y_m,
        "n_phase_encode_steps": ny,
        "delta_ky_cycles_per_m": delta_k_y,
    }


def kspace_position(g_tesla_per_m, t_s):
    g = np.asarray(g_tesla_per_m, dtype=float) if isinstance(g_tesla_per_m, (list, tuple)) else np.array([g_tesla_per_m])
    t = np.asarray(t_s, dtype=float) if isinstance(t_s, (list, tuple)) else np.array([t_s])
    if g.shape != t.shape:
        return {"error": "g_tesla_per_m y t_s deben tener la misma forma"}
    k = GAMMA_HZ * g * t  # ciclos/m (k = gamma*integral(G dt), G constante)
    return {"k_cycles_per_m": k.tolist(), "g_tesla_per_m": g.tolist(), "t_s": t.tolist()}


def _validate():
    errors = []
    tests_total = 0
    tests_passed = 0

    tests_total += 1
    r = slice_thickness(rf_bandwidth_hz=1000.0, gz_tesla_per_m=0.01)
    expected = 1000.0 / (GAMMA_HZ * 0.01)
    if abs(r["slice_thickness_m"] - expected) < 1e-12:
        tests_passed += 1
    else:
        errors.append("slice_thickness: calculo no coincide con la formula")

    tests_total += 1
    r = slice_thickness(rf_bandwidth_hz=1000.0, gz_tesla_per_m=0.0)
    if "error" in r:
        tests_passed += 1
    else:
        errors.append("slice_thickness: deberia rechazar gz=0")

    tests_total += 1
    r = frequency_encoding(gx_tesla_per_m=0.02, fov_x_m=0.25, nx=128)
    if abs(r["bandwidth_per_pixel_hz"] * 128 - r["total_bandwidth_hz"]) < 1e-6:
        tests_passed += 1
    else:
        errors.append("frequency_encoding: bandwidth_per_pixel*nx != total_bandwidth")

    tests_total += 1
    r = phase_encode_steps(fov_y_m=0.2, resolution_y_m=0.01)
    if r["n_phase_encode_steps"] == 20:
        tests_passed += 1
    else:
        errors.append(f"phase_encode_steps: esperado 20, obtuvo {r['n_phase_encode_steps']}")

    tests_total += 1
    r = kspace_position(g_tesla_per_m=0.01, t_s=0.001)
    expected = GAMMA_HZ * 0.01 * 0.001
    if abs(r["k_cycles_per_m"][0] - expected) < 1e-6:
        tests_passed += 1
    else:
        errors.append("kspace_position: calculo escalar incorrecto")

    tests_total += 1
    r = kspace_position(g_tesla_per_m=0.05, t_s=0.0)
    if abs(r["k_cycles_per_m"][0]) < 1e-9:
        tests_passed += 1
    else:
        errors.append("kspace_position: t=0 deberia dar k=0")

    return {
        "tool": TOOL_NAME,
        "tests_passed": tests_passed,
        "tests_total": tests_total,
        "errors": errors,
        "status": "PASSED" if tests_passed == tests_total else "FAILED",
        "validation_passed": tests_passed == tests_total,
    }


def run(mode, params=None):
    params = params or {}
    if mode == "slice_thickness":
        return slice_thickness(**params)
    if mode == "frequency_encoding":
        return frequency_encoding(**params)
    if mode == "phase_encode_steps":
        return phase_encode_steps(**params)
    if mode == "kspace_position":
        return kspace_position(**params)
    if mode == "validate":
        return _validate()
    return {"error": f"modo desconocido: {mode}"}


TOOL_MODES = [
    "slice_thickness",
    "frequency_encoding",
    "phase_encode_steps",
    "kspace_position",
    "validate",
]

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Matematica de gradientes de campo en RM: seleccion de corte, "
        "codificacion de frecuencia y de fase, y trayectoria en k-space."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": TOOL_MODES,
                "description": "Modo de calculo (ver docstring de run())",
            },
            "params": {
                "type": "object",
                "description": "Parametros segun el modo (ver docstring de run())",
            },
        },
        "required": ["mode"],
    },
}


def _register():
    try:
        from tool_registry import register_tool
        register_tool(
            TOOL_NAME,
            TOOL_SCHEMA,
            lambda args: run(args.get("mode"), args.get("params", {})),
        )
    except ImportError:
        pass


_register()


if __name__ == "__main__":
    result = run("validate")
    print(json.dumps(result, indent=2, default=str))
    total = result["tests_total"]
    passed = result["tests_passed"]
    if result["validation_passed"]:
        print("→ LISTO PARA DESCARGAR e integrar a octave-mcp/tools/")
    else:
        print(f"→ {total - passed} test(s) fallaron — revisar")
