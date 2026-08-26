"""
kspace_reconstruction_tool.py

Reconstruccion de imagenes de RM a partir de datos de k-space: FFT
inversa 2D, zero-filling (interpolacion por relleno de ceros en
k-space), y demostracion de aliasing por submuestreo en la direccion
de codificacion de fase. Complementa a gradient_field_tool (que calcula
como se recorre el k-space) operando sobre los datos ya adquiridos.

Convencion: k-space como matriz compleja representada por partes real
e imaginaria por separado (listas de listas), origen de k-space en el
centro (se aplica fftshift/ifftshift internamente).

Modes:
  - fft_reconstruct: IFFT2 de k-space -> imagen (magnitud y fase)
    (params: kspace_real, kspace_imag)
  - zero_fill: relleno de ceros en k-space a un tamano objetivo antes
    de reconstruir (params: kspace_real, kspace_imag, target_shape)
  - undersample_aliasing: submuestreo por factor R en fase, sin
    unfolding, para mostrar el patron de aliasing resultante
    (params: kspace_real, kspace_imag, reduction_factor)
  - validate: auto-validacion (genera una imagen sintetica, la lleva a
    k-space y reconstruye, comparando error cuadratico medio)
"""
import json

import numpy as np

TOOL_NAME = "kspace_reconstruction_tool"


def _to_complex(kspace_real, kspace_imag):
    return np.asarray(kspace_real, dtype=float) + 1j * np.asarray(kspace_imag, dtype=float)


def _reconstruct(kspace):
    return np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(kspace)))


def fft_reconstruct(kspace_real, kspace_imag):
    kspace = _to_complex(kspace_real, kspace_imag)
    image = _reconstruct(kspace)
    return {
        "shape": list(image.shape),
        "magnitude": np.abs(image).tolist(),
        "phase": np.angle(image).tolist(),
    }


def zero_fill(kspace_real, kspace_imag, target_shape):
    kspace = _to_complex(kspace_real, kspace_imag)
    ny, nx = kspace.shape
    ty, tx = target_shape
    if ty < ny or tx < nx:
        return {"error": "target_shape debe ser >= al tamano original en ambas dimensiones"}
    padded = np.zeros((ty, tx), dtype=complex)
    oy, ox = (ty - ny) // 2, (tx - nx) // 2
    padded[oy:oy + ny, ox:ox + nx] = kspace
    image = _reconstruct(padded)
    return {
        "original_shape": [ny, nx],
        "padded_shape": [ty, tx],
        "magnitude": np.abs(image).tolist(),
    }


def undersample_aliasing(kspace_real, kspace_imag, reduction_factor=2):
    kspace = _to_complex(kspace_real, kspace_imag)
    mask = np.zeros_like(kspace)
    mask[::reduction_factor, :] = kspace[::reduction_factor, :]
    image_full = _reconstruct(kspace)
    image_aliased = _reconstruct(mask) * reduction_factor  # compensa energia perdida
    return {
        "reduction_factor": reduction_factor,
        "magnitude_full": np.abs(image_full).tolist(),
        "magnitude_aliased": np.abs(image_aliased).tolist(),
        "nota": "el aliasing se manifiesta como replicas de la imagen "
                "desplazadas FOV/R en la direccion de fase, superpuestas",
    }


def _validate():
    errors = []
    tests_total = 0
    tests_passed = 0

    tests_total += 1
    n = 16
    x = np.linspace(-1, 1, n)
    xx, yy = np.meshgrid(x, x)
    original = np.exp(-(xx ** 2 + yy ** 2) * 4)
    kspace = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(original)))
    r = fft_reconstruct(kspace.real.tolist(), kspace.imag.tolist())
    recon = np.array(r["magnitude"])
    mse = float(np.mean((recon - original) ** 2))
    if mse < 1e-20:
        tests_passed += 1
    else:
        errors.append(f"fft_reconstruct: MSE ida-vuelta demasiado alto ({mse})")

    tests_total += 1
    r = zero_fill(kspace.real.tolist(), kspace.imag.tolist(), [32, 32])
    if r.get("padded_shape") == [32, 32] and len(r["magnitude"]) == 32:
        tests_passed += 1
    else:
        errors.append(f"zero_fill: forma resultante incorrecta ({r.get('padded_shape')})")

    tests_total += 1
    r = zero_fill(kspace.real.tolist(), kspace.imag.tolist(), [8, 8])
    if "error" in r:
        tests_passed += 1
    else:
        errors.append("zero_fill: deberia rechazar target_shape menor al original")

    tests_total += 1
    r = undersample_aliasing(kspace.real.tolist(), kspace.imag.tolist(),
                              reduction_factor=1)
    full = np.array(r["magnitude_full"])
    aliased = np.array(r["magnitude_aliased"])
    if float(np.mean((full - aliased) ** 2)) < 1e-20:
        tests_passed += 1
    else:
        errors.append("undersample_aliasing: R=1 deberia igualar la reconstruccion completa")

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
    if mode == "fft_reconstruct":
        return fft_reconstruct(**params)
    if mode == "zero_fill":
        return zero_fill(**params)
    if mode == "undersample_aliasing":
        return undersample_aliasing(**params)
    if mode == "validate":
        return _validate()
    return {"error": f"modo desconocido: {mode}"}


TOOL_MODES = ["fft_reconstruct", "zero_fill", "undersample_aliasing", "validate"]

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Reconstruccion de imagenes de RM desde k-space: FFT2 inversa, "
        "zero-filling, y demostracion de aliasing por submuestreo en fase."
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
