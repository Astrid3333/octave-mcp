"""Cross-check multi-motor: la misma batería de problemas en 4 CAS.

Ejemplo de verificación cruzada: cada problema se resuelve en los
motores que lo soportan (maxima, sagebrush, lispium, cadabra2) y el
resultado de cada uno se compara contra un oráculo sympy calculado en
vivo. Incluye PINS de quirks conocidos (noun-forms de maxima que
salen con ok=True, degradación a float de lispium en enteros grandes,
eco de formas sin evaluar).

Uso:  .venv/bin/python examples/multi_cas_crosscheck.py
"""

import json
import re
import subprocess
import sys

import sympy

SERVER = "/home/astrid/octave-mcp/server.py"
PYTHON = "/home/astrid/octave-mcp/.venv/bin/python"

x, n, k = sympy.symbols("x n k")


class Wire:
    """Cliente MCP stdio minimo (initialize + tools/call)."""

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
                raise RuntimeError("server.py cerro stdout")
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
            raise RuntimeError("RPC error: %s" % resp["error"])
        for item in resp["result"].get("content", []):
            if item.get("type") == "text":
                try:
                    return json.loads(item["text"])
                except json.JSONDecodeError:
                    return item["text"]
        return resp["result"]

    def close(self):
        self.proc.kill()


# ---------------------------------------------------------------- helpers

def _ok(r, engine):
    if not r.get("ok"):
        raise RuntimeError("%s fallo: %s" % (engine, r.get("error") or r))
    return r


def mx(w, expr):
    r = w.call_tool("maxima_eval_tool", {"mode": "compute",
                                         "operation": "eval", "expr": expr})
    return _ok(r, "maxima").get("result") or ""


def mx_raw(w, expr):
    return w.call_tool("maxima_eval_tool", {"mode": "compute",
                                            "operation": "eval", "expr": expr})


def sg(w, code):
    r = w.call_tool("sagebrush_math_tool", {"mode": "compute",
                                            "operation": "sage",
                                            "code": code})
    return (_ok(r, "sagebrush").get("stdout") or "").strip()


def lp(w, code):
    r = w.call_tool("lispium_math_tool", {"mode": "compute",
                                          "operation": "eval", "code": code})
    out = (_ok(r, "lispium").get("result") or "").splitlines()
    return out[-1] if out else ""


def lp_raw(w, code):
    return w.call_tool("lispium_math_tool", {"mode": "compute",
                                             "operation": "eval",
                                             "code": code})


def cd(w, code):
    r = w.call_tool("cadabra2_math_tool", {"mode": "compute",
                                           "operation": "eval",
                                           "code": code})
    return (_ok(r, "cadabra2").get("stdout") or "").strip()


# ------------------------------------------------- dialect -> sympy

def mx_sympy(text):
    t = text.replace("%e", "E").replace("inf", "oo").replace("^", "**")
    return sympy.sympify(t)


def sg_sympy(text):
    t = text.replace("^", "**")
    t = re.sub(r"(?<![A-Za-z0-9_])e\*\*", "E**", t)
    if t.strip() == "e":
        return sympy.E
    return sympy.sympify(t)


_FUNCS = {"sin": sympy.sin, "cos": sympy.cos, "exp": sympy.exp,
          "log": sympy.log, "sqrt": sympy.sqrt, "gcd": sympy.gcd}


def _atom(tok):
    if re.fullmatch(r"-?\d+", tok):
        return sympy.Integer(int(tok))
    if re.fullmatch(r"-?\d*\.\d+(e[+-]?\d+)?", tok, re.I):
        return sympy.Float(tok)
    return sympy.Symbol(tok)


def _to_sympy(node):
    if isinstance(node, str):
        return _atom(node)
    head, args = node[0], node[1:]
    vals = [_to_sympy(a) for a in args]
    if head == "+":
        return sympy.Add(*vals)
    if head == "-" and len(vals) == 1:
        return -vals[0]
    if head == "-":
        return sympy.Add(vals[0], *[-v for v in vals[1:]])
    if head == "*":
        return sympy.Mul(*vals)
    if head == "/":
        return vals[0] / vals[1]
    if head == "^":
        return vals[0] ** vals[1]
    if head in _FUNCS:
        return _FUNCS[head](*vals)
    raise ValueError("forma lisp desconocida: %r" % (head,))


def lp_sympy(text):
    tokens = re.findall(r"\(|\)|[^\s()]+", text)
    pos = 0

    def parse():
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            items = []
            while tokens[pos] != ")":
                items.append(parse())
            pos += 1
            return items
        return tok

    return _to_sympy(parse())


def same_symbolic(got, expected):
    return sympy.simplify(sympy.sympify(got) - sympy.sympify(expected)) == 0


CHECKS = []


def check(label, ok, detail):
    CHECKS.append(bool(ok))
    print("    %s %s: %s" % ("OK  " if ok else "FAIL", label, detail))
    return ok


# ------------------------------------------------------------- battery

def main():
    print("Cross-check multi-motor (maxima/sagebrush/lispium/cadabra2 "
          "vs sympy)")
    w = Wire()
    try:
        # --- 1. derivada de un producto: 3 motores + sympy
        oracle = sympy.diff(sympy.sin(x ** 2) * sympy.exp(x), x)
        v = mx_sympy(mx(w, "diff(sin(x^2)*exp(x),x)"))
        check("deriv-maxima", same_symbolic(v, oracle),
              "d/dx sin(x^2)e^x = %s" % v)
        v = sg_sympy(sg(w, "x = var('x')\n"
                           "print(diff(sin(x^2)*exp(x), x))"))
        check("deriv-sagebrush", same_symbolic(v, oracle),
              "d/dx sin(x^2)e^x = %s" % v)
        v = lp_sympy(lp(w, "(diff (* (sin (* x x)) (exp x)) x)"))
        check("deriv-lispium", same_symbolic(v, oracle),
              "d/dx sin(x^2)e^x = %s" % v)

        # --- 2. integral definida: maxima + sagebrush
        oracle = sympy.integrate(x ** 2 * sympy.exp(-x), (x, 0, sympy.oo))
        v = mx_sympy(mx(w, "integrate(x^2*exp(-x),x,0,inf)"))
        check("int-maxima", same_symbolic(v, oracle),
              "int_0^inf x^2 e^-x = %s" % v)
        v = sg_sympy(sg(w, "x = var('x')\n"
                           "print(integrate(x^2*exp(-x), (x, 0, oo)))"))
        check("int-sagebrush", same_symbolic(v, oracle),
              "int_0^inf x^2 e^-x = %s" % v)

        # --- 3. factorizacion x^4-1
        oracle = sympy.expand(sympy.factor(x ** 4 - 1))
        v = mx_sympy(mx(w, "factor(x^4-1)"))
        check("factor-maxima", sympy.expand(v - oracle) == 0,
              "factor(x^4-1) = %s" % v)
        v = sg_sympy(sg(w, "x = var('x')\nprint(factor(x^4-1))"))
        check("factor-sagebrush", sympy.expand(v - oracle) == 0,
              "factor(x^4-1) = %s" % v)

        # --- 4. sistema lineal x+y=3, x-y=1 -> (2,1)
        oracle = dict(zip(sympy.solve([x + sympy.Symbol("y") - 3,
                                       x - sympy.Symbol("y") - 1],
                                      [x, sympy.Symbol("y")]),
                          [sympy.Integer(2), sympy.Integer(1)]))
        raw = mx(w, "solve([x+y=3,x-y=1],[x,y])")
        got = {sympy.Symbol(a): sympy.Integer(int(b))
               for a, b in re.findall(r"(\w+) = (-?\d+)", raw)}
        check("sistema-maxima", got == oracle, "x=2, y=1 -> %s" % raw)
        raw = sg(w, "x, y = var('x y')\n"
                    "print(solve([x+y==3, x-y==1], [x, y]))")
        got = {sympy.Symbol(a): sympy.Integer(int(b))
               for a, b in re.findall(r"(\w+) == (-?\d+)", raw)}
        check("sistema-sagebrush", got == oracle, "x=2, y=1 -> %s" % raw)

        # --- 5. gcd: 3 motores
        oracle = sympy.gcd(462, 1071)
        v = sympy.Integer(int(mx(w, "gcd(462,1071)")))
        check("gcd-maxima", v == oracle, "gcd(462,1071) = %d" % v)
        v = sympy.Integer(int(sg(w, "print(gcd(462, 1071))")))
        check("gcd-sagebrush", v == oracle, "gcd(462,1071) = %d" % v)
        v = sympy.Integer(int(lp(w, "(gcd 462 1071)")))
        check("gcd-lispium", v == oracle, "gcd(462,1071) = %d" % v)

        # --- 6. limit (1+1/n)^n -> e
        oracle = sympy.limit((1 + 1 / n) ** n, n, sympy.oo)
        v = mx_sympy(mx(w, "limit((1+1/n)^n,n,inf)"))
        check("limit-maxima", same_symbolic(v, oracle),
              "limit = %s" % v)
        v = sg_sympy(sg(w, "n = var('n')\nprint(limit((1+1/n)^n, n, oo))"))
        check("limit-sagebrush", same_symbolic(v, oracle),
              "limit = %s" % v)

        # --- 7. primalidad de 2^61-1 (Mersenne): maxima + sagebrush
        oracle = sympy.isprime(2 ** 61 - 1)
        v = mx(w, "primep(2^61-1)").strip()
        check("primo-maxima", (v == "true") == oracle,
              "primep(2^61-1) = %s (oracle %s)" % (v, oracle))
        v = sg(w, "print(is_prime(2^61-1))")
        check("primo-sagebrush", (v == "True") == oracle,
              "is_prime(2^61-1) = %s (oracle %s)" % (v, oracle))

        # --- 8. entero grande exacto: 3 motores exactos
        oracle = 2 ** 61 - 1
        v = mx_sympy(mx(w, "2^61-1"))
        check("bigint-maxima", v == oracle, "2^61-1 = %d" % v)
        v = sympy.Integer(int(sg(w, "print(2^61-1)")))
        check("bigint-sagebrush", v == oracle, "2^61-1 = %d" % v)
        v = sympy.Integer(int(cd(w, "print(str(evaluate("
                                     "Ex('2**61 - 1'))))")))
        check("bigint-cadabra2", v == oracle, "2^61-1 = %d" % v)

        # --- 9. identidad polinomica (x+1)^2-x^2-2x-1 = 0: 3 motores
        oracle = sympy.Integer(0)
        v = mx_sympy(mx(w, "radcan((x+1)^2-x^2-2*x-1)"))
        check("ident-maxima", same_symbolic(v, oracle), "radcan = %s" % v)
        v = sg_sympy(sg(w, "x = var('x')\n"
                           "print(((x+1)^2-x^2-2*x-1).full_simplify())"))
        check("ident-sagebrush", same_symbolic(v, oracle),
              "full_simplify = %s" % v)
        v = sympy.sympify(cd(w, "print(str(evaluate(Ex('(x+1)**2 - x**2"
                                " - 2*x - 1'))))"))
        check("ident-cadabra2", same_symbolic(v, oracle),
              "evaluate = %s" % v)

        # --- 10. determinante 2x2
        oracle = sympy.Matrix([[1, 2], [3, 4]]).det()
        v = sympy.Integer(int(mx(w, "determinant(matrix([1,2],[3,4]))")))
        check("det-maxima", v == oracle, "det = %d" % v)
        v = sympy.Integer(int(sg(w, "print(matrix(ZZ, [[1,2],[3,4]]"
                                    ").det())")))
        check("det-sagebrush", v == oracle, "det = %d" % v)

        # --- 11. totient euler_phi(100) = 40
        oracle = sympy.totient(100)
        v = sympy.Integer(int(sg(w, "print(euler_phi(100))")))
        check("totient-sagebrush", v == oracle, "euler_phi(100) = %d" % v)

        # --- 12. factorial 20 exacto: maxima + sagebrush
        oracle = sympy.Integer(sympy.factorial(20))
        v = sympy.Integer(int(mx(w, "factorial(20)")))
        check("fact-maxima", v == oracle, "20! = %d" % v)
        v = sympy.Integer(int(sg(w, "print(factorial(20))")))
        check("fact-sagebrush", v == oracle, "20! = %d" % v)

        # --- 13. serie de Basel sum 1/k^2 = pi^2/6
        oracle = sympy.summation(1 / k ** 2, (k, 1, sympy.oo))
        v = sg_sympy(sg(w, "k = var('k')\n"
                           "print(symbolic_sum(1/k^2, k, 1, oo))"))
        check("basel-sagebrush", same_symbolic(v, oracle),
              "sum = %s" % v)

        # ---------------- PINS: quirks documentados (no son acuerdos)

        r = mx_raw(w, "eulerphi(100)")
        pin = r.get("ok") and (r.get("result") or "").strip() == "eulerphi(100)"
        check("pin-maxima-noun-eulerphi", pin,
              "ok=True con forma noun sin evaluar "
              "('%s'): ok solo NO es exito" % (r.get("result") or ""))

        r = mx_raw(w, "sum(1/k^2,k,1,inf)")
        pin = r.get("ok") and (r.get("result") or "").startswith("'sum")
        check("pin-maxima-noun-sum", pin,
              "ok=True con 'sum(...) sin evaluar: revisar siempre "
              "el valor")

        r = lp_raw(w, "(^ 2 61)")
        last = (r.get("result") or "").splitlines()[-1]
        pin = r.get("ok") and "e" in last
        check("pin-lispium-float-bigint", pin,
              "(^ 2 61) -> %s: degrada enteros grandes a float" % last)

        r = lp_raw(w, "(factorial 20)")
        last = (r.get("result") or "").splitlines()[-1]
        pin = r.get("ok") and "e" in last
        check("pin-lispium-float-factorial", pin,
              "(factorial 20) -> %s: 20! exacto en otros motores" % last)

        r = lp_raw(w, "(simplify (+ (^ (+ x 1) 2) (* -1 (^ x 2))"
                      " (* -2 x) -1))")
        last = (r.get("result") or "").splitlines()[-1].strip()
        pin = r.get("ok") and last != "0" and "(^" in last
        check("pin-lispium-eco-simplify", pin,
              "simplify devuelve %s (potencias sin reducir): no "
              "evalua identidades simbolicas" % last)

        r = sg(w, "var('qq ww')\nprint('ww' in globals())")
        pin = r.strip() == "False"
        check("pin-sage-var-no-inyecta", pin,
              "var('qq ww') no inyecta en globals (%r): usar "
              "x, y = var('x y')" % r.strip())
    finally:
        w.close()

    n_ok = sum(CHECKS)
    print("    ----")
    print("    %d/%d PASS" % (n_ok, len(CHECKS)))
    return 0 if n_ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
