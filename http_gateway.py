#!/usr/bin/env python3
"""
http_gateway.py - expone octave-mcp (server.py, stdio) como MCP remoto por HTTP.
No modifica server.py: lo lanza como subproceso. Solo usa la libreria estandar.

Variables de entorno:
  MCP_SECRET   (obligatoria) token secreto; la URL del conector queda
               https://TU-HOST/<MCP_SECRET>/mcp
  PORT         puerto HTTP (default 8000)
  CALL_TIMEOUT segundos max por llamada (default 120)
  BLOCK_SHELL  "1" (default) bloquea llamadas obvias a shell en octave_run
"""
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SECRET = os.environ.get("MCP_SECRET", "")
PORT = int(os.environ.get("PORT", "8000"))
CALL_TIMEOUT = float(os.environ.get("CALL_TIMEOUT", "120"))
BLOCK_SHELL = os.environ.get("BLOCK_SHELL", "1") == "1"

# Freno basico, NO es una garantia. La proteccion real es: contenedor
# sin privilegios, sin secretos dentro, y URL secreta.
SHELL_RE = re.compile(
    r"\b(system|unix|dos|shell_cmd|popen2?|exec|fork|kill|urlread|urlwrite|"
    r"getenv|setenv|putenv|evalc|feval|unlink|delete|rmdir|rename|movefile|"
    r"copyfile|fopen|fread|fwrite|fdisp|fprintf|save|load|dlmread|csvread|"
    r"textread|fileread|urlread|ls|dir|cd|pwd)\s*\(",
    re.I,
)
BLOCKED_TOOLS = {"octave_run_script"}


class Backend:
    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None

    def _start(self):
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1, cwd=HERE,
        )

    def _stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None

    def request(self, msg):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            result = {}

            def worker():
                try:
                    self.proc.stdin.write(json.dumps(msg) + "\n")
                    self.proc.stdin.flush()
                    while True:
                        line = self.proc.stdout.readline()
                        if not line:
                            result["err"] = "el servidor se cerro"
                            return
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except ValueError:
                            continue
                        if obj.get("id") == msg.get("id"):
                            result["resp"] = obj
                            return
                except Exception as e:
                    result["err"] = str(e)

            t = threading.Thread(target=worker, daemon=True)
            t.start()
            t.join(CALL_TIMEOUT)
            if t.is_alive():
                self._stop()
                return _err(msg.get("id"), -32000,
                            f"timeout tras {CALL_TIMEOUT:.0f}s; servidor reiniciado")
            if "resp" in result:
                return result["resp"]
            self._stop()
            return _err(msg.get("id"), -32603, result.get("err", "error interno"))

    def notify(self, msg):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                try:
                    self.proc.stdin.write(json.dumps(msg) + "\n")
                    self.proc.stdin.flush()
                except Exception:
                    pass


def _err(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _tool_result(req_id, text, is_error=True):
    return {"jsonrpc": "2.0", "id": req_id,
            "result": {"content": [{"type": "text", "text": text}], "isError": is_error}}


backend = Backend()


def guard(msg):
    if msg.get("method") != "tools/call":
        return None
    p = msg.get("params") or {}
    name = p.get("name")
    args = p.get("arguments") or {}
    target, targs = name, args
    if name == "call_tool":
        target, targs = args.get("name"), args.get("arguments") or {}
    if target in BLOCKED_TOOLS:
        return _tool_result(msg.get("id"), f"'{target}' esta deshabilitada en el modo remoto.")
    if BLOCK_SHELL and target in ("octave_run", "run_octave", "octave_eval_expr"):
        code = targs.get("code") or targs.get("expression") or ""
        if SHELL_RE.search(code):
            return _tool_result(
                msg.get("id"),
                "Bloqueado en modo remoto: el codigo usa funciones de sistema/archivos.")
    return None


def handle(msg):
    if "id" not in msg:
        backend.notify(msg)
        return None
    method = msg.get("method")
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg["id"], "result": {}}
    if method in ("resources/list", "prompts/list", "resources/templates/list"):
        key = method.split("/")[0]
        return {"jsonrpc": "2.0", "id": msg["id"], "result": {key: []}}
    blocked = guard(msg)
    if blocked:
        return blocked
    return backend.request(msg)


class Handler(BaseHTTPRequestHandler):
    server_version = "octave-mcp-gateway"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body=b"", ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _authorized(self):
        return self.path.split("?")[0].rstrip("/") == f"/{SECRET}/mcp"

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, b'{"ok":true}')
        if not self._authorized():
            return self._send(404)
        self._send(405, b"", extra={"Allow": "POST"})

    def do_DELETE(self):
        self._send(200 if self._authorized() else 404)

    def do_OPTIONS(self):
        self._send(204, b"", extra={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        })

    def do_POST(self):
        if not self._authorized():
            return self._send(404)
        try:
            n = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(n) or b"null")
        except Exception:
            return self._send(400, json.dumps(_err(None, -32700, "JSON invalido")).encode())
        batch = isinstance(payload, list)
        msgs = payload if batch else [payload]
        out = [r for r in (handle(m) for m in msgs if isinstance(m, dict)) if r]
        if not out:
            return self._send(202)
        body = json.dumps(out if batch else out[0], ensure_ascii=False).encode()
        self._send(200, body)


if __name__ == "__main__":
    if len(SECRET) < 16:
        sys.exit("Define MCP_SECRET con al menos 16 caracteres")
    print(f"octave-mcp gateway en :{PORT}  ->  /<MCP_SECRET>/mcp", file=sys.stderr)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
