---
name: octave-mcp
description: Use when the user wants scientific/numeric computation served by their local GNU Octave MCP server — linear algebra, ODEs/PDEs, symbolic math, curve fitting, physics/chemistry/biology simulations, plotting data, or "run this in Octave". Talks to the `octave` MCP (meta-tools only), so it covers all 369+ registered tools. Also use when debugging why an octave-mcp tool fails or validating the whole tool suite.
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

`tools/list_full` (366 entries) is a private endpoint for the validation
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

**None open.** The full validation suite is green (351/351 evaluated tools
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
- `alkahest` 3.12.0 (Rust CAS: Gröbner, derivation logs, Lean 4
  certificates) is installed in the venv → `alkahest_cas_tool` passes its
  22 validate checks (diff/integrate/simplify/limit/series/solve/sums +
  number theory + matrix/jacobian/diophantine/real_roots). Besides the
  classical ops, the tool exposes linear algebra (`matrix` with actions
  eigenvals/eigenvects/inverse/det/rank/trace/rref/jordan_form),
  `jacobian`, `diophantine` (parametric linear + Pell) and `real_roots`
  (CAD-style real-root isolation). Upstream beta bug: its Rust kernel
  aborts (SIGILL, uncatchable) on some `number_theory` inputs (e.g.
  `factorint(2^64+1)`, `totient(2^64+1)`, `nextprime(2^120)`) — the tool
  runs all four NT ops in an isolated subprocess and falls back to sympy
  on crash, reporting `engine`/`fallback_reason`. If the octave MCP ever
  dies mid-call, suspect a native crash like this one.
- Maxima 5.46.0 (system package `maxima`, invoked via
  `maxima --very-quiet --batch-string=...` with `display2d:false` and
  `<<R>>`/`<<E>>` markers + `errcatch`/`first()` unwrapping) →
  `maxima_eval_tool` passes its 8 validate checks (integrate/diff/
  solve/factor/limit/taylor + error fence). Syntax errors abort the
  batch (no markers, rc=0) — detect via `incorrect syntax`/`Lisp error`
  in stdout; unknown functions stay unevaluated (no error, Maxima idiom).
- Sagebrush 0.7.2 (PyPI `sagebrush` / `sagebrush-mcp`, Rust engines,
  Sage-compatible syntax, no Sage/PARI/FLINT needed) →
  `sagebrush_math_tool` passes its 11 validate checks (ECM factor of
  2^64-1, Mersenne primality, exact 1/2, class number 3 of Q(√-23),
  poly factor, elliptic conductor 37, symbolic diff, ZZ det,
  newform 11.2.a.a, session persistence, error fence). Its `sage`/`python`
  operations share ONE persistent `sagebrush.session.Session` per server
  process (variables persist across calls; `operation=reiniciar` restarts);
   `factor`/`number_field`/`newforms` run isolated. This is the tool to
   reach for ECM, number fields/class groups, modular forms or elliptic
   curves — nothing else in the server covers those.
- Lispium 0.16.0 (PyPI `lispium`, self-contained Zig binary via
  `lispium.cli.get_binary_path()`, Lisp syntax, no Python deps) →
  `lispium_math_tool` passes its 17 validate checks (factorial 100 exact
  vs `math.factorial`, float-window pin for n=18..20, silent unknown
  function, small binomial, diff/integrate/solve/factor, modpow vs
  `pow()`, prime? flags + pinned prime? M61 bug, det/eigenvalues/linsolve,
  define+lambda, Parse/Eval fences). One-shot per call: writes a temp
  `.lspm` and runs `lispium run` — no session across calls (`define`
  lives only within one call). Engine quirks pinned by validate:
  `(factorial n)` prints float for n=18..20; unknown functions return
  unevaluated with exit 0; `solve` formats `(solutions a b)`; `binomial`
  degrades to float beyond ~10^15; `prime?` only trustworthy to ~2^53
  (literals bigger → Eval error, expression values bigger → returns 0,
  bug: M61=2^61-1 answers 0 while sagebrush/sympy say prime). Reach for
  it as an INDEPENDENT cross-check engine — it does NOT factor integers
  (use sagebrush/maxima) and has no Laplace/ilt (use maxima_eval_tool).
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
369 registered / 351 evaluated / 351 PASSED / 0 FAILED / 0 ERROR / 18 SKIPPED).
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
