"""Smoke test de CI: arranca el server stdio, verifica meta-tools, conteo
de tools (373) y dos validaciones puras-python (concrete + pdelta).

No requiere maxima/sage/lispium: solo el venv de requirements.txt.
Sale con código 0 si todo pasa, 1 si algo falla.
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMEOUT_S = 60.0


def fail(msg):
    print(f"SMOKE FAIL: {msg}")
    sys.exit(1)


def main():
    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "server.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ROOT,
        text=True,
        bufsize=1,
    )

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def recv(msg_id, timeout=TIMEOUT_S):
        end = time.time() + timeout
        while time.time() < end:
            line = proc.stdout.readline()
            if not line:
                return None
            try:
                doc = json.loads(line)
            except ValueError:
                continue
            if doc.get("id") == msg_id:
                return doc
        return None

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        if recv(1) is None:
            err = proc.stderr.read() if proc.poll() is not None else ""
            fail(f"initialize sin respuesta; stderr={err[:500]}")
        print("SMOKE: initialize ok")

        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        doc = recv(2)
        if doc is None:
            fail("tools/list sin respuesta")
        meta = [t["name"] for t in doc["result"]["tools"]]
        if sorted(meta) != ["call_tool", "get_tool_schema", "list_tools"]:
            fail(f"meta-tools inesperados: {meta}")
        print(f"SMOKE: meta-tools ok ({meta})")

        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
              "params": {"name": "list_tools", "arguments": {}}})
        doc = recv(3)
        if doc is None:
            fail("list_tools sin respuesta")
        payload = json.loads(doc["result"]["content"][0]["text"])
        names = payload if isinstance(payload, list) else payload.get(
            "tools", payload.get("names", []))
        if names and isinstance(names[0], dict):
            names = [t.get("name") for t in names]
        if len(names) != 373:
            fail(f"esperaba 373 tools, hay {len(names)}")
        print("SMOKE: list_tools == 373 ok")

        for i, tool in enumerate(
            ("concrete_design_tool", "pdelta_tool"), start=4
        ):
            send({"jsonrpc": "2.0", "id": i, "method": "tools/call",
                  "params": {"name": tool, "arguments": {"mode": "validate"}}})
            doc = recv(i)
            if doc is None:
                fail(f"{tool} validate sin respuesta")
            try:
                res = json.loads(doc["result"]["content"][0]["text"])
            except (KeyError, ValueError, IndexError) as e:
                fail(f"{tool} respuesta no-parseable: {e}; raw={str(doc)[:300]}")
            if res.get("validation_passed") is not True:
                fail(f"{tool} validation_passed={res.get('validation_passed')}"
                     f" ({res.get('total_passed')}/{res.get('total_checks')})")
            print(f"SMOKE: {tool} validate "
                  f"{res.get('total_passed')}/{res.get('total_checks')} ok")
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=15)
        except Exception:
            proc.kill()

    print("SMOKE PASS")


if __name__ == "__main__":
    main()
