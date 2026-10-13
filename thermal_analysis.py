"""
thermal_analysis: modo nuevo para finite_element_tool.
Conduccion de calor 1D/2D estacionaria y transitoria, FEM lineal.
"""
import numpy as np

def steady_1d(length, n_nodes, k, T_left, T_right, q=None):
    """
    Conduccion estacionaria 1D: d/dx(k dT/dx) = -q (q = fuente interna, opcional)
    FEM con elementos lineales de 2 nodos. BCs Dirichlet en ambos extremos.
    """
    n_el = n_nodes - 1
    dx = length / n_el
    K = np.zeros((n_nodes, n_nodes))
    F = np.zeros(n_nodes)
    ke = (k / dx) * np.array([[1, -1], [-1, 1]])
    for e in range(n_el):
        K[e:e+2, e:e+2] += ke
        if q is not None:
            fe = q * dx / 2 * np.array([1, 1])
            F[e:e+2] += fe
    # Dirichlet BCs
    K[0, :] = 0; K[0, 0] = 1; F[0] = T_left
    K[-1, :] = 0; K[-1, -1] = 1; F[-1] = T_right
    T = np.linalg.solve(K, F)
    x = np.linspace(0, length, n_nodes)
    return x, T

def transient_1d(length, n_nodes, alpha, T_initial, T_left, T_right, t_end, n_steps):
    """
    Conduccion transitoria 1D: dT/dt = alpha * d2T/dx2
    FEM en espacio (elementos lineales) + Euler implicito en el tiempo.
    Condicion inicial uniforme T_initial, extremos fijos Dirichlet.
    """
    n_el = n_nodes - 1
    dx = length / n_el
    dt = t_end / n_steps
    M = np.zeros((n_nodes, n_nodes))  # matriz de masa (capacitancia)
    K = np.zeros((n_nodes, n_nodes))  # matriz de rigidez (conductancia)
    me = (dx / 6) * np.array([[2, 1], [1, 2]])
    ke = (alpha / dx) * np.array([[1, -1], [-1, 1]])
    for e in range(n_el):
        M[e:e+2, e:e+2] += me
        K[e:e+2, e:e+2] += ke
    T = np.full(n_nodes, T_initial, dtype=float)
    T[0] = T_left; T[-1] = T_right
    A = M + dt * K
    A[0, :] = 0; A[0, 0] = 1
    A[-1, :] = 0; A[-1, -1] = 1
    for _ in range(n_steps):
        b = M @ T
        b[0] = T_left
        b[-1] = T_right
        T = np.linalg.solve(A, b)
    x = np.linspace(0, length, n_nodes)
    return x, T

def steady_2d(Lx, Ly, nx, ny, T_top, T_bottom=0.0, T_left=0.0, T_right=0.0):
    """
    Laplace 2D en rectangulo: d2T/dx2 + d2T/dy2 = 0
    Diferencias finitas 5 puntos (equivalente a FEM bilineal en malla estructurada
    para este caso). BCs Dirichlet en los 4 bordes.
    """
    dx = Lx / (nx - 1)
    dy = Ly / (ny - 1)
    N = nx * ny
    A = np.zeros((N, N))
    b = np.zeros(N)
    def idx(i, j):
        return j * nx + i
    for j in range(ny):
        for i in range(nx):
            k = idx(i, j)
            if i == 0:
                A[k, k] = 1; b[k] = T_left
            elif i == nx - 1:
                A[k, k] = 1; b[k] = T_right
            elif j == 0:
                A[k, k] = 1; b[k] = T_bottom
            elif j == ny - 1:
                A[k, k] = 1; b[k] = T_top
            else:
                A[k, k] = -2 / dx**2 - 2 / dy**2
                A[k, idx(i+1, j)] = 1 / dx**2
                A[k, idx(i-1, j)] = 1 / dx**2
                A[k, idx(i, j+1)] = 1 / dy**2
                A[k, idx(i, j-1)] = 1 / dy**2
    T = np.linalg.solve(A, b)
    return T.reshape(ny, nx)

if __name__ == "__main__":
    # --- Validacion 1: steady_1d contra solucion analitica lineal ---
    x, T = steady_1d(length=1.0, n_nodes=11, k=10.0, T_left=100.0, T_right=0.0)
    T_analytic = 100.0 + (0.0 - 100.0) * x / 1.0
    err = np.max(np.abs(T - T_analytic))
    print(f"[steady_1d] error maximo vs analitico: {err:.2e}")
    assert err < 1e-10, "steady_1d no coincide con la solucion analitica"

    # --- Validacion 2: transient_1d contra serie de Fourier ---
    # Barra con T_inicial=1 en todo el dominio, extremos T=0 (Dirichlet), sin fuente.
    # Solucion analitica: T(x,t) = sum_n (4/(n*pi)) sin(n*pi*x/L) exp(-alpha*(n*pi/L)^2*t), n impar
    L = 1.0
    alpha = 0.01
    t_end = 2.0
    x, T = transient_1d(length=L, n_nodes=41, alpha=alpha, T_initial=1.0,
                         T_left=0.0, T_right=0.0, t_end=t_end, n_steps=400)
    def fourier_solution(x, t, L, alpha, n_terms=100):
        T = np.zeros_like(x)
        for n in range(1, n_terms * 2, 2):  # solo n impar
            T += (4 / (n * np.pi)) * np.sin(n * np.pi * x / L) * np.exp(-alpha * (n * np.pi / L)**2 * t)
        return T
    T_analytic = fourier_solution(x, t_end, L, alpha)
    err = np.max(np.abs(T - T_analytic))
    print(f"[transient_1d] error maximo vs serie de Fourier (100 terminos): {err:.4f} (T max = {T.max():.4f})")
    assert err < 0.02, "transient_1d se desvia demasiado de la solucion analitica"

    # --- Validacion 3: steady_2d contra solucion analitica de Laplace ---
    # Rectangulo Lx=Ly=1, T=T0 en el borde superior, 0 en los otros tres.
    # Solucion analitica (separacion de variables):
    # T(x,y) = sum_n (2*T0/(n*pi)) * (1-(-1)^n) * sinh(n*pi*y/Lx)/sinh(n*pi*Ly/Lx) * sin(n*pi*x/Lx)
    T0 = 100.0
    Lx = Ly = 1.0
    nx = ny = 21
    T2d = steady_2d(Lx, Ly, nx, ny, T_top=T0)
    def laplace_analytic(x, y, Lx, Ly, T0, n_terms=200):
        T = np.zeros_like(x)
        for n in range(1, n_terms + 1):
            coef = (2 * T0 / (n * np.pi)) * (1 - (-1)**n)
            if coef == 0:
                continue
            T += coef * np.sinh(n * np.pi * y / Lx) / np.sinh(n * np.pi * Ly / Lx) * np.sin(n * np.pi * x / Lx)
        return T
    xs = np.linspace(0, Lx, nx)
    ys = np.linspace(0, Ly, ny)
    Xg, Yg = np.meshgrid(xs, ys)
    T_analytic_2d = laplace_analytic(Xg, Yg, Lx, Ly, T0)
    # comparar solo puntos interiores (evitar bordes con posible mala convergencia de la serie)
    err = np.max(np.abs(T2d[1:-1, 1:-1] - T_analytic_2d[1:-1, 1:-1]))
    print(f"[steady_2d] error maximo vs analitico (interior): {err:.4f} (T max = {T2d.max():.4f})")
    assert err < 1.0, "steady_2d se desvia demasiado de la solucion analitica"

    print("\nTodas las validaciones de thermal_analysis pasaron OK.")
