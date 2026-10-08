# Herramientas SKIPPED de validate (por diseño)

## Exclusiones legítimas (10 tools):

### Wrappers de I/O (6 tools) — no aplica self-test
- workspace_list, workspace_describe, workspace_load, workspace_save
- workspace_delete
- run_octave

**Motivo:** son puro pass-through a disco/I/O. Un modo `validate` que se auto-chequee sin tocar disco no tiene sentido.

### run_math_pipeline
**Motivo:** `mode=validate` corre un pipeline real (default), no un autochequeo. Es el comportamiento esperado.

### data_provenance_tool
**Motivo:** no declara acción `validate` en su schema; es una tool de metadatos/proveniencia.

### bot_farm_pipeline_tool
**Motivo:** no declara acción `validate` en su schema; orquesta el pipeline de bots vía pasos explícitos.

### ethnomath_comparative_tool
**Motivo:** no declara acción `validate` en su schema; es una herramienta comparativa pura.

---

**Decisión:** del catálogo completo (`tools/list_full` = 347), el runner evalúa 337; en el run histórico (b943d27) 255 pasan OK y 82 quedan errored/failed en ese run. Las 10 restantes quedan documentadas como exclusiones por diseño, NO como deuda técnica.