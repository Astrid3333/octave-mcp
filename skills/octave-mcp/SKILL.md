---
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

Do not burn turns rediscovering these; expect these failures and say so:

- `.venv-pyscf` is missing → `dft_tool` errors.
- `attractor_trajectory` fails a real numeric check (`d_final=0.1795` < 1.0
  on the butterfly-effect test) — a genuine tool bug, not an environment issue.
- `frame_analysis_tool` returns checks with no verdict field — numeric OK,
  contract non-compliant.

Already fixed here (do not redo unless the machine changes):

- `umap-learn` 0.5.12 is installed in the venv → `numeral_systems_embedding`
  passes (`sklearn.manifold.TSNE` also works as the alternative).
- Rust sub-motors are compiled (`cargo build --release` in each of
  `submotors/{cfd_cavity,bem_electromagnetic,fem_poisson2d}/`) → `cfd_tool`,
  `bem_electromagnetic_tool` and `fem_electromagnetic_tool` pass.
- Octave forge packages are installed (via `ppa:ubuntuhandbook1/octave`
  which provides `octave-dev 11.3`; then `pkg install -forge control` +
  `signal`) → `compute_hilbert_transform` passes.

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
.venv/bin/python health_check_tool.py               # same engine, JSON report
```

Both must agree (expected as of 2026-10-22:
365 registered / 347 evaluated / 344 PASSED / 1 FAILED / 2 ERROR / 18 SKIPPED).
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
