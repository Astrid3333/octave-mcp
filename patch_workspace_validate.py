#!/usr/bin/env python3
"""
patch_workspace_validate.py

Aplica a workspace_tool.py:
  1. Captura el ValueError de _paths() en las 5 funciones que la llaman
     (save_run, load_run, load_run_safe, describe_run, delete_run) ->
     devuelven {"error": ...} en vez de lanzar.
  2. Cambia el handler de workspace_load para usar load_run_safe en vez
     de load_run (arregla el gap de allow_pickle con datos dtype=object).
  3. Actualiza el docstring de load_run_safe.
  4. Agrega validate_workspace_tool() + su schema + su registro.

Uso:
  python3 patch_workspace_validate.py --dry-run   # solo reporta
  python3 patch_workspace_validate.py             # aplica, backup .bak
"""
import ast
import shutil
import sys
from pathlib import Path

TARGET = Path("workspace_tool.py")

OLD_PATHS_LINE = "    npz_path, meta_path, safe_id = _paths(run_id)\n"
NEW_PATHS_BLOCK = (
    "    try:\n"
    "        npz_path, meta_path, safe_id = _paths(run_id)\n"
    "    except ValueError as e:\n"
    "        return {\"error\": str(e)}\n"
)

OLD_HANDLER = (
    '        name="workspace_load",\n'
    "        schema=WORKSPACE_LOAD_SCHEMA,\n"
    "        handler=lambda args: load_run(**args),\n"
)
NEW_HANDLER = (
    '        name="workspace_load",\n'
    "        schema=WORKSPACE_LOAD_SCHEMA,\n"
    "        handler=lambda args: load_run_safe(**args),  # antes: load_run(**args)\n"
)

OLD_DOCSTRING_HEAD = (
    "    Como load_run, pero con allow_pickle=True: necesario para releer\n"
    "    resultados que save_run guardó como arrays dtype=object (dicts\n"
    "    anidados, listas de dicts -- el caso normal para 'results' de\n"
    "    run_pipeline). load_run (sin _safe) se deja intacto: ya está\n"
    "    wireado como workspace_load y no debe cambiarle el comportamiento\n"
    "    a una tool existente.\n"
)
NEW_DOCSTRING_HEAD = (
    "    Como load_run, pero con allow_pickle=True: necesario para releer\n"
    "    resultados que save_run guardó como arrays dtype=object (dicts\n"
    "    anidados, listas de dicts -- el caso normal para 'results' de\n"
    "    run_pipeline). Desde esta sesión, esta es la función wireada como\n"
    "    workspace_load (el tool MCP real) -- load_run (sin _safe) queda\n"
    "    como función interna sin allow_pickle para otros callers directos\n"
    "    del módulo que no necesiten leer dtype=object.\n"
)

APPEND_BLOCK = '''

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
'''


def main():
    dry_run = "--dry-run" in sys.argv

    if not TARGET.exists():
        print(f"ERROR: no encuentro {TARGET} en el directorio actual.")
        sys.exit(1)

    content = TARGET.read_text()

    n_paths = content.count(OLD_PATHS_LINE)
    if n_paths != 5:
        print(f"ABORTO: esperaba 5 ocurrencias de la línea _paths(run_id), encontré {n_paths}. "
              "No toco nada -- revisá manualmente.")
        sys.exit(1)
    content = content.replace(OLD_PATHS_LINE, NEW_PATHS_BLOCK)

    if OLD_HANDLER not in content:
        print("ABORTO: no encontré el bloque exacto del handler de workspace_load. No toco nada.")
        sys.exit(1)
    content = content.replace(OLD_HANDLER, NEW_HANDLER)

    if OLD_DOCSTRING_HEAD in content:
        content = content.replace(OLD_DOCSTRING_HEAD, NEW_DOCSTRING_HEAD)
        docstring_updated = True
    else:
        docstring_updated = False
        print("AVISO: no encontré el docstring exacto de load_run_safe (no bloqueante, sigo).")

    if "def validate_workspace_tool" in content:
        print("ABORTO: ya existe validate_workspace_tool en el archivo -- ¿se corrió esto antes?")
        sys.exit(1)
    content += APPEND_BLOCK

    try:
        ast.parse(content)
    except SyntaxError as e:
        print(f"ABORTO: el resultado no parsea como Python válido: {e}")
        sys.exit(1)

    print("OK -- 5/5 líneas _paths() envueltas en try/except")
    print("OK -- handler de workspace_load apunta a load_run_safe")
    print(f"{'OK' if docstring_updated else 'SKIP'} -- docstring de load_run_safe")
    print("OK -- validate_workspace_tool + schema + registro agregados")
    print("OK -- ast.parse() pasa sobre el resultado completo")

    if dry_run:
        print("\n--dry-run: no escribí nada. Corré sin esa flag para aplicar.")
        return

    backup = TARGET.with_suffix(".py.bak")
    shutil.copy(TARGET, backup)
    TARGET.write_text(content)
    print(f"\nAplicado. Backup en {backup}")


if __name__ == "__main__":
    main()
