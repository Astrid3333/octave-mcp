#!/usr/bin/env python3
"""
test_bio_tools.py

Prueba rapida de los 9 bio tools recien wireados en server.py, todos
llamados con mode='validate' (soportado por default en los 9). Reusa
el mismo patron send_request/recv del harness existente.

Uso:
    python3 test_bio_tools.py /home/astrid/octave-mcp/server.py
"""
import json
import queue
import subprocess
import sys
import threading
import time

TOOLS = [
    "genome_signal_analysis",
    "polarization_mapping",
    "geometric_algebra_protein",
    "optical_sequence_id",
    "infrasound_tool",
    "bacterial_growth_tool",
    "viral_lattice_tool",
    "enzyme_stochastic",
    "evo_LGCA_tool",
]


def reader_thread(proc, out_q):
    for line in proc.stdout:
        out_q.put(line)


def send_request(proc, out_q, req_id, method, params, timeout=15):
    req = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    start = time.time()
    while time.time() - start < timeout:
        try:
            line = out_q.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            resp = json.loads(line)
        except json.JSONDecodeError:
            continue
        if resp.get("id") == req_id:
            return resp
    return {"ok": False, "error": f"timeout despues de {timeout}s"}


def main():
    if len(sys.argv) < 2:
        print("uso: python3 test_bio_tools.py /ruta/a/server.py")
        sys.exit(1)

    server_path = sys.argv[1]
    proc = subprocess.Popen(
        [sys.executable, server_path],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    out_q = queue.Queue()
    t = threading.Thread(target=reader_thread, args=(proc, out_q), daemon=True)
    t.start()

    print("=== initialize ===")
    resp = send_request(proc, out_q, 1, "initialize", {})
    print(resp)
    if proc.poll() is not None:
        print("El proceso crasheo en initialize. stderr:")
        print(proc.stderr.read())
        sys.exit(1)

    results = {}
    print(f"\n=== corriendo {len(TOOLS)} bio tools con mode=validate ===\n")
    for i, tool_name in enumerate(TOOLS, start=2):
        t0 = time.time()
        resp = send_request(
            proc, out_q, i, "tools/call",
            {"name": tool_name, "arguments": {"mode": "validate"}},
        )
        elapsed = time.time() - t0
        ok = "error" not in resp
        results[tool_name] = ok
        status = "OK" if ok else "FAIL"
        print(f"--- {tool_name} ---")
        print(f"[{status}] ({elapsed:.2f}s): {resp}\n")

    print("=== resumen ===")
    for tool_name, ok in results.items():
        print(f"  {tool_name}: {'OK' if ok else 'FAIL'}")

    proc.terminate()


if __name__ == "__main__":
    main()
