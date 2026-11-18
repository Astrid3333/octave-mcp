---
name: octave-mcp
description: Use when the user wants scientific/numeric computation served by their local GNU Octave MCP server — linear algebra, ODEs/PDEs, symbolic math, curve fitting, physics/chemistry/biology simulations, plotting data, or "run this in Octave". Talks to the `octave` MCP (meta-tools only), so it covers all 387 tools (390 with deprecated aliases). Also use when debugging why an octave-mcp tool fails or validating the whole tool suite.
---

# Octave MCP (local)

A local MCP server exposing 387 numeric/simulation tools backed by GNU Octave
and Python. It lives at `/home/astrid/octave-mcp` and is registered in opencode
as the MCP `octave` (global opencode config, `mcp.octave`, command
`cd /home/astrid/octave-mcp && exec .venv/bin/python server.py`).

## 0 · The server exposes exactly THREE meta-tools

`tools/list` deliberately returns only:

| tool | use |
|---|---|
| `list_tools` | discover: substring filter on name or description (`{"filter": "ode"}`) |
| `get_tool_schema` | full `inputSchema` for one tool — read it before calling |
| `call_tool` | invoke: `{"name": <tool>, "arguments": {...}}` |

Never invent a tool name from memory. Always:
`list_tools` → `get_tool_schema` → `call_tool`.

`tools/list_full` (387 entries) is a private endpoint for the validation
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

## 2 · Known gaps in this environment (verified 2026-11-14)

**None open.** The full validation suite is green: 384/384 tools that expose
a `validate` mode pass (387 listed + 3 deprecated aliases = 390), 0 FAILED,
0 ERROR; the 6 remaining tools expose no `validate` mode and are reported
as SKIPPED. If
something breaks after a machine change, check the fixed list
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
  24 validate checks (diff/integrate/simplify/limit/series/solve/sums
  incl. Bernoulli limit and Basel sum at infinity + number theory +
  matrix/jacobian/diophantine/real_roots). Besides the
  classical ops, the tool exposes linear algebra (`matrix` with actions
  eigenvals/eigenvects/inverse/det/rank/trace/rref/jordan_form),
  `jacobian`, `diophantine` (parametric linear + Pell) and `real_roots`
  (CAD-style real-root isolation). `bounds`/`point` accept `"oo"` (the
  tool maps it to `pool.pos_infinity()`); the Basel special case only
  matches the term form `k^(-2)` — `1/k^2` parses as `1/(k^2)` and
  raises `PySumError` E-SUM-002, which the server returns as PLAIN TEXT
  (no JSON envelope; pinned by the cross-check battery). Upstream beta
  bug: its Rust kernel
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
  For ODEs the derivative must be QUOTED: `ode2('diff(y,x)+y=0,y,x)`
  works, while unquoted `ode2(diff(y,x)+y=0,y,x)` returns ok=True with
   the literal `false` (ok is not success); `ic1(sol, x=0, y=1)` is the
   three-arg form this Maxima accepts (no derivative argument — for a
   second-order ODE with `y'(0)` use `ic2(sol, x=0, y=1, 'diff(y,x)=0')`).
   `laplace(f,t,s)` works and agrees with sympy; `ilt` is the inverse
   transform but its argument order is `(f, s, t)` — the reverse of
   `laplace` (passing `(f,t,s)` yields ok=True with a garbage `delta`
   expression; ok is not success).
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
    curves — nothing else in the server covers those. `desolve` DOES
   work for ODEs (1st order linear/separable + 2nd order constant
   coefficients, `ics=[x0,y0]`, verified by residual in the
   cross-check battery and agreeing with maxima `ode2`) but the
   dependent variable must be an APPLIED function: `y = function('y')(t)`
    — the raw form `function('y', t)` returns an unapplied Python closure
    and `diff(y,t)+y` then dies with TypeError (usage error, pinned).
    `desolve_rk4(f, y, ics=[x0,y0], end_points=, step=)` runs the RK4
    integrator and returns the step table `[[x,y],...]`; with
    `y = var('y')` (a symbol, not a function). There is no `laplace`
    (use `maxima_eval_tool`).
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
- Cadabra2 2.6.0 (PyPI `cadabra2`, Kasper Peeters, C++ module + Python
  API, LaTeX input) → `cadabra2_math_tool` passes its 18 validate
  checks (antisymmetric canonicalise, metric elimination, Grassmann
  fermion ordering → 0, substitute pins, evaluate vs raw numerals,
  simplify, distribute, sympy-bridge quirks, silent Ex truncation,
  list-property comma rule, non-contracting delta, python error
  fence). Fresh subprocess per call (properties Indices/Metric/... are
  process-global — declare everything in the same call). Reach for it
  for tensor-index algebra, fermion reordering (`sort_product`, NOT
  `canonicalise`) and CAS cross-checks of sympy. Limits pinned by
  validate: `expand` does not expand powers (use `simplify`);
  `substitute` does not descend into power bases (use full patterns
  `x^2 = a`); `Ex()` never raises on malformed input (truncates
  silently); Kronecker delta does not contract (`eliminate_metric`
  does); sympy bridge with `^` is broken — write `x**2`; no CLI, no
  `__version__`.
- CAS cross-check battery: `examples/multi_cas_crosscheck.py` runs the
  same problems across five engines (maxima, sagebrush, lispium,
  cadabra2, alkahest) plus an ODE/Laplace section (`ode2`/`ic1`/`ic2`/
  `laplace`/`ilt` from maxima, `desolve` + `desolve_rk4` from sagebrush,
  router field hints laplace/ode — all vs sympy
  `dsolve`/`laplace_transform`/`inverse_laplace_transform`, ODE
  solutions checked by residual (or numeric error vs the analytic
  solution for RK4), not by constant matching) against a live sympy
  oracle — 99/99 PASS as of 2026-10-25 (63 functional checks + 36 fuzz),
  ruff clean. Section 16 adds FUZZING DIFFERENTIAL: 12 rounds
  (`FUZZ_ROUNDS`, default) of random expression trees (depth-limited
  `+ - * ^ sin cos` over integers and rationals, no division/exp) evaluated
  in maxima, lispium and sagebrush against the sympy value+derivative
  oracle at a random float point (tolerance 1e-6 abs / 1e-8 rel). Seeded
  (`FUZZ_SEED`, default 20261024) and deterministic: two runs produce an
  identical diff. Sage quirks pinned there: the preparser rewrites
  literals to Integer in error text, and pure Integer expressions need an
  SR() wrapper before subs. Ten PINS document
  the known quirks (maxima noun-forms with ok=True, lispium float
  degradation, eco of unevaluated forms, sage `var()` non-injection,
  alkahest Basel term form, sagebrush applied-function requirement,
  maxima ode2 quoting, maxima `ilt` argument order). It is the second
  gate of `run_validations_guarded.py` (suite first, then battery).
  Run it after touching any CAS tool: `.venv/bin/python
  examples/multi_cas_crosscheck.py`.
- CAS router: `cas_router_math_tool` unifies the four CAS tools
  (maxima/sagebrush/lispium/cadabra2) plus sympy with 15 validate checks
  (including field-laplace and field-ode routed to maxima).
  mode=compute operation=eval takes a `query` written in the TARGET
  engine's dialect (the router does NOT translate): route = explicit
  `engine` > `field` hint (tensor→cadabra2, numero/prime→sagebrush,
  laplace/calculo→maxima, lisp→lispium) > content sniff (LaTeX tensor
  subscripts like '_{'/cusps→cadabra2, euler_phi/is_prime→sagebrush,
  '(^ '/'(factor'→lispium, %e/diff(→maxima) > default maxima. With
  `fallback=true` (default) it chains the other engines and reports
  `engine_used` + `attempts[]` (who failed and why); cadabra2 queries
  are wrapped as `evaluate(Ex(...))`, sagebrush runs op=sage.
  operation=guia returns the routing table. operation=crosscheck runs the
  same query in every engine at once (explicit `engines` list or default
  maxima/sagebrush/lispium/cadabra2 + sympy) and returns per-engine
  `results` plus an `agreement` verdict — the differential in one call.
  Reach for the router when unsure which engine fits, or for
  fallback-resilient one-liners.
- sympy_eval_tool: sympy in-process as fifth CAS engine, 9 validate
  checks (arithmetic, diff, integrate, solve, factorial(100) exact vs
  math.factorial, laplace_transform, sqrt auto-simplified, simplify of
  (x^2-4)/(x-2), error fence). Python dialect (`x**2`, `diff(f, x)`),
  no subprocess, no session; sympify uses Python eval so only trusted
  input (local server). It is the sympy engine behind the router's
  operation=crosscheck (agreement is normalized with sympy) and the same
  oracle family the battery uses. `timeout` is accepted for router
  compatibility but cannot interrupt in-process evaluation. Reach for it
  for portable symbolic cross-checks; for big-integer factorization or
  deep number theory use sagebrush/maxima instead.
- Advanced combinatorics (added 2026-11-14): eight new pure-Python/SymPy
  tools, auto-registered through `tool_registry` and dispatched by
  `call_tool`: `polya_burnside_tool` (cycle index, Burnside orbit counts,
  cyclic/dihedral/explicit groups), `generating_functions_tool` (OGF/EGF,
  coefficient extraction, closed forms), `block_designs_tool` (BIBD
  verification, finite-field projective planes, MOLS, Hadamard matrices),
  `ramsey_extremal_tool` (R(s,t) with explicit `exact_known` flags,
  Turán-type extremal numbers), `poset_lattice_tool` (Möbius function,
  Whitney numbers, meet/join checks), `young_tableaux_tool` (hook length,
  RSK, Kostka), `matroid_tool` (bases, flats, loops/coloops, base-polytope
  inequalities) and `graph_combinatorics_tool` (chromatic polynomial,
  Tutte polynomial incl. loops and parallel edges, matching polynomial).
  Every one exposes `mode="validate"` with exact numeric checks (58 checks
  in total); `combinatorics_tool` is the classical enumeration tool and
  `advanced_combinatorics_common.py` holds the shared helpers. Regression
  tests live in `tests/test_advanced_combinatorics.py` (unittest).
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
.venv/bin/python run_validations_guarded.py         # suite + battery (99/99),
                                                    # exit 0 solo si ambas OK
.venv/bin/python health_check_tool.py               # same engine, JSON report;
                                                    # parallel 4 workers: ~148s
                                                    # (con la maquina cargada
                                                    # ~235s); PARALLEL_WORKERS=1
                                                    # = serie ~5.2 min (cap 900s)
.venv/bin/python health_check_tool.py --subset=a,b  # solo esas tools: segundos,
                                                    # conteos del lote
```

Subconjunto por MCP (para validar un lote sin la suite completa):
`octave_call_tool` con `health_check_tool` y
`{"mode":"summary","subset":["a","b"]}` — conteos solo del lote,
nombres inexistentes en `unknown_tools`, y con 0 coincidencias
`overall_health="no_tools"` (nunca `healthy`). Sin `subset` = suite
completa, igual que siempre.

A local (untracked) `.git/hooks/pre-push` runs the guarded suite before
every push (~4 min); it aborts on red. Bypass only when urgent:
`git push --no-verify`.

Both must agree (expected as of 2026-11-14:
389 registered / 383 evaluated / 383 PASSED / 0 FAILED / 0 ERROR /
6 SKIPPED for tools without a validate mode).
These counts drift over time: refresh them from `health_check_tool.py` (JSON
report) before regenerating this skill, instead of trusting the numbers above.
Exit code 1 means failures. Always use `.venv/bin/python` (or
`sys.executable` from a venv script) — never system `python3`, which lacks the
`ocas` dependency and makes the server die at import.

## 5 · CI (GitHub Actions)

`.github/workflows/ci.yml` (same template as the pre-existing
`readme-check.yml`: checkout@v4, setup-python@v5, Python 3.12) has two
jobs:

- **lint**: installs `ruff==0.15.19` (the version this repo is pinned to)
  and checks ONLY the maintained-file manifest `ci/ruff_files.txt`
  (35 files: router, sympy_eval, statistics, workspace, materials, audio math,
  composite, eurocode/fire/timber/concrete/pdelta, examples battery,
  the 9 combinatorics modules + their shared helper + regression test).
  `server.py` IS in the manifest and relies on the documented
  `E402`/`F401` per-file ignores in `.ruff.toml` (its imports ARE the
  registration mechanism) — never run repo-wide `ruff check .` as a CI
  gate: the legacy tree carries hundreds of pre-existing errors.
- **smoke**: `pip install -r requirements.txt` (verified sufficient — no
  maxima/sage/lispium needed) then `python ci/smoke.py`, a stdio MCP
  client that asserts initialize OK, exactly 3 meta-tools, 387 tools in
  `list_tools`, and `validate` on `concrete_design_tool` + `pdelta_tool`.

README is generated: edit `render_readme.py` and run
`.venv/bin/python render_readme.py` (CI-check `--check` fails if stale).
Both jobs were run locally before push: lint `All checks passed!`,
smoke `SMOKE PASS`, exit 0.

## 6 · Local install / packaging

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
