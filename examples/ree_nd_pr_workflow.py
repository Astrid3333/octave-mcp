#!/usr/bin/env python3
"""
ree_nd_pr_workflow.py

Ejemplo end-to-end: separar Neodimio (Nd) de Praseodimio (Pr) por SX,
el par de tierras raras adyacentes mas dificil de separar (son casi
identicos quimicamente -- por eso beta es chico, ~1.4 a 2.3 segun el
extractante usado, tipicamente P507/EHEHPA o PC88A en medio nitrico/clorhidrico).

Uso:
    python3 ree_nd_pr_workflow.py
    python3 ree_nd_pr_workflow.py --beta 1.8 --pureza 0.995

Requiere ree_solvent_extraction_tool.py en el mismo directorio o en el PYTHONPATH.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ree_solvent_extraction_tool import _stage_count, _mccabe_thiele  # noqa: E402


def run_workflow(beta, feed_ratio, pureza_objetivo, oa_ratio):
    """
    beta: factor de separacion Nd/Pr del sistema extractante elegido
    feed_ratio: [Nd]/[Pr] en la alimentacion (bastnasita tipica: ~1.0-1.3)
    pureza_objetivo: fraccion de Nd deseada en el producto (ej 0.995 = 99.5%)
    oa_ratio: razon de flujos organico/acuoso operada en planta
    """
    # product_ratio = Nd/Pr equivalente a la pureza deseada
    product_ratio = pureza_objetivo / (1.0 - pureza_objetivo)

    print("=" * 70)
    print("PASO 1: Fenske -- etapas minimas teoricas (reflujo total)")
    print("=" * 70)
    fenske = _stage_count(beta=beta, feed_ratio=feed_ratio, product_ratio=product_ratio)
    print(json.dumps(fenske, indent=2, ensure_ascii=False))

    n_stages_real = fenske["n_stages_practical"] + 2  # margen sobre el minimo teorico
    print(f"\n-> Fenske dice minimo {fenske['n_stages_practical']} etapas ideales.")
    print(f"   En planta real (reflujo finito) se usan tipicamente algunas mas.")
    print(f"   Simulamos con {n_stages_real} etapas reales.\n")

    print("=" * 70)
    print(f"PASO 2: McCabe-Thiele/Kremser -- perfil con {n_stages_real} etapas reales")
    print("=" * 70)
    # D_Nd y D_Pr tal que D_Nd/D_Pr = beta (convencion: A=Nd es el mas extraible)
    D_Pr = 1.0
    D_Nd = beta * D_Pr

    mccabe = _mccabe_thiele(
        D_A=D_Nd, D_B=D_Pr,
        n_stages=n_stages_real,
        oa_ratio=oa_ratio,
        feed_conc_A=feed_ratio,  # Nd
        feed_conc_B=1.0,          # Pr (normalizado)
    )
    print(json.dumps(mccabe, indent=2, ensure_ascii=False))

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"Pureza de Nd lograda en el extracto organico: {mccabe['purity_A_in_extract']*100:.2f}%")
    print(f"Objetivo era:                                  {pureza_objetivo*100:.2f}%")
    print(f"Recuperacion de Nd:                             {mccabe['recovery_A_pct']:.2f}%")

    if mccabe["purity_A_in_extract"] >= pureza_objetivo:
        print("\n[OK] La pureza objetivo se alcanza o supera con estas etapas/O-A.")
    else:
        print("\n[AVISO] No se alcanza la pureza objetivo -- subir n_stages, oa_ratio, "
              "o revisar si el beta del extractante elegido es suficiente.")

    return fenske, mccabe


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ejemplo de separacion SX Nd/Pr")
    parser.add_argument("--beta", type=float, default=1.8,
                         help="Factor de separacion Nd/Pr (default 1.8, tipico P507)")
    parser.add_argument("--feed-ratio", type=float, default=1.15,
                         help="[Nd]/[Pr] en la alimentacion (default 1.15, tipico bastnasita)")
    parser.add_argument("--pureza", type=float, default=0.995,
                         help="Pureza objetivo de Nd en el producto (default 0.995)")
    parser.add_argument("--oa-ratio", type=float, default=1.2,
                         help="Razon de flujos organico/acuoso (default 1.2)")
    args = parser.parse_args()

    run_workflow(
        beta=args.beta,
        feed_ratio=args.feed_ratio,
        pureza_objetivo=args.pureza,
        oa_ratio=args.oa_ratio,
    )
