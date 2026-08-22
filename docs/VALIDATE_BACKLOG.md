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
| ancient_calculator | ✅ validate ya existía y funciona (6 checks, confirmado 2026-08-22). No detectada por discovery (usa preset, no mode) — ver nota arriba. |

## Grupo 3 — A revisar (posible caso mixto: ¿determinista o explicativo?)

| Tool | Notas |
|---|---|
| math_explainer | revisar si genera output determinista chequeable |
| math_interpreter | ídem |
| math_philosophy_history | probablemente exenta (contenido, no cómputo) |
| ethnomath | revisar |
| ethnomath2 | revisar |
| originarios | revisar |
| paleography | revisar |
| levant | revisar |

## Próximos pasos
1. Revisar una por una las 8 restantes del Grupo 3, reclasificar a Grupo 1 o 2.
2. Resolver el rename de run_math_pipeline (liberar mode=validate real).
3. Empezar backlog del Grupo 2 (8 confirmadas + las que bajen del Grupo 3).
4. Evaluar normalizar schema de toxicity_predictor para que discovery la cuente.
5. Evaluar normalizar preset→mode en ancient_calculator para que discovery la cuente.
