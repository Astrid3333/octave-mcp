# Estado de migración mode=validate — octave-mcp

Última actualización: 2026-08-22 (post-commit 525cc66)

## Resumen
- Total tools registradas: 240
- Con mode=validate (evaluadas, todas PASSED): 209 (+2 reales: toxicity_predictor
  y ancient_calculator, no detectadas por discovery — ver notas abajo)
- Sin mode=validate en el discovery automático: 31

## Nota: toxicity_predictor
Tiene wrapper de validate funcional (23 checks, todos pasan si se llama
mode="validate" directo), pero TOOL_SCHEMA usa formato ad-hoc
({"name","description","modes":{...}}) sin inputSchema/properties/mode/enum
estándar, por lo que run_all_validations.py no la detecta. Mismo caso
documentado para persistent_homology_tool en 9d8fc15. Pendiente: decidir si
normalizar el schema (fuera de alcance de la tanda de validate).

## Nota: ancient_calculator
Tiene función validate() funcional (6 checks, todos pasan al llamar
preset="validate" directo — verificado 2026-08-22): suanpan con acarreo real,
soroban mecánica cielo/tierra, roman_hand_abacus acarreo duodecimal, yupana
reconstrucción base-40 + invariante Fibonacci por fila, manejo de negativos.
No detectada por discovery porque el parámetro de dispatch es "preset", no
"mode" (el enum que busca run_all_validations.py está bajo la clave "mode").
Pendiente: decidir si normalizar preset→mode (cambio invasivo, tocaría todas
las llamadas existentes) o dejarlo documentado como excepción conocida.

---

## Grupo 1 — Exentas (no aplica mode=validate por diseño)

| Tool | Motivo |
|---|---|
| workspace_delete | operación de estado, no cómputo |
| workspace_describe | operación de estado, no cómputo |
| workspace_link | operación de estado, no cómputo |
| workspace_list | operación de estado, no cómputo |
| workspace_load | operación de estado, no cómputo |
| workspace_save | operación de estado, no cómputo |
| octave_eval_expr | passthrough a Octave, sin resultado fijo esperado |
| octave_run | passthrough a Octave, sin resultado fijo esperado |
| octave_run_script | passthrough a Octave, sin resultado fijo esperado |
| octave_version | passthrough/metadata |
| run_octave | passthrough a Octave, sin resultado fijo esperado |
| plot_workspace_run | ejecución/renderizado, sin resultado numérico fijo |
| health_check_tool | ya es un chequeador; validate sería circular |
| run_math_pipeline | mode=validate ya ocupado (ejecuta pipeline default) — **candidato a rename**, no ausencia real |

## Grupo 2 — Backlog (pendiente implementar validate)

| Tool | Notas |
|---|---|
| entropy_structure | |
| persistent_homology | |
| lscm_tool | |
| multivariate_bayes_tool | |
| statistical_physics_tool | |
| knowledge_graph_tool | |
| semantic_bridge | |
| numeral_systems_embedding | |

## Resueltas (ex-Grupo 3)

| Tool | Resultado |
|---|---|
| math_visualization | ✅ validate agregado (6 checks, commit 525cc66). Detectada por discovery automático (usa mode). |
| math_interpreter | ✅ validate agregado (6 checks, commit eda4eb0). Detectada por discovery automático (usa mode, wrapper de handler). |
| originarios | ✅ validate agregado (8 checks: mapuche n=1 y n=1234, aymara n=21/41 forma contraida vs plena, n=347 sufijo -ni, rangos invalidos, preset desconocido — commit 17035d7). No detectada por discovery (usa preset, no mode). |
| paleography | ✅ validate agregado (7 checks: seriación diagonal Guttman, regresión lineal perfecta r²=1.0, clasificación Mahalanobis, errores de entrada — commits 3788c0b + f77ebcb). Detectada por discovery automático tras corregir el enum en el schema correcto (ver nota abajo). |
| ancient_calculator | ✅ validate ya existía y funciona (6 checks, confirmado 2026-08-22). No detectada por discovery (usa preset, no mode) — ver nota arriba. |
| ethnomath | ✅ validate ya existía y funciona (8 checks: maya round-trip, teorema chino resto, vedic x2 métodos, quipu round-trip, pi Arquímedes + enri japonés Richardson, preset desconocido). No detectada por discovery (usa preset, no mode) — mismo caso que ancient_calculator. |
| ethnomath2 | ✅ validate ya existía y funciona (12 checks: duplación egipcia, al-Khwarizmi 3 casos, al-Kashi sin(1°), campesino ruso, sexagesimal otomano + tabla senos, calendario rúnico nórdico, ciclo metónico sudeste asiático, preset desconocido; confirmado 2026-08-22). No detectada por discovery (usa preset, no mode).
| math_explainer | ➡️ Grupo 1 (exenta). Templating puro: interpola valores ya calculados por otra tool en texto español, sin mode, sin cómputo propio. No hay solución analítica que verificar, solo fidelidad de formato — fuera de alcance de esta tanda. |
| math_philosophy_history | ➡️ Grupo 1 (exenta, confirmado). `compute_math_philosophy_history(topic, params) -> str`, contenido narrativo fijo por tópico, sin mode, sin cómputo. |

## Nota: schemas huérfanos / duplicados (hallazgo en paleography_tool.py)
`paleography_tool.py` tenía DOS definiciones de schema (`PALEOGRAPHY_TOOL_SCHEMA`
con parámetros en inglés y enum, y `PALEOGRAPHY_SCHEMA` con parámetros en español
sin enum). `register_tool()` usaba la segunda (la huérfana en la práctica era la
primera, aunque tenía mejor forma). El patch inicial de validate agregó el enum
al schema equivocado (`PALEOGRAPHY_TOOL_SCHEMA`), y aunque el smoke test de
`mode="validate"` pasaba perfecto (el handler ya lo aceptaba), el discovery de
run_all_validations.py no lo contaba porque miraba el schema realmente registrado
(`PALEOGRAPHY_SCHEMA`), que no tenía enum en absoluto. Corregido en f77ebcb.
**Vale la pena revisar si este patrón (dos schemas, uno huérfano) se repite en
otras tools del ecosistema** — puede estar ocultando otros casos silenciosos
donde el schema que se edita no es el que se registra.

## Grupo 3 — A revisar (pendiente)

| Tool | Notas |
|---|---|
| levant | revisar (última pendiente) |

## Próximos pasos
1. Revisar la última pendiente (levant).
2. Resolver el rename de run_math_pipeline (liberar mode=validate real).
3. Empezar backlog del Grupo 2 real (entropy_structure, persistent_homology,
   lscm_tool, multivariate_bayes_tool, statistical_physics_tool,
   knowledge_graph_tool, semantic_bridge, numeral_systems_embedding).
4. Evaluar normalizar schema de toxicity_predictor para que discovery la cuente.
5. Evaluar normalizar preset→mode en ancient_calculator, ethnomath, ethnomath2
   y originarios para que discovery las cuente (mismo problema estructural
   en las cuatro).
6. Auditar el resto de tools del ecosistema por el patrón de "schema huérfano"
   descubierto en paleography_tool.py (dos definiciones de schema, register_tool
   usa una distinta a la que se edita habitualmente).
