"""
pde_tool.py

Ecuaciones en derivadas parciales via diferencias finitas explicitas en
Octave: ecuacion de calor (u_t = alpha*u_xx) y ecuacion de onda
(u_tt = c^2*u_xx) en 1D, con condiciones de borde Dirichlet homogeneas.

Extension natural de stiff_ode_tool (que resuelve EDOs) hacia EDPs.
Relevante para simular propagacion termica en el sistema LIG sobre madera
de coigue (ecuacion de calor 1D como primera aproximacion antes de ir a
2D/3D) o vibracion de estructuras.

Esquemas explicitos: estables solo bajo condicion CFL --
calor: r = alpha*dt/dx^2 <= 0.5
onda:  courant = c*dt/dx <= 1
El modulo calcula dt automaticamente para cumplir la condicion con margen,
y lo reporta explicitamente en el output.

Mismo patron de validacion: para el primer modo normal (condicion inicial
sinusoidal, bordes fijos en 0) existe solucion analitica exacta --
calor: u(x,t) = sin(pi*x/L)*exp(-alpha*(pi/L)^2*t)
onda:  u(x,t) = sin(pi*x/L)*cos(c*pi/L*t)
-- se compara el resultado numerico contra esa solucion para validar el
esquema antes de aplicarlo a condiciones iniciales custom.
"""
import subprocess
import tempfile
import os
import math

PDE_SCHEMA = {
    "name": "compute_pde",
    "description": (
        "Ecuaciones en derivadas parciales via diferencias finitas "
        "explicitas en Octave: heat_equation (u_t=alpha*u_xx) y "
        "wave_equation (u_tt=c^2*u_xx) en 1D, bordes Dirichlet=0. Preset "
        "'known_first_mode' compara contra solucion analitica exacta del "
        "primer modo normal (condicion inicial sin(pi*x/L)). 'custom' "
        "acepta perfil inicial arbitrario via 'initial_profile'."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["heat_equation", "wave_equation"], "default": "heat_equation"},
            "preset": {"type": "string", "enum": ["known_first_mode", "custom"], "default": "known_first_mode"},
            "L": {"type": "number", "default": 1.0, "description": "Longitud del dominio"},
            "coefficient": {"type": "number", "default": 0.01, "description": "alpha (calor) o c (onda)"},
            "n_points": {"type": "integer", "default": 50, "description": "Puntos en el eje espacial"},
            "t_final": {"type": "number", "default": None, "description": "Tiempo final. Si None, se elige automaticamente"},
            "initial_profile": {"type": "array", "description": "Perfil inicial u(x,0), solo si preset='custom'. Longitud debe ser n_points"},
        },
    },
}


def _run_octave(code, timeout=30):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as fh:
        fh.write(code)
        script_path = fh.name
    try:
        r = subprocess.run(["octave", "--no-gui", "--no-init-file", script_path],
                            capture_output=True, text=True, timeout=timeout)
    finally:
        os.unlink(script_path)
    if r.returncode != 0:
        return None, r.stderr.strip()
    return r.stdout.strip(), None


def _vec_to_octave(v):
    return "[" + ",".join(str(x) for x in v) + "]"


def compute_pde(mode="heat_equation", preset="known_first_mode", L=1.0, coefficient=0.01,
                 n_points=50, t_final=None, initial_profile=None):
    known = None
    dx = L / (n_points - 1)

    if mode == "heat_equation":
        alpha = coefficient
        dt = 0.4 * dx ** 2 / alpha  # r=0.4 < 0.5, margen de seguridad bajo CFL
        r = alpha * dt / dx ** 2
        if t_final is None:
            t_final = 500 * dt
        n_steps = max(1, int(round(t_final / dt)))
        t_actual = n_steps * dt

        if preset == "custom":
            if not initial_profile or len(initial_profile) != n_points:
                return {"error": f"preset='custom' requiere 'initial_profile' de longitud {n_points}"}
            u0 = initial_profile
        elif preset == "known_first_mode":
            u0 = [math.sin(math.pi * i * dx / L) for i in range(n_points)]
            known = {
                "solucion_analitica": "u(x,t) = sin(pi*x/L) * exp(-alpha*(pi/L)^2*t)",
                "nota": "primer modo normal de la ecuacion de calor con bordes fijos en 0",
            }
        else:
            return {"error": f"preset '{preset}' no aplica"}

        u0_str = _vec_to_octave(u0)
        code = f"""
u = {u0_str}';
nx = {n_points};
r = {r};
n_steps = {n_steps};
for step = 1:n_steps
  u_new = u;
  u_new(2:end-1) = u(2:end-1) + r*(u(3:end) - 2*u(2:end-1) + u(1:end-2));
  u_new(1) = 0; u_new(end) = 0;
  u = u_new;
end
printf("%.10f ", u);
"""
        out, err = _run_octave(code)
        if out is None:
            return {"error": "octave fallo", "stderr": err}
        u_final = [float(v) for v in out.split()]

        result = {
            "mode": "heat_equation", "L": L, "alpha": alpha, "n_points": n_points,
            "dx": round(dx, 6), "dt": round(dt, 8), "cfl_r": round(r, 4),
            "cfl_stable": r <= 0.5, "n_steps": n_steps, "t_final": round(t_actual, 6),
            "u_final_sample": [round(v, 6) for v in u_final[::max(1, n_points // 10)]],
        }
        if known:
            x_vals = [i * dx for i in range(n_points)]
            u_analytic = [math.sin(math.pi * xi / L) * math.exp(-alpha * (math.pi / L) ** 2 * t_actual) for xi in x_vals]
            max_err = max(abs(a - b) for a, b in zip(u_final, u_analytic))
            result["max_error_vs_analytic"] = round(max_err, 8)
            result["known_reference"] = known

    elif mode == "wave_equation":
        c = coefficient
        courant = 0.5
        dt = courant * dx / c
        if t_final is None:
            t_final = 200 * dt
        n_steps = max(1, int(round(t_final / dt)))
        t_actual = n_steps * dt

        if preset == "custom":
            if not initial_profile or len(initial_profile) != n_points:
                return {"error": f"preset='custom' requiere 'initial_profile' de longitud {n_points}"}
            u0 = initial_profile
        elif preset == "known_first_mode":
            u0 = [math.sin(math.pi * i * dx / L) for i in range(n_points)]
            known = {
                "solucion_analitica": "u(x,t) = sin(pi*x/L) * cos(c*pi/L*t)",
                "nota": "primer modo normal de la ecuacion de onda, velocidad inicial cero",
            }
        else:
            return {"error": f"preset '{preset}' no aplica"}

        u0_str = _vec_to_octave(u0)
        code = f"""
u_prev = {u0_str}';
u_curr = u_prev;  % velocidad inicial = 0
nx = {n_points};
courant = {courant};
n_steps = {n_steps};
for step = 1:n_steps
  u_next = zeros(nx,1);
  u_next(2:end-1) = 2*u_curr(2:end-1) - u_prev(2:end-1) + courant^2*(u_curr(3:end) - 2*u_curr(2:end-1) + u_curr(1:end-2));
  u_next(1) = 0; u_next(end) = 0;
  u_prev = u_curr;
  u_curr = u_next;
end
printf("%.10f ", u_curr);
"""
        out, err = _run_octave(code)
        if out is None:
            return {"error": "octave fallo", "stderr": err}
        u_final = [float(v) for v in out.split()]

        result = {
            "mode": "wave_equation", "L": L, "c": c, "n_points": n_points,
            "dx": round(dx, 6), "dt": round(dt, 8), "courant_number": courant,
            "cfl_stable": courant <= 1.0, "n_steps": n_steps, "t_final": round(t_actual, 6),
            "u_final_sample": [round(v, 6) for v in u_final[::max(1, n_points // 10)]],
        }
        if known:
            x_vals = [i * dx for i in range(n_points)]
            u_analytic = [math.sin(math.pi * xi / L) * math.cos(c * math.pi / L * t_actual) for xi in x_vals]
            max_err = max(abs(a - b) for a, b in zip(u_final, u_analytic))
            result["max_error_vs_analytic"] = round(max_err, 8)
            result["known_reference"] = known

    else:
        return {"error": f"mode desconocido: {mode}"}

    return result


if __name__ == "__main__":
    import json
    print(json.dumps(compute_pde("heat_equation", "known_first_mode"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_pde("wave_equation", "known_first_mode"), indent=2, ensure_ascii=False))
