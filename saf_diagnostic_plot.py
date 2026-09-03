#!/usr/bin/env python3
"""
Diagnostico interseismico: velocidad GPS paralela a la falla vs distancia
perpendicular a la traza, comparado contra el modelo clasico de bloqueo
elastico (Savage & Burford, 1973):

    v_parallel(x) = v0 + (S / pi) * arctan((x - x0) / D)

donde:
    S  = tasa de slip geologica del segmento (mm/anio, FIJA, conocida)
    D  = profundidad de bloqueo (locking depth, km -> se ajusta)
    x0 = offset de la traza respecto al origen asumido (km, opcional, --fit-x0)
    v0 = offset de marco de referencia (mm/anio, se ajusta)

Si el ajuste es bueno (RMS residual bajo, D fisicamente razonable, ~3-30 km
para el sur de SAF) el dato es consistente con bloqueo interseismico limpio y
el problema real esta en la inversion (regularizacion, parametrizacion).
Si el ajuste es malo (dispersion grande no explicada por distancia, D fuera
de rango, o forma no-arcotangente) el problema esta en los datos de entrada
(estaciones campaign viejas de alta incertidumbre, ventanas temporales no
puramente interseismicas, mezcla de marcos de referencia), no en la inversion.

USO:
    python3 saf_diagnostic_plot.py diagnostic_Carrizo.csv diagnostic_Mojave.csv \\
        diagnostic_SanBernardino.csv diagnostic_Coachella.csv \\
        --names Carrizo,Mojave,"San Bernardino",Coachella \\
        --slip-rates 26.5,21.0,24.0,22.0

FORMATO ESPERADO DEL CSV (con encabezado):
    station,dist_perp_km,v_parallel_mm_yr,sigma_v_mm_yr

    dist_perp_km      distancia perpendicular FIRMADA a la traza (mantene el
                       mismo signo/criterio que ya usas en la proyeccion de
                       run_southern_saf_coupling.py, para que x0~0 tenga sentido)
    v_parallel_mm_yr  velocidad GPS proyectada sobre el rumbo (fault-parallel),
                       la misma que ya calculas ahi
    sigma_v_mm_yr     opcional; si falta o esta vacia, se usa peso uniforme

No inventa geometria de falla ni reproyecta nada: consume directamente los
valores que tu script de inversion ya calcula, asi que el resultado es
comparable 1:1 con lo que entra al inversor de coupling.
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit


def load_csv(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    if not rows:
        raise ValueError(f"{path}: no se encontraron filas")
    dist = np.array([float(r["dist_perp_km"]) for r in rows])
    vpar = np.array([float(r["v_parallel_mm_yr"]) for r in rows])
    has_sigma = "sigma_v_mm_yr" in rows[0] and all(
        (r.get("sigma_v_mm_yr") not in (None, "")) for r in rows
    )
    if has_sigma:
        sigma = np.array([float(r["sigma_v_mm_yr"]) for r in rows])
    else:
        sigma = np.ones_like(vpar)
    stations = [r.get("station", "") for r in rows]
    return stations, dist, vpar, sigma


def arctan_model(x, v0, D, x0, S):
    return v0 + (S / np.pi) * np.arctan((x - x0) / D)


def fit_segment(dist, vpar, sigma, slip_rate, fit_x0=False):
    S = slip_rate

    if fit_x0:
        def model(x, v0, D, x0):
            return arctan_model(x, v0, D, x0, S)
        p0 = [float(np.median(vpar)), 15.0, 0.0]
        bounds = ([-200.0, 1.0, -50.0], [200.0, 100.0, 50.0])
    else:
        def model(x, v0, D):
            return arctan_model(x, v0, D, 0.0, S)
        p0 = [float(np.median(vpar)), 15.0]
        bounds = ([-200.0, 1.0], [200.0, 100.0])

    popt, pcov = curve_fit(
        model, dist, vpar, p0=p0, sigma=sigma, absolute_sigma=True,
        bounds=bounds, maxfev=20000,
    )
    perr = np.sqrt(np.diag(pcov))
    resid = vpar - model(dist, *popt)
    rms = float(np.sqrt(np.mean(resid ** 2)))
    chi2 = float(np.sum((resid / sigma) ** 2))
    dof = len(vpar) - len(popt)
    chi2_red = chi2 / dof if dof > 0 else float("nan")
    return popt, perr, rms, chi2_red, model


def plot_segment(ax, name, dist, vpar, sigma, popt, model, rms, chi2_red):
    ax.errorbar(dist, vpar, yerr=sigma, fmt="o", ms=3, alpha=0.5,
                color="tab:blue", ecolor="tab:blue", elinewidth=0.5,
                capsize=0, label="GPS (componente paralela a falla)")
    xx = np.linspace(float(dist.min()), float(dist.max()), 400)
    ax.plot(xx, model(xx, *popt), color="tab:red", lw=2,
            label="Ajuste arcotangente (Savage-Burford)")
    ax.axhline(0, color="gray", lw=0.8, ls=":")
    ax.axvline(0, color="gray", lw=0.8, ls=":")
    D = popt[1]
    txt = f"D = {D:.1f} km\nRMS = {rms:.2f} mm/yr\nchi2_red = {chi2_red:.2f}"
    ax.text(0.03, 0.97, txt, transform=ax.transAxes, va="top", fontsize=9,
            bbox=dict(boxstyle="round", fc="white", alpha=0.8))
    ax.set_title(name)
    ax.set_xlabel("distancia perpendicular a la traza (km)")
    ax.set_ylabel("velocidad paralela a la falla (mm/yr)")
    ax.legend(fontsize=8, loc="lower right")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csvs", nargs="+", help="uno o mas CSV, uno por segmento")
    ap.add_argument("--names", help="nombres de segmento separados por coma, mismo orden que los CSV")
    ap.add_argument("--slip-rates", required=True,
                     help="tasas de slip geologicas (mm/yr) separadas por coma, mismo orden que los CSV")
    ap.add_argument("--fit-x0", action="store_true",
                     help="ademas de v0 y D, ajustar tambien el offset de la traza x0 (km)")
    ap.add_argument("--out", default="saf_interseismic_diagnostic.png")
    args = ap.parse_args()

    csvs = [Path(p) for p in args.csvs]
    slip_rates = [float(s) for s in args.slip_rates.split(",")]
    if len(slip_rates) != len(csvs):
        sys.exit("Error: --slip-rates necesita un valor por cada CSV, en el mismo orden")

    if args.names:
        names = [n.strip() for n in args.names.split(",")]
    else:
        names = [p.stem.replace("diagnostic_", "") for p in csvs]
    if len(names) != len(csvs):
        sys.exit("Error: --names necesita un valor por cada CSV, en el mismo orden")

    n = len(csvs)
    ncols = 2
    nrows = (n + 1) // 2
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 4.5 * nrows), squeeze=False)
    axes_flat = axes.flatten()

    print("=" * 70)
    print("DIAGNOSTICO INTERSISMICO: ajuste arcotangente por segmento")
    print("=" * 70)

    for i, (csv_path, name, S) in enumerate(zip(csvs, names, slip_rates)):
        stations, dist, vpar, sigma = load_csv(csv_path)
        popt, perr, rms, chi2_red, model = fit_segment(
            dist, vpar, sigma, S, fit_x0=args.fit_x0)
        plot_segment(axes_flat[i], name, dist, vpar, sigma, popt, model, rms, chi2_red)

        v0, D = popt[0], popt[1]
        v0_err, D_err = perr[0], perr[1]
        print(f"\nSegmento: {name}  (n_estaciones={len(dist)}, slip_rate={S} mm/yr)")
        print(f"  v0 (offset de marco de referencia) = {v0:.2f} +/- {v0_err:.2f} mm/yr")
        print(f"  D  (profundidad de bloqueo)         = {D:.1f} +/- {D_err:.1f} km")
        if args.fit_x0:
            print(f"  x0 (offset de traza)                = {popt[2]:.1f} +/- {perr[2]:.1f} km")
        print(f"  RMS residual = {rms:.2f} mm/yr")
        print(f"  chi2 reducido = {chi2_red:.2f}")
        if 3.0 <= D <= 30.0:
            print("  -> D en rango fisicamente plausible para el sur de SAF: "
                  "el patron interseismico simple SI explica el dato")
        else:
            print("  -> D fuera del rango tipico (3-30 km): sospechar de este "
                  "segmento en particular (mezcla de fuentes, ventana temporal, outliers)")

    for j in range(n, len(axes_flat)):
        fig.delaxes(axes_flat[j])

    fig.tight_layout()
    fig.savefig(args.out, dpi=150)
    print(f"\nGuardado: {args.out}")


if __name__ == "__main__":
    main()
