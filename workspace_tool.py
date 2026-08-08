"""
workspace_tool.py

Módulo para octave-mcp: espacio de trabajo persistente en disco para
encadenar análisis largos sin recalcular. Guarda arrays/resultados de
cualquier otro tool bajo un run_id, y los deja disponibles para lectura
posterior (ej: plot_tool leyendo la trayectoria completa de un atractor
calculado por lyapunov_tool, sin tener que rehacer la integración RK4).

INTEGRACIÓN EN server.py (mismo patrón FastMCP que el resto):

    from workspace_tool import (
        save_run, load_run, list_runs, describe_run, delete_run
    )

    @mcp.tool()
    def workspace_save(run_id: str, data: dict, meta: dict | None = None) -> dict:
        return save_run(run_id, data, meta)

    @mcp.tool()
    def workspace_load(run_id: str, keys: list[str] | None = None) -> dict:
        return load_run(run_id, keys)

    @mcp.tool()
    def workspace_list(filter_tool: str | None = None) -> dict:
        return list_runs(filter_tool)

    @mcp.tool()
    def workspace_describe(run_id: str) -> dict:
        return describe_run(run_id)

    @mcp.tool()
    def workspace_delete(run_id: str) -> dict:
        return delete_run(run_id)

FORMATO DE ALMACENAMIENTO: cada run_id genera dos archivos en
~/mcp_octave/.workspace/:
    <run_id>.npz   -> arrays numéricos (numpy savez_compressed)
    <run_id>.meta.json -> metadata: tool de origen, timestamp, params, shapes

Por qué .npz y no .mat: no depende de tener Octave disponible para leer/
escribir el workspace, es liviano, y numpy ya es dependencia transitiva de
scipy (usado en varios de tus tools con curve_fit). Si algún tool necesita
releer un run DESDE Octave (ej: para graficar con comandos nativos de Octave
en vez de matplotlib), se puede agregar una función save_run_mat() aparte
que exporte a .mat bajo demanda, sin tocar el formato base.

PRÓXIMO PASO SUGERIDO: modificar lyapunov_tool.py para que, si recibe un
run_id, guarde la trayectoria completa (y, y2 en cada paso) vía save_run()
en vez de descartarla — hoy el script de Octave solo imprime el punto final.
Eso es lo que necesita plot_tool para poder dibujar el atractor completo.
"""

import os
import json
import time
import numpy as np
from pathlib import Path

WORKSPACE_DIR = Path(os.environ.get("OCTAVE_MCP_WORKSPACE", str(Path.home() / "mcp_octave" / ".workspace")))


def _ensure_workspace_dir():
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


def _paths(run_id: str):
    safe_id = "".join(c for c in run_id if c.isalnum() or c in ("-", "_"))
    if not safe_id:
        raise ValueError("run_id inválido tras sanitizar (solo alfanumérico, '-', '_').")
    return (
        WORKSPACE_DIR / f"{safe_id}.npz",
        WORKSPACE_DIR / f"{safe_id}.meta.json",
        safe_id,
    )


def save_run(run_id: str | None, data: dict, meta: dict | None = None) -> dict:
    """
    Guarda un dict de arrays/escalares bajo run_id. Si run_id es None,
    se autogenera uno con timestamp.

    Args:
        run_id: identificador único. Si None, se genera "run_<epoch_ms>".
        data: dict {nombre_array: valor}. Valores pueden ser listas,
            números, o np.ndarray; todo se convierte a np.ndarray.
        meta: metadata libre (ej: {"tool": "compute_lyapunov_exponent",
            "system": "chen_lee", "params": {...}}).

    Returns:
        dict con run_id, path, shapes guardados, y meta.
    """
    _ensure_workspace_dir()
    if not run_id:
        run_id = f"run_{int(time.time() * 1000)}"

    npz_path, meta_path, safe_id = _paths(run_id)

    arrays = {}
    shapes = {}
    for k, v in data.items():
        arr = np.asarray(v)
        arrays[k] = arr
        shapes[k] = {"shape": list(arr.shape), "dtype": str(arr.dtype)}

    np.savez_compressed(npz_path, **arrays)

    full_meta = {
        "run_id": safe_id,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "shapes": shapes,
        **(meta or {}),
    }
    meta_path.write_text(json.dumps(full_meta, indent=2, ensure_ascii=False))

    return {"run_id": safe_id, "path": str(npz_path), "shapes": shapes, "meta": full_meta}


def load_run(run_id: str, keys: list[str] | None = None) -> dict:
    """
    Carga un run guardado. Si keys es None, devuelve todos los arrays
    (cuidado con trayectorias muy largas: usar describe_run primero).

    Returns:
        dict con data (arrays como listas, listos para JSON) y meta.
    """
    npz_path, meta_path, safe_id = _paths(run_id)
    if not npz_path.exists():
        return {"error": f"run_id '{safe_id}' no encontrado en {WORKSPACE_DIR}"}

    with np.load(npz_path) as npz:
        available = list(npz.files)
        selected = keys if keys else available
        data = {}
        for k in selected:
            if k not in available:
                continue
            data[k] = npz[k].tolist()

    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return {"run_id": safe_id, "data": data, "meta": meta}


def list_runs(filter_tool: str | None = None) -> dict:
    """Lista todos los runs guardados, opcionalmente filtrados por meta['tool']."""
    _ensure_workspace_dir()
    runs = []
    for meta_path in sorted(WORKSPACE_DIR.glob("*.meta.json")):
        meta = json.loads(meta_path.read_text())
        if filter_tool and meta.get("tool") != filter_tool:
            continue
        runs.append(meta)
    return {"count": len(runs), "runs": runs}


def describe_run(run_id: str) -> dict:
    """Devuelve shapes/dtypes de un run SIN cargar los arrays completos a memoria."""
    npz_path, meta_path, safe_id = _paths(run_id)
    if not npz_path.exists():
        return {"error": f"run_id '{safe_id}' no encontrado en {WORKSPACE_DIR}"}
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return {"run_id": safe_id, "shapes": meta.get("shapes", {}), "meta": meta}


def delete_run(run_id: str) -> dict:
    """Borra los archivos de un run."""
    npz_path, meta_path, safe_id = _paths(run_id)
    deleted = []
    for p in (npz_path, meta_path):
        if p.exists():
            p.unlink()
            deleted.append(str(p))
    return {"run_id": safe_id, "deleted": deleted}


# --- Schemas para registro manual (patrón types.Tool / allowlist) ---
WORKSPACE_SAVE_SCHEMA = {
    "name": "workspace_save",
    "description": "Guarda arrays/resultados de un análisis bajo un run_id para reutilizarlos después (ej: en plot_tool) sin recalcular.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "run_id": {"type": "string", "description": "Identificador único. Si se omite, se autogenera."},
            "data": {"type": "object", "description": "Dict de arrays/escalares a guardar."},
            "meta": {"type": "object", "description": "Metadata libre: tool de origen, params usados, etc."},
        },
        "required": ["data"],
    },
}

WORKSPACE_LOAD_SCHEMA = {
    "name": "workspace_load",
    "description": "Carga un run guardado previamente por run_id.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "run_id": {"type": "string"},
            "keys": {"type": "array", "items": {"type": "string"}, "description": "Subconjunto de arrays a cargar (opcional)."},
        },
        "required": ["run_id"],
    },
}

WORKSPACE_LIST_SCHEMA = {
    "name": "workspace_list",
    "description": "Lista todos los runs guardados en el workspace, opcionalmente filtrados por tool de origen.",
    "inputSchema": {
        "type": "object",
        "properties": {"filter_tool": {"type": "string"}},
        "required": [],
    },
}

WORKSPACE_DESCRIBE_SCHEMA = {
    "name": "workspace_describe",
    "description": "Muestra shapes/dtypes de un run sin cargar los arrays completos (útil para trayectorias largas antes de graficar).",
    "inputSchema": {
        "type": "object",
        "properties": {"run_id": {"type": "string"}},
        "required": ["run_id"],
    },
}

WORKSPACE_DELETE_SCHEMA = {
    "name": "workspace_delete",
    "description": "Borra un run del workspace.",
    "inputSchema": {
        "type": "object",
        "properties": {"run_id": {"type": "string"}},
        "required": ["run_id"],
    },
}


if __name__ == "__main__":
    r = save_run(None, {"trayectoria": [[1, 1, 1], [1.1, 0.9, 1.2]]}, {"tool": "test"})
    print("saved:", r)
    print("list:", list_runs())
    print("describe:", describe_run(r["run_id"]))
    print("load:", load_run(r["run_id"]))
    print("delete:", delete_run(r["run_id"]))# (pegá el contenido de arriba)
