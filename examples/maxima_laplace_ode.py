#!/usr/bin/env python3
"""Ejercicio donde maxima_eval_tool es necesaria: Laplace -> ODE.

Oscilador amortiguado forzado:
    y''(t) + 0.4 y'(t) + y(t) = sin(2 t),   y(0) = y'(0) = 0

Cadena sobre el wire MCP real:
1. octave_math_tool (transforms/laplace) FALLA: el paquete symbolic de
   Octave no esta instalado (syms undefined). No existe inversa de
   Laplace en el runtime de Octave.
2. maxima_eval_tool (batch): laplace(ODE) -> ICs -> solve -> ilt ->
   forma cerrada + residual ratsimp == 0 + ICs verificadas + muestras
   float en t = 0:0.05:5.
3. octave_run: ode45 numérico independiente en la misma malla.
4. Comparacion max|Maxima - ode45| y PNG superpuesto.

Uso:
    .venv/bin/python examples/maxima_laplace_ode.py [--png RUTA]
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SERVER = "/home/astrid/octave-mcp/server.py"
PYTHON = "/home/astrid/octave-mcp/.venv/bin/python"
DEFAULT_PNG = "/tmp/opencode/maxima_laplace_ode.png"
WORKSPACE = Path("/home/astrid/Documents/OpenScience/sessions/2026-10-19-0153")


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


def parse_marker_zones(stdout):
    """Extrae zonas entre print('<<R>>') ... print('<<E>>') del eco de batch.

    Mismo contrato que _parse_markers de maxima_eval_tool: la zona va
    del eco "<<R>>" hasta el eco de print("<<E>>"); se descarta la
    primera línea (eco del disp) y el trailing done/vacío.
    """
    lines = stdout.splitlines()
    zones = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == '"<<R>>"':
            j = i + 1
            while j < len(lines) and 'print("<<E>>")' not in lines[j]:
                j += 1
            zone = lines[i + 1:j]
            if zone:
                zone = zone[1:]  # eco del disp
            while zone and zone[-1].strip() in ("", "done"):
                zone.pop()
            zones.append("\n".join(zone))
            i = j + 1
        else:
            i += 1
    return zones


def parse_floats(text):
    return [float(x) for x in re.findall(
        r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", text)]


MAXIMA_CODE = """display2d:false;
eq: 'diff(y(t),t,2) + 0.4*'diff(y(t),t) + y(t) = sin(2*t)$
Leq: laplace(eq, t, s)$
S1: subst([y(0)=0, at('diff(y(t),t,1), t=0)=0], Leq)$
Y: solve(S1, 'laplace(y(t),t,s))$
Ys: rhs(first(Y))$
yf: ilt(Ys, s, t)$
print("<<R>>"); disp(yf); print("<<E>>");
res: ratsimp(diff(yf,t,2) + (2/5)*diff(yf,t) + yf - sin(2*t));
print("<<R>>"); disp(res); print("<<E>>");
print("<<R>>"); disp([subst(t=0, yf), subst(t=0, diff(yf,t))]); print("<<E>>");
print("<<R>>"); disp(makelist(float(subst(t=T, yf)), T, 0, 5, 0.05)); print("<<E>>");
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--png", default=DEFAULT_PNG)
    args = parser.parse_args()

    wire = Wire()
    try:
        # --- 1) evidencia: Octave NO puede hacer Laplace simbolico ---
        print("[1] octave_math_tool transforms/laplace "
              "(prueba de necesidad)")
        gap = wire.call_tool(
            "octave_math_tool",
            {"mode": "transforms",
             "params": {"op": "laplace", "expr": "exp(-2*t)*sin(3*t)"}},
        )
        gap_txt = json.dumps(gap, ensure_ascii=False)
        need = "syms" in gap_txt or "error" in gap.lower()
        print("    FALLA como se esperaba: "
              + ("syms undefined (pkg symbolic ausente)" if need
                 else "sin error visible"))
        print("    -> el runtime de Octave no ofrece Laplace simbolico "
              "ni inversa; maxima_eval_tool cubre el hueco")

        # --- 2) cadena Laplace simbolica en Maxima ---
        print("[2] maxima_eval_tool batch: laplace(ODE) -> ICs -> "
              "solve -> ilt")
        batch = wire.call_tool(
            "maxima_eval_tool",
            {"mode": "compute", "operation": "batch",
             "code": MAXIMA_CODE, "timeout": 60},
        )
        stdout = batch["stdout"] if isinstance(batch, dict) else str(batch)
        zones = parse_marker_zones(stdout)
        if len(zones) < 4:
            print(f"    ERROR: se esperaban 4 zonas, hay {len(zones)}")
            print(stdout[:1500])
            return 1
        closed = zones[0]
        residual = zones[1].strip()
        ics = parse_floats(zones[2])
        y_maxima = parse_floats(zones[3])
        print(f"    forma cerrada y(t) = {closed[:90]}...")
        print(f"    residual ratsimp(diff(yf,2)+0.4*diff(yf)+yf-sin(2t)) "
              f"= {residual}")
        print(f"    ICs [y(0), y'(0)] = {ics}")
        ok_sym = (residual == "0" and len(ics) == 2
                  and all(abs(v) < 1e-12 for v in ics)
                  and len(y_maxima) == 101)
        print(f"    muestras float: {len(y_maxima)} puntos en "
              "t=0:0.05:5  -> " + ("OK" if ok_sym else "INCOMPLETO"))

        # --- 3) ode45 independiente en Octave ---
        print("[3] octave_run ode45: solucion numerica referee")
        octave_code = """
grid = 0:0.05:5;
odefun = @(t, y) [y(2); sin(2*t) - 0.4*y(2) - y(1)];
opt = odeset('RelTol', 1e-9, 'AbsTol', 1e-11);
[t, Y] = ode45(odefun, [0, 5], [0; 0], opt);
yi = interp1(t, Y(:, 1), grid, 'spline');
printf('ODE45_VALS ');
printf('%.17g ', yi);
printf('\\n');
printf('ODE45_MAXERR %.3e\\n', max(abs([yi(1), diff(yi)])));
"""
        ode = wire.call_tool(
            "octave_run",
            {"code": octave_code, "timeout": 120, "mode": "execute"},
        )
        ode_txt = ode if isinstance(ode, str) else json.dumps(
            ode, ensure_ascii=False)
        vals_line = next(
            (ln for ln in ode_txt.splitlines() if "ODE45_VALS" in ln), "")
        y_octave = parse_floats(vals_line.split("ODE45_VALS", 1)[-1])
        print(f"    ode45 devuelve {len(y_octave)} valores en la malla")

        if len(y_octave) != len(y_maxima):
            print("    ERROR: longitudes distintas "
                  f"({len(y_maxima)} vs {len(y_octave)})")
            return 1

        # --- 4) comparacion simbolico vs numerico ---
        err = max(abs(a - b) for a, b in zip(y_maxima, y_octave))
        print(f"[4] max|y_Maxima - y_ode45| sobre 101 puntos = {err:.3e}")

        # --- 5) PNG superpuesto ---
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        t_axis = [i * 0.05 for i in range(len(y_maxima))]
        fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=140)
        ax.plot(t_axis, y_octave, "b-", lw=2.0,
                label="ode45 (Octave, numerico)")
        ax.plot(t_axis[::4], y_maxima[::4], "ro", ms=5,
                label="ilt (Maxima, cerrado, c/5 pts)")
        ax.set_xlabel("t [s]")
        ax.set_ylabel("y(t)")
        ax.set_title("y''+0.4y'+y=sin(2t): Maxima ilt vs Octave ode45 "
                     f"(max err {err:.1e})")
        ax.grid(True, alpha=0.35)
        ax.legend(loc="upper right")
        fig.tight_layout()
        fig.savefig(args.png)
        plt.close(fig)
        ws_png = WORKSPACE / "maxima_laplace_ode.png"
        shutil.copy(args.png, ws_png)
        print(f"    PNG: {args.png} (copia en workspace: {ws_png})")

        # --- veredicto ---
        ok = ok_sym and err < 1e-6
        print("\nEJERCICIO COMPLETO: Maxima (laplace/ilt simbolico) -> "
              "Octave (ode45 numerico) coinciden" if ok
              else "\nEJERCICIO FALLO: revisar residuales o error")
        print(f"  residual=0: {residual == '0'} | ICs: {ics} | "
              f"max err = {err:.3e}")
        return 0 if ok else 1
    finally:
        wire.close()


if __name__ == "__main__":
    sys.exit(main())
