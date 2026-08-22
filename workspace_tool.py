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

    try:
        npz_path, meta_path, safe_id = _paths(run_id)
    except ValueError as e:
        return {"error": str(e)}

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
    try:
        npz_path, meta_path, safe_id = _paths(run_id)
    except ValueError as e:
        return {"error": str(e)}
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



def load_run_safe(run_id: str, keys: list[str] | None = None) -> dict:
    """
    Como load_run, pero con allow_pickle=True: necesario para releer
    resultados que save_run guardó como arrays dtype=object (dicts
    anidados, listas de dicts -- el caso normal para 'results' de
    run_pipeline). Desde esta sesión, esta es la función wireada como
    workspace_load (el tool MCP real) -- load_run (sin _safe) queda
    como función interna sin allow_pickle para otros callers directos
    del módulo que no necesiten leer dtype=object.

    Trade-off de seguridad: allow_pickle=True puede ejecutar código
    arbitrario al deserializar un .npz malicioso. Aceptable acá
    porque WORKSPACE_DIR es 100% autogenerado localmente por las
    propias tools de este servidor, no un lugar donde entren
    archivos de terceros.
    """
    try:
        npz_path, meta_path, safe_id = _paths(run_id)
    except ValueError as e:
        return {"error": str(e)}
    if not npz_path.exists():
        return {"error": f"run_id '{safe_id}' no encontrado en {WORKSPACE_DIR}"}

    with np.load(npz_path, allow_pickle=True) as npz:
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
    try:
        npz_path, meta_path, safe_id = _paths(run_id)
    except ValueError as e:
        return {"error": str(e)}
    if not npz_path.exists():
        return {"error": f"run_id '{safe_id}' no encontrado en {WORKSPACE_DIR}"}
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return {"run_id": safe_id, "shapes": meta.get("shapes", {}), "meta": meta}


def delete_run(run_id: str) -> dict:
    """Borra los archivos de un run."""
    try:
        npz_path, meta_path, safe_id = _paths(run_id)
    except ValueError as e:
        return {"error": str(e)}
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


LINKS_PATH = WORKSPACE_DIR / "_links.json"


def _read_links() -> dict:
    if not LINKS_PATH.exists():
        return {}
    return json.loads(LINKS_PATH.read_text())


def _write_links(links: dict):
    _ensure_workspace_dir()
    LINKS_PATH.write_text(json.dumps(links, indent=2, ensure_ascii=False))


def workspace_link(mode: str, alias: str | None = None, run_id: str | None = None) -> dict:
    """
    Alias legibles para run_id, guardados en _links.json dentro de
    WORKSPACE_DIR (no colisiona con el glob *.meta.json de list_runs).
    mode: create (valida run_id vía describe_run antes de guardar),
    resolve (marca 'dangling' si el run fue borrado después),
    list, delete (no toca el run apuntado).
    """
    links = _read_links()

    if mode == "create":
        if not alias or not run_id:
            return {"error": "create requiere alias y run_id"}
        check = describe_run(run_id)
        if "error" in check:
            return {"error": f"run_id '{run_id}' no existe, no se puede linkear: {check['error']}"}
        links[alias] = check["run_id"]
        _write_links(links)
        return {"alias": alias, "run_id": check["run_id"], "created": True}

    if mode == "resolve":
        if not alias:
            return {"error": "resolve requiere alias"}
        target = links.get(alias)
        if target is None:
            return {"error": f"alias '{alias}' no encontrado"}
        check = describe_run(target)
        dangling = "error" in check
        return {"alias": alias, "run_id": target, "dangling": dangling}

    if mode == "list":
        return {"count": len(links), "links": links}

    if mode == "delete":
        if not alias:
            return {"error": "delete requiere alias"}
        if alias not in links:
            return {"error": f"alias '{alias}' no encontrado"}
        del links[alias]
        _write_links(links)
        return {"alias": alias, "deleted": True}

    return {"error": f"mode '{mode}' inválido (usar create/resolve/list/delete)"}


WORKSPACE_LINK_SCHEMA = {
    "name": "workspace_link",
    "description": "Crea/resuelve/lista/borra alias legibles para run_ids del workspace (ej: alias 'ultimo_sismo' -> run_id real).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["create", "resolve", "list", "delete"]},
            "alias": {"type": "string"},
            "run_id": {"type": "string"},
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    r = save_run(None, {"trayectoria": [[1, 1, 1], [1.1, 0.9, 1.2]]}, {"tool": "test"})
    print("saved:", r)
    print("list:", list_runs())
    print("describe:", describe_run(r["run_id"]))
    print("load:", load_run(r["run_id"]))
    print("delete:", delete_run(r["run_id"]))# (pegá el contenido de arriba)

try:
    from tool_registry import register_tool
    register_tool(
        name="workspace_save",
        schema=WORKSPACE_SAVE_SCHEMA,
        handler=lambda args: save_run(**args),
    )
except ImportError:
    pass


try:
    from tool_registry import register_tool
    register_tool(
        name="workspace_load",
        schema=WORKSPACE_LOAD_SCHEMA,
        handler=lambda args: load_run_safe(**args),  # antes: load_run(**args)
    )
except ImportError:
    pass


try:
    from tool_registry import register_tool
    register_tool(
        name="workspace_list",
        schema=WORKSPACE_LIST_SCHEMA,
        handler=lambda args: list_runs(**args),
    )
except ImportError:
    pass


try:
    from tool_registry import register_tool
    register_tool(
        name="workspace_describe",
        schema=WORKSPACE_DESCRIBE_SCHEMA,
        handler=lambda args: describe_run(**args),
    )
except ImportError:
    pass


try:
    from tool_registry import register_tool
    register_tool(
        name="workspace_delete",
        schema=WORKSPACE_DELETE_SCHEMA,
        handler=lambda args: delete_run(**args),
    )
except ImportError:
    pass


try:
    from tool_registry import register_tool
    register_tool(
        name="workspace_link",
        schema=WORKSPACE_LINK_SCHEMA,
        handler=lambda args: workspace_link(**args),
    )
except ImportError:
    pass



def validate_workspace_tool() -> dict:
    """
    Autochequeo de workspace_tool: ejercita save→describe→list→load→delete
    y el ciclo completo de workspace_link contra runs temporales con
    prefijo '_validate_'. Toca únicamente el manejo de run_id inválido y
    qué función usa workspace_load internamente (load_run_safe) -- el
    resto del comportamiento público de las 6 funciones no cambió.
    """
    import time as _time
    checks = []
    test_run_id = f"_validate_{int(_time.time()*1000)}"
    obj_run_id = f"{test_run_id}_obj"
    alias = f"_validate_alias_{int(_time.time()*1000)}"
    auto = {}

    def _check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    try:
        saved = save_run(test_run_id, {"x": [1.0, 2.0, 3.0], "y": [[1, 2], [3, 4]]},
                          {"tool": "workspace_validate_selftest"})
        _check("save_run_basic",
               saved.get("run_id") == test_run_id
               and saved["shapes"].get("x", {}).get("shape") == [3]
               and saved["shapes"].get("y", {}).get("shape") == [2, 2],
               detail=str(saved.get("shapes")))

        auto = save_run(None, {"z": [1]}, {"tool": "workspace_validate_selftest"})
        _check("save_run_autogenerate_id", auto.get("run_id", "").startswith("run_"))

        desc = describe_run(test_run_id)
        _check("describe_run_matches_save", desc.get("shapes") == saved["shapes"])

        listed = list_runs()
        ids_present = {r.get("run_id") for r in listed.get("runs", [])}
        _check("list_runs_includes_created", test_run_id in ids_present)

        filtered = list_runs(filter_tool="workspace_validate_selftest")
        filtered_ids = {r.get("run_id") for r in filtered.get("runs", [])}
        _check("list_runs_filter_tool", {test_run_id, auto["run_id"]}.issubset(filtered_ids))

        loaded = load_run_safe(test_run_id)
        _check("load_run_safe_roundtrip",
               loaded.get("data", {}).get("x") == [1.0, 2.0, 3.0]
               and loaded.get("data", {}).get("y") == [[1, 2], [3, 4]])

        partial = load_run_safe(test_run_id, keys=["x"])
        _check("load_run_safe_partial_keys",
               "x" in partial.get("data", {}) and "y" not in partial.get("data", {}))

        loaded_plain = load_run(test_run_id)
        _check("load_run_plain_still_works_for_numeric_data",
               loaded_plain.get("data", {}).get("x") == [1.0, 2.0, 3.0])

        save_run(obj_run_id, {"results": [{"a": 1}, {"b": 2}]},
                 {"tool": "workspace_validate_selftest"})
        obj_loaded = load_run_safe(obj_run_id)
        _check("load_run_safe_handles_object_dtype",
               "error" not in obj_loaded and obj_loaded.get("data", {}).get("results") is not None,
               detail=str(obj_loaded.get("data")))

        _check("describe_run_missing_id_returns_error",
               "error" in describe_run("_no_deberia_existir_jamas_"))
        _check("load_run_missing_id_returns_error",
               "error" in load_run("_no_deberia_existir_jamas_"))

        created = workspace_link("create", alias=alias, run_id=test_run_id)
        _check("link_create", created.get("created") is True)

        resolved = workspace_link("resolve", alias=alias)
        _check("link_resolve_not_dangling",
               resolved.get("run_id") == test_run_id and resolved.get("dangling") is False)

        link_list = workspace_link("list")
        _check("link_list_includes_alias", alias in link_list.get("links", {}))

        delete_run(test_run_id)
        dangling = workspace_link("resolve", alias=alias)
        _check("link_dangling_after_underlying_delete", dangling.get("dangling") is True)

        workspace_link("delete", alias=alias)
        _check("link_resolve_after_alias_delete_errors",
               "error" in workspace_link("resolve", alias=alias))

        redelete = delete_run(test_run_id)
        _check("delete_run_idempotent_on_missing", redelete.get("deleted") == [])
        never_existed = delete_run("_jamas_creado_tampoco_")
        _check("delete_run_missing_id_no_raise",
               "error" not in never_existed and never_existed.get("deleted") == [])

        for fn, name, extra_args in [
            (save_run, "save_run", ({"a": [1]},)),
            (load_run, "load_run", ()),
            (load_run_safe, "load_run_safe", ()),
            (describe_run, "describe_run", ()),
            (delete_run, "delete_run", ()),
        ]:
            try:
                r = fn("!!!", *extra_args)
                _check(f"{name}_invalid_id_returns_error", "error" in r, detail=str(r))
            except Exception as e:
                _check(f"{name}_invalid_id_returns_error", False, detail=repr(e))

    finally:
        for rid in (test_run_id, obj_run_id, auto.get("run_id")):
            if rid:
                try:
                    delete_run(rid)
                except Exception:
                    pass
        try:
            workspace_link("delete", alias=alias)
        except Exception:
            pass

    passed = sum(1 for c in checks if c["passed"])
    return {
        "tool": "workspace_tool", "checks": checks,
        "passed": passed, "total": len(checks), "all_passed": passed == len(checks),
    }


WORKSPACE_VALIDATE_SCHEMA = {
    "name": "workspace_validate",
    "description": "Autochequeo de workspace_tool: ejercita save→describe→list→load→delete y el ciclo de workspace_link, incluyendo manejo de run_id inválido y datos dtype=object.",
    "inputSchema": {"type": "object", "properties": {}, "required": []},
}

try:
    from tool_registry import register_tool
    register_tool(
        name="workspace_validate",
        schema=WORKSPACE_VALIDATE_SCHEMA,
        handler=lambda args: validate_workspace_tool(),
    )
except ImportError:
    pass
