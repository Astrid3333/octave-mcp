# octave-mcp

Servidor MCP (Model Context Protocol) con un ecosistema amplio de herramientas de cómputo científico, estadístico, de ingeniería y simulación — todas expuestas como tools invocables desde Claude Desktop u otros clientes MCP compatibles.

## Herramientas destacadas: Probabilidad avanzada e inferencia bayesiana

### `advanced_probability_tool`
Probabilidad avanzada e inferencia bayesiana. Modos (`mode` + `params`):

- **`distributions`** — pdf/cdf/cuantiles/muestreo para 15 distribuciones (continuas y discretas) vía `scipy.stats`. Validado contra momentos analíticos (error <5% en media y varianza sobre 200k muestras).
  - Parámetros: `name` (ver lista abajo), `action` (`pdf`|`cdf`|`quantile`|`sample`|`summary`), `params` (parámetros propios de la distribución), `x` (para pdf/cdf), `q` (para quantile), `n_samples`/`seed` (para sample).
  - Distribuciones soportadas: `normal`, `t`, `chi2`, `f`, `uniform`, `exponential`, `beta`, `gamma`, `weibull`, `lognormal`, `binomial`, `poisson`, `geometric`, `negative_binomial`, `hypergeometric`.
- **`bayesian_inference`** — Metropolis-Hastings propio para `beta_binomial`, `normal_known_variance`, y `linear_regression`. Validado contra posteriores conjugados exactos (error <0.1% en media, <2% en varianza).
- **`model_comparison`** — WAIC y LOO (importance sampling con pesos truncados; no es PSIS completo). Valida correctamente que el modelo verdadero gana sobre uno mal especificado (172 vs 299 en el caso sintético de referencia).
- **`posterior_predictive`** — p-value predictivo posterior con estadístico de prueba (max/min/mean/sd). Calibración de intervalos verificada al 90% (±0.2pp). Nota: el p-value es conservador por construcción (no uniforme), comportamiento documentado en la literatura, no un bug.
- **`validate`** — corre todos los chequeos anteriores de una vez y devuelve `validation_passed`.

### `advanced_stochastic_tool`
Procesos estocásticos avanzados, numpy-only:

- **`hmm`** — Hidden Markov Model discreto (forward-backward exacto + Viterbi). Validado contra fuerza bruta.
- **`kalman`** — Filtro de Kalman lineal-gaussiano. Validado: MSE filtrado < MSE observación cruda, covarianza converge al punto fijo de Riccati.
- **`particle_filter`** — Bootstrap particle filter con resampling sistemático. Validado contra Kalman (error relativo <5%).
- **`garch`** — GARCH(1,1) por máxima verosimilitud con reinicios múltiples. Recupera parámetros con error <15% en varianza incondicional.

### `multivariate_bayes_tool`
Estadística bayesiana multivariada y reducción de dimensión:

- **`mvn_sample`** / **`mvt_sample`** / **`wishart_sample`** — muestreo y verificación de momentos para normal, t y Wishart multivariadas.
- **`hierarchical`** — modelo jerárquico normal-normal (estilo "8 schools") vía Gibbs sampling.
- **`hmc_regression`** — regresión lineal bayesiana vía Hamiltonian Monte Carlo (leapfrog propio). Tasa de aceptación >95%.
- **`pca_biplot`** — PCA vía SVD y eigh, cross-validados entre sí.
- **`pca_cv`** — selección de componentes vía cross-validation real (holdout) con detección de codo tipo kneedle.
- **`factor_analysis`** — Factor Analysis vía EM (Rubin-Thayer).

## Uso

Cada tool se invoca con `mode` (o el parámetro que corresponda) + `params`, según el schema de cada uno. Ver el docstring de cada módulo (`advanced_probability_tool.py`, `advanced_stochastic_tool.py`, `multivariate_bayes_tool.py`) para el detalle completo de validaciones numéricas.

## Estado

Todos los modos listados arriba están wireados en `server.py`, probados en vivo, y con `validation_passed: true` en sus auto-chequeos internos.
