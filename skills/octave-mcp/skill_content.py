# -*- coding: utf-8 -*-
"""Copia de la skill de opencode ``octave-mcp`` empaquetada como Python, para
que otra IA pueda consumirla/revisarla sin leer el .md del repo.

Uso:
    python3 skill_content.py               # imprime el SKILL.md vigente
    python3 skill_content.py --metadata    # imprime solo nombre/descripcion
    import skill_content as sc; sc.SKILL_MD; sc.check_sync()

Fuente de verdad: SKILL.md (mismo directorio). Al importar, SKILL_MD se lee
de ese archivo si existe; si el .py esta solo (copiado a otra maquina), usa
la copia embebida ``_SKILL_MD_EMBEDDED``, que se regenera desde SKILL.md y
esta en r-string para que ningun backslash futuro del markdown se interprete.
SKILL_NAME/SKILL_DESCRIPTION se derivan del frontmatter de SKILL_MD: no hay
ningun valor duplicado a mano. Solo stdlib.

Nota: SKILL_MD en si nunca esta desincronizado (siempre refleja el disco o,
en su defecto, el embebido); lo que puede envejecer es el fallback
``_SKILL_MD_EMBEDDED``, y eso es lo que vigila check_sync(). Regenerar con
``regenerate_skill_content.py`` (mismo directorio).
"""

import os
import re

SKILL_PATH = "skills/octave-mcp/SKILL.md"

# Copia byte a byte de SKILL.md (ver check_sync()). No editar a mano:
# regenerar con regenerate_skill_content.py.
_SKILL_MD_EMBEDDED = r"""---
name: octave-mcp
description: Use when the user wants scientific/numeric computation served by their local GNU Octave MCP server — linear algebra, ODEs/PDEs, symbolic math, curve fitting, physics/chemistry/biology simulations, plotting data, or "run this in Octave". Talks to the `octave` MCP (meta-tools only), so it covers all 360+ registered tools. Also use when debugging why an octave-mcp tool fails or validating the whole tool suite.
---

# Octave MCP (local)

A local MCP server exposing 360+ numeric/simulation tools backed by GNU Octave
and Python. It lives at `/home/astrid/octave-mcp` and is registered in opencode
as the MCP `octave` (global opencode config, `mcp.octave`, command
`cd /home/astrid/octave-mcp && exec .venv/bin/python server.py`).

## 0 · The server exposes exactly THREE meta-tools

`tools/list` deliberately returns only:

| tool | use |
|---|---|
| `octave_list_tools` | discover: substring filter on name or description (`{"filter": "ode"}`) |
| `octave_get_tool_schema` | full `inputSchema` for one tool — read it before calling |
| `octave_call_tool` | invoke: `{"name": <tool>, "arguments": {...}}` |

Never invent a tool name from memory. Always:
`octave_list_tools` → `octave_get_tool_schema` → `octave_call_tool`.

`tools/list_full` (362 entries) is a private endpoint for the validation
harness, not for clients.

## 1 · Calling convention

```json
{"name": "call_tool", "arguments": {"name": "octave_run", "arguments": {"code": "disp(2+2)"}}}
```

- Arguments are nested one level (`arguments.arguments`), not flat.
- Most tools accept `{"mode": "validate", "params": {}}` and return a
  self-check result instead of doing real work. Use it to test a tool works
  before using it for real: **cheap and safe**.
- Verdict field: `validation_passed`, `all_passed`, `ok`, `all_pass`,
  `todos_correctos` or `all_params_within_2sigma` (any is accepted; the
  canonical list is `VALIDATION_FIELD_ALIASES` in `run_all_validations.py`).
- A few tools use a flat signature (no `params` kwarg) or a different mode
  name (`self_test`, `validate_physics`, `mock_recovery`) or a different
  parameter name (`preset`, `topic`, `source_tool`, `method`). If
  `mode=validate` returns `TypeError`, read the schema and retry. The full
  mapping is in `run_all_validations.py`
  (`ALTERNATE_VALIDATE_MODE`, `ALTERNATE_VALIDATE_PARAM_NAME`,
  `FLAT_SIGNATURE_TOOLS`).

## 2 · Known gaps in this environment (verified 2026-10-22)

**None open.** The full validation suite is green (347/347 evaluated tools
pass). If something breaks after a machine change, check the fixed list
below first — those are the things that used to fail:

- `umap-learn` 0.5.12 is installed in the venv → `numeral_systems_embedding`
  passes (`sklearn.manifold.TSNE` also works as the alternative).
- Rust sub-motors are compiled (`cargo build --release` in each of
  `submotors/{cfd_cavity,bem_electromagnetic,fem_poisson2d}/`) → `cfd_tool`,
  `bem_electromagnetic_tool` and `fem_electromagnetic_tool` pass.
- Octave forge packages are installed (via `ppa:ubuntuhandbook1/octave`
  which provides `octave-dev 11.3`; then `pkg install -forge control` +
  `signal`) → `compute_hilbert_transform` passes.
- `.venv-pyscf` exists (PySCF 2.14.0, own numpy) → `dft_tool` passes.
- `attractor_trajectory` butterfly check now measures at t=40 (empirical
  `d(t)`: the `d>1` crossing is at t≈30.5, max 47 at t≈33.7, d(40)=8.2 —
  a t=30 horizon was just short of the crossing, tool math was fine).
- `frame_analysis_tool` validate now returns `validation_passed` with
  per-check `passed`, and its equilibrium sum deduplicates `bc` nodes
  (multi-DOF constraints used to double-count reactions, e.g. 3×10000).

## 3 · Debugging a failing tool

1. `octave_call_tool` with `{"mode":"validate","params":{}}`.
2. If that errors, read the real signature with `octave_get_tool_schema` and
   retry with the tool's own parameter names.
3. If the tool itself is broken, fix it in its module and register it via
   `tool_registry` (see below).

### The dispatch trap

The meta `call_tool` does **not** fall through to the long legacy `elif`
chain in `server.py`. A tool is invocable through `call_tool` only if:

- it is registered in `tool_registry` (modules auto-register with
  `register_tool(name=..., schema=..., handler=...)`, which is the
  convention — one import line in `server.py`), **or**
- it has an explicit special case in the `call_tool` branch of `server.py`
  (`octave_run`, `octave_eval_expr`, `octave_run_script`, `octave_version`,
  `run_octave`).

Being listed in `list_tools` is **not** proof it is invocable. When you add a
legacy handler, register it too, and remove any static catalog entry that
would then be duplicated (`TOOLS = static_list + tool_registry.get_schemas()`).

## 4 · Running the full validation suite

```bash
cd /home/astrid/octave-mcp
.venv/bin/python run_all_validations.py --verbose   # ~2.5 min, 4 workers
.venv/bin/python health_check_tool.py               # same engine, JSON report;
                                                    # serial: ~5.2 min (cap 900s)
```

Both must agree (expected as of 2026-10-22:
365 registered / 347 evaluated / 347 PASSED / 0 FAILED / 0 ERROR / 18 SKIPPED).
These counts drift over time: refresh them from `health_check_tool.py` (JSON
report) before regenerating this skill, instead of trusting the numbers above.
Exit code 1 means failures. Always use `.venv/bin/python` (or
`sys.executable` from a venv script) — never system `python3`, which lacks the
`ocas` dependency and makes the server die at import.

## 5 · Local install / packaging

- Runtime: `.venv` (680M, machine-specific absolute paths — never ship it).
- Portable copy: zip excluding `.venv*`, `.git`, `archive/`, `__pycache__`,
  `*.bak*`, `submotors/*/target/` → ~18M of source, ~3.3M zipped.
- **This skill ships inside the repo** at `skills/octave-mcp/SKILL.md` and is
  registered with one entry in the global opencode config:
  `"skills": {"paths": ["<repo>/skills"]}` (same pattern as bend-mcp).
  Verify with `opencode debug skill` (look for `octave-mcp` and a
  `location` inside this repo). No restart needed to check; the running
  session only reloads skills after a restart.
- `skill_content.py` (same directory) is the copy of this skill for consumers
  that read `.py` instead of `.md`. On import it reads this SKILL.md from disk
  when present and otherwise falls back to `_SKILL_MD_EMBEDDED` (a raw
  triple-quoted literal regenerated from this file — so backslashes in future
  markdown cannot corrupt it). `SKILL_NAME`/`SKILL_DESCRIPTION` are parsed from the
  frontmatter of `SKILL_MD`, never duplicated. `python3 skill_content.py
  [--metadata]` prints them; `check_sync()` compares the embedded literal
  against the `.md` in binary (`"rb"` vs UTF-8 bytes): `True` when identical,
  `None` when the `.md` was copied away, `AssertionError` when they diverge
  (CRLF changes count as divergence). Regenerate the embedded copy with
  `python3 regenerate_skill_content.py` (same directory): it refuses with a
  clear error if the `.md` contains a backslash, three consecutive double
  quotes, or CR line endings — each of those would break or silently falsify
  the raw literal or the binary check.
- The GitHub remote is `git@github.com:Astrid3333/octave-mcp.git`; visibility
  is set on GitHub and does not affect local opencode usage (the MCP reads
  the local path only).
"""


def _md_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "SKILL.md")


def _read_disk():
    """Contenido del .md vecino como str (bytes exactos, utf-8), o None."""
    path = _md_path()
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8")


SKILL_MD = _read_disk()
if SKILL_MD is None:
    SKILL_MD = _SKILL_MD_EMBEDDED


def _frontmatter(text):
    """Extrae {name, description, ...} del frontmatter de un SKILL.md.

    Limitacion: solo claves de una linea en formato ``clave: valor``; no
    entiende YAML multilineo (``>``/``|``) ni valores entre comillas (se
    los devolveria tal cual). Vale para el frontmatter de este skill; si
    alguna vez crece, parsear con PyYAML en vez de ampliar esto.
    """
    m = re.match(r"^---\n(.*?)\n---", text.replace("\r\n", "\n"), re.S)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


_fm = _frontmatter(SKILL_MD)
SKILL_NAME = _fm.get("name", "")
SKILL_DESCRIPTION = _fm.get("description", "")


def check_sync():
    """Comprueba la copia embebida contra el SKILL.md vecino, en binario.

    Returns:
        True: el .md existe y es byte a byte igual a _SKILL_MD_EMBEDDED.
        None: no hay .md al lado del .py (copia suelta; nada que comprobar).

    Raises:
        AssertionError: el .md existe pero difiere de la copia embebida
        (incluye cambios CRLF/LF: se comparan bytes, no texto normalizado).
        En ese caso SKILL_MD sigue leyendo el .md vigente del disco; hay que
        regenerar skill_content.py con regenerate_skill_content.py.
    """
    path = _md_path()
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw != _SKILL_MD_EMBEDDED.encode("utf-8"):
        raise AssertionError(
            "skill_content.py esta desincronizado de SKILL.md "
            "(regenera con regenerate_skill_content.py)"
        )
    return True


def main(argv):
    if "--metadata" in argv:
        print("name:", SKILL_NAME)
        print("description:", SKILL_DESCRIPTION)
        return 0
    print(SKILL_MD, end="")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
