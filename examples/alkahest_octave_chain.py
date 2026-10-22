#!/usr/bin/env python3
"""Cadena demo alkahest -> Octave sobre el wire MCP real.

1. alkahest_cas_tool: diff simbólico de f(x)=sin(x^2)*exp(x)
   (DerivedResult con steps de reglas de reescritura).
2. octave_run: toma el value en notación infija, lo verifica contra
   diferencias centrales y quadgk, y grafica f y f' a un PNG.

Uso:
    .venv/bin/python examples/alkahest_octave_chain.py [--png RUTA]
"""
import argparse
import json
import subprocess
import sys

SERVER = "/home/astrid/octave-mcp/server.py"
PYTHON = "/home/astrid/octave-mcp/.venv/bin/python"
DEFAULT_PNG = "/tmp/opencode/alkahest_octave_chain.png"


class Wire:
    """Cliente MCP stdio mínimo (initialize + tools/call)."""

    def __init__(self):
        self.proc = subprocess.Popen(
            [PYTHON, SERVER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._id = 0
        self._send({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                    "params": {}})
        self._recv(0)

    def _send(self, payload):
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()

    def _recv(self, expect_id):
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("server.py cerró stdout")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == expect_id:
                return msg

    def call_tool(self, name, args):
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
                    "params": {"name": name, "arguments": args}})
        resp = self._recv(self._id)
        if "error" in resp:
            raise RuntimeError(f"RPC error: {resp['error']}")
        for item in resp["result"].get("content", []):
            if item.get("type") == "text":
                try:
                    return json.loads(item["text"])
                except json.JSONDecodeError:
                    return item["text"]
        return resp["result"]

    def close(self):
        self.proc.kill()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--png", default=DEFAULT_PNG)
    args = parser.parse_args()

    wire = Wire()
    try:
        expr = "sin(x^2)*exp(x)"

        # --- 1) CAS simbólico en alkahest ---
        print("[1] alkahest_cas_tool: diff de f(x) = sin(x^2)*exp(x)")
        diff = wire.call_tool(
            "alkahest_cas_tool",
            {"mode": "compute", "operation": "diff", "expr": expr},
        )
        value = diff["value"]
        rules = ", ".join(s["rule"] for s in diff["steps"])
        print(f"    value = {value}")
        print(f"    steps = {len(diff['steps'])} ({rules})")

        print("[2] alkahest_cas_tool: integrate x^2 en [0, 2]")
        integ = wire.call_tool(
            "alkahest_cas_tool",
            {"mode": "compute", "operation": "integrate", "expr": "x^2",
             "bounds": [0, 2]},
        )
        print(f"    value = {integ['value']}  "
              f"certificado Lean 4: {integ['certificate_chars']} chars")

        # --- 2) verificación + gráfico en Octave ---
        # Los value de alkahest son infijos de escalares: en Octave los
        # símbolos llegan como vectores, así que todos los operadores binarios
        # se vuelven elementwise (^->.^; * y / sin importar espacios).
        def to_octave(src):
            return src.replace("^", ".^").replace("*", ".*").replace("/", "./")

        octave_value = to_octave(value)      # f' simbólica (alkahest)
        octave_fn = to_octave(expr)          # f original (para diferenciar)
        print("[3] octave_run: verificar derivada + graficar")
        octave_code = f"""
x = linspace(0, 2, 400);
f = @(x) {octave_fn};
df = @(x) {octave_value};
y = df(x);                       % derivada simbolica de alkahest
h = 1e-6;
yn = (f(x + h) - f(x - h)) / (2 * h);   % derivada central de f
err = max(abs(y - yn));
printf('max |derivada alkahest - diferencias centrales| = %.3e\\n', err);

v_num = quadgk(@(t) t .^ 2, 0, 2);
v_sym = 8 / 3;
printf('quadgk(x^2,[0,2]) = %.12f, valor simbolico 8/3, |dif| = %.3e\\n',
       v_num, abs(v_num - v_sym));

figure('visible', 'off');
plot(x, f(x), 'k:', 'LineWidth', 1.0); hold on;
plot(x, yn, 'r--', 'LineWidth', 1.2);
plot(x, y, 'b-', 'LineWidth', 2.2);
xlabel('x'); ylabel('valor');
title('f(x) = sin(x^2)\\cdotexp(x): funcion y derivada (alkahest vs Octave)');
legend('f(x)', 'derivada central (Octave)', 'derivada simbolica (alkahest)',
       'location', 'northwest');
grid on;
print(gcf, '{args.png}', '-dpng', '-r140');
printf('PNG_ESCRITO %s\\n', '{args.png}');
"""
        out = wire.call_tool(
            "octave_run",
            {"code": octave_code, "timeout": 120, "mode": "execute"},
        )
        stdout = out if isinstance(out, str) else json.dumps(
            out, ensure_ascii=False)
        print(stdout.strip()[:1200])

        # --- 3) veredicto ---
        lines = [ln for ln in str(stdout).splitlines()]
        err_line = next((ln for ln in lines if "diferencias centrales" in ln), "")
        ok_chain = (
            "PNG_ESCRITO" in str(stdout)
            and err_line
            and float(err_line.split("= ")[-1]) < 1e-6
        )
        print("\nCADENA COMPLETA: alkahest (CAS) -> Octave (verificación "
              "numérica + PNG)" if ok_chain
              else "\nCADENA FALLÓ: revisar salida de Octave")
        return 0 if ok_chain else 1
    finally:
        wire.close()


if __name__ == "__main__":
    sys.exit(main())
