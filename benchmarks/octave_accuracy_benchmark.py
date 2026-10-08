"""Accuracy benchmark for octave-mcp: GNU Octave vs analytic/scipy ground truth.

Replicates the exact subprocess from octave-mcp server.py:273
    subprocess.run(["octave", "--no-gui", "--eval", code], timeout=30)
(here with a generous timeout, since timeout is irrelevant to numeric accuracy).

Each workload is an independent run_octave(code) call emitting BM_* markers with
"% .17g" precision. Markers are parsed and compared against numpy/scipy/analytic
references with the scaled error norm_err(a,b) = max|a-b| / max(max|b|, 1e-12).
"""

import json
import os
import re
import subprocess
import sys
from datetime import date

import numpy as np
from scipy.linalg import svd as scipy_svd

OCTAVE_BIN = "octave"
EVAL_ARGS = [OCTAVE_BIN, "--no-gui", "--eval"]

MARK_RE = re.compile(
    r"BM_([A-Z0-9]+)=" + r"\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)"
)

VERSION_CODE = 'printf("%s", version());'

ODE_REF = float(np.exp(-2))
INT_REF = 2.0
DET_REF = 42.0


def real_root_of_cubic():
    for r in np.roots([1.0, 0.0, -1.0, -2.0]):
        if abs(r.imag) < 1e-9:
            return float(r.real)
    raise RuntimeError("no real root for x^3 - x - 2")


ROOT_REF = real_root_of_cubic()
EIG_REF = np.sort(np.linalg.eigvalsh([[2.0, 1.0, 0.0], [1.0, 2.0, 0.0], [0.0, 0.0, 4.0]]))
SVD_REF = np.sort(scipy_svd(np.diag([3.0, 1.0, 2.0]))[1])[::-1]
FFT_REF = np.fft.fft(np.sin(2.0 * np.pi * np.arange(16) / 8.0))


def run_octave(code):
    result = subprocess.run(
        EVAL_ARGS + [code], capture_output=True, text=True, timeout=120
    )
    return result.stdout + result.stderr


def octave_version():
    text = run_octave(VERSION_CODE)
    match = re.search(r"\d+\.\d+\.\d+", text)
    return match.group(0) if match else "unknown"


def parse_markers(text):
    return {name: float(value) for name, value in MARK_RE.findall(text)}


def norm_err(a, b):
    a = np.asarray(a)
    b = np.asarray(b)
    scale = max(float(np.max(np.abs(b))), 1e-12)
    return float(np.max(np.abs(a - b)) / scale)


def fft_value_from(markers):
    values = {}
    for name, value in markers.items():
        values[name] = value
    if not any(name.startswith("FFT") for name in values):
        return None
    tensor = []
    for k in range(16):
        re_k = values.get("FFT%02dRE" % k)
        im_k = values.get("FFT%02dIM" % k)
        if re_k is None or im_k is None:
            return None
        tensor.append(re_k + 1j * im_k)
    return np.asarray(tensor)


def to_json_safe(value):
    if isinstance(value, np.ndarray):
        if np.iscomplexobj(value):
            return [[float(z.real), float(z.imag)] for z in value.ravel().tolist()]
        return value.tolist()
    if isinstance(value, np.complexfloating):
        return [float(value.real), float(value.imag)]
    if isinstance(value, complex):
        return [value.real, value.imag]
    if isinstance(value, np.floating) or isinstance(value, np.integer):
        return float(value)
    return value


def workload_definitions():
    return [
        {
            "name": "ode_lsode_decay",
            "code": (
                "function y = f(x,t); y = -2*x; endfunction\n"
                'lsode_options("relative tolerance", 1e-12)\n'
                'lsode_options("absolute tolerance", 1e-14)\n'
                "t = (0:0.01:1).';\n"
                "y = lsode(@f, 1.0, t);\n"
                'fprintf("BM_ODE=% .17g\\n", y(end));'
            ),
            "check": lambda m: (m["ODE"], ODE_REF, norm_err(m["ODE"], ODE_REF)),
            "tol": 1e-8,
        },
        {
            "name": "ode_rk4_decay",
            "code": (
                "f = @(t,x) -2*x;\n"
                "h = 0.001; n = 1000; x = 1.0;\n"
                "for k = 1:n\n"
                "  t = (k-1)*h;\n"
                "  k1 = f(t,x); k2 = f(t+h/2, x+h*k1/2); k3 = f(t+h/2, x+h*k2/2); k4 = f(t+h, x+h*k3);\n"
                "  x = x + h*(k1+2*k2+2*k3+k4)/6;\n"
                "endfor\n"
                'fprintf("BM_RK4=% .17g\\n", x);'
            ),
            "check": lambda m: (m["RK4"], ODE_REF, norm_err(m["RK4"], ODE_REF)),
            "tol": 1e-8,
        },
        {
            "name": "quad_poly",
            "code": (
                "v = quad(@(x) x.^3 - 2*x + 1, 0, 2);\n"
                'fprintf("BM_QUAD=% .17g\\n", v);'
            ),
            "check": lambda m: (m["QUAD"], INT_REF, norm_err(m["QUAD"], INT_REF)),
            "tol": 1e-8,
        },
        {
            "name": "quadgk_sin",
            "code": (
                "v = quadgk(@sin, 0, pi);\n"
                'fprintf("BM_QGK=% .17g\\n", v);'
            ),
            "check": lambda m: (m["QGK"], INT_REF, norm_err(m["QGK"], INT_REF)),
            "tol": 1e-8,
        },
        {
            "name": "trapz_sin",
            "code": (
                "x = linspace(0, pi, 100001);\n"
                "v = trapz(x, sin(x));\n"
                'fprintf("BM_TRAPZ=% .17g\\n", v);'
            ),
            "check": lambda m: (m["TRAPZ"], INT_REF, norm_err(m["TRAPZ"], INT_REF)),
            "tol": 1e-6,
        },
        {
            "name": "root_fzero",
            "code": (
                "r = fzero(@(x) x.^3 - x - 2, 1.5);\n"
                'fprintf("BM_FZERO=% .17g\\n", r);'
            ),
            "check": lambda m: (m["FZERO"], ROOT_REF, norm_err(m["FZERO"], ROOT_REF)),
            "tol": 1e-8,
        },
        {
            "name": "root_newton",
            "code": (
                "f = @(x) x.^3 - x - 2;\n"
                "df = @(x) 3*x.^2 - 1;\n"
                "x = 1.5; xold = 0;\n"
                "for it = 1:100\n"
                "  xold = x;\n"
                "  x = x - f(x)/df(x);\n"
                "  if abs(x - xold) < 1e-14, break, end\n"
                "endfor\n"
                'fprintf("BM_NT=% .17g\\n", x);'
            ),
            "check": lambda m: (m["NT"], ROOT_REF, norm_err(m["NT"], ROOT_REF)),
            "tol": 1e-8,
        },
        {
            "name": "det_tri",
            "code": (
                "A = [2 0 0; 4 3 0; 5 6 7];\n"
                'fprintf("BM_DET=% .17g\\n", det(A));'
            ),
            "check": lambda m: (m["DET"], DET_REF, norm_err(m["DET"], DET_REF)),
            "tol": 1e-8,
        },
        {
            "name": "eig_sym",
            "code": (
                "A = [2 1 0; 1 2 0; 0 0 4];\n"
                "d = sort(real(eig(A)));\n"
                'fprintf("BM_EIG1=% .17g\\n", d(1));\n'
                'fprintf("BM_EIG2=% .17g\\n", d(2));\n'
                'fprintf("BM_EIG3=% .17g\\n", d(3));'
            ),
            "check": lambda m: (
                [m["EIG1"], m["EIG2"], m["EIG3"]],
                EIG_REF,
                norm_err([m["EIG1"], m["EIG2"], m["EIG3"]], EIG_REF),
            ),
            "tol": 1e-8,
        },
        {
            "name": "svd_diag",
            "code": (
                "A = diag([3 1 2]);\n"
                "s = svd(A);\n"
                'fprintf("BM_SVD1=% .17g\\n", s(1));\n'
                'fprintf("BM_SVD2=% .17g\\n", s(2));\n'
                'fprintf("BM_SVD3=% .17g\\n", s(3));'
            ),
            "check": lambda m: (
                [m["SVD1"], m["SVD2"], m["SVD3"]],
                SVD_REF,
                norm_err([m["SVD1"], m["SVD2"], m["SVD3"]], SVD_REF),
            ),
            "tol": 1e-8,
        },
        {
            "name": "fft_sin",
            "code": (
                "x = sin(2*pi*(0:15)/8);\n"
                "X = fft(x);\n"
                "for k = 0:15\n"
                '  fprintf("BM_FFT%02dRE=% .17g\\n", k, real(X(k+1)));\n'
                '  fprintf("BM_FFT%02dIM=% .17g\\n", k, imag(X(k+1)));\n'
                "endfor"
            ),
            "check": lambda m: (
                fft_value_from(m),
                FFT_REF,
                norm_err(fft_value_from(m), FFT_REF),
            ),
            "tol": 1e-10,
        },
    ]


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))
    results_file = os.path.join(
        out_dir, "results_octave_accuracy_%s.json" % date.today().isoformat()
    )

    version = octave_version()
    numpy_version = np.__version__

    from scipy import __version__ as scipy_version

    workloads = workload_definitions()
    results = {}
    n_pass = 0

    print("octave version: %s" % version)
    print("%-18s %12s %12s  %s" % ("workload", "rel_err", "tol", "result"))
    print("-" * 58)

    for w in workloads:
        text = run_octave(w["code"])
        markers = parse_markers(text)
        try:
            value, ref, err = w["check"](markers)
        except (KeyError, TypeError):
            value, ref, err = None, None, float("inf")
        passed = err == err and err <= w["tol"]
        n_pass += 1 if passed else 0
        results[w["name"]] = {
            "value": to_json_safe(value),
            "ref": to_json_safe(ref),
            "rel_err": None if err != err else round(err, 3),
            "tol": w["tol"],
            "pass": passed,
            "stderr_tail": text[-400:] if not passed else None,
        }
        print(
            "%-18s %12.3e %12.3e  %s"
            % (w["name"], err if err == err else float("nan"), w["tol"], "OK" if passed else "FAIL")
        )

    summary = {"passed": n_pass, "total": len(workloads)}
    payload = {
        "date": date.today().isoformat(),
        "octave_version": version,
        "python": sys.version.split()[0],
        "numpy": numpy_version,
        "scipy": scipy_version,
        "replicates": "octave-mcp server.py:273 run_octave subprocess",
        "summary": summary,
        "workloads": results,
    }
    with open(results_file, "w") as fh:
        json.dump(payload, fh, indent=2)
    print("-" * 58)
    print("summary: %d/%d passed" % (n_pass, len(workloads)))
    print("results -> %s" % results_file)
    return 0 if n_pass == len(workloads) else 1


if __name__ == "__main__":
    sys.exit(main())