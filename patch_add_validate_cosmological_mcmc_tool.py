#!/usr/bin/env python3
"""
patch_add_validate_cosmological_mcmc_tool.py

Agrega el modo "validate" a cosmological_mcmc_tool.py (autochequeo interno
para run_all_validations.py), siguiendo el mismo patron robusto de los
demas patches del repo: dry-run, backup con timestamp, anclas de texto
exactas (aborta si no las encuentra o si el patch ya esta aplicado),
py_compile + ast.parse de verificacion con rollback automatico si el
patch rompe la sintaxis.

La funcion _validate() que agrega corre estos 8 chequeos:
  1) mock_recovery con los defaults propios de la tool (60000 pasos) ->
     all_params_within_2sigma debe ser True
  2) acceptance_rate del MCMC en rango sano (0.1-0.6)
  3) chi2_per_dof razonable (<3) para el fit sintetico
  4) _h_model se reduce al LCDM estandar cuando rho_c -> infinito
  5) la correccion holonomica reduce H(z) para rho_c finito (direccion
     fisica correcta)
  6) _log_prior rechaza valores fuera de los bounds (-inf) y acepta los
     que estan dentro (0.0)
  7) un modo desconocido devuelve {"error": ...} sin lanzar excepcion
  8) reproducibilidad con la misma semilla (corrida corta, 3000 pasos,
     para no duplicar el costo del check 1)

Uso:
    cd ~/octave-mcp
    python3 patch_add_validate_cosmological_mcmc_tool.py --dry-run
    python3 patch_add_validate_cosmological_mcmc_tool.py
"""

import argparse
import ast
import datetime
import py_compile
import sys
from pathlib import Path

TARGET_PATH = Path("cosmological_mcmc_tool.py")

# ---------------------------------------------------------------------------
# 1) Enum del schema: agrega "validate" a la lista de modos validos
# ---------------------------------------------------------------------------
SCHEMA_ENUM_OLD = (
    '            "mode": {"type": "string", '
    '"enum": ["mock_recovery", "fit_hz_chronometers"]},'
)
SCHEMA_ENUM_NEW = (
    '            "mode": {"type": "string", '
    '"enum": ["mock_recovery", "fit_hz_chronometers", "validate"]},'
)

# ---------------------------------------------------------------------------
# 2) Docstring del modulo: documenta el nuevo modo junto a los otros dos
# ---------------------------------------------------------------------------
DOCSTRING_OLD = (
    "    al. 2005, Stern et al. 2010, Moresco et al. 2012/2016, Ratsimbazafy\n"
    "    et al. 2017).\n"
    '"""'
)
DOCSTRING_NEW = (
    "    al. 2005, Stern et al. 2010, Moresco et al. 2012/2016, Ratsimbazafy\n"
    "    et al. 2017).\n"
    "  - validate: autochequeo interno para run_all_validations.py -- corre\n"
    "    mock_recovery con los defaults de la tool y valida recuperacion,\n"
    "    acceptance_rate y chi2_per_dof; chequea el limite LCDM estandar\n"
    "    cuando rho_c->inf, la direccion fisica de la correccion\n"
    "    holonomica, el prior, el manejo de modo desconocido, y\n"
    "    reproducibilidad con semilla fija.\n"
    '"""'
)

# ---------------------------------------------------------------------------
# 3) Cuerpo: agrega _validate() justo antes de compute_cosmological_mcmc_tool
#    y agrega la rama de dispatch dentro de esta ultima
# ---------------------------------------------------------------------------
DISPATCH_OLD = '''def compute_cosmological_mcmc_tool(mode, params=None):
    params = params or {}
    if mode == "mock_recovery":
        return _mode_mock_recovery(params)
    elif mode == "fit_hz_chronometers":
        return _mode_fit_hz_chronometers(params)
    else:
        return {"error": f"Modo desconocido: {mode}. Modos validos: mock_recovery, fit_hz_chronometers."}'''

DISPATCH_NEW = '''def _validate():
    """Autochequeo interno matematico (no placeholder) para
    run_all_validations.py. Devuelve {"mode": "validate", "passed": bool,
    "checks": {...}, "errors": [...]}."""
    checks = {}
    errors = []

    # 1) mock_recovery con los defaults propios de la tool (60000 pasos --
    #    no se recortan para no arriesgar falsos negativos de recuperacion)
    try:
        mock_result = _mode_mock_recovery({})
        checks["mock_recovery_all_within_2sigma"] = bool(
            mock_result.get("all_params_within_2sigma", False)
        )
        if not checks["mock_recovery_all_within_2sigma"]:
            errors.append(
                "mock_recovery: no todos los parametros se recuperaron "
                "dentro de 2 sigma"
            )
    except Exception as e:
        mock_result = None
        checks["mock_recovery_all_within_2sigma"] = False
        errors.append(f"mock_recovery lanzo excepcion: {e}")

    # 2) acceptance_rate en rango sano (tipico de MCMC bien adaptado)
    if mock_result is not None:
        acc = mock_result.get("acceptance_rate", 0.0)
        checks["acceptance_rate_value"] = acc
        checks["acceptance_rate_healthy"] = bool(0.1 <= acc <= 0.6)
        if not checks["acceptance_rate_healthy"]:
            errors.append(f"acceptance_rate fuera de rango sano: {acc}")
    else:
        checks["acceptance_rate_healthy"] = False

    # 3) chi2_per_dof razonable para el fit sintetico
    if mock_result is not None:
        chi2_dof = mock_result.get("chi2_per_dof", float("inf"))
        checks["chi2_per_dof_value"] = chi2_dof
        checks["chi2_per_dof_reasonable"] = bool(chi2_dof < 3.0)
        if not checks["chi2_per_dof_reasonable"]:
            errors.append(f"chi2_per_dof demasiado alto: {chi2_dof}")
    else:
        checks["chi2_per_dof_reasonable"] = False

    # 4) _h_model se reduce al LCDM estandar cuando rho_c -> infinito
    z_test = np.array([0.0, 0.5, 1.0, 1.5, 2.0])
    H0_test, Om0_test = 70.0, 0.3
    h_holonomic_huge_rhoc = _h_model(z_test, H0_test, Om0_test, rho_c=1e12)
    e2_test = Om0_test * (1.0 + z_test) ** 3 + (1.0 - Om0_test)
    h_lcdm_standard = H0_test * np.sqrt(e2_test)
    max_rel_diff = float(
        np.max(np.abs(h_holonomic_huge_rhoc - h_lcdm_standard) / h_lcdm_standard)
    )
    checks["reduces_to_lcdm_max_rel_diff"] = max_rel_diff
    checks["reduces_to_lcdm_at_large_rho_c"] = bool(max_rel_diff < 1e-4)
    if not checks["reduces_to_lcdm_at_large_rho_c"]:
        errors.append(
            f"_h_model no converge a LCDM estandar para rho_c grande "
            f"(diff relativa maxima={max_rel_diff})"
        )

    # 5) la correccion holonomica reduce H(z) para rho_c finito (direccion
    #    fisica correcta: el techo LQG frena la expansion, no la acelera)
    rho_c_finite = 10.0 ** 6.0
    h_holonomic_finite = _h_model(z_test, H0_test, Om0_test, rho_c=rho_c_finite)
    checks["holonomic_correction_reduces_H"] = bool(
        np.all(h_holonomic_finite <= h_lcdm_standard + 1e-10)
    )
    if not checks["holonomic_correction_reduces_H"]:
        errors.append(
            "La correccion holonomica no reduce H(z) respecto a LCDM "
            "estandar para rho_c finito"
        )

    # 6) _log_prior rechaza fuera de bounds (-inf) y acepta dentro (0.0)
    theta_in_bounds = np.array([70.0, 0.3, 6.0])
    theta_out_of_bounds = np.array([200.0, 0.3, 6.0])  # H0 fuera de (40,100)
    lp_in = _log_prior(theta_in_bounds)
    lp_out = _log_prior(theta_out_of_bounds)
    checks["log_prior_accepts_in_bounds"] = bool(lp_in == 0.0)
    checks["log_prior_rejects_out_of_bounds"] = bool(np.isneginf(lp_out))
    if not checks["log_prior_accepts_in_bounds"]:
        errors.append(f"_log_prior no devolvio 0.0 dentro de bounds (dio {lp_in})")
    if not checks["log_prior_rejects_out_of_bounds"]:
        errors.append(f"_log_prior no devolvio -inf fuera de bounds (dio {lp_out})")

    # 7) un modo desconocido devuelve {"error": ...} sin lanzar excepcion
    #    (asi es como ya se comporta el dispatcher legacy en server.py)
    try:
        unknown_result = compute_cosmological_mcmc_tool(mode="no_existe", params={})
        checks["unknown_mode_returns_error_dict"] = bool(
            isinstance(unknown_result, dict) and "error" in unknown_result
        )
        if not checks["unknown_mode_returns_error_dict"]:
            errors.append(
                f"Modo desconocido no devolvio un dict con 'error': {unknown_result}"
            )
    except Exception as e:
        checks["unknown_mode_returns_error_dict"] = False
        errors.append(f"Modo desconocido lanzo excepcion en vez de devolver error: {e}")

    # 8) reproducibilidad con la misma semilla (corrida corta, 3000 pasos,
    #    para no duplicar el costo del check 1)
    try:
        run_a = _mode_mock_recovery(
            {"n_steps": 3000, "burn_in": 500, "thin": 5, "seed": 123}
        )
        run_b = _mode_mock_recovery(
            {"n_steps": 3000, "burn_in": 500, "thin": 5, "seed": 123}
        )
        reproducible = all(
            run_a["posterior_summary"][name]["mean"]
            == run_b["posterior_summary"][name]["mean"]
            for name in PARAM_NAMES
        )
        checks["reproducible_with_same_seed"] = bool(reproducible)
        if not checks["reproducible_with_same_seed"]:
            errors.append("Dos corridas con la misma semilla dieron resultados distintos")
    except Exception as e:
        checks["reproducible_with_same_seed"] = False
        errors.append(f"Test de reproducibilidad lanzo excepcion: {e}")

    return {
        "mode": "validate",
        "passed": len(errors) == 0,
        "checks": checks,
        "errors": errors,
    }


def compute_cosmological_mcmc_tool(mode, params=None):
    params = params or {}
    if mode == "mock_recovery":
        return _mode_mock_recovery(params)
    elif mode == "fit_hz_chronometers":
        return _mode_fit_hz_chronometers(params)
    elif mode == "validate":
        return _validate()
    else:
        return {
            "error": (
                f"Modo desconocido: {mode}. Modos validos: mock_recovery, "
                "fit_hz_chronometers, validate."
            )
        }'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not TARGET_PATH.exists():
        print(f"ERROR: no se encontro {TARGET_PATH.resolve()}", file=sys.stderr)
        sys.exit(1)

    content = TARGET_PATH.read_text(encoding="utf-8")

    assert content.count(SCHEMA_ENUM_OLD) == 1, (
        "No encontre (o encontre mas de una vez) el enum del schema "
        "esperado -- ajustar SCHEMA_ENUM_OLD manualmente."
    )
    assert content.count(DOCSTRING_OLD) == 1, (
        "No encontre (o encontre mas de una vez) el cierre del docstring "
        "esperado -- ajustar DOCSTRING_OLD manualmente."
    )
    assert content.count(DISPATCH_OLD) == 1, (
        "No encontre (o encontre mas de una vez) el bloque de "
        "compute_cosmological_mcmc_tool esperado -- ajustar DISPATCH_OLD "
        "manualmente (probablemente el archivo ya cambio desde que se "
        "escribio este patch)."
    )
    assert 'mode == "validate"' not in content, (
        "El modo validate ya parece estar wireado en "
        "cosmological_mcmc_tool.py -- nada que hacer."
    )

    print("=== PLAN DE PATCH ===")
    print('1) Enum del schema: agrega "validate" junto a mock_recovery/fit_hz_chronometers')
    print("2) Docstring del modulo: documenta el modo validate")
    print("3) Cuerpo: agrega _validate() (8 chequeos) + rama de dispatch")
    print()

    if args.dry_run:
        print("--dry-run: no se modifico ningun archivo.")
        return

    backup_name = f"cosmological_mcmc_tool.py.bak_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    Path(backup_name).write_text(content, encoding="utf-8")
    print(f"Backup: {backup_name}")

    content = content.replace(SCHEMA_ENUM_OLD, SCHEMA_ENUM_NEW, 1)
    content = content.replace(DOCSTRING_OLD, DOCSTRING_NEW, 1)
    content = content.replace(DISPATCH_OLD, DISPATCH_NEW, 1)

    TARGET_PATH.write_text(content, encoding="utf-8")

    try:
        py_compile.compile(str(TARGET_PATH), doraise=True)
        ast.parse(content)
        print("cosmological_mcmc_tool.py actualizado y validado sintacticamente.")
    except (py_compile.PyCompileError, SyntaxError) as e:
        print("ERROR de sintaxis tras el patch:", e, file=sys.stderr)
        print(f"Restaurando desde backup {backup_name}...", file=sys.stderr)
        Path(backup_name).replace(TARGET_PATH)
        sys.exit(1)

    print()
    print("Smoke test (modo validate, deberia dar passed=true y errors=[]):")
    print(
        '  echo \'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":'
        '{"name":"cosmological_mcmc_tool","arguments":{"mode":"validate",'
        '"params":{}}}}\' | timeout 90 python3 server.py'
    )
    print()
    print("O directo en Python (mas rapido para iterar, corre en <1s con los")
    print("params default salvo por el check 1 que usa 60000 pasos):")
    print(
        '  python3 -c "from cosmological_mcmc_tool import '
        "compute_cosmological_mcmc_tool as f; import json; "
        "print(json.dumps(f('validate'), indent=2, default=str))\""
    )


if __name__ == "__main__":
    main()
