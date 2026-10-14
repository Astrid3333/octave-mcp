"""
struct_kernel_py.py

Wrapper ctypes del cdylib Rust `struct_kernel` (struct_kernel_rs).
Carga libstruct_kernel.so con argtypes explícitos (usize ⇒ c_size_t; el
default de ctypes es 32 bits y segfaultea con tamaño de matriz en los
argumentos). Si la librería no está compilada, cada función devuelve
None y el caller cae a numpy (fallback determinista, menos preciso en
sistemas mal condicionados).

Unidades: SI (m, N, Pa). Row-major, igual que el lado Rust.
"""

import ctypes
import os

_LIB_ENV = "STRUCT_KERNEL_PATH"
_LIB_DEFAULT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "struct_kernel_rs", "target", "release", "libstruct_kernel.so",
)

_P = ctypes.c_void_p


def _load():
    path = os.environ.get(_LIB_ENV, _LIB_DEFAULT)
    if not os.path.exists(path):
        return None
    try:
        lib = ctypes.CDLL(path)
    except OSError:
        return None

    lib.sk_version.restype = ctypes.c_uint32
    lib.sk_version.argtypes = []

    lib.sk_kahan_sum.restype = None
    lib.sk_kahan_sum.argtypes = [
        _P, ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
    ]

    lib.sk_ldlt_solve.restype = ctypes.c_int
    lib.sk_ldlt_solve.argtypes = [
        ctypes.c_size_t, _P, _P, _P,
    ]

    lib.sk_frame2d_solve.restype = ctypes.c_int
    lib.sk_frame2d_solve.argtypes = [
        ctypes.c_size_t, ctypes.c_size_t,   # nn, nm
        _P, _P,                              # coords, members
        ctypes.c_size_t, _P,                 # n_bc, bc (i64)
        ctypes.c_size_t, _P,                 # n_nl, nl
        _P, _P, _P,                          # u_out, reac_out, end_forces
    ]

    lib.sk_eigen_generalized.restype = ctypes.c_int
    lib.sk_eigen_generalized.argtypes = [
        ctypes.c_size_t, _P, _P, ctypes.c_size_t, _P, _P,
    ]

    lib.sk_beam_exact_stiffness.restype = ctypes.c_int
    lib.sk_beam_exact_stiffness.argtypes = [
        ctypes.c_double, ctypes.c_double, ctypes.c_double,
        ctypes.c_double, ctypes.c_double, ctypes.c_double, _P,
    ]

    lib.sk_ec3_buckling_chi.restype = ctypes.c_int
    lib.sk_ec3_buckling_chi.argtypes = [
        ctypes.c_double, ctypes.c_double, ctypes.POINTER(ctypes.c_double),
    ]
    lib.sk_ec3_chi_lt.restype = ctypes.c_int
    lib.sk_ec3_chi_lt.argtypes = [
        ctypes.c_double, ctypes.c_double, ctypes.POINTER(ctypes.c_double),
    ]
    lib.sk_ec3_lambda_bar.restype = ctypes.c_int
    lib.sk_ec3_lambda_bar.argtypes = [
        ctypes.c_double, ctypes.c_double, ctypes.c_double,
        ctypes.POINTER(ctypes.c_double),
    ]
    lib.sk_euler_ncr.restype = ctypes.c_int
    lib.sk_euler_ncr.argtypes = [
        ctypes.c_double, ctypes.c_double, ctypes.c_double,
        ctypes.POINTER(ctypes.c_double),
    ]
    return lib


_LIB = _load()
AVAILABLE = _LIB is not None

if AVAILABLE:
    KERNEL_VERSION = _LIB.sk_version()
else:
    KERNEL_VERSION = 0


def _dbl_array(seq):
    return (ctypes.c_double * len(seq))(*[float(x) for x in seq])


def _i64_array(seq):
    return (ctypes.c_int64 * len(seq))(*[int(x) for x in seq])


def version():
    return KERNEL_VERSION


def solve_linear(a, b):
    """Resuelve A x = b (A n×n destruida). Devuelve x o None si no hay kernel."""
    if not AVAILABLE:
        return None
    n = len(b)
    ac = _dbl_array([v for row in a for v in row])
    bc = _dbl_array(b)
    xc = (ctypes.c_double * n)()
    rc = _LIB.sk_ldlt_solve(n, ac, bc, xc)
    if rc != 0:
        return None
    return list(xc)


def kahan_sum(xs):
    """Suma compensada Neumaier. Devuelve (sum, err) o None."""
    if not AVAILABLE:
        return None
    xc = _dbl_array(xs)
    s = ctypes.c_double()
    e = ctypes.c_double()
    _LIB.sk_kahan_sum(xc, len(xs), ctypes.byref(s), ctypes.byref(e))
    return (s.value, e.value)


def euler_ncr(e_mod, iz, l_cr):
    """N_cr = π² EI / L_cr²."""
    if not AVAILABLE:
        return None
    out = ctypes.c_double()
    rc = _LIB.sk_euler_ncr(float(e_mod), float(iz), float(l_cr), ctypes.byref(out))
    return out.value if rc == 0 else None


def lambda_bar(area, fy, n_cr):
    """λ̄ = √(A fy / N_cr)."""
    if not AVAILABLE:
        return None
    out = ctypes.c_double()
    rc = _LIB.sk_ec3_lambda_bar(float(area), float(fy), float(n_cr), ctypes.byref(out))
    return out.value if rc == 0 else None


def buckling_chi(lambda_bar_val, alpha):
    """χ de pandeo EC3 (curvas a0/a/b/c/d)."""
    if not AVAILABLE:
        return None
    out = ctypes.c_double()
    rc = _LIB.sk_ec3_buckling_chi(float(lambda_bar_val), float(alpha), ctypes.byref(out))
    return out.value if rc == 0 else None


def chi_lt(lambda_lt_bar, alpha_lt):
    """χ_LT de pandeo lateral EC3 6.3.2.2 (misma fórmula, curva por α_LT)."""
    if not AVAILABLE:
        return None
    out = ctypes.c_double()
    rc = _LIB.sk_ec3_chi_lt(float(lambda_lt_bar), float(alpha_lt), ctypes.byref(out))
    return out.value if rc == 0 else None


def beam_exact_stiffness(e_mod, g_mod, area, iz, asy, length):
    """Matriz de rigidez local 6×6 Timoshenko (row-major 36). None si falla."""
    if not AVAILABLE:
        return None
    out = (ctypes.c_double * 36)()
    rc = _LIB.sk_beam_exact_stiffness(
        float(e_mod), float(g_mod), float(area), float(iz),
        float(asy), float(length), out,
    )
    return list(out) if rc == 0 else None


def frame2d_solve(coords, members, bc, nodal_loads=None):
    """Análisis de pórtico 2D. coords 2·nn; members 8·nm [i,j,A,E,Iz,G,As,w];
    bc 2·n [node, dof] con dof 0=u,1=v,2=θ; nodal_loads 3·n [node,dof,F].
    Devuelve (u, reac, end_forces, rc) o None si no hay kernel."""
    if not AVAILABLE:
        return None
    import numpy as np
    coords = np.asarray(coords, dtype=np.float64).ravel()
    members = np.asarray(members, dtype=np.float64).ravel()
    bc = np.asarray(bc, dtype=np.int64).ravel()
    nl = np.asarray(nodal_loads if nodal_loads is not None else [], dtype=np.float64).ravel()
    nn = coords.size // 2
    nm = members.size // 8
    n_bc = bc.size // 2
    n_nl = nl.size // 3
    u = np.zeros(3 * nn)
    reac = np.zeros(3 * nn)
    ef = np.zeros(6 * nm)
    rc = _LIB.sk_frame2d_solve(
        nn, nm,
        coords.ctypes.data_as(_P),
        members.ctypes.data_as(_P),
        n_bc,
        bc.ctypes.data_as(_P) if n_bc else _P(),
        n_nl,
        nl.ctypes.data_as(_P) if n_nl else _P(),
        u.ctypes.data_as(_P),
        reac.ctypes.data_as(_P),
        ef.ctypes.data_as(_P),
    )
    return u, reac, ef, rc


def eigen_generalized(k, m=None, nev=1):
    """Autovalores generalizados K φ = λ M φ (nev más pequeños).
    Devuelve (vals, vecs column-wise) o None."""
    if not AVAILABLE:
        return None
    import numpy as np
    k = np.asarray(k, dtype=np.float64)
    n = k.shape[0]
    mc = None
    if m is not None:
        m = np.asarray(m, dtype=np.float64)
        mc = m.ctypes.data_as(_P)
    vals = np.zeros(nev)
    vecs = np.zeros(n * nev)
    rc = _LIB.sk_eigen_generalized(
        n, k.ctypes.data_as(_P), mc, nev,
        vals.ctypes.data_as(_P), vecs.ctypes.data_as(_P),
    )
    if rc != 0:
        return None
    return vals, vecs.reshape(n, nev)
