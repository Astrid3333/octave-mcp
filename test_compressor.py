#!/usr/bin/env python3
"""
test_compressor.py

Levanta octave-mcp/server.py a traves de mcp_compressor.CompressorClient
y compara:
  - tools que expone el server ORIGINAL (via JSON-RPC directo, sin proxy)
  - tools comprimidas que veria un cliente CONECTADO AL PROXY

Uso:
    python3 test_compressor.py /ruta/a/octave-mcp/server.py [nivel]

    nivel: low | medium | high | max   (default: low)
"""

import sys
import json
import subprocess

def contar_tools_originales(server_path):
    """Llama tools/list directo contra el server, sin pasar por el proxy."""
    init_msg = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"}
        }
    })
    list_msg = json.dumps({
        "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}
    })

    proc = subprocess.run(
        ["python3", server_path],
        input=init_msg + "\n" + list_msg + "\n",
        capture_output=True, text=True, timeout=30
    )

    tools = []
    for line in proc.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == 2 and "result" in msg:
            tools = msg["result"].get("tools", [])

    tokens_aprox = len(json.dumps(tools)) // 4  # heuristica ~4 chars/token
    return tools, tokens_aprox


def contar_tools_comprimidas(server_path, nivel):
    """Levanta el proxy via SDK y lista lo que ve el cliente comprimido."""
    from mcp_compressor import CompressorClient

    with CompressorClient(
        servers={"octave": {"command": "python3", "args": [server_path]}},
        compression_level=nivel,
    ) as proxy:
        tools = [
            {"name": t.name, "description": getattr(t, "description", "")}
            for t in proxy.tools
        ]
        tokens_aprox = len(json.dumps(tools)) // 4
        return tools, tokens_aprox


def main():
    if len(sys.argv) < 2:
        print("uso: python3 test_compressor.py /ruta/a/server.py [nivel]")
        sys.exit(1)

    server_path = sys.argv[1]
    nivel = sys.argv[2] if len(sys.argv) > 2 else "low"

    print(f"=== octave-mcp sin comprimir ===")
    orig_tools, orig_tokens = contar_tools_originales(server_path)
    print(f"n_tools: {len(orig_tools)}")
    print(f"tokens aprox (schema completo): ~{orig_tokens}")
    print()

    print(f"=== proxy mcp-compressor, nivel='{nivel}' ===")
    comp_tools, comp_tokens = contar_tools_comprimidas(server_path, nivel)
    print(f"n_tools expuestas al cliente: {len(comp_tools)}")
    for t in comp_tools:
        print(f"  - {t['name']}: {t['description'][:80]}")
    print(f"tokens aprox (superficie comprimida): ~{comp_tokens}")
    print()

    if orig_tokens > 0:
        reduccion = 100 * (1 - comp_tokens / orig_tokens)
        print(f"=== resumen ===")
        print(f"reduccion aprox de tokens: {reduccion:.1f}%")
        print(f"({orig_tokens} -> {comp_tokens} tokens)")


if __name__ == "__main__":
    main()
