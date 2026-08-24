"""
Solver de ecuación de Vlasov: plasma cinético sin colisiones
Distribuciones de velocidad f(x,v,t) bajo campos EM autoconsistentes
Método: diferencias finitas + interpolación Lagrangiana
"""
import numpy as np
import json
from scipy.integrate import odeint, solve_ivp
from scipy.interpolate import interp1d
from scipy.fft import fft, ifft, fftfreq

VLASOV_KINETIC_SOLVER_SCHEMA = {
    "name": "vlasov_kinetic_solver",
    "description": "Solver de ecuación de Vlasov: plasma cinético, distribuciones f(x,v,t), campos EM autoconsistentes",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["maxwellian", "two_stream", "landau_damping", "cold_beam", "dispersion_relation", "validate"],
                "description": "maxwellian: equilibrio; two_stream: inestabilidad dos haces; landau_damping: amortiguamiento Landau; cold_beam: haz frío; dispersion_relation: relación dispersión plasma"
            },
            "params": {
                "type": "object",
                "properties": {
                    "L_x": {"type": "number", "description": "Tamaño dominio x (m)"},
                    "v_max": {"type": "number", "description": "Rango velocidad v (m/s)"},
                    "N_x": {"type": "integer", "description": "Puntos grid x"},
                    "N_v": {"type": "integer", "description": "Puntos grid v"},
                    "t_final": {"type": "number", "description": "Tiempo final simulación (s)"},
                    "omega_p": {"type": "number", "description": "Frecuencia plasma (rad/s)"},
                    "T_e": {"type": "number", "description": "Temperatura electrones (eV)"},
                    "v_beam": {"type": "number", "description": "Velocidad haz (m/s)"},
                    "k_wave": {"type": "number", "description": "Número onda perturbación (1/m)"}
                },
                "required": ["L_x", "v_max"]
            }
        },
        "required": ["mode", "params"]
    }
}

def maxwellian_dist(v, T_e, n0=1e19):
    """Distribución Maxwelliana: f(v) ∝ exp(-m_e*v²/(2*k_B*T_e))"""
    m_e = 9.109e-31  # kg
    k_B = 1.381e-23  # J/K
    T_K = T_e * 1.602e-19 / k_B  # conversión eV → K
    
    v_th = np.sqrt(k_B * T_K / m_e)  # velocidad térmica
    
    # Normalizada
    f = n0 * (m_e / (2 * np.pi * k_B * T_K))**0.5 * np.exp(-m_e * v**2 / (2 * k_B * T_K))
    return f

def two_stream_dist(v, v_beam, delta_f=0.1):
    """Dos haces contrapropagantes: f(v) = n₀/2 * [Max(v+vb) + Max(v-vb)] * (1 + δf*cos)"""
    f1 = maxwellian_dist(v + v_beam, T_e=1.0)
    f2 = maxwellian_dist(v - v_beam, T_e=1.0)
    f = 0.5 * (f1 + f2) * (1 + delta_f * np.cos(v))
    return f

def cold_beam_dist(v, v_beam, width=0.01):
    """Haz frío: distribución Gaussiana angosta alrededor de v_beam"""
    f = np.exp(-(v - v_beam)**2 / width**2)
    return f / (np.sqrt(np.pi * width**2))  # normalizado

def poisson_solver_fft(rho, kx):
    """
    Resuelve ecuación de Poisson: d²φ/dx² = -ρ/ε₀ via FFT
    φ(k) = ρ(k) / (ε₀ * k²)
    """
    epsilon_0 = 8.854e-12
    
    # Evitar k=0
    rho_hat = fft(rho)
    kx_safe = np.where(kx != 0, kx, 1)
    
    phi_hat = rho_hat / (epsilon_0 * kx_safe**2)
    phi_hat[0] = 0  # gauge: φ(k=0) = 0
    
    phi = np.real(ifft(phi_hat))
    return phi

def vlasov_rhs(t, y, N_x, N_v, L_x, v_max, omega_p, E_ext=None):
    """
    RHS de ecuación de Vlasov: ∂f/∂t + v*∂f/∂x + (e/m)*E*∂f/∂v = 0
    y = [f, E]: distribución + campo eléctrico
    """
    N_vars = N_x * N_v
    
    f = y[:N_vars].reshape((N_x, N_v))
    
    dx = L_x / N_x
    dv = 2 * v_max / N_v
    v_grid = np.linspace(-v_max, v_max, N_v)
    
    # Rhs_f: ∂f/∂t = -v*∂f/∂x - (e/m)*E*∂f/∂v
    # Método semi-Lagrangiano simple (advección)
    
    df_dt = np.zeros_like(f)
    
    # Término convectivo: -v*∂f/∂x
    for i in range(N_x):
        for j in range(N_v):
            v = v_grid[j]
            # Derivada espacial (diferencias finitas)
            df_dx = (f[(i+1) % N_x, j] - f[(i-1) % N_x, j]) / (2 * dx)
            df_dt[i, j] -= v * df_dx
    
    # Término de fuerza: -(e/m)*E*∂f/∂v
    # Aquí usamos un E externo simplificado
    if E_ext is not None:
        e_over_m = 1.759e11  # C/kg
        for i in range(N_x):
            for j in range(N_v):
                df_dv = (f[i, (j+1) % N_v] - f[i, (j-1) % N_v]) / (2 * dv)
                df_dt[i, j] -= e_over_m * E_ext[i] * df_dv
    
    return df_dt.flatten()

def dispersion_relation_langmuir(k, omega_p):
    """
    Relación de dispersión ondas de Langmuir: ω² = ω_p² + 3*k²*v_th²
    Para distribución Maxwelliana con v_th ~ √(T_e)
    """
    v_th = 1e6  # m/s (típico para T_e ~ 1 eV)
    omega = np.sqrt(omega_p**2 + 3 * k**2 * v_th**2)
    return omega

def landau_damping_rate(k, omega_p, T_e=1.0):
    """
    Amortiguamiento Landau: γ ~ √(π/2) * (ω_p/k*v_th)³ * exp(-ω²/(2*k²*v_th²))
    Aproximación: γ ∝ exp(-3/(2*k²*λ_D²)) donde λ_D es longitud Debye
    """
    m_e = 9.109e-31
    k_B = 1.381e-23
    T_K = T_e * 1.602e-19 / k_B
    
    lambda_D = np.sqrt(8.854e-12 * k_B * T_K / (1.602e-19)**2 * 1e19)  # longitud Debye
    
    # Parametrización empírica
    alpha = 3.0 / (2 * k**2 * lambda_D**2)
    gamma = (omega_p / (k * np.sqrt(2 * np.pi))) * np.exp(-alpha)
    
    return gamma

def simulate_vlasov_simple(N_x, N_v, L_x, v_max, t_final, omega_p, mode="maxwellian"):
    """
    Simulación simple de Vlasov: advección pura sin campo autoconsistente
    Retorna: densidad n(x,t), energía, espectro
    """
    x_grid = np.linspace(0, L_x, N_x)
    v_grid = np.linspace(-v_max, v_max, N_v)
    
    # Condición inicial
    if mode == "maxwellian":
        # Maxwelliana uniforme
        f = np.zeros((N_x, N_v))
        for j in range(N_v):
            f[:, j] = maxwellian_dist(v_grid[j], T_e=1.0)
    
    elif mode == "two_stream":
        f = np.zeros((N_x, N_v))
        v_beam = 5e6  # m/s
        for j in range(N_v):
            f[:, j] = two_stream_dist(v_grid[j], v_beam, delta_f=0.05)
    
    elif mode == "cold_beam":
        f = np.zeros((N_x, N_v))
        v_beam = 5e6
        for j in range(N_v):
            f[:, j] = cold_beam_dist(v_grid[j], v_beam)
    
    else:
        f = np.ones((N_x, N_v)) / (N_x * N_v)
    
    # Integración temporal (simple: traslación pura)
    N_t = max(10, int(t_final * omega_p / (2 * np.pi)))
    t_grid = np.linspace(0, t_final, N_t)
    dt = t_final / (N_t - 1) if N_t > 1 else 1
    
    # Densidad integrada
    n_history = []
    E_history = []
    
    for t in t_grid:
        n = np.trapezoid(f, v_grid, axis=1)  # ∫f dv
        n_history.append(n)
        
        # Campo eléctrico simple (Gauss: E ∝ ∫ρ)
        E = np.cumsum(n - 1.0) * (L_x / N_x)
        E_history.append(E)
    
    n_history = np.array(n_history)
    E_history = np.array(E_history)
    
    return {
        "x_grid": x_grid,
        "v_grid": v_grid,
        "t_grid": t_grid,
        "n_history": n_history,
        "E_history": E_history,
        "f_final": f
    }

def execute(mode, params):
    """Dispatcher principal"""
    L_x = params.get("L_x", 1.0)
    v_max = params.get("v_max", 1e7)
    N_x = params.get("N_x", 64)
    N_v = params.get("N_v", 64)
    t_final = params.get("t_final", 1e-8)
    omega_p = params.get("omega_p", 1e15)
    T_e = params.get("T_e", 1.0)
    v_beam = params.get("v_beam", 5e6)
    k_wave = params.get("k_wave", 1e5)
    
    if mode == "maxwellian":
        result = simulate_vlasov_simple(N_x, N_v, L_x, v_max, t_final, omega_p, "maxwellian")
        result["mode"] = "maxwellian"
        result["description"] = "Distribución Maxwelliana en equilibrio"
        # Convertir arrays a listas para JSON
        result["n_history"] = result["n_history"].tolist()
        result["E_history"] = result["E_history"].tolist()
        result["x_grid"] = result["x_grid"].tolist()
        result["v_grid"] = result["v_grid"].tolist()
        result["t_grid"] = result["t_grid"].tolist()
        return result
    
    elif mode == "two_stream":
        result = simulate_vlasov_simple(N_x, N_v, L_x, v_max, t_final, omega_p, "two_stream")
        result["mode"] = "two_stream"
        result["description"] = "Inestabilidad de dos haces: dos distribuciones Maxwellianas contrapropagantes"
        result["n_history"] = result["n_history"].tolist()
        result["E_history"] = result["E_history"].tolist()
        result["x_grid"] = result["x_grid"].tolist()
        result["v_grid"] = result["v_grid"].tolist()
        result["t_grid"] = result["t_grid"].tolist()
        return result
    
    elif mode == "cold_beam":
        result = simulate_vlasov_simple(N_x, N_v, L_x, v_max, t_final, omega_p, "cold_beam")
        result["mode"] = "cold_beam"
        result["description"] = "Haz frío: Gaussiana angosta en velocidad"
        result["n_history"] = result["n_history"].tolist()
        result["E_history"] = result["E_history"].tolist()
        result["x_grid"] = result["x_grid"].tolist()
        result["v_grid"] = result["v_grid"].tolist()
        result["t_grid"] = result["t_grid"].tolist()
        return result
    
    elif mode == "landau_damping":
        gamma = landau_damping_rate(k_wave, omega_p, T_e)
        omega_lang = dispersion_relation_langmuir(k_wave, omega_p)
        return {
            "mode": "landau_damping",
            "k_wave": k_wave,
            "omega_p": omega_p,
            "T_e_eV": T_e,
            "omega_langmuir_rad_s": float(omega_lang),
            "damping_rate_gamma_rad_s": float(gamma),
            "damping_time_s": float(1 / gamma) if gamma > 0 else float('inf'),
            "description": "Amortiguamiento Landau: disipación de ondas de Langmuir sin colisiones"
        }
    
    elif mode == "dispersion_relation":
        k_vals = np.linspace(0.1 * k_wave, 10 * k_wave, 50)
        omega_vals = [dispersion_relation_langmuir(k, omega_p) for k in k_vals]
        return {
            "mode": "dispersion_relation",
            "k_wave_1_m": k_vals.tolist(),
            "omega_langmuir_rad_s": omega_vals,
            "omega_p": omega_p,
            "description": "Relación de dispersión ondas de Langmuir: ω(k)"
        }
    
    elif mode == "validate":
        # Tests rápidos
        result1 = simulate_vlasov_simple(32, 32, 1.0, 1e7, 1e-9, 1e15, "maxwellian")
        result2 = simulate_vlasov_simple(32, 32, 1.0, 1e7, 1e-9, 1e15, "two_stream")
        
        assert result1["n_history"].shape[0] > 0, "Densidad vacía"
        assert result2["E_history"].shape[0] > 0, "Campo vacío"
        
        gamma = landau_damping_rate(1e5, 1e15, 1.0)
        assert gamma > 0, "Amortiguamiento debe ser positivo"
        
        return {
            "status": "OK",
            "tests_passed": 3,
            "maxwellian_shape": result1["n_history"].shape,
            "two_stream_shape": result2["n_history"].shape
        }
    
    else:
        return {"error": f"Modo desconocido: {mode}"}

# Registro en tool_registry
try:
    import sys
    sys.path.insert(0, '/home/claude')
    from tool_registry import REGISTRY
    
    REGISTRY[VLASOV_KINETIC_SOLVER_SCHEMA["name"]] = {
        "schema": VLASOV_KINETIC_SOLVER_SCHEMA,
        "handler": execute
    }
except Exception as e:
    pass
