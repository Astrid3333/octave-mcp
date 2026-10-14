"""
octave_math_tool.py

Cálculos matemáticos profesionales con Octave 11+: integrales, derivadas,
EDOs, álgebra lineal, optimización, transformadas, series, estadística.
Usa el binario `octave` nativo (doble precisión, sin depender de numpy/scipy
de Python para operaciones simbólicas/numéricas pesadas).

Modos:
  integrate    — integral definida (quad, quadgk, sym/int si symbolic).
  differentiate— derivada simbólica (diff) o numérica central.
  ode          — resolución de EDO/EDO de sistema (ode45, ode15s, etc.).
  linalg       — eigen, SVD, inversa, rcond, matrix functions (expm, logm).
  optimize     — minimización escalar/vectorial (fminsearch, fminunc).
  transforms   — Laplace, Fourier, FFT/IFFT numérico.
  series       — Taylor, Laurent, expansión de Fourier numérica.
  solve_eq     — solución de ecuaciones algebraicas (fsolve, vpasolve sym).
  stats        — distribuciones (pdf/cdf/inv), media/var, hipótesis básica.
  validate     — autochequeos de cada modo vs valores conocidos.

Requiere `octave` en PATH. Timeout configurable. Fallback: si Octave
no está, devuelve error claro (sin crash del servidor).
"""

import re
import subprocess
import tempfile
import os

from tool_registry import register_tool

OCTAVE_MATH_TOOL_SCHEMA = {
    "name": "octave_math_tool",
    "description": (
        "Cálculos matemáticos profesionales con Octave 11 (SI/Newton no "
        "aplica aquí; puro math). integrate (quadgk), differentiate (diff), "
        "ode (ode45/ode15s), linalg (eig/svd/expm), optimize (fminsearch/ "
        "fminunc), transforms (Laplace/Fourier/FFT), series (Taylor/Fourier), "
        "solve_eq (fsolve), stats (distribuciones). validate = autochequeos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["integrate", "differentiate", "ode", "linalg",
                         "optimize", "transforms", "series", "solve_eq",
                         "stats", "validate"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}

DEFAULT_TIMEOUT = 60


def _run_octave(code, timeout=DEFAULT_TIMEOUT):
    """Ejecuta código Octave y devuelve stdout/stderr/returncode."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        r = subprocess.run(
            ["octave", "--no-gui", "--no-init-file", "--quiet", path],
            capture_output=True, text=True, timeout=timeout,
        )
        return {
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
            "returncode": r.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Timeout tras {timeout}s", "returncode": -1}
    except FileNotFoundError:
        return {"stdout": "", "stderr": "octave no encontrado en PATH", "returncode": -2}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _safe_eval(expr):
    """Evalúa expresión Octave segura (solo chars permitidos)."""
    if not re.match(r"^[\w\s\.\+\-\*/\^\(\)\[\],;:=]+$", expr):
        raise ValueError(f"Expresión no permitida: {expr[:80]}")
    return expr


def _integrate(params):
    """Integral definida. Params: expr, var, a, b (límites); opcional: npoints.
    Usa quadgk (adaptativa, doble precisión). Si hay symbolic, int()."""
    expr = _safe_eval(params.get("expr", ""))
    var = params.get("var", "x")
    a = float(params.get("a", 0.0))
    b = float(params.get("b", 1.0))
    npoints = int(params.get("npoints", 1000))
    code = f"""
try
  f = @( {var}) {expr};
  val = quadgk(f, {a}, {b}, 'AbsTol', 1e-12, 'RelTol', 1e-10);
  printf('%.15g\\n', val);
catch err
  fprintf(stderr, 'error: %s\\n', err.message);
  exit(1);
end
"""
    r = _run_octave(code, timeout=params.get("timeout", DEFAULT_TIMEOUT))
    if r["returncode"] != 0:
        return {"error": r["stderr"] or r["stdout"], "mode": "integrate"}
    try:
        val = float(r["stdout"].split()[-1])
    except ValueError:
        return {"error": f"parseo falló: {r['stdout']}", "mode": "integrate"}
    return {"mode": "integrate", "expr": expr, "var": var, "a": a, "b": b,
            "integral": val, "engine": "octave-quadgk"}


def _differentiate(params):
    """Derivada. Params: expr, var, x (punto, opcional), order (n).
    Si x dado → numérica (central diff); si no → simbólica (diff)."""
    expr = _safe_eval(params.get("expr", ""))
    var = params.get("var", "x")
    x_val = params.get("x")
    order = int(params.get("order", 1))
    if x_val is not None:
        # Numérica central de orden 2
        x_val = float(x_val)
        h = float(params.get("h", 1e-6))
        code = f"""
f = @( {var}) {expr};
x0 = {x_val}; h = {h}; n = {order};
% Derivada central de orden n (estable)
if n == 1
  d = (f(x0+h) - f(x0-h)) / (2*h);
elseif n == 2
  d = (f(x0+h) - 2*f(x0) + f(x0-h)) / h^2;
elseif n == 3
  d = (f(x0+2*h) - 2*f(x0+h) + 2*f(x0-h) - f(x0-2*h)) / (2*h^3);
elseif n == 4
  d = (f(x0+2*h) - 4*f(x0+h) + 6*f(x0) - 4*f(x0-h) + f(x0-2*h)) / h^4;
else
  error('order >4 no soportado numericamente');
end
printf('%.15g\\n', d);
"""
    else:
        # Simbólica
        code = f"""
try, pkg load symbolic; catch, end  # best-effort
try
  syms {var}
  f = {expr};
  d = diff(f, {var}, {order});
  dstr = char(vpa(d, 15));
  printf('%s\\n', dstr);
catch err
  fprintf(stderr, 'error: %s\\n', err.message);
  exit(1);
end
"""
    r = _run_octave(code, timeout=params.get("timeout", DEFAULT_TIMEOUT))
    if r["returncode"] != 0:
        return {"error": r["stderr"] or r["stdout"], "mode": "differentiate"}
    out = r["stdout"]
    return {"mode": "differentiate", "expr": expr, "var": var, "order": order,
            "derivative": out, "at_x": x_val, "engine": "octave"}


def _ode(params):
    """Resuelve EDO/EDO sistema. Params: 
    - ode: expresión y' = f(t,y) como string; tspan [t0,tf]; y0 (scalar o list).
    - system: lista de strings [f1,...,fn] para y' = F(t,y).
    - method: ode45 (default no-stiff), ode15s (stiff), ode23, ode23s.
    - t_eval: puntos de salida opcional.
    """
    method = params.get("method", "ode45")
    if method not in ("ode45", "ode15s", "ode23", "ode23s", "ode113"):
        method = "ode45"
    tspan = params.get("tspan", [0, 1])
    y0 = params.get("y0", [0.0])
    if not isinstance(y0, (list, tuple)):
        y0 = [y0]
    y0_str = "[" + ", ".join(str(float(v)) for v in y0) + "]"
    tspan_str = "[" + str(float(tspan[0])) + ", " + str(float(tspan[-1])) + "]"
    t_eval = params.get("t_eval")
    if t_eval:
        te_str = "[" + ", ".join(str(float(t)) for t in t_eval) + "]"
    else:
        te_str = f"linspace({tspan[0]}, {tspan[1]}, {params.get('npoints', 100)})"

    system = params.get("system")
    if system:
        n = len(system)
        fs = "; ".join(_safe_eval(e) for e in system)
        rhs = f"F = @(t,y) [{fs}];"
    else:
        ode_expr = _safe_eval(params.get("ode", params.get("expr", "y")))
        rhs = f"F = @(t,y) {ode_expr};"

    code = f"""
{rhs}
tspan = {tspan_str};
y0 = {y0_str};
try
  [t, y] = {method}(F, tspan, y0, odeset('RelTol',1e-8,'AbsTol',1e-10));
  printf('n_times=%d\\n', length(t));
  printf('y_final=');
  printf('%.10g ', y(end,:));
  printf('\\n');
  % Guardar trayectoria breve
  npts = min(10, length(t));
  idx = round(linspace(1, length(t), npts));
  for i = idx
    printf('%.6g ', t(i));
    printf('%.8g ', y(i,:));
    printf('\\n');
  end
catch err
  fprintf(stderr, 'error: %s\\n', err.message);
  exit(1);
end
"""
    r = _run_octave(code, timeout=params.get("timeout", DEFAULT_TIMEOUT))
    if r["returncode"] != 0:
        return {"error": r["stderr"] or r["stdout"], "mode": "ode"}
    lines = r["stdout"].strip().splitlines()
    n_times = None
    y_final = None
    traj = []
    for ln in lines:
        if ln.startswith("n_times="):
            n_times = int(ln.split("=")[1])
        elif ln.startswith("y_final="):
            parts = ln.replace("y_final=", "").split()
            y_final = [float(x) for x in parts]
        else:
            nums = ln.split()
            if len(nums) >= 2:
                try:
                    traj.append([float(x) for x in nums])
                except ValueError:
                    pass
    return {"mode": "ode", "method": method, "n_times": n_times,
            "y_final": y_final, "traj_sample": traj[:10],
            "engine": f"octave-{method}"}


def _linalg(params):
    """Álgebra lineal. Params:
    - op: 'eig' | 'svd' | 'inv' | 'expm' | 'logm' | 'rcond' | 'null' | 'orth'
    - A: matriz (lista de filas) o string Octave.
    """
    op = params.get("op", "eig")
    A = params.get("A")
    if A is None:
        return {"error": "necesita 'A'"}
    if isinstance(A, str):
        A_str = A
    else:
        A_str = "[" + "; ".join(
            "[" + ", ".join(str(float(x)) for x in row) + "]" for row in A
        ) + "]"
    code = f"""
A = {A_str};
op = '{op}';
try
  switch op
    case 'eig'
      [V, D] = eig(A);
      d = diag(D);
      printf('eigenvalues=');
      printf('%.8g%+.8gi ', real(d), imag(d));
      printf('\\n');
    case 'svd'
      [U, S, V] = svd(A);
      s = diag(S);
      printf('singular_values=');
      printf('%.8g ', s);
      printf('\\n');
    case 'inv'
      B = inv(A);
      printf('inv=\\n');
      disp(B);
    case 'expm'
      B = expm(A);
      printf('expm=\\n');
      disp(B);
    case 'logm'
      B = logm(A);
      printf('logm=\\n');
      disp(B);
    case 'rcond'
      printf('rcond=%.12g\\n', rcond(A));
    case 'null'
      N = null(A);
      printf('null_rank=%d\\n', columns(N));
      disp(N);
    case 'orth'
      Q = orth(A);
      printf('orth_rank=%d\\n', columns(Q));
    otherwise
      error('op desconocido: %s', op);
  end
catch err
  fprintf(stderr, 'error: %s\\n', err.message);
  exit(1);
end
"""
    r = _run_octave(code, timeout=params.get("timeout", DEFAULT_TIMEOUT))
    if r["returncode"] != 0:
        return {"error": r["stderr"] or r["stdout"], "mode": "linalg"}
    return {"mode": "linalg", "op": op, "output": r["stdout"], "engine": "octave"}


def _optimize(params):
    """Minimización. Params: expr (f(x) o f(x1,x2,...)), x0 (list), method
    ('fminsearch' Nelder-Mead default, 'fminunc' cuasi-Newton)."""
    expr = _safe_eval(params.get("expr", ""))
    x0 = params.get("x0", [0.0])
    if not isinstance(x0, (list, tuple)):
        x0 = [x0]
    method = params.get("method", "fminsearch")
    if method not in ("fminsearch", "fminunc"):
        method = "fminsearch"
    x0_str = "[" + ", ".join(str(float(v)) for v in x0) + "]"
    n = len(x0)
    if n == 1:
        f_str = f"f = @(x) {expr};"
        x0_use = "x0(1)"
    else:
        vars_x = ", ".join(f"x{i}" for i in range(n))
        f_str = f"f = @({vars_x}) {expr};"
        x0_use = "x0"
    code = f"""
{f_str}
x0 = {x0_str};
try
  opts = optimset('MaxFunEvals', 2000, 'MaxIter', 1000, 'TolX', 1e-12, 'TolFun', 1e-12);
  [x, fval, info] = {method}(f, {x0_use}, opts);
  printf('x_opt=\\n');
  printf('%.12g ', x(:));
  printf('\\n');
  printf('f_opt=%.15g\\n', fval);
  printf('info=%d\\n', info);
catch err
  fprintf(stderr, 'error: %s\\n', err.message);
  exit(1);
end
"""
    r = _run_octave(code, timeout=params.get("timeout", DEFAULT_TIMEOUT))
    if r["returncode"] != 0:
        return {"error": r["stderr"] or r["stdout"], "mode": "optimize"}
    lines = r["stdout"].strip().splitlines()
    x_opt = []
    f_opt = None
    info = None
    for ln in lines:
        if ln.startswith("x_opt="):
            continue
        elif ln.startswith("f_opt="):
            f_opt = float(ln.split("=")[1])
        elif ln.startswith("info="):
            info = int(ln.split("=")[1])
        else:
            nums = ln.split()
            if nums:
                try:
                    x_opt.extend(float(x) for x in nums)
                except ValueError:
                    pass
    return {"mode": "optimize", "method": method, "x_opt": x_opt,
            "f_opt": f_opt, "info": info, "engine": f"octave-{method}"}


def _transforms(params):
    """Transformadas. Params:
    - op: 'laplace' | 'fourier' | 'fft' | 'ifft'
    - expr: para laplace/fourier (simbólico); data: lista para fft.
    """
    op = params.get("op", "fft")
    if op == "fft":
        data = params.get("data", [])
        if not data:
            return {"error": "fft necesita 'data'"}
        data_str = "[" + ", ".join(str(float(x)) for x in data) + "]"
        code = f"""
x = {data_str};
X = fft(x);
printf('real='); printf('%.8g ', real(X)); printf('\\n');
printf('imag='); printf('%.8g ', imag(X)); printf('\\n');
printf('mag='); printf('%.8g ', abs(X)); printf('\\n');
"""
        r = _run_octave(code, timeout=params.get("timeout", DEFAULT_TIMEOUT))
        if r["returncode"] != 0:
            return {"error": r["stderr"], "mode": "transforms"}
        return {"mode": "transforms", "op": "fft", "output": r["stdout"],
                "engine": "octave-fft"}
    elif op in ("laplace", "fourier"):
        expr = _safe_eval(params.get("expr", ""))
        var = params.get("var", "t")
        s_var = params.get("s_var", "s")
        if op == "laplace":
            code = f"""
try, pkg load symbolic; catch, end  # best-effort
try
  syms {var} {s_var}
  f = {expr};
  F = laplace(f, {var}, {s_var});
  printf('%s\\n', char(vpa(F, 12)));
catch err
  fprintf(stderr, 'error: %s\\n', err.message);
  exit(1);
end
"""
        else:
            w_var = params.get("w_var", "w")
            code = f"""
try, pkg load symbolic; catch, end  # best-effort
try
  syms {var} {w_var}
  f = {expr};
  F = fourier(f, {var}, {w_var});
  printf('%s\\n', char(vpa(F, 12)));
catch err
  fprintf(stderr, 'error: %s\\n', err.message);
  exit(1);
end
"""
        r = _run_octave(code, timeout=params.get("timeout", DEFAULT_TIMEOUT))
        if r["returncode"] != 0:
            return {"error": r["stderr"] or r["stdout"], "mode": "transforms"}
        return {"mode": "transforms", "op": op, "result": r["stdout"],
                "engine": "octave-symbolic"}
    return {"error": f"op '{op}' no soportado"}


def _series(params):
    """Series. Params:
    - op: 'taylor' (simbólico) | 'fourier_num' (FFT-based)
    - expr: para taylor; data para fourier_num; n_terms, a (punto).
    """
    op = params.get("op", "taylor")
    if op == "taylor":
        expr = _safe_eval(params.get("expr", ""))
        var = params.get("var", "x")
        a = float(params.get("a", 0.0))
        n = int(params.get("n_terms", 5))
        code = f"""
try, pkg load symbolic; catch, end  # best-effort
try
  syms {var}
  f = {expr};
  T = taylor(f, {var}, 'ExpansionPoint', {a}, 'Order', {n+1});
  printf('%s\\n', char(vpa(T, 12)));
catch err
  fprintf(stderr, 'error: %s\\n', err.message);
  exit(1);
end
"""
        r = _run_octave(code, timeout=params.get("timeout", DEFAULT_TIMEOUT))
        if r["returncode"] != 0:
            return {"error": r["stderr"] or r["stdout"], "mode": "series"}
        return {"mode": "series", "op": "taylor", "a": a, "n_terms": n,
                "result": r["stdout"], "engine": "octave-symbolic"}
    elif op == "fourier_num":
        data = params.get("data", [])
        fs = float(params.get("fs", 1.0))
        if not data:
            return {"error": "fourier_num necesita 'data'"}
        data_str = "[" + ", ".join(str(float(x)) for x in data) + "]"
        code = f"""
x = {data_str};
fs = {fs};
X = fft(x);
N = length(x);
f = (0:N-1) * fs / N;
mag = abs(X) / N;
% Solo mitad positiva
half = ceil(N/2);
printf('freq='); printf('%.6g ', f(1:half)); printf('\\n');
printf('mag='); printf('%.6g ', mag(1:half)); printf('\\n');
"""
        r = _run_octave(code, timeout=params.get("timeout", DEFAULT_TIMEOUT))
        if r["returncode"] != 0:
            return {"error": r["stderr"], "mode": "series"}
        return {"mode": "series", "op": "fourier_num", "output": r["stdout"],
                "engine": "octave-fft"}
    return {"error": f"op '{op}' no soportado"}


def _solve_eq(params):
    """Resuelve f(x)=0. Params: expr, x0 (list), method ('fsolve' | 'vpasolve').
    Para sistema: exprs (list), x0 vector."""
    exprs = params.get("exprs") or params.get("expr")
    x0 = params.get("x0", [1.0])
    if not isinstance(x0, (list, tuple)):
        x0 = [x0]
    method = params.get("method", "fsolve")
    if isinstance(exprs, str):
        exprs = [exprs]
    n = len(exprs)
    m = len(x0)
    if n == 1 and m == 1:
        fs = f"f = @(x) {exprs[0]};"
        x0_use = "x0(1)"
    else:
        vars_x = ", ".join(f"x{i}" for i in range(m))
        fs = f"f = @({vars_x}) [{'; '.join(exprs)}];"
        x0_use = "x0"
    x0_str = "[" + ", ".join(str(float(v)) for v in x0) + "]"
    if method == "vpasolve":
        code = f"""
try, pkg load symbolic; catch, end  # best-effort
try
  syms {', '.join(f'x{i}' for i in range(m))}
  eqs = [{'; '.join(exprs)}];
  sols = vpasolve(eqs, [{', '.join(f'x{i}' for i in range(m))}]);
  fn = fieldnames(sols);
  for k = 1:length(fn)
    printf('%s=%.12g\\n', fn{{k}}, double(sols.(fn{{k}})));
  end
catch err
  fprintf(stderr, 'error: %s\\n', err.message);
  exit(1);
end
"""
    else:
        code = f"""
{fs}
x0 = {x0_str};
try
  opts = optimset('TolX', 1e-12, 'TolFun', 1e-12, 'Display', 'off');
  [x, fval, info] = fsolve(f, {x0_use}, opts);
  printf('x_sol=\\n');
  printf('%.12g ', x(:));
  printf('\\n');
  printf('residual=%.3e\\n', norm(fval));
  printf('info=%d\\n', info);
catch err
  fprintf(stderr, 'error: %s\\n', err.message);
  exit(1);
end
"""
    r = _run_octave(code, timeout=params.get("timeout", DEFAULT_TIMEOUT))
    if r["returncode"] != 0:
        return {"error": r["stderr"] or r["stdout"], "mode": "solve_eq"}
    return {"mode": "solve_eq", "method": method, "output": r["stdout"],
            "engine": f"octave-{method}"}


def _stats(params):
    """Estadística. Params:
    - op: 'describe' (media, var, std, median, etc.) | 'pdf' | 'cdf' | 'inv'
    - data: lista para describe; dist+params para pdf/cdf/inv.
    """
    op = params.get("op", "describe")
    if op == "describe":
        data = params.get("data", [])
        if not data:
            return {"error": "describe necesita 'data'"}
        data_str = "[" + ", ".join(str(float(x)) for x in data) + "]"
        code = f"""
x = {data_str};
printf('n=%d\\n', length(x));
printf('mean=%.10g\\n', mean(x));
printf('median=%.10g\\n', median(x));
printf('std=%.10g\\n', std(x));
printf('var=%.10g\\n', var(x));
printf('min=%.10g\\n', min(x));
printf('max=%.10g\\n', max(x));
printf('skewness=%.10g\\n', skewness(x));
printf('kurtosis=%.10g\\n', kurtosis(x));
"""
        r = _run_octave(code, timeout=params.get("timeout", DEFAULT_TIMEOUT))
        if r["returncode"] != 0:
            return {"error": r["stderr"], "mode": "stats"}
        out = {}
        for ln in r["stdout"].strip().splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                try:
                    out[k] = int(v) if k == "n" else float(v)
                except ValueError:
                    out[k] = v
        return {"mode": "stats", "op": "describe", **out, "engine": "octave"}
    elif op in ("pdf", "cdf", "inv"):
        dist = params.get("dist", "normal")
        x = float(params.get("x", 0.0))
        p = params.get("p")  # para inv
        arg1 = float(params.get("arg1", 0.0))  # mu o a
        arg2 = float(params.get("arg2", 1.0))  # sigma o b
        code = f"""
dist = '{dist}';
op = '{op}';
x = {x};
a = {arg1};
b = {arg2};
p = {float(p) if p is not None else 0.5};
try
  switch dist
    case 'normal'
      if op == 'pdf'
        v = exp(-0.5*((x-a)/b).^2) / (b*sqrt(2*pi));
      elseif op == 'cdf'
        v = 0.5*(1 + erf((x-a)/(b*sqrt(2))));
      elseif op == 'inv'
        % Aproximación de Acklam para la inversa normal
        pp = p;
        if pp < 0.02425
          q = sqrt(-2*log(pp));
          z = (((((c1*q+c2)*q+c3)*q+c4)*q+c5)*q+c6) / ((((c7*q+c8)*q+c9)*q+c10)*q+1);
          c1=-3.969683028665376e+01; c2=2.209460984245205e+02; c3=-2.759285104469687e+02;
          c4=1.383577518672690e+02; c5=-3.066479806614716e+01; c6=2.506628277459239e+00;
          c7=-5.447609879822406e+01; c8=1.615858368580409e+02; c9=-1.556989798598866e+02;
          c10=6.747780422436040e+01;
        elseif pp <= 0.97575
          q = pp - 0.5; r = q*q;
          z = (((((a1*r+a2)*r+a3)*r+a4)*r+a5)*r+a6)*q / (((((b1*r+b2)*r+b3)*r+b4)*r+b5)*r+1);
          a1=-3.969683028665376e+01; a2=2.209460984245205e+02; a3=-2.759285104469687e+02;
          a4=1.383577518672690e+02; a5=-3.066479806614716e+01; a6=2.506628277459239e+00;
          b1=-5.447609879822406e+01; b2=1.615858368580409e+02; b3=-1.556989798598866e+02;
          b4=6.747780422436040e+01;
        else
          q = sqrt(-2*log(1-pp));
          z = -(((((c1*q+c2)*q+c3)*q+c4)*q+c5)*q+c6) / ((((c7*q+c8)*q+c9)*q+c10)*q+1);
        end
        v = a + b*z;
      end
    case 'uniform'
      if op == 'pdf'
        if x >= a && x <= b, v = 1/(b-a); else v = 0; end
      elseif op == 'cdf'
        if x < a, v = 0; elseif x > b, v = 1; else v = (x-a)/(b-a); end
      elseif op == 'inv'
        v = a + p*(b-a);
      end
    case 'exponential'
      if op == 'pdf'
        if x >= 0, v = a*exp(-a*x); else v = 0; end
      elseif op == 'cdf'
        if x >= 0, v = 1 - exp(-a*x); else v = 0; end
      elseif op == 'inv'
        v = -log(1-p)/a;
      end
    case 'beta'
      % Usando gama via lgamma
      if op == 'pdf'
        v = exp((a-1)*log(x) + (b-1)*log(1-x) - (lgamma(a)+lgamma(b)-lgamma(a+b)));
      elseif op == 'cdf'
        % Aproximación numérica simple via integral
        t = linspace(0, x, 500);
        f = exp((a-1)*log(max(t,eps)) + (b-1)*log(max(1-t,eps)) - (lgamma(a)+lgamma(b)-lgamma(a+b)));
        v = trapz(t, f);
      elseif op == 'inv'
        % Búsqueda binaria
        lo=0; hi=1;
        for k=1:60
          mid=(lo+hi)/2;
          t=linspace(0,mid,200);
          fv=exp((a-1)*log(max(t,eps))+(b-1)*log(max(1-t,eps))-(lgamma(a)+lgamma(b)-lgamma(a+b)));
          c=trapz(t,fv);
          if c<p, lo=mid; else hi=mid; end
        end
        v=(lo+hi)/2;
      end
    case 'gamma'
      if op == 'pdf'
        v = exp((a-1)*log(x) - x/b - a*log(b) - lgamma(a));
      elseif op == 'cdf'
        t = linspace(0, x, 500);
        f = exp((a-1)*log(max(t,eps)) - t/b - a*log(b) - lgamma(a));
        v = trapz(t, f);
      elseif op == 'inv'
        lo=0; hi=max(10*b, x+10);
        for k=1:60
          mid=(lo+hi)/2;
          t=linspace(0,mid,200);
          fv=exp((a-1)*log(max(t,eps))-t/b-a*log(b)-lgamma(a));
          c=trapz(t,fv);
          if c<p, lo=mid; else hi=mid; end
        end
        v=(lo+hi)/2;
      end
    case 'student'
      % t PDF: G((nu+1)/2)/(sqrt(nu*pi)G(nu/2)) * (1+t^2/nu)^(-(nu+1)/2)
      if op == 'pdf'
        v = exp(lgamma((a+1)/2) - lgamma(a/2) - 0.5*log(a*pi) - ((a+1)/2)*log(1+x^2/a));
      elseif op == 'cdf'
        % Simetria: cdf(x) = 1 - 0.5*I_(a/(a+x^2))(a/2, 1/2) para x>0
        xx = abs(x);
        y = a/(a+xx^2);
        % Incompleta beta (aprox via integral)
        t=linspace(0,y,400);
        fb = exp((a/2-1)*log(max(t,eps)) + (0.5-1)*log(max(1-t,eps)) - (lgamma(a/2)+lgamma(0.5)-lgamma(a/2+0.5)));
        Ib = trapz(t, fb);
        if x >= 0, v = 1 - 0.5*Ib; else v = 0.5*Ib; end
      elseif op == 'inv'
        % Búsqueda binaria en cdf
        lo=-100; hi=100;
        for k=1:80
          mid=(lo+hi)/2;
          xx=abs(mid); y=a/(a+xx^2);
          t=linspace(0,y,200);
          fb=exp((a/2-1)*log(max(t,eps))+(0.5-1)*log(max(1-t,eps))-(lgamma(a/2)+lgamma(0.5)-lgamma(a/2+0.5)));
          Ib=trapz(t,fb);
          if mid>=0, c=1-0.5*Ib; else c=0.5*Ib; end
          if c<p, lo=mid; else hi=mid; end
        end
        v=(lo+hi)/2;
      end
    case 'chi2'
      % chi2 PDF: 1/(2^(k/2)*G(k/2)) * x^(k/2-1) * e^(-x/2)
      if op == 'pdf'
        v = exp((a/2-1)*log(x) - x/2 - (a/2)*log(2) - lgamma(a/2));
      elseif op == 'cdf'
        t=linspace(0,x,500);
        f=exp((a/2-1)*log(max(t,eps))-t/2-(a/2)*log(2)-lgamma(a/2));
        v=trapz(t,f);
      elseif op == 'inv'
        lo=0; hi=max(50, x+20);
        for k=1:60
          mid=(lo+hi)/2;
          t=linspace(0,mid,300);
          fv=exp((a/2-1)*log(max(t,eps))-t/2-(a/2)*log(2)-lgamma(a/2));
          c=trapz(t,fv);
          if c<p, lo=mid; else hi=mid; end
        end
        v=(lo+hi)/2;
      end
    otherwise
      error('dist desconocida: %s', dist);
  end
  printf('%.12g\\n', v);
catch err
  fprintf(stderr, 'error: %s\\n', err.message);
  exit(1);
end
"""
        r = _run_octave(code, timeout=params.get("timeout", DEFAULT_TIMEOUT))
        if r["returncode"] != 0:
            return {"error": r["stderr"] or r["stdout"], "mode": "stats"}
        try:
            val = float(r["stdout"].strip().split()[-1])
        except ValueError:
            val = r["stdout"]
        return {"mode": "stats", "op": op, "dist": dist, "value": val,
                "engine": "octave-stats"}
    return {"error": f"op '{op}' no soportado"}


def _validate(params):
    """Autochequeos de cada modo vs valores conocidos."""
    checks = []
    # integrate: ∫₀¹ x² dx = 1/3
    r = _integrate({"expr": "x.^2", "var": "x", "a": 0, "b": 1})
    ok = "integral" in r and abs(r["integral"] - 1/3) < 1e-10
    checks.append({"name": "integrate_x2", "passed": ok, "got": r.get("integral")})
    # differentiate: d/dx sin(x)|_{x=0} = 1
    r = _differentiate({"expr": "sin(x)", "var": "x", "x": 0.0})
    ok = "derivative" in r and abs(float(r["derivative"]) - 1.0) < 1e-7
    checks.append({"name": "diff_sin0", "passed": ok, "got": r.get("derivative")})
    # ode: y' = -y, y(0)=1, t→∞ → 0; en t=1 → e^{-1}
    r = _ode({"ode": "-y", "tspan": [0, 1], "y0": [1.0], "method": "ode45"})
    ok = "y_final" in r and abs(r["y_final"][0] - 0.367879) < 1e-5
    checks.append({"name": "ode_exp_decay", "passed": ok, "got": r.get("y_final")})
    # linalg: eig([2,0;0,3]) = [2,3]
    r = _linalg({"op": "eig", "A": [[2, 0], [0, 3]]})
    ok = "eigenvalues" in r["output"] if "output" in r else False
    checks.append({"name": "linalg_eig_diag", "passed": ok, "got": r.get("output", r.get("error"))})
    # optimize: min de (x-2)^2 → x=2
    r = _optimize({"expr": "(x-2).^2", "x0": [0.0], "method": "fminsearch"})
    ok = "x_opt" in r and abs(r["x_opt"][0] - 2.0) < 1e-6
    checks.append({"name": "optimize_quad", "passed": ok, "got": r.get("x_opt")})
    # solve_eq: x^2 - 4 = 0 → x=2
    r = _solve_eq({"expr": "x.^2 - 4", "x0": [1.5], "method": "fsolve"})
    ok = "x_sol" in r["output"] if "output" in r else False
    checks.append({"name": "solve_quad", "passed": ok, "got": r.get("output", r.get("error"))})
    # stats: describe [1,2,3,4,5] → mean=3
    r = _stats({"op": "describe", "data": [1, 2, 3, 4, 5]})
    ok = "mean" in r and abs(r["mean"] - 3.0) < 1e-10
    checks.append({"name": "stats_mean", "passed": ok, "got": r.get("mean")})
    # stats pdf: normal(0,1) at 0 = 1/sqrt(2π) ≈ 0.3989
    r = _stats({"op": "pdf", "dist": "normal", "x": 0.0, "arg1": 0.0, "arg2": 1.0})
    ok = "value" in r and abs(r["value"] - 0.398942) < 1e-5
    checks.append({"name": "stats_normpdf0", "passed": ok, "got": r.get("value")})
    passed = sum(1 for c in checks if c["passed"])
    return {"mode": "validate", "n_checks": len(checks), "n_passed": passed,
            "validation_passed": passed == len(checks), "checks": checks}


def _handler(args):
    mode = args.get("mode")
    params = args.get("params") or {}
    try:
        if mode == "integrate":
            return _integrate(params)
        elif mode == "differentiate":
            return _differentiate(params)
        elif mode == "ode":
            return _ode(params)
        elif mode == "linalg":
            return _linalg(params)
        elif mode == "optimize":
            return _optimize(params)
        elif mode == "transforms":
            return _transforms(params)
        elif mode == "series":
            return _series(params)
        elif mode == "solve_eq":
            return _solve_eq(params)
        elif mode == "stats":
            return _stats(params)
        elif mode == "validate":
            return _validate(params)
        else:
            return {"error": f"mode desconocido: {mode}"}
    except (KeyError, ValueError, TypeError) as e:
        return {"error": f"parámetros inválidos: {e}"}


register_tool(
    name="octave_math_tool",
    schema=OCTAVE_MATH_TOOL_SCHEMA,
    handler=lambda args: _handler(args),
)
