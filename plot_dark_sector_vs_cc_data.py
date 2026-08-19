"""
plot_dark_sector_vs_cc_data.py
================================

Contrasta las 4 familias de unified_dark_sector_tool contra datos reales
de H(z) medidos con cronómetros cósmicos (Moresco et al. 2012, 2016;
compilación BC03 de CCcovariance/data/HzTable_MM_BC03.dat).

No es un ajuste (fit): los parámetros de cada familia (xi, z_dagger, k, beta)
quedan FIJOS en los mismos valores que veníamos usando para comparar entre
familias, y H0=70 fijo. Esto es un chequeo visual de "¿cae dentro de las
barras de error con parámetros razonables?", no una inferencia de
parámetros. Para eso haría falta un MCMC/least-squares real sobre (H0, xi,
z_dagger, k, beta) simultáneamente, con la matriz de covarianza completa
(no solo la diagonal) — ver CCcovariance/data/data_MM20.dat para la receta
de covarianza si se quiere ir un paso más allá.

Uso: correr desde ~/octave-mcp (donde están unified_dark_sector_tool.py Y
la carpeta CCcovariance/ clonada)

    python3 plot_dark_sector_vs_cc_data.py
"""
import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from unified_dark_sector_tool import Cosmology, compute_Hz

CC_FILE = "CCcovariance/data/HzTable_MM_BC03.dat"

# --- 1. cargar datos reales -------------------------------------------------
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
print(f"Cargados {len(z_obs)} puntos de {CC_FILE} (z de {z_obs.min():.2f} a {z_obs.max():.2f})")

# --- 2. calcular las 4 familias sobre una grilla fina + en los puntos z_obs -
cosmo = Cosmology(H0=70.0, Om0=0.3, Or0=8.24e-5)
z_grid = np.linspace(0.0, max(2.5, z_obs.max() * 1.05), 300)

families = [
    ("lcdm", {}, "ΛCDM (control)", "-"),
    ("wang_meng", {"xi": 0.1}, "Wang-Meng (ξ=0.1)", "--"),
    ("signswitch", {"z_dagger": 2.0, "k": 5.0}, "Λ_s signswitch (z†=2, k=5)", "-."),
    ("ide_h3", {"beta": 0.05}, "IDE Q~H³ (β=0.05)", ":"),
]

print("\nchi2 (diagonal, sin covarianza completa, parametros fijos NO ajustados):")
fig, ax = plt.subplots(figsize=(9, 6.5))

ax.errorbar(z_obs, H_obs, yerr=err_obs, fmt="o", color="black",
            markersize=4, capsize=3, elinewidth=1, label="Cronómetros cósmicos (Moresco et al., BC03)")

for fam, kwargs, label, style in families:
    out_grid = compute_Hz(z_grid, cosmo, fam, **kwargs)
    ax.plot(z_grid, out_grid["H"], style, linewidth=2, label=label)

    out_obs = compute_Hz(z_obs, cosmo, fam, **kwargs)
    chi2 = np.sum(((H_obs - out_obs["H"]) / err_obs) ** 2)
    dof = len(z_obs)
    print(f"  {fam:12s} chi2 = {chi2:7.2f}   chi2/dof = {chi2/dof:.2f}")

ax.set_xlabel("z (redshift)")
ax.set_ylabel("H(z)  [km/s/Mpc]")
ax.set_title("H(z): 4 familias (parámetros fijos, sin ajustar) vs cronómetros cósmicos")
ax.legend(fontsize=9)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig("dark_sector_vs_cc_data.png", dpi=150, bbox_inches="tight")
print("\nGuardado: dark_sector_vs_cc_data.png")
print("\nNota: chi2/dof bajo ac\u00e1 NO significa 'modelo confirmado' -- los par\u00e1metros")
print("no fueron ajustados a estos datos, son los mismos que eleg\u00edamos antes para")
print("comparar entre familias. Es una foto de compatibilidad visual, no una inferencia.")
