"""
cfd_tool.py
Fase 3 del roadmap: dinamica de fluidos computacional (CFD) en Octave/Python puro.

Modos:
  - poiseuille_flow    : flujo de Stokes (bajo Reynolds) entre placas paralelas,
                         resuelto por diferencias finitas 1D (perfil parabolico).
                         Validado contra la solucion analitica de Hagen-Poiseuille plano.
  - lid_driven_cavity  : cavidad cuadrada con tapa movil, Navier-Stokes 2D laminar
                         via formulacion vorticidad-funcion de corriente (omega-psi),
                         avance temporal explicito (FTCS) + Poisson por SOR.
                         Validado contra el benchmark clasico de Ghia, Ghia & Shin (1982),
                         perfil de velocidad u en la linea vertical central, Re=100.

Ambos modos siguen el mismo patron de diferencias finitas explicitas que pde_tool.
"""
import numpy as np

CFD_TOOL_SCHEMA = {
    "name": "cfd_tool",
    "description": (
        "Dinamica de fluidos computacional: flujo de Poiseuille plano (Stokes flow, "
        "validado contra solucion analitica exacta) y cavidad con tapa movil "
        "(lid-driven cavity, Navier-Stokes 2D laminar via vorticidad-funcion de "
        "corriente, validado contra el benchmark de Ghia, Ghia & Shin 1982)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["poiseuille_flow", "lid_driven_cavity"]},
            "params": {"type": "object", "description": "Parametros especificos de cada modo, ver docstrings."},
        },
        "required": ["mode"],
    },
}

# Benchmark Ghia, Ghia & Shin (1982), Tabla I: u(y) en x=0.5, Re=100
_GHIA_RE100_Y = np.array([
    0.0000, 0.0547, 0.0625, 0.0703, 0.1016, 0.1719, 0.2813, 0.4531,
    0.5000, 0.6172, 0.7344, 0.8516, 0.9531, 0.9609, 0.9688, 0.9766, 1.0000
])
_GHIA_RE100_U = np.array([
     0.00000, -0.03717, -0.04192, -0.04775, -0.06434, -0.10150, -0.15662, -0.21090,
    -0.20581, -0.13641,  0.00332,  0.23151,  0.68717,  0.73722,  0.78871,  0.84123,  1.00000
])


def _poiseuille_flow(mu=1.0e-3, dpdx=-1.0, h=1.0, n=41):
    """
    Flujo de Stokes plano entre placas paralelas separadas por h, gradiente de
    presion constante dpdx (< 0 empuja el flujo). Resuelto por diferencias finitas
    (matriz tridiagonal) para -mu*u''(y) = -dpdx, u(0)=u(h)=0.
    Solucion analitica: u(y) = (-dpdx/(2*mu)) * y*(h-y)
    """
    y = np.linspace(0, h, n)
    dy = y[1] - y[0]
    A = np.zeros((n, n))
    b = np.zeros(n)
    A[0, 0] = 1.0
    A[-1, -1] = 1.0
    for i in range(1, n - 1):
        A[i, i - 1] = 1.0 / dy**2
        A[i, i] = -2.0 / dy**2
        A[i, i + 1] = 1.0 / dy**2
        b[i] = dpdx / mu
    u_fd = np.linalg.solve(A, b)
    u_analytic = (-dpdx / (2 * mu)) * y * (h - y)
    err = np.abs(u_fd - u_analytic)
    max_err = float(np.max(err))
    denom = float(np.max(np.abs(u_analytic))) or 1.0
    return {
        "mode": "poiseuille_flow",
        "y": y.tolist(),
        "u_fd": u_fd.tolist(),
        "u_analytic": u_analytic.tolist(),
        "max_abs_error": max_err,
        "max_relative_error": max_err / denom,
        "validation": "Hagen-Poiseuille plano, solucion analitica exacta",
    }


def _lid_driven_cavity(n=41, Re=100.0, U=1.0, L=1.0, n_steps=4000, dt=None, sor_iters=60, sor_omega=1.0):
    """
    Cavidad cuadrada [0,L]x[0,L], tapa superior con velocidad U hacia la derecha,
    resto de paredes con no-deslizamiento. Formulacion vorticidad-funcion de
    corriente:
        laplaciano(psi) = -omega                          (Poisson, por SOR)
        u = d(psi)/dy ,  v = -d(psi)/dx
        d(omega)/dt + u*d(omega)/dx + v*d(omega)/dy = nu*laplaciano(omega)
    Condiciones de borde de vorticidad via formula de Thom (2do orden).

    Nota: el solver de Poisson esta vectorizado (todas las celdas se actualizan
    en simultaneo a partir de psi "vieja"), es decir es Jacobi puro, no
    Gauss-Seidel. sor_omega debe quedarse en 1.0: un factor de sobrerelajacion
    >1 diverge con Jacobi (solo es estable con barrido secuencial tipo
    Gauss-Seidel). El nombre "sor_iters/sor_omega" se mantiene por compatibilidad
    con el patch de wireo, pero en la practica es un Jacobi damped/puro.
    """
    nu = U * L / Re
    dx = dy = L / (n - 1)
    if dt is None:
        dt = 0.2 * min(dx * dy / (4 * nu), dx / max(U, 1e-9))

    psi = np.zeros((n, n))
    omega = np.zeros((n, n))

    for step in range(n_steps):
        # --- Poisson para psi: laplaciano(psi) = -omega, via SOR ---
        for _ in range(sor_iters):
            psi[1:-1, 1:-1] = (1 - sor_omega) * psi[1:-1, 1:-1] + sor_omega * 0.25 * (
                psi[2:, 1:-1] + psi[:-2, 1:-1] + psi[1:-1, 2:] + psi[1:-1, :-2]
                + dx * dy * omega[1:-1, 1:-1]
            )

        # --- Vorticidad en las paredes (formula de Thom) ---
        omega[0, :]   = -2.0 * psi[1, :]    / dy**2                      # pared inferior (y=0)
        omega[-1, :]  = -2.0 * psi[-2, :]   / dy**2 - 2.0 * U / dy       # tapa movil (y=L)
        omega[:, 0]   = -2.0 * psi[:, 1]    / dx**2                      # pared izquierda
        omega[:, -1]  = -2.0 * psi[:, -2]   / dx**2                      # pared derecha

        # --- Velocidades desde la funcion de corriente ---
        u = np.zeros((n, n))
        v = np.zeros((n, n))
        u[1:-1, 1:-1] = (psi[2:, 1:-1] - psi[:-2, 1:-1]) / (2 * dy)
        v[1:-1, 1:-1] = -(psi[1:-1, 2:] - psi[1:-1, :-2]) / (2 * dx)
        u[-1, :] = U

        # --- Transporte de vorticidad (FTCS) ---
        domega_dx = np.zeros((n, n))
        domega_dy = np.zeros((n, n))
        domega_dx[1:-1, 1:-1] = (omega[1:-1, 2:] - omega[1:-1, :-2]) / (2 * dx)
        domega_dy[1:-1, 1:-1] = (omega[2:, 1:-1] - omega[:-2, 1:-1]) / (2 * dy)
        lap_omega = np.zeros((n, n))
        lap_omega[1:-1, 1:-1] = (
            (omega[2:, 1:-1] - 2 * omega[1:-1, 1:-1] + omega[:-2, 1:-1]) / dy**2
            + (omega[1:-1, 2:] - 2 * omega[1:-1, 1:-1] + omega[1:-1, :-2]) / dx**2
        )

        advection = u * domega_dx + v * domega_dy
        omega[1:-1, 1:-1] = omega[1:-1, 1:-1] + dt * (
            -advection[1:-1, 1:-1] + nu * lap_omega[1:-1, 1:-1]
        )

    # velocidad u final en la linea vertical central (x = L/2)
    i_mid = n // 2
    y = np.linspace(0, L, n)
    u_centerline = u[:, i_mid]

    u_interp = np.interp(_GHIA_RE100_Y * L, y, u_centerline)
    err = np.abs(u_interp - _GHIA_RE100_U * U)
    max_err = float(np.max(err))

    return {
        "mode": "lid_driven_cavity",
        "grid_size": n,
        "reynolds": Re,
        "n_steps": n_steps,
        "dt": dt,
        "y_centerline": y.tolist(),
        "u_centerline": u_centerline.tolist(),
        "ghia_y": _GHIA_RE100_Y.tolist(),
        "ghia_u": _GHIA_RE100_U.tolist(),
        "max_abs_error_vs_ghia": max_err,
        "validation": "Ghia, Ghia & Shin (1982), Re=100, linea vertical central",
    }


def compute_cfd(mode, params=None):
    params = params or {}
    if mode == "poiseuille_flow":
        return _poiseuille_flow(**params)
    elif mode == "lid_driven_cavity":
        return _lid_driven_cavity(**params)
    else:
        raise ValueError(f"modo desconocido: {mode}. Use poiseuille_flow | lid_driven_cavity")


if __name__ == "__main__":
    import time

    r1 = compute_cfd("poiseuille_flow", {"mu": 1.0e-3, "dpdx": -1.0, "h": 1.0, "n": 41})
    print("poiseuille_flow max_relative_error =", r1["max_relative_error"])

    t0 = time.time()
    r2 = compute_cfd("lid_driven_cavity", {"n": 41, "Re": 100.0, "n_steps": 4000})
    print(f"lid_driven_cavity max_abs_error_vs_ghia = {r2['max_abs_error_vs_ghia']:.4f}  "
          f"({time.time()-t0:.1f}s)")
