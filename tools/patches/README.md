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
