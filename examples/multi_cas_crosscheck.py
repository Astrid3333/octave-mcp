"""Cross-check multi-motor: la misma batería de problemas en 5 CAS.

Ejemplo de verificación cruzada: cada problema se resuelve en los
motores que lo soportan (maxima, sagebrush, lispium, cadabra2,
alkahest) y el resultado de cada uno se compara contra un oráculo
sympy calculado en vivo. Incluye sección ODE/Laplace (ode2/ic1/ic2/
laplace/ilt de maxima, desolve + desolve_rk4 de sagebrush, router con
hints laplace/ode — todo vs dsolve/laplace_transform/
inverse_laplace_transform o residuo numérico) y PINS de quirks
conocidos (noun-forms de maxima que salen con ok=True, orden de ilt,
degradación a float de lispium en enteros grandes, eco de formas sin
evaluar, function sin aplicar en sagebrush, forma de término Basel en
alkahest, quoting de ode2) y FUZZING DIFERENCIAL con semilla fija:
expresiones aleatorias (enteros, x, + - ^, sin/cos) evaluadas en
maxima/sagebrush/lispium — valor y derivada en un punto de muestra —
contra el oráculo sympy con tolerancia numérica. Semilla y rondas
controlables con FUZZ_SEED / FUZZ_ROUNDS (entorno).

Uso:  .venv/bin/python examples/multi_cas_crosscheck.py
"""

import ast
import json
import os
import random
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


# ------------------------------------------------- fuzzing diferencial

FUZZ_SEED = int(os.environ.get("FUZZ_SEED", "20261024"))
FUZZ_ROUNDS = int(os.environ.get("FUZZ_ROUNDS", "12"))
FUZZ_TOL_ABS = 1e-6
FUZZ_TOL_REL = 1e-8

_FZ_GRID = ([sympy.Integer(v) for v in (-2, -1, 1, 2)]
            + [sympy.Rational(*p) for p in
               ((1, 2), (3, 4), (1, 3), (2, 3), (-1, 2), (-3, 4))])


def _fz_gen(rng, depth):
    """Expresión aleatoria acotada: sin división ni exp (magnitudes seguras)."""
    if depth <= 0:
        return x if rng.random() < 0.5 else sympy.Integer(rng.randint(1, 9))
    op = rng.choice(["+", "-", "*", "pow", "sin", "cos"])
    if op == "pow":
        base = x if rng.random() < 0.6 else sympy.Integer(rng.randint(2, 9))
        return base ** rng.randint(1, 3)
    if op in ("sin", "cos"):
        f = sympy.sin if op == "sin" else sympy.cos
        return f(_fz_gen(rng, depth - 1))
    a = _fz_gen(rng, depth - 1)
    b = _fz_gen(rng, depth - 1)
    return a + b if op == "+" else a - b if op == "-" else a * b


def _fz_infix(e):
    """Dialecto maxima/sage: ^ para potencias."""
    return str(e).replace("**", "^")


def _fz_lisp(e):
    """Dialecto lispium (s-express) de una expresión sympy."""
    if e.is_Integer:
        return str(int(e))
    if e == x:
        return "x"
    if isinstance(e, sympy.Add):
        return "(+ %s)" % " ".join(_fz_lisp(a) for a in e.args)
    if isinstance(e, sympy.Mul):
        return "(* %s)" % " ".join(_fz_lisp(a) for a in e.args)
    if isinstance(e, sympy.Pow):
        return "(^ %s %s)" % (_fz_lisp(e.args[0]), _fz_lisp(e.args[1]))
    if isinstance(e, sympy.sin):
        return "(sin %s)" % _fz_lisp(e.args[0])
    if isinstance(e, sympy.cos):
        return "(cos %s)" % _fz_lisp(e.args[0])
    raise ValueError("fuzz: forma desconocida %r" % (e,))


def _fz_close(got, orcl):
    return abs(got - orcl) <= FUZZ_TOL_ABS + FUZZ_TOL_REL * abs(orcl)


def _fz_detail(got_v, v_or, got_d, d_or):
    return ("f(x0)=%.12g (oráculo %.12g), f'(x0)=%.12g (oráculo %.12g)"
            % (got_v, v_or, got_d, d_or))


def fuzz(w):
    """Rondas deterministas (semilla fija) valor+derivada en 3 motores."""
    rng = random.Random(FUZZ_SEED)
    print("  fuzzing diferencial (semilla=%d, rondas=%d)"
          % (FUZZ_SEED, FUZZ_ROUNDS))
    for i in range(FUZZ_ROUNDS):
        expr = _fz_gen(rng, 1 + i % 3)
        x0 = rng.choice(_FZ_GRID)
        x0f = float(x0)
        dexpr = sympy.diff(expr, x)
        v_or = float(expr.subs(x, x0))
        d_or = float(dexpr.subs(x, x0))
        inf = _fz_infix(expr)
        lis = _fz_lisp(expr)

        # maxima: valor y derivada en dos llamadas (dialecto ^)
        try:
            got_v = float(mx(w, "float(subst(x=%s, %s))" % (x0, inf)))
            got_d = float(mx(w, "float(subst(x=%s, diff(%s, x)))"
                                  % (x0, inf)))
            ok = _fz_close(got_v, v_or) and _fz_close(got_d, d_or)
            det = _fz_detail(got_v, v_or, got_d, d_or)
        except Exception as exc:
            ok, det = False, "excepción: %s" % exc
        check("fuzz-maxima-%02d" % i, ok, det)

        # sagebrush: ambas salidas en un solo print
        try:
            out = sg(w, "x = var('x')\nprint(float((SR(%s)).subs(x==%s)), "
                        "float((diff(SR(%s), x)).subs(x==%s)))"
                         % (inf, x0, inf, x0))
            p = out.split()
            got_v, got_d = float(p[0]), float(p[1])
            ok = _fz_close(got_v, v_or) and _fz_close(got_d, d_or)
            det = _fz_detail(got_v, v_or, got_d, d_or)
        except Exception as exc:
            ok, det = False, "excepción: %s" % exc
        check("fuzz-sagebrush-%02d" % i, ok, det)

        # lispium: valor con let numérico; derivada simbólica -> sympy
        try:
            got_v = float(lp(w, "(let ((x %r)) %s)" % (x0f, lis)))
            d_lisp = lp_sympy(lp(w, "(diff %s x)" % lis))
            got_d = float(sympy.sympify(d_lisp).subs(x, x0))
            ok = _fz_close(got_v, v_or) and _fz_close(got_d, d_or)
            det = _fz_detail(got_v, v_or, got_d, d_or)
        except Exception as exc:
            ok, det = False, "excepción: %s" % exc
        check("fuzz-lispium-%02d" % i, ok, det)


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

        # --- 15. ODE y Laplace: maxima ode2/ic1/ic2/laplace/ilt,
        #     desolve + desolve_rk4 de sagebrush, router con hints
        #     de campo, todos vs sympy (residuo / mismo simbólico).
        def mx_parse(out):
            rhs = out.split("=", 1)[1].strip()
            return sympy.sympify(rhs.replace("%c", "C1")
                                 .replace("%k1", "K1").replace("%k2", "K2")
                                 .replace("%e", "E").replace("^", "**"))

        def mx_rhs(expr):
            return mx_parse(mx(w, expr))

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

        # ODE 2º orden: ic1 SOLO admite (soln, x=0, y=0); para la
        # condición sobre la derivada va ic2.
        v = mx_rhs("ode2('diff(y,x,2)+y=0,y,x)")
        residual = sympy.simplify(sympy.diff(v, x, 2) + v)
        check("ode2-2o-maxima", residual == 0,
              "y''+y=0 -> %s (residuo %s)" % (v, residual))

        v = mx_rhs("ic2(ode2('diff(y,x,2)+y=0,y,x),"
                   "x=0,y=1,'diff(y,x)=0)")
        residual = sympy.simplify(sympy.diff(v, x, 2) + v)
        check("ode2-2o-ic-maxima",
              residual == 0 and v.subs(x, 0) == 1
              and sympy.diff(v, x).subs(x, 0) == 0,
              "y(0)=1, y'(0)=0 -> %s (residuo %s, y(0)=%s, y'(0)=%s)"
              % (v, residual, v.subs(x, 0), sympy.diff(v, x).subs(x, 0)))

        oracle = sympy.laplace_transform(sympy.sin(t), t, s)[0]
        v = mx_sympy(mx(w, "laplace(sin(t),t,s)"))
        check("laplace-sin-maxima", same_symbolic(v, oracle),
              "L{sin t} = %s" % v)

        oracle = sympy.laplace_transform(t * sympy.exp(a * t), t, s)[0]
        v = mx_sympy(mx(w, "laplace(exp(a*t)*t,t,s)"))
        check("laplace-te-at-maxima", same_symbolic(v, oracle),
              "L{t e^{at}} = %s" % v)

        # Laplace inversa: ilt va (f, s, t) — orden contrario a laplace.
        # El oráculo sympy trae Heaviside(t); trabajamos en t>0.
        oracle = sympy.inverse_laplace_transform(
            1 / (s ** 2 + 1), s, t).subs(sympy.Heaviside(t), 1)
        v = mx_sympy(mx(w, "ilt(1/(s^2+1),s,t)"))
        check("ilt-sin-maxima", same_symbolic(v, oracle),
              "L^-1{1/(s^2+1)} = %s" % v)

        oracle = sympy.inverse_laplace_transform(
            s / (s ** 2 + 1), s, t).subs(sympy.Heaviside(t), 1)
        v = mx_sympy(mx(w, "ilt(s/(s^2+1),s,t)"))
        check("ilt-cos-maxima", same_symbolic(v, oracle),
              "L^-1{s/(s^2+1)} = %s" % v)

        # ODEs en sagebrush: desolve funciona con function APLICADA
        # 'y'(t); la solución trae _C/_Kn y se valida por residuo.
        def sg_ode(code):
            return sg_sympy(sg(w, code))

        v = sg_ode("t = var('t')\ny = function('y')(t)\n"
                   "print(desolve(diff(y,t) == -y, y))")
        residual = sympy.simplify(sympy.diff(v, t) + v)
        check("desolve-sagebrush", residual == 0,
              "y'=-y -> %s (residuo %s)" % (v, residual))

        v = sg_ode("t = var('t')\ny = function('y')(t)\n"
                   "print(desolve(diff(y,t) == -y, y, ics=[0, 1]))")
        residual = sympy.simplify(sympy.diff(v, t) + v)
        check("desolve-ic-sagebrush", residual == 0 and v.subs(t, 0) == 1,
              "y(0)=1 -> %s (residuo %s, y(0)=%s)"
              % (v, residual, v.subs(t, 0)))

        v = sg_ode("t = var('t')\ny = function('y')(t)\n"
                   "print(desolve(diff(y,t) - 2*y == exp(t), y))")
        residual = sympy.simplify(sympy.diff(v, t) - 2 * v - sympy.exp(t))
        check("desolve-forzada-sagebrush", residual == 0,
              "y'-2y=e^t -> %s (residuo %s)" % (v, residual))

        v = sg_ode("t = var('t')\ny = function('y')(t)\n"
                   "print(desolve(diff(y,t,2) + y == 0, y))")
        residual = sympy.simplify(sympy.diff(v, t, 2) + v)
        check("desolve-2o-sagebrush", residual == 0,
              "y''+y=0 -> %s (residuo %s)" % (v, residual))

        # RK4 numérico: y' = x+y, y(0)=1 -> y = 2e^x - x - 1.
        # Se compara el camino completo contra la solución analítica.
        raw = sg(w, "y = var('y')\n"
                "print(desolve_rk4(x + y, y, ics=[0, 1],"
                " end_points=1, step=0.5))")
        pts = ast.literal_eval(raw)
        exact = 2 * sympy.exp(sympy.Symbol("xr")) - sympy.Symbol("xr") - 1
        err = max(abs(float(exact.subs("xr", px) - py))
                  for px, py in pts)
        check("rk4-sagebrush", pts[0] == [0, 1] and err < 0.01,
              "y'=x+y, h=0.5 -> %d puntos, err máx %.5f vs 2e^x-x-1"
              % (len(pts), err))

        # Router con hints de campo: laplace/ode -> maxima.
        r = w.call_tool("cas_router_math_tool",
                        {"mode": "compute", "operation": "eval",
                         "field": "laplace", "query": "laplace(sin(t),t,s)"})
        v = mx_sympy((r.get("result") or "").strip()) if r.get("ok") \
            else None
        oracle = sympy.laplace_transform(sympy.sin(t), t, s)[0]
        check("router-laplace",
              r.get("ok") and r.get("engine_used") == "maxima"
              and r.get("routed_by") == "field-laplace"
              and v is not None and same_symbolic(v, oracle),
              "field=laplace -> %s/%s, L{sin t} = %s"
              % (r.get("engine_used"), r.get("routed_by"), v))

        r = w.call_tool("cas_router_math_tool",
                        {"mode": "compute", "operation": "eval",
                         "field": "ode",
                         "query": "ode2('diff(y,x)+y=0,y,x)"})
        v = mx_parse(r.get("result") or "") if r.get("ok") else None
        residual = sympy.simplify(sympy.diff(v, x) + v) if v is not None \
            else None
        check("router-ode",
              r.get("ok") and r.get("engine_used") == "maxima"
              and r.get("routed_by") == "field-ode" and residual == 0,
              "field=ode -> %s/%s, y'+y=0 -> %s (residuo %s)"
              % (r.get("engine_used"), r.get("routed_by"), v, residual))

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
        check("pin-sage-function-aplica", pin,
              "function('y', t) devuelve el closure SIN aplicar "
              "(TypeError al sumar): usar function('y')(t)")

        r = mx_raw(w, "ode2(diff(y,x)+y=0,y,x)")
        pin = r.get("ok") and (r.get("result") or "").strip() == "false"
        check("pin-maxima-ode2-false", pin,
              "ode2 sin ' en diff -> ok=True con 'false': la derivada "
              "debe ir cotada ('diff(...)), y ok True no es exito")

        r = mx_raw(w, "ilt(1/(s^2+1),t,s)")
        pin = r.get("ok") and "delta" in (r.get("result") or "")
        check("pin-maxima-ilt-orden", pin,
              "ilt con el orden de laplace (f,t,s) -> ok=True con "
              "delta(s)/(s^2+1): ilt va (f,s,t), y ok True no es exito")

        # --- 16. fuzzing diferencial con semilla fija (ver FUZZ_SEED)
        fuzz(w)
    finally:
        w.close()

    n_ok = sum(CHECKS)
    print("    ----")
    print("    %d/%d PASS" % (n_ok, len(CHECKS)))
    return 0 if n_ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
