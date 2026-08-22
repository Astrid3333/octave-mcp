# Estado de migración mode=validate — octave-mcp

Última actualización: 2026-08-22 (post-commit 7927058)

## Resumen
- Total tools registradas: 240
- Con mode=validate (evaluadas, todas PASSED): 208 (+1 real: toxicity_predictor,
  no detectada por discovery — ver nota abajo)
- Sin mode=validate: 32

## Nota: toxicity_predictor
Tiene wrapper de validate funcional (23 checks, todos pasan si se llama
mode="validate" directo), pero TOOL_SCHEMA usa formato ad-hoc
({"name","description","modes":{...}}) sin inputSchema/properties/mode/enum
estándar, por lo que run_all_validations.py no la detecta. Mismo caso
documentado para persistent_homology_tool en 9d8fc15. Pendiente: decidir si
normalizar el schema (fuera de alcance de la tanda de validate).

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

## Grupo 3 — A revisar (posible caso mixto: ¿determinista o explicativo?)

| Tool | Notas |
|---|---|
| math_explainer | revisar si genera output determinista chequeable |
| math_interpreter | ídem |
| math_philosophy_history | probablemente exenta (contenido, no cómputo) |
| math_visualization | revisar si hay invariantes de la figura generada a chequear |
| ancient_calculator | revisar |
| ethnomath | revisar |
| ethnomath2 | revisar |
| originarios | revisar |
| paleography | revisar |
| levant | revisar |

## Próximos pasos
1. Revisar una por una las 10 del Grupo 3, reclasificar a Grupo 1 o 2.
2. Resolver el rename de run_math_pipeline (liberar mode=validate real).
3. Empezar backlog del Grupo 2 (8 confirmadas + las que bajen del Grupo 3).
4. Evaluar normalizar schema de toxicity_predictor para que discovery la cuente.
