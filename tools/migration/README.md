Flujo de migración de tools legacy a register_tool():
  1. build_*_plan.py       -- arma el plan (JSON), no toca nada
  2. apply_*.py --dry-run  -- reporta qué cambiaría, no escribe
  3. apply_*.py            -- aplica de verdad, deja .bak por archivo tocado
  4. verify_*.py           -- confirma el resultado (existencia, schemas, registro)
Reportes/planes de cada corrida quedan en docs/migration/phase3/.
