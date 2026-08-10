# Benchmark: mcp-compressor sobre octave-mcp

Medido con `test_compressor.py` contra `server.py` (105 tools) el 2026-08-10.

`mcp-compressor` (atlassian-labs, v0.31.7) envuelve el server real como proxy stdio.
En vez de exponer las 105 tools con schema completo, expone 2 tools wrapper:
- `octave_get_tool_schema`: devuelve el schema completo de una tool puntual, bajo demanda.
- `octave_invoke_tool`: invoca la tool ya elegida.

El cliente pide el schema completo solo de la tool que va a usar, en vez de recibir
las 105 de entrada. Sin perdida de funcionalidad (todas las tools siguen invocables).

## Resultados

| nivel    | tokens aprox (superficie inicial) | reduccion vs. sin comprimir (~23526 tok) |
|----------|-----------------------------------|-------------------------------------------|
| sin comprimir | ~23526 | -      |
| low      | ~10682                            | 54.6%                                      |
| medium   | ~7854                             | 66.6%                                      |
| high     | ~2543                             | 89.2%                                      |

## Reproducir

```bash
cd ~/octave-mcp
python3 test_compressor.py ~/octave-mcp/server.py <low|medium|high|max>
```

## Config aplicada en Claude Desktop

`~/.config/Claude/claude_desktop_config.json`, entrada `octave-mcp`:

```json
{
  "command": "/home/astrid/.local/bin/mcp-compressor",
  "args": [
    "-c", "high",
    "--",
    "python3",
    "/home/astrid/octave-mcp/server.py"
  ]
}
```

Nivel elegido: `high` (89.2% de reduccion, sin perdida de funcionalidad segun
la documentacion oficial de mcp-compressor).
