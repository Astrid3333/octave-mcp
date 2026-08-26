# tools/patches/

Scripts de patch puntuales, ya aplicados al repo. Se conservan como
referencia histórica -- no hace falta (ni conviene) volver a correrlos.

- `patch_wire_gait.py` -- wireó gait_analysis_tool.py en server.py
  (import + auto-registro vía tool_registry.register_tool()).
- `patch_wire_socket.py` -- mismo patrón para socket_topology_tool.py.
- `fix_handlers.py` -- corrigió la firma de `_handler` en
  gait_analysis_tool.py y socket_topology_tool.py: el dispatch real de
  tool_registry llama al handler con el dict de args completo como un
  solo parámetro posicional (no expandido vía **kwargs).
- `patch_add_temperature_sweep.py` -- agregó el modo `temperature_sweep`
  a statmech_partition_tool.py (barrido de T con guardado opcional en
  workspace vía workspace_tool.save_run).
- `patch_fix_spectroscopy_register.py` -- corrigió el bloque de registro
  de spectroscopy_tool.py: register_tool() vivía dentro de una función
  _register() que solo se invocaba bajo `if __name__ == '__main__':`,
  además con firma incorrecta (`modes=TOOL_MODES` en vez de pasar
  TOOL_SCHEMA como segundo argumento posicional).
- `patch_add_validation_passed_spectroscopy.py` -- agregó el campo
  `validation_passed` al dict que devuelve run_self_test() en
  spectroscopy_tool.py (el harness solo reconoce ese campo, u otros
  alias en VALIDATION_FIELD_ALIASES, no 'status').
- `patch_fix_registration_and_validation.py` -- versión combinada de
  los dos patches anteriores (registro + validation_passed), aplicada a
  angle_math_tool.py, que traía el mismo bug de registro heredado del
  mismo documento externo.
- `patch_add_angle_math_import.py` -- agregó `import angle_math_tool`
  a server.py (el archivo nunca había llegado a importarse, por eso
  el fix de registro por sí solo no alcanzaba).
