"""
thermal_conduction_tool.py
Conduccion de calor FEM: 1D estacionario, 1D transitorio (Crank-Nicolson),
y 2D estacionario (elementos triangulares lineales, malla rectangular).

Modos:
  - steady_1d    : barra/pared 1D, FEM lineal, Dirichlet en ambos extremos,
                    generacion volumetrica uniforme opcional
  - transient_1d : misma barra, condicion inicial uniforme, extremos fijados
                    a T=0 en t=0+, integracion Crank-Nicolson en el tiempo
  - steady_2d    : placa rectangular, malla de triangulos lineales (misma
                    familia que plane_stress_tool/thermal_structural_tool
                    pero con temperatura como GDL escalar en vez de
                    desplazamiento vectorial); tres lados a T1, un lado a T2

Validado contra:
  - steady_1d (q_gen=0):  T(x) = T0 + (TL-T0)*x/L                          (perfil lineal)
  - steady_1d (q_gen!=0): T(x) = T0 + [(TL-T0)/L + q*L/(2k)]*x - q/(2k)*x^2 (parabola exacta,
                           de k*T''=-q con T(0)=T0, T(L)=TL)
  - transient_1d:         theta(x,t) = sum_{n=1,3,5,...} (4/(n*pi))*Ti*sin(n*pi*x/L)
                                        * exp(-n^2*pi^2*alpha*t/L^2)
                           (serie de Fourier, losa con ambos extremos a T=0 para t>0,
                           condicion inicial uniforme Ti -- caso estandar de libro de
                           texto, ej. Incropera / Carslaw & Jaeger)
  - steady_2d:             theta(x,y) = (2/pi) * sum_{n=1,3,5,...} (2/n) * sin(n*pi*x/Lx)
                                          * sinh(n*pi*y/Lx)/sinh(n*pi*Ly/Lx)
                           (placa rectangular, tres lados a T1 y uno a T2 --
                           caso estandar de libro de texto, ej. Incropera cap. 4).
                           Comparacion excluye las dos esquinas donde la condicion
                           de borde es discontinua (T1 y T2 chocan) -- ahi la
                           solucion verdadera es multivaluada y ni la serie ni el
                           FEM pueden converger a un unico valor.
"""
import numpy as np

THERMAL_CONDUCTION_TOOL_SCHEMA = {
    "name": "thermal_conduction_tool",
    "description": (
        "Conduccion de calor FEM: steady_1d (barra 1D estacionaria, Dirichlet en "
        "ambos extremos, generacion volumetrica uniforme opcional), transient_1d "
        "(misma barra, Crank-Nicolson en el tiempo, extremos fijados a T=0 en "
        "t=0+), y steady_2d (placa rectangular via triangulos lineales, tres "
        "lados a T1 y uno a T2). Validado contra soluciones analiticas de libro "
        "de texto (perfil lineal/parabolico en steady_1d, serie de Fourier en "
        "transient_1d y steady_2d)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["steady_1d", "transient_1d", "steady_2d", "validate"]},
            "params": {"type": "object", "description": "Parametros especificos de cada modo, ver docstring."},
        },
        "required": ["mode"],
    },
}


def _steady_1d(k=200.0, A=0.001, L=1.0, T0=100.0, TL=20.0, q_gen=0.0, n_el=20):
    """
    k [W/m/K], A [m^2], L [m], T0/TL: Dirichlet en x=0 / x=L,
    q_gen [W/m^3]: generacion volumetrica uniforme (default 0).
    """
    n_nodes = n_el + 1
    le = L / n_el
    x = np.linspace(0.0, L, n_nodes)

    ke = (k * A / le) * np.array([[1, -1], [-1, 1]])
    K = np.zeros((n_nodes, n_nodes))
    for e in range(n_el):
        K[e:e + 2, e:e + 2] += ke

    fe = q_gen * A * le / 2.0 * np.array([1.0, 1.0])
    F = np.zeros(n_nodes)
    for e in range(n_el):
        F[e:e + 2] += fe

    free = list(range(1, n_nodes - 1))
    T_full = np.zeros(n_nodes)
    T_full[0] = T0
    T_full[-1] = TL
    if free:
        F_mod = (F[free]
                  - K[np.ix_(free, [0])].flatten() * T0
                  - K[np.ix_(free, [n_nodes - 1])].flatten() * TL)
        Kff = K[np.ix_(free, free)]
        T_full[free] = np.linalg.solve(Kff, F_mod)

    if q_gen == 0.0:
        T_analytic = T0 + (TL - T0) * x / L
    else:
        C1 = (TL - T0) / L + q_gen * L / (2.0 * k)
        T_analytic = T0 + C1 * x - q_gen / (2.0 * k) * x**2

    err = np.abs(T_full - T_analytic)
    denom = np.maximum(np.abs(T_analytic), 1e-9)
    rel_err_pct = float(np.max(100.0 * err / denom))

    return {
        "mode": "steady_1d",
        "x": x.tolist(),
        "temperature_fem": T_full.tolist(),
        "temperature_analytic": T_analytic.tolist(),
        "max_relative_error_pct": rel_err_pct,
    }


def _transient_1d(k=200.0, rho=8000.0, cp=500.0, A=0.001, L=1.0, T_i=100.0,
                   n_el=20, t_final=50.0, n_steps=500, n_fourier_terms=99,
                   eval_fraction=0.5):
    """
    Condicion inicial T(x,0)=T_i uniforme; T(0,t)=T(L,t)=0 para t>0.
    k [W/m/K], rho [kg/m^3], cp [J/kg/K] -> alpha = k/(rho*cp).
    eval_fraction: fraccion de t_final en la que se compara max_relative_error_pct
    (t_final en si puede tener theta~0 en los extremos y errores relativos ruidosos
    solo ahi; se reporta tambien el estado final completo igualmente).
    """
    alpha = k / (rho * cp)
    n_nodes = n_el + 1
    le = L / n_el
    x = np.linspace(0.0, L, n_nodes)
    dt = t_final / n_steps

    ke = (k * A / le) * np.array([[1, -1], [-1, 1]])
    me = (rho * cp * A * le / 6.0) * np.array([[2, 1], [1, 2]])
    K = np.zeros((n_nodes, n_nodes))
    M = np.zeros((n_nodes, n_nodes))
    for e in range(n_el):
        K[e:e + 2, e:e + 2] += ke
        M[e:e + 2, e:e + 2] += me

    T = np.full(n_nodes, float(T_i))
    T[0] = 0.0
    T[-1] = 0.0

    free = list(range(1, n_nodes - 1))
    Mff = M[np.ix_(free, free)]
    Kff = K[np.ix_(free, free)]
    A_lhs = Mff / dt + Kff / 2.0
    A_rhs = Mff / dt - Kff / 2.0

    eval_time = eval_fraction * t_final
    n_eval_steps = int(round(eval_time / dt))
    T_at_eval = None

    for step in range(n_steps):
        rhs = A_rhs @ T[free]
        T[free] = np.linalg.solve(A_lhs, rhs)
        T[0] = 0.0
        T[-1] = 0.0
        if step + 1 == n_eval_steps:
            T_at_eval = T.copy()

    if T_at_eval is None:
        T_at_eval = T.copy()

    def fourier_solution(t):
        n_range = np.arange(1, 2 * n_fourier_terms, 2)
        T_an = np.zeros(n_nodes)
        for n in n_range:
            coeff = (4.0 / (n * np.pi)) * T_i
            T_an += coeff * np.sin(n * np.pi * x / L) * np.exp(-(n**2) * (np.pi**2) * alpha * t / L**2)
        return T_an

    T_analytic_eval = fourier_solution(eval_time)
    T_analytic_final = fourier_solution(t_final)

    denom = np.maximum(np.abs(T_analytic_eval), 1e-3 * T_i)
    mask = np.abs(T_analytic_eval) > 1e-3 * T_i
    err = np.abs(T_at_eval - T_analytic_eval)
    rel_err_pct = float(np.max(100.0 * err[mask] / denom[mask])) if mask.any() else 0.0

    return {
        "mode": "transient_1d",
        "t_eval": eval_time,
        "t_final": t_final,
        "x": x.tolist(),
        "temperature_fem_at_t_eval": T_at_eval.tolist(),
        "temperature_analytic_at_t_eval": T_analytic_eval.tolist(),
        "temperature_fem_at_t_final": T.tolist(),
        "temperature_analytic_at_t_final": T_analytic_final.tolist(),
        "max_relative_error_pct": rel_err_pct,
    }


def _build_rect_mesh(nx, ny, Lx, Ly):
    xs = np.linspace(0.0, Lx, nx + 1)
    ys = np.linspace(0.0, Ly, ny + 1)
    nodes = []
    node_id = {}
    idx = 0
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            nodes.append((x, y))
            node_id[(i, j)] = idx
            idx += 1
    triangles = []
    for j in range(ny):
        for i in range(nx):
            n00 = node_id[(i, j)]
            n10 = node_id[(i + 1, j)]
            n01 = node_id[(i, j + 1)]
            n11 = node_id[(i + 1, j + 1)]
            triangles.append((n00, n10, n11))
            triangles.append((n00, n11, n01))
    return np.array(nodes), triangles


def _sinh_ratio(a, b):
    # sinh(a)/sinh(b) para 0<=a<=b, forma estable para a,b grandes:
    # sinh(a)/sinh(b) = (exp(a-b) - exp(-a-b)) / (1 - exp(-2b))
    return (np.exp(a - b) - np.exp(-a - b)) / (1.0 - np.exp(-2.0 * b))


def _steady_2d(k=1.0, thickness=1.0, Lx=1.0, Ly=1.0, T1=0.0, T2=100.0,
               nx=20, ny=20, n_fourier_terms=60):
    """
    Placa rectangular, tres lados (x=0, x=Lx, y=0) a T1, lado y=Ly a T2.
    k [W/m/K], thickness [m], Lx/Ly [m], T1/T2 [K o C].
    """
    nodes, triangles = _build_rect_mesh(nx, ny, Lx, Ly)
    n_nodes = len(nodes)
    K = np.zeros((n_nodes, n_nodes))
    for (i1, i2, i3) in triangles:
        x1, y1 = nodes[i1]
        x2, y2 = nodes[i2]
        x3, y3 = nodes[i3]
        b = np.array([y2 - y3, y3 - y1, y1 - y2])
        c = np.array([x3 - x2, x1 - x3, x2 - x1])
        area2 = x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)
        area = abs(area2) / 2.0
        ke = k * thickness / (4.0 * area) * (np.outer(b, b) + np.outer(c, c))
        idx = [i1, i2, i3]
        for a in range(3):
            for bb in range(3):
                K[idx[a], idx[bb]] += ke[a, bb]

    T_full = np.zeros(n_nodes)
    fixed = set()
    tol = 1e-9
    for i, (x, y) in enumerate(nodes):
        if abs(y - 0.0) < tol or abs(x - 0.0) < tol or abs(x - Lx) < tol:
            T_full[i] = T1
            fixed.add(i)
        elif abs(y - Ly) < tol:
            T_full[i] = T2
            fixed.add(i)

    free = [i for i in range(n_nodes) if i not in fixed]
    fixed_list = list(fixed)
    if free:
        F_mod = -K[np.ix_(free, fixed_list)] @ T_full[fixed_list]
        Kff = K[np.ix_(free, free)]
        T_full[free] = np.linalg.solve(Kff, F_mod)

    def analytic(x, y):
        theta = 0.0
        for n in range(1, 2 * n_fourier_terms, 2):  # solo impares
            a = n * np.pi * y / Lx
            bb = n * np.pi * Ly / Lx
            theta += (2.0 / n) * np.sin(n * np.pi * x / Lx) * _sinh_ratio(a, bb)
        theta *= 2.0 / np.pi
        return T1 + theta * (T2 - T1)

    T_analytic = np.array([analytic(x, y) for x, y in nodes])

    corner_dist = np.minimum(
        np.hypot(nodes[:, 0] - 0.0, nodes[:, 1] - Ly),
        np.hypot(nodes[:, 0] - Lx, nodes[:, 1] - Ly),
    )
    corner_exclusion = 0.2 * min(Lx, Ly)
    mask = corner_dist > corner_exclusion

    err = np.abs(T_full - T_analytic)
    denom = max(abs(T2 - T1), 1e-9)
    rel_err_pct = float(np.max(100.0 * err[mask] / denom))

    return {
        "mode": "steady_2d",
        "n_nodes": n_nodes,
        "n_triangles": len(triangles),
        "temperature_fem": T_full.tolist(),
        "temperature_analytic": T_analytic.tolist(),
        "max_relative_error_pct": rel_err_pct,
        "max_relative_error_pct_including_corners": float(np.max(100.0 * err / denom)),
    }


def _mode_validate():
    r_lin = _steady_1d(k=15.0, A=0.01, L=1.0, T0=100.0, TL=20.0, q_gen=0.0, n_el=20)
    r_gen = _steady_1d(k=15.0, A=0.01, L=1.0, T0=100.0, TL=20.0, q_gen=5e4, n_el=20)
    r_trans = _transient_1d(k=15.0, rho=7800.0, cp=460.0, A=0.01, L=0.1, T_i=100.0,
                             n_el=40, t_final=358.8, n_steps=1600, eval_fraction=0.5)
    r_2d = _steady_2d(k=15.0, thickness=0.01, Lx=1.0, Ly=1.0, T1=20.0, T2=100.0,
                       nx=30, ny=30, n_fourier_terms=80)

    checks = {
        "steady_linear_matches_analytic": r_lin["max_relative_error_pct"] < 1e-6,
        "steady_generation_matches_analytic": r_gen["max_relative_error_pct"] < 1.0,
        "transient_matches_fourier_series": r_trans["max_relative_error_pct"] < 1.0,
        "steady_2d_matches_fourier_series": r_2d["max_relative_error_pct"] < 1.0,
    }
    return {
        "mode": "validate",
        "steady_1d_linear": r_lin,
        "steady_1d_with_generation": r_gen,
        "transient_1d": r_trans,
        "steady_2d": r_2d,
        "checks": checks,
        "expected": (
            "steady_1d sin generacion: perfil exactamente lineal (FEM lineal es "
            "exacto para conduccion pura sin generacion, error debe ser ~0). Con "
            "generacion uniforme: parabola exacta de k*T''=-q, error <1%%. "
            "transient_1d: coincide con la serie de Fourier de la losa con "
            "extremos a T=0 y condicion inicial uniforme (Incropera / Carslaw & "
            "Jaeger), error <1%% lejos de los extremos. steady_2d: coincide con "
            "la serie de Fourier de la placa rectangular con tres lados a T1 y "
            "uno a T2 (Incropera cap. 4), error <1%% excluyendo las dos esquinas "
            "con condicion de borde discontinua."
        ),
        "validation_passed": all(checks.values()),
    }


def compute_thermal_conduction(mode, params=None):
    params = params or {}
    if mode == "steady_1d":
        return _steady_1d(**params)
    elif mode == "transient_1d":
        return _transient_1d(**params)
    elif mode == "steady_2d":
        return _steady_2d(**params)
    elif mode == "validate":
        return _mode_validate()
    else:
        raise ValueError(f"modo desconocido: {mode}. Use steady_1d | transient_1d | steady_2d | validate")


if __name__ == "__main__":
    import json
    print(json.dumps(compute_thermal_conduction("validate"), indent=2))
