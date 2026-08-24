# Herramientas SKIPPED de validate (por diseño)

## Exclusiones legítimas (9 tools):

### Wrappers de I/O (7 tools) — no aplica self-test
- workspace_list, workspace_describe, workspace_load, workspace_save
- workspace_delete, workspace_link
- run_octave

**Motivo:** son puro pass-through a disco/I/O. Un modo `validate` que se auto-chequee sin tocar disco no tiene sentido.

### run_math_pipeline
**Motivo:** `mode=validate` corre un pipeline real (default), no un autochequeo. Es el comportamiento esperado.

### health_check_tool
**Motivo:** la tool *es* el healthcheck. Autovalidarse llamándose a sí misma es circular.

---

**Decisión:** todas las 255 tools con modo `validate` implementado pasan OK (b943d27).
Los 9 restantes quedan documentados como exclusiones por diseño, NO como deuda técnica.
