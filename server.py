#!/usr/bin/env python3
import subprocess, json, sys, os

# Permite importar lyapunov_tool.py si está en la misma carpeta que este server.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lyapunov_tool import compute_lyapunov_exponent, LYAPUNOV_TOOL_SCHEMA
from stiff_ode_tool import integrate_stiff_ode, STIFF_ODE_TOOL_SCHEMA
from bifurcation_tool import compute_bifurcation_diagram, BIFURCATION_TOOL_SCHEMA


def run_octave(code):
    result = subprocess.run(
        ["octave", "--no-gui", "--eval", code],
        capture_output=True, text=True, timeout=30
    )
    return result.stdout + result.stderr


TOOLS = [
    {
        "name": "run_octave",
        "description": "Ejecuta codigo GNU Octave",
        "inputSchema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
    LYAPUNOV_TOOL_SCHEMA,
    STIFF_ODE_TOOL_SCHEMA,
    BIFURCATION_TOOL_SCHEMA,
]


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        req_id = req.get("id")
        method = req.get("method", "")
        if req_id is None:
            continue

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "octave-mcp", "version": "1.1"},
                },
            }

        elif method == "tools/list":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

        elif method == "tools/call":
            tool_name = req["params"]["name"]
            args = req["params"].get("arguments", {})

            if tool_name == "run_octave":
                output = run_octave(args["code"])
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": output or "(sin salida)"}]},
                }

            elif tool_name == "compute_lyapunov_exponent":
                result = compute_lyapunov_exponent(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "integrate_stiff_ode":
                result = integrate_stiff_ode(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "compute_bifurcation_diagram":
                result = compute_bifurcation_diagram(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            else:
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32601, "message": f"Tool desconocido: {tool_name}"},
                }

        else:
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}

        print(json.dumps(resp), flush=True)

    except Exception as e:
        print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}), flush=True)
