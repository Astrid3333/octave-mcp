"""
fit_dark_sector_to_cc_data.py
===============================

A diferencia de plot_dark_sector_vs_cc_data.py (que solo evaluaba chi2 con
parametros elegidos a mano), este script AJUSTA de verdad: para cada
familia, minimiza chi2(H0, params_familia) contra los 15 puntos de
cronometros cosmicos (Moresco et al. 2012/2016, BC03).

Complejidad pareja entre familias (para que el AIC compare algo justo):
  lcdm        -> 1 parametro libre: H0
  wang_meng   -> 2 parametros libres: H0, xi
  signswitch  -> 2 parametros libres: H0, z_dagger   (k queda fijo en 5.0,
                 si no quedaria en 3 params y no es comparable con las demas)
  ide_h3      -> 2 parametros libres: H0, beta

chi2 es diagonal (solo sigma_i, sin covarianza cruzada) -- una version mas
rigurosa usaria la matriz de covarianza completa de Moresco et al. (2020),
ver CCcovariance/data/data_MM20.dat.

AIC = chi2_min + 2*k (k = num. parametros libres). Menor AIC = mejor
balance ajuste/complejidad. Delta_AIC > ~2 respecto de LCDM se suele leer
como evidencia debil a favor/en contra; > ~10, evidencia fuerte. Con solo
15 puntos y errores grandes, no esperar mucha capacidad de discriminacion.

Uso: correr desde ~/octave-mcp (con unified_dark_sector_tool.py y
CCcovariance/ ya clonado)

    python3 fit_dark_sector_to_cc_data.py
"""
import numpy as np
from scipy.optimize import minimize

from unified_dark_sector_tool import Cosmology, compute_Hz

CC_FILE = "CCcovariance/data/HzTable_MM_BC03.dat"

# --- cargar datos ------------------------------------------------------
z_obs, H_obs, err_obs = [], [], []
with open(CC_FILE) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(",")
        z_obs.append(float(parts[0]))
        H_obs.append(float(parts[1]))
        err_obs.append(float(parts[2]))
z_obs = np.array(z_obs)
H_obs = np.array(H_obs)
err_obs = np.array(err_obs)
n_data = len(z_obs)
print(f"Cargados {n_data} puntos de {CC_FILE}\n")


def chi2_of(H0, family, **kwargs):
    cosmo = Cosmology(H0=H0, Om0=0.3, Or0=8.24e-5)
    out = compute_Hz(z_obs, cosmo, family, **kwargs)
    return np.sum(((H_obs - out["H"]) / err_obs) ** 2)


# --- definir cada familia: nombres de parametros libres + guess + bounds
fit_specs = {
    "lcdm": {
        "param_names": [],
        "x0": [70.0],
        "bounds": [(50.0, 100.0)],
        "unpack": lambda x: (x[0], {}),
    },
    "wang_meng": {
        "param_names": ["xi"],
        "x0": [70.0, 0.0],
        "bounds": [(50.0, 100.0), (-1.0, 1.0)],
        "unpack": lambda x: (x[0], {"xi": x[1]}),
    },
    "signswitch": {
        "param_names": ["z_dagger"],
        "x0": [70.0, 2.0],
        "bounds": [(50.0, 100.0), (0.3, 5.0)],
        "unpack": lambda x: (x[0], {"z_dagger": x[1], "k": 5.0}),
    },
    "ide_h3": {
        "param_names": ["beta"],
        "x0": [70.0, 0.0],
        "bounds": [(50.0, 100.0), (-0.3, 0.3)],
        "unpack": lambda x: (x[0], {"beta": x[1]}),
    },
}

results = {}
print(f"{'familia':12s} {'k':>3s} {'H0':>8s}  " +
      "  ".join(f"{'param':>10s}" for _ in range(2)) +
      f"  {'chi2':>8s} {'chi2/dof':>9s} {'AIC':>8s}")

for fam, spec in fit_specs.items():
    k = len(spec["x0"])  # num. parametros libres

    def neg_obj(x, fam=fam, spec=spec):
        H0, kwargs = spec["unpack"](x)
        return chi2_of(H0, fam, **kwargs)

    res = minimize(neg_obj, x0=spec["x0"], bounds=spec["bounds"], method="L-BFGS-B")
    chi2_min = res.fun
    dof = n_data - k
    aic = chi2_min + 2 * k
    H0_best, kwargs_best = spec["unpack"](res.x)
    results[fam] = {"chi2": chi2_min, "k": k, "dof": dof, "aic": aic,
                     "H0": H0_best, "params": kwargs_best}

    param_str = "  ".join(f"{name}={kwargs_best[name]:.4f}" for name in spec["param_names"])
    print(f"{fam:12s} {k:3d} {H0_best:8.2f}  {param_str:22s}  "
          f"{chi2_min:8.2f} {chi2_min/dof:9.3f} {aic:8.2f}")

aic_lcdm = results["lcdm"]["aic"]
print("\nDelta_AIC respecto de LCDM (positivo = peor que LCDM, penalizando complejidad):")
for fam, r in results.items():
    print(f"  {fam:12s} Delta_AIC = {r['aic'] - aic_lcdm:+.2f}")

print("\nRecordatorio: chi2 diagonal (sin covarianza cruzada), 15 puntos con errores")
print("grandes -> poca capacidad de discriminacion. Esto ajusta los parametros dentro")
print("del rango donde hay datos (z<2); NO dice nada sobre el comportamiento a z>2,")
print("que es donde las familias mas se separan entre si (ver dark_sector_comparison.png).")
