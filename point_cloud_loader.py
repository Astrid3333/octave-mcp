"""
point_cloud_loader.py -- Carga de nubes de puntos desde archivo (XYZ/TXT,
PLY ascii, CSV) y calculo de estadisticas basicas (bounding box, centroide,
extension, conteo).

Modos:
  load      -- lee un archivo de disco y devuelve puntos + stats
  stats     -- calcula stats sobre un arreglo de puntos ya dado
  validate  -- round-trip write/read en los 3 formatos contra valores
              conocidos (cubo unitario) + verificacion directa de stats
"""

import os
import csv as _csv_module
import tempfile

import numpy as np


# ---------------------------------------------------------------------------
# Parsers / writers por formato
# ---------------------------------------------------------------------------

def _parse_xyz(text):
    pts = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace(",", " ").split()
        if len(parts) < 3:
            continue
        pts.append([float(parts[0]), float(parts[1]), float(parts[2])])
    return np.array(pts, dtype=float)


def _write_xyz(points):
    lines = [f"{float(p[0])!r} {float(p[1])!r} {float(p[2])!r}" for p in points]
    return "\n".join(lines) + "\n"


def _parse_csv(text, has_header=None):
    reader = list(_csv_module.reader(text.strip().splitlines()))
    if not reader:
        return np.array([], dtype=float).reshape(0, 3)
    first = reader[0]
    header_detected = False
    try:
        [float(x) for x in first[:3]]
    except ValueError:
        header_detected = True
    if has_header is None:
        has_header = header_detected
    rows = reader[1:] if has_header else reader
    pts = [[float(r[0]), float(r[1]), float(r[2])] for r in rows if len(r) >= 3]
    return np.array(pts, dtype=float)


def _write_csv(points):
    lines = ["x,y,z"]
    for p in points:
        lines.append(f"{float(p[0])!r},{float(p[1])!r},{float(p[2])!r}")
    return "\n".join(lines) + "\n"


def _parse_ply_ascii(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "ply":
        raise ValueError("archivo PLY invalido: falta magic 'ply' en la primera linea")
    n_vertex = None
    n_props_before_data = 0
    header_end = None
    for i, line in enumerate(lines[1:], start=1):
        stripped = line.strip()
        if stripped.startswith("element vertex"):
            n_vertex = int(stripped.split()[-1])
        elif stripped.startswith("property"):
            n_props_before_data += 1
        elif stripped == "end_header":
            header_end = i
            break
    if n_vertex is None or header_end is None:
        raise ValueError("archivo PLY invalido: no se encontro 'element vertex' o 'end_header'")
    data_lines = lines[header_end + 1: header_end + 1 + n_vertex]
    pts = []
    for line in data_lines:
        parts = line.strip().split()
        pts.append([float(parts[0]), float(parts[1]), float(parts[2])])
    return np.array(pts, dtype=float)


def _write_ply_ascii(points):
    header = [
        "ply",
        "format ascii 1.0",
        f"element vertex {len(points)}",
        "property float x",
        "property float y",
        "property float z",
        "end_header",
    ]
    body = [f"{float(p[0])!r} {float(p[1])!r} {float(p[2])!r}" for p in points]
    return "\n".join(header + body) + "\n"


_FORMAT_PARSERS = {"xyz": _parse_xyz, "csv": _parse_csv, "ply": _parse_ply_ascii}
_FORMAT_WRITERS = {"xyz": _write_xyz, "csv": _write_csv, "ply": _write_ply_ascii}

_EXT_TO_FORMAT = {".xyz": "xyz", ".txt": "xyz", ".csv": "csv", ".ply": "ply"}


def _infer_format(path, fmt=None):
    if fmt:
        return fmt
    ext = os.path.splitext(path)[1].lower()
    if ext not in _EXT_TO_FORMAT:
        raise ValueError(f"no se pudo inferir formato de '{path}'; especifique 'format'")
    return _EXT_TO_FORMAT[ext]


def _load_point_cloud(path, fmt=None):
    fmt = _infer_format(path, fmt)
    with open(path, "r") as f:
        text = f.read()
    return _FORMAT_PARSERS[fmt](text)


def _compute_stats(points):
    points = np.asarray(points, dtype=float)
    if points.size == 0:
        return {"num_points": 0}
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    centroid = points.mean(axis=0)
    std = points.std(axis=0, ddof=0)
    return {
        "num_points": int(points.shape[0]),
        "bbox": {"min": mins.tolist(), "max": maxs.tolist()},
        "centroid": centroid.tolist(),
        "extent": (maxs - mins).tolist(),
        "std": std.tolist(),
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def compute_point_cloud_loader(mode, **params):
    if mode == "validate":
        return _validate_point_cloud_loader()
    elif mode == "load":
        path = params["path"]
        fmt = params.get("format")
        points = _load_point_cloud(path, fmt)
        stats = _compute_stats(points)
        return {
            "num_points": int(points.shape[0]),
            "points_preview": points[:10].tolist(),
            "stats": stats,
        }
    elif mode == "stats":
        points = np.array(params["points"], dtype=float)
        return _compute_stats(points)
    else:
        raise ValueError(f"modo desconocido: {mode}. Use load | stats")


# ---------------------------------------------------------------------------
# Validacion: round-trip write/read en cada formato contra un cubo unitario
# conocido, mas verificacion directa de las stats.
# ---------------------------------------------------------------------------

def _validate_point_cloud_loader():
    checks = []

    cube = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
        [1, 1, 0], [1, 0, 1], [0, 1, 1], [1, 1, 1],
    ], dtype=float)

    for fmt in ("xyz", "csv", "ply"):
        writer = _FORMAT_WRITERS[fmt]
        parser = _FORMAT_PARSERS[fmt]
        text = writer(cube)
        recovered = parser(text)
        diff = float(np.max(np.abs(recovered - cube))) if recovered.shape == cube.shape else float("inf")
        checks.append({
            "name": f"roundtrip_{fmt}",
            "expected": "max abs diff < 1e-9 y misma forma (8, 3)",
            "got": {"shape": list(recovered.shape), "max_abs_diff": round(diff, 12)},
            "passed": bool(recovered.shape == cube.shape and diff < 1e-9),
        })

    # round-trip tambien a traves de disco real (tempfile), no solo en memoria
    with tempfile.TemporaryDirectory() as tmpdir:
        for fmt, ext in (("xyz", ".xyz"), ("csv", ".csv"), ("ply", ".ply")):
            path = os.path.join(tmpdir, f"cube{ext}")
            with open(path, "w") as f:
                f.write(_FORMAT_WRITERS[fmt](cube))
            loaded = _load_point_cloud(path)
            diff = float(np.max(np.abs(loaded - cube))) if loaded.shape == cube.shape else float("inf")
            checks.append({
                "name": f"disk_roundtrip_{fmt}_autodetect_format",
                "expected": "max abs diff < 1e-9",
                "got": round(diff, 12),
                "passed": bool(diff < 1e-9),
            })

    stats = _compute_stats(cube)
    expected_centroid = [0.5, 0.5, 0.5]
    expected_bbox_min = [0.0, 0.0, 0.0]
    expected_bbox_max = [1.0, 1.0, 1.0]
    centroid_diff = float(np.max(np.abs(np.array(stats["centroid"]) - expected_centroid)))
    bbox_diff = float(max(
        np.max(np.abs(np.array(stats["bbox"]["min"]) - expected_bbox_min)),
        np.max(np.abs(np.array(stats["bbox"]["max"]) - expected_bbox_max)),
    ))
    checks.append({
        "name": "stats_centroid_cube_unitario",
        "expected": f"{expected_centroid} (diff < 1e-9)",
        "got": {"centroid": stats["centroid"], "diff": round(centroid_diff, 12)},
        "passed": bool(centroid_diff < 1e-9),
    })
    checks.append({
        "name": "stats_bbox_cube_unitario",
        "expected": f"min={expected_bbox_min} max={expected_bbox_max} (diff < 1e-9)",
        "got": {"bbox": stats["bbox"], "diff": round(bbox_diff, 12)},
        "passed": bool(bbox_diff < 1e-9),
    })
    checks.append({
        "name": "stats_num_points",
        "expected": 8,
        "got": stats["num_points"],
        "passed": bool(stats["num_points"] == 8),
    })

    all_passed = all(c["passed"] for c in checks)
    return {"mode": "validate", "checks": checks, "all_passed": all_passed}


if __name__ == "__main__":
    result = _validate_point_cloud_loader()
    for c in result["checks"]:
        status = "OK" if c["passed"] else "FALLO"
        print(f"[{status}] {c['name']}: esperado={c['expected']}  obtenido={c['got']}")
    print("\nTodas las validaciones pasaron." if result["all_passed"] else "\nHAY VALIDACIONES QUE FALLARON.")


POINT_CLOUD_LOADER_TOOL_SCHEMA = {
    "name": "point_cloud_loader",
    "description": (
        "Carga de nubes de puntos desde archivo (XYZ/TXT, PLY ascii, CSV) "
        "con autodeteccion de formato por extension, y calculo de "
        "estadisticas basicas (bounding box, centroide, extension, "
        "desviacion estandar por eje, conteo de puntos)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["load", "stats", "validate"]},
            "params": {"type": "object", "description": "Parametros especificos de cada modo, ver docstrings."},
        },
        "required": ["mode"],
    },
}


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass


def _handle(args):
    _params = args.get("params") or {}
    return compute_point_cloud_loader(mode=args["mode"], **_params)


register_tool("point_cloud_loader", POINT_CLOUD_LOADER_TOOL_SCHEMA, _handle)
