"""
plot_dark_sector_comparison.py
================================

Grafica H(z) para las cuatro familias expuestas de unified_dark_sector_tool
sobre el mismo eje, para comparar visualmente cómo diverge cada una de LCDM.

No reimplementa ninguna física: llama directamente a compute_Hz() del
módulo real, así que el gráfico refleja exactamente lo que corre el tool
MCP (mismo código, mismos defaults salvo lo que se pase acá).

Uso: correr desde la raíz del repo (donde está unified_dark_sector_tool.py)

    python3 plot_dark_sector_comparison.py

Genera dark_sector_comparison.png en el directorio actual.
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from unified_dark_sector_tool import Cosmology, compute_Hz

cosmo = Cosmology(H0=70.0, Om0=0.3, Or0=8.24e-5)
z = np.linspace(0.0, 5.0, 300)

families = [
    ("lcdm", {}, "ΛCDM (control)", "-"),
    ("wang_meng", {"xi": 0.1}, "Wang-Meng (ξ=0.1)", "--"),
    ("signswitch", {"z_dagger": 2.0, "k": 5.0}, "Λ_s signswitch (z†=2, k=5)", "-."),
    ("ide_h3", {"beta": 0.05}, "IDE Q~H³ (β=0.05)", ":"),
]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

curves = {}
for fam, kwargs, label, style in families:
    out = compute_Hz(z, cosmo, fam, **kwargs)
    curves[fam] = out
    ax1.plot(z, out["H"], style, label=label, linewidth=2)

ax1.set_xlabel("z (redshift)")
ax1.set_ylabel("H(z)  [km/s/Mpc]")
ax1.set_title("H(z) por familia")
ax1.legend(fontsize=9)
ax1.grid(alpha=0.3)

# panel derecho: desviación relativa contra LCDM, más fácil de leer que
# las curvas absolutas cuando divergen mucho a z alto
H_lcdm = curves["lcdm"]["H"]
for fam, kwargs, label, style in families:
    if fam == "lcdm":
        continue
    dev = 100.0 * (curves[fam]["H"] - H_lcdm) / H_lcdm
    ax2.plot(z, dev, style, label=label, linewidth=2)
ax2.axhline(0, color="k", linewidth=0.8)
ax2.set_xlabel("z (redshift)")
ax2.set_ylabel("(H_familia - H_ΛCDM) / H_ΛCDM  [%]")
ax2.set_title("Desviación relativa vs ΛCDM")
ax2.legend(fontsize=9)
ax2.grid(alpha=0.3)

fig.suptitle(
    "Comparación H(z) — ninguna familia ajustada a datos observacionales reales",
    fontsize=10, y=1.02,
)
fig.tight_layout()
fig.savefig("dark_sector_comparison.png", dpi=150, bbox_inches="tight")
print("Guardado: dark_sector_comparison.png")
