# octave-mcp

Servidor MCP (JSON-RPC manual, sin FastMCP) que expone 120 herramientas matemáticas y de simulación científica sobre Octave/Python, pensadas para usarse desde Claude Desktop u otros clientes MCP.

> **Nota de unificación:** este repositorio es el único proyecto activo. El antiguo `mcp-octave-real` (FastMCP, 39 tools) fue absorbido por completo — todas sus herramientas, incluidas las de historia cuantitativa (`plague_sir`, `settlement_clusters`, `historical_extractor`, `braid_group`, Benford en `historian`), viven ahora acá. `mcp-octave-real` queda deprecado y no debe usarse ni documentarse como proyecto en paralelo.

## Arquitectura

- `server.py`: dispatcher manual (sin FastMCP). Cada tool nuevo requiere tres ediciones coordinadas: línea de import, entrada en la lista `TOOLS`, y bloque `elif tool_name ==` en el dispatch.
- Dependencias: numpy y sympy. **No** hay scipy instalado.
- Test rápido: pipear `initialize`, `tools/list`, `tools/call` (3 líneas JSON-RPC) a `timeout 30 python3 server.py`.
- Workspace persistente (`workspace_save` / `workspace_load` / `workspace_list` / `workspace_describe` / `workspace_delete`) para reutilizar resultados entre llamadas sin recomputar.

## Herramientas por área

### Orquestación y utilidades base
`octave_run`, `octave_run_script`, `octave_eval_expr`, `octave_version`, `run_math_pipeline`, `math_interpreter`, `math_explainer`, `math_error_analyzer`, `math_benchmark`, `cross_validation`, `plot_workspace_run`, `math_visualization`

### Gestión de workspace
`workspace_save`, `workspace_load`, `workspace_list`, `workspace_describe`, `workspace_delete`

### Álgebra, cálculo y análisis
`linear_algebra`, `symbolic`, `ocas_symbolic`, `abstract_algebra`, `compute_gradient_hessian`, `compute_jacobian`, `compute_hilbert_transform`, `tensor_calculus`, `integrate_stiff_ode`, `pde`, `math_interpolation`

### Sistemas dinámicos, caos y control
`compute_lyapunov_exponent`, `compute_lyapunov_v2`, `compute_bifurcation_diagram`, `population_dynamics`, `reaction_diffusion`, `reaction_diffusion_real`, `percolation_theory`, `stochastic_processes`, `control_theory`, `optimal_control`, `optimization`

### Estadística, datos y aprendizaje
`statistics`, `machine_learning_math`, `information_theory`, `spatial_statistics`, `network_science`, `persistent_homology`, `wavelet`, `entropy_structure`, `text_analysis_math`, `chemometrics_tool`, `econometrics_tool`, `graph_algorithms`

### Física y química
`quantum_information`, `qm_potential_well`, `nuclear_decay_chain`, `enzyme_kinetics`, `antibiotic_diffusion`, `population_genetics`, `braid_group`, `tritbraid`

### Matemática financiera y teoría de juegos
`financial_math` (Black-Scholes, griegas, VaR, anualidades, bonos, riesgo catastrófico vía Monte Carlo Poisson compuesto/lognormal), `game_theory`

### Historia cuantitativa, arqueología y etnomatemática
*(absorbidas de `mcp-octave-real`)*
`historian`, `historical_extractor`, `archaeological_simulation`, `settlement_clusters`, `plague_sir`, `paleography`, `archaeoastronomy`, `numeral_systems_embedding`, `math_philosophy_history`, `ethnomath`, `ethnomath2`, `originarios`, `levant`, `ancestral_octave`, `ancient_calculator`, `music_math`

### Construcción y cubicaciones
> ⚠️ Estimación preliminar / educativa. `structural_analysis` no reemplaza el cálculo y timbre de un ingeniero estructural para obra real.

`quantity_takeoff` (volumen de hormigón, encofrado, peso de acero, excavación prismática, conteo de albañilería, resumen BOQ), `structural_analysis` (reacciones/corte/momento/deflexión de vigas, fuerzas axiales en cerchas 2D vía método de nudos con autoverificación de equilibrio, propiedades de sección, chequeo de esfuerzo), `earthworks` (volumen por área media entre secciones transversales, método de grilla para corte/relleno en terreno irregular, esponjamiento/contracción, diagrama de masas y puntos de balance), `budgeting_tool` (costo directo, análisis de precio unitario/APU, gastos generales/utilidad/contingencia/IVA, escalamiento por inflación, presupuesto agregado por capítulos), `construction_scheduling_tool` (ruta crítica vía CPM, carga diaria de recursos, compresión de cronograma/crashing por menor pendiente de costo)

### Topografía y geomática
`survey_angles_tool` (conversión de azimuts/rumbos, notación N/S-E/W), `survey_distance_tool` (distancia horizontal/vertical por estadia, corrección de pendiente), `survey_curvature_tool` (corrección por curvatura y refracción terrestre), `traverse_adjustment_tool` (ajuste de poligonales, cierre de coordenadas), `survey_curves_tool` (curvas circulares horizontales: tangente, longitud de curva, externa), `survey_area_volume_tool` (área por coordenadas, volumen entre secciones)

### Geometría, mallas y cosmología
`distmesh_tool` (generación de malla 2D, algoritmo de Persson & Strang), `sdf_tool` (funciones de distancia con signo), `lscm_tool` (parametrización conforme de superficies por mínimos cuadrados), `mesh_pde_tool` (EDPs sobre malla no estructurada), `mesh_spectral_tool` (análisis espectral de malla), `geometric_algebra_protein` (álgebra geométrica aplicada a estructura de proteínas), `quantum_astro_tool`, `semiclassical_cosmology_tool`, `cosmological_mcmc_tool`, `quantum_cosmology_tool`, `polarization_mapping`

### Biología computacional
`genome_signal_analysis`, `bacterial_growth_tool`, `viral_lattice_tool`, `enzyme_stochastic`, `evo_LGCA_tool`, `optical_sequence_id`, `infrasound_tool`

### Divulgación matemática
`math_humanizer_tool` (conceptos matemáticos traducidos a analogías cotidianas + conexión filosófica + nota técnica — contenido de referencia curado, mismo espíritu que `math_philosophy_history` o `ethnomath`)

---

*Total: 120 herramientas registradas en el dispatcher (contadas directo desde `TOOLS` en `server.py`). Este número puede variar levemente con el tiempo; correr `tools/list` contra el servidor es la fuente de verdad.*
## Fisica / simulacion (bloque final del roadmap)

| Tool | Acciones | Validacion analitica | Error numerico |
|---|---|---|---|
| `multibody_dynamics_tool` | `compound_pendulum`, `rigid_body_euler`, `two_link_manipulator` | T=2π√(I/mgd); conservacion de energia/\|L\|² en rotacion libre de par; conservacion de energia en pendulo doble | 0.016% / drift ~3.7e-13 / drift ~1.1e-12 |
| `particle_simulation_tool` | `kepler_orbit`, `elastic_collision_nbody`, `random_walk_diffusion` | 3ª ley de Kepler T=2π√(a³/GM); formula de colision elastica de libro de texto; MSD=2Dt | 5e-13% / drift ~1e-15 / 0.34% |
| `finite_element_tool` | `bar_1d`, `beam_bending`, `truss_2d` | u=PL/AE (barra); δ=PL³/3EI (viga voladizo Euler-Bernoulli); equilibrio de nodos (cercha) | 0% / ~1.7e-12% / residual 0 |

octave-mcp: 88 -> 120 tools. Agregados: bloque de topografia/geomatica (6), geometria/mallas/cosmologia, biologia computacional.
Pendiente: conectores externos (FreeCAD, BIM/IFC) — oCAS ya integrado.

## Acustica y Electromagnetismo

- **acoustics_tool**: ondas de presion 1D (`pressure_wave_1d`), modos propios de sala
  (`room_modes`), tiempo de reverberacion via formula de Sabine (`reverberation_sabine`).
  Validado contra solucion analitica y contra la relacion esperada RT60(reflectante) >
  RT60(absorbente).
