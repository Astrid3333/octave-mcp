"""Cross-check multi-motor: la misma batería de problemas en 5 CAS.

Ejemplo de verificación cruzada: cada problema se resuelve en los
motores que lo soportan (maxima, sagebrush, lispium, cadabra2,
alkahest) y el resultado de cada uno se compara contra un oráculo
sympy calculado en vivo. Incluye sección ODE/Laplace (ode2/ic1/laplace
de maxima vs dsolve/laplace_transform de sympy) y PINS de quirks
conocidos (noun-forms de maxima que salen con ok=True, degradación a
float de lispium en enteros grandes, eco de formas sin evaluar,
desolve del shim sagebrush, forma de término Basel en alkahest).

Uso:  .venv/bin/python examples/multi_cas_crosscheck.py
"""

import json
import re
import subprocess
import sys

import sympy

SERVER = "/home/astrid/octave-mcp/server.py"
PYTHON = "/home/astrid/octave-mcp/.venv/bin/python"

x, n, k, t, s, a, C1 = sympy.symbols("x n k t s a C1")


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


def ak(w, **args):
    r = w.call_tool("alkahest_cas_tool", {"mode": "compute", **args})
    return _ok(r, "alkahest")


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
    print("Cross-check multi-motor (maxima/sagebrush/lispium/cadabra2/"
          "alkahest vs sympy)")
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

        # --- 14. alkahest: 5to motor (value en dialecto con ^)
        oracle = sympy.diff(sympy.sin(x ** 2) * sympy.exp(x), x)
        v = mx_sympy(ak(w, operation="diff", expr="sin(x^2)*exp(x)",
                        var="x").get("value") or "")
        check("deriv-alkahest", same_symbolic(v, oracle),
              "d/dx sin(x^2)e^x = %s" % v)

        oracle = sympy.integrate(x ** 2 * sympy.exp(-x), (x, 0, sympy.oo))
        v = mx_sympy(ak(w, operation="integrate", expr="x^2*exp(-x)",
                        var="x", bounds=[0, "oo"]).get("value") or "")
        check("int-alkahest", same_symbolic(v, oracle),
              "int_0^inf x^2 e^-x = %s" % v)

        oracle = sympy.limit((1 + 1 / n) ** n, n, sympy.oo)
        v = mx_sympy(ak(w, operation="limit", expr="(1+1/n)^n", var="n",
                        point="oo").get("value") or "")
        check("limit-alkahest", same_symbolic(v, oracle),
              "limit = %s" % v)

        oracle = sympy.summation(1 / k ** 2, (k, 1, sympy.oo))
        v = mx_sympy(ak(w, operation="sum_definite", expr="k^(-2)", var="k",
                        bounds=[1, "oo"]).get("value") or "")
        check("basel-alkahest", same_symbolic(v, oracle),
              "sum k^-2 = %s" % v)

        oracle = dict(zip(sympy.solve([x + sympy.Symbol("y") - 3,
                                       x - sympy.Symbol("y") - 1],
                                      [x, sympy.Symbol("y")]),
                          [sympy.Integer(2), sympy.Integer(1)]))
        sols = ak(w, operation="solve",
                  equations=["x+y-3", "x-y-1"], vars=["x", "y"]).get(
                      "solutions") or []
        got = {sympy.Symbol(name): sympy.Integer(int(val))
               for d in sols for name, val in d.items()}
        check("sistema-alkahest", got == oracle, "x=2, y=1 -> %s" % sols)

        oracle = sympy.Matrix([[1, 2], [3, 4]]).det()
        v = sympy.Integer(int(ak(w, operation="matrix",
                                 matrix=[[1, 2], [3, 4]],
                                 action="det").get("det")))
        check("det-alkahest", v == oracle, "det = %d" % v)

        oracle = sympy.totient(100)
        v = sympy.Integer(int(ak(w, operation="totient", n=100).get(
            "totient")))
        check("totient-alkahest", v == oracle, "totient(100) = %d" % v)

        oracle = sympy.isprime(2 ** 61 - 1)
        v = bool(ak(w, operation="isprime", n=2 ** 61 - 1).get("isprime"))
        check("primo-alkahest", v == oracle,
              "isprime(2^61-1) = %s (oracle %s)" % (v, oracle))

        oracle = sympy.factorint(462)
        v = {int(p): int(e) for p, e in
             (ak(w, operation="factorint", n=462).get("factors") or {}).items()}
        check("factorint-alkahest", v == oracle,
              "factorint(462) = %s" % v)

        # --- 15. ODE y Laplace: maxima ode2/ic1/laplace vs sympy
        def mx_rhs(expr):
            out = mx(w, expr)
            rhs = out.split("=", 1)[1].strip()
            return sympy.sympify(rhs.replace("%c", "C1")
                                 .replace("%e", "E").replace("^", "**"))

        yv = sympy.Function("y")
        oracle = sympy.dsolve(sympy.diff(yv(x), x) + yv(x), yv(x)).rhs
        v = mx_rhs("ode2('diff(y,x)+y=0,y,x)")
        residual = sympy.simplify(sympy.diff(v, x) + v)
        check("ode2-maxima", residual == 0,
              "y'+y=0 -> %s (residuo %s; oráculo %s)" % (v, residual, oracle))

        v = mx_rhs("ic1(ode2('diff(y,x)+y=0,y,x),x=0,y=1)")
        residual = sympy.simplify(sympy.diff(v, x) + v)
        check("ode2-ic-maxima", residual == 0 and v.subs(x, 0) == 1,
              "y(0)=1 -> %s (residuo %s, y(0)=%s)"
              % (v, residual, v.subs(x, 0)))

        v = mx_rhs("ode2('diff(y,x)-2*y=exp(x),y,x)")
        residual = sympy.simplify(sympy.diff(v, x) - 2 * v - sympy.exp(x))
        check("ode2-forzada-maxima", residual == 0,
              "y'-2y=e^x -> %s (residuo %s)" % (v, residual))

        oracle = sympy.laplace_transform(sympy.sin(t), t, s)[0]
        v = mx_sympy(mx(w, "laplace(sin(t),t,s)"))
        check("laplace-sin-maxima", same_symbolic(v, oracle),
              "L{sin t} = %s" % v)

        oracle = sympy.laplace_transform(t * sympy.exp(a * t), t, s)[0]
        v = mx_sympy(mx(w, "laplace(exp(a*t)*t,t,s)"))
        check("laplace-te-at-maxima", same_symbolic(v, oracle),
              "L{t e^{at}} = %s" % v)

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

        r = w.call_tool("alkahest_cas_tool",
                        {"mode": "compute", "operation": "sum_definite",
                         "expr": "1/k^2", "var": "k", "bounds": [1, "oo"]})
        pin = isinstance(r, str) and r.startswith("PySumError")
        check("pin-alkahest-basel-forma", pin,
              "sum 1/k^2 -> PySumError E-SUM-002 (texto plano, sin ok): "
              "Basel exige la forma k^(-2)")

        r = w.call_tool("sagebrush_math_tool",
                        {"mode": "compute", "operation": "sage",
                         "code": "t = var('t')\ny = function('y', t)\n"
                                 "print(desolve(diff(y,t)+y, y))"})
        pin = (isinstance(r, dict) and r.get("ok") is False
               and "TypeError" in (r.get("error") or ""))
        check("pin-sage-desolve-roto", pin,
              "desolve del shim falla con TypeError en aritmética de "
              "function: no usable para ODE")

        r = mx_raw(w, "ode2(diff(y,x)+y=0,y,x)")
        pin = r.get("ok") and (r.get("result") or "").strip() == "false"
        check("pin-maxima-ode2-false", pin,
              "ode2 sin ' en diff -> ok=True con 'false': la derivada "
              "debe ir cotada ('diff(...)), y ok True no es exito")
    finally:
        w.close()

    n_ok = sum(CHECKS)
    print("    ----")
    print("    %d/%d PASS" % (n_ok, len(CHECKS)))
    return 0 if n_ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
