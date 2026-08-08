"""
reaction_diffusion_tool.py

Inestabilidad de Turing (reaccion-difusion linealizada): un sistema de dos
especies que es estable en ausencia de difusion puede volverse inestable
cuando se agrega difusion con coeficientes distintos -- este es el
mecanismo matematico de 1952 (Turing) que explica patrones biologicos
(rayas, manchas, morfogenesis).

Se trabaja con el sistema linealizado alrededor del estado homogeneo, que
tiene condiciones analiticas exactas (Murray, Mathematical Biology) para
predecir CUANDO ocurre la inestabilidad y CUAL numero de onda crece mas
rapido -- en vez de perseguir formacion de patron no lineal completo
(Gray-Scott, FitzHugh-Nagumo), que es numericamente mucho mas sensible a
parametros y tiempo de integracion sin agregar rigor matematico extra.

Extension directa de pde_tool (que resuelve difusion pura) agregando
terminos de reaccion lineal + acoplamiento entre dos especies.

Validacion: se compara la tasa de crecimiento medida numericamente
(ajuste log-lineal de la amplitud de la perturbacion en el numero de onda
mas inestable, usando el AUTOVECTOR correcto del sistema linealizado como
condicion inicial) contra la tasa de crecimiento analitica exacta.
"""
import subprocess
import tempfile
import os
import math

REACTION_DIFFUSION_SCHEMA = {
    "name": "compute_reaction_diffusion",
    "description": (
        "Inestabilidad de Turing en un sistema de reaccion-difusion "
        "linealizado de 2 especies (du/dt=Du*u_xx+a11*u+a12*v, "
        "dv/dt=Dv*v_xx+a21*u+a22*v). check_turing_instability evalua las "
        "4 condiciones analiticas clasicas (Murray) y calcula el numero de "
        "onda mas inestable. simulate_growth_rate corre la EDP linealizada "
        "en Octave sobre el autovector del modo mas inestable y compara la "
        "tasa de crecimiento numerica contra la analitica."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["check_turing_instability", "simulate_growth_rate"], "default": "check_turing_instability"},
            "a11": {"type": "number", "default": 1.0}, "a12": {"type": "number", "default": -1.0},
            "a21": {"type": "number", "default": 2.0}, "a22": {"type": "number", "default": -1.5},
            "Du": {"type": "number", "default": 1.0}, "Dv": {"type": "number", "default": 10.0},
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


def _eig2x2(M):
    a, b, c, d = M[0][0], M[0][1], M[1][0], M[1][1]
    tr = a + d
    det = a * d - b * c
    disc = tr ** 2 - 4 * det
    if disc >= 0:
        sq = disc ** 0.5
        l1, l2 = (tr + sq) / 2, (tr - sq) / 2
        v1 = _eigvec_real(M, l1)
        return [(l1, v1)]
    else:
        return [(complex(tr / 2, (abs(disc)) ** 0.5 / 2), None)]


def _eigvec_real(M, lam):
    a, b = M[0][0] - lam, M[0][1]
    if abs(b) > 1e-12:
        return (b, lam - M[0][0]) if abs(b) > 1e-12 else (1.0, 0.0)
    c, d = M[1][0], M[1][1] - lam
    if abs(c) > 1e-12:
        return (d, -c)
    return (1.0, 0.0)


def compute_reaction_diffusion(mode="check_turing_instability", a11=1.0, a12=-1.0,
                                a21=2.0, a22=-1.5, Du=1.0, Dv=10.0):
    trace = a11 + a22
    det = a11 * a22 - a12 * a21
    cond1 = trace < 0
    cond2 = det > 0
    turing3 = Dv * a11 + Du * a22
    cond3 = turing3 > 0
    turing4 = turing3 ** 2 - 4 * Du * Dv * det
    cond4 = turing4 > 0
    all_conditions = cond1 and cond2 and cond3 and cond4

    diagnostics = {
        "matrix_A": [[a11, a12], [a21, a22]], "Du": Du, "Dv": Dv,
        "cond1_estable_sin_difusion_trace_negativa": {"cumple": cond1, "valor": round(trace, 6)},
        "cond2_estable_sin_difusion_det_positivo": {"cumple": cond2, "valor": round(det, 6)},
        "cond3_signo_cruzado_difusion": {"cumple": cond3, "valor": round(turing3, 6)},
        "cond4_discriminante_positivo": {"cumple": cond4, "valor": round(turing4, 6)},
        "inestabilidad_turing_presente": all_conditions,
    }

    if not all_conditions:
        diagnostics["nota"] = "no se cumplen las 4 condiciones de Turing -- no hay inestabilidad inducida por difusion con estos parametros"
        if mode == "check_turing_instability":
            return diagnostics
        else:
            return {"error": "simulate_growth_rate requiere que se cumplan las 4 condiciones de Turing primero (usar check_turing_instability)"}

    k_star_sq = (det / (Du * Dv)) ** 0.5
    A_eff = [[a11 - Du * k_star_sq, a12], [a21, a22 - Dv * k_star_sq]]
    eig_result = _eig2x2(A_eff)
    lam_star, vec = eig_result[0]

    diagnostics["k_star_squared_numero_de_onda_mas_inestable"] = round(k_star_sq, 6)
    diagnostics["lambda_star_tasa_crecimiento_analitica"] = round(lam_star, 6) if isinstance(lam_star, float) else str(lam_star)

    if mode == "check_turing_instability":
        return diagnostics

    # simulate_growth_rate
    if vec is None:
        return {"error": "autovalor complejo en el modo critico -- este caso (patron oscilatorio) no esta implementado, solo inestabilidad estacionaria"}
    v0, v1 = vec
    norm = (v0 ** 2 + v1 ** 2) ** 0.5
    v0, v1 = v0 / norm, v1 / norm

    k_mode = k_star_sq ** 0.5
    nx = 400
    L = 2 * math.pi / k_mode * 3
    dx = L / nx
    dt = 0.0005
    n_steps = 2000

    code = f"""
a11={a11}; a12={a12}; a21={a21}; a22={a22};
Du={Du}; Dv={Dv};
nx={nx}; dx={dx}; dt={dt}; n_steps={n_steps};
x = (0:nx-1)*dx;
k_mode = {k_mode};
u = 0.0001*{v0}*cos(k_mode*x)';
v = 0.0001*{v1}*cos(k_mode*x)';
amps = [];
for step = 1:n_steps
  lap_u = (circshift(u,1) + circshift(u,-1) - 2*u) / dx^2;
  lap_v = (circshift(v,1) + circshift(v,-1) - 2*v) / dx^2;
  du = Du*lap_u + a11*u + a12*v;
  dv = Dv*lap_v + a21*u + a22*v;
  u = u + dt*du;
  v = v + dt*dv;
  if mod(step,50)==0
    amps(end+1) = max(abs(u));
  end
end
printf("%.10e ", amps);
"""
    out, err = _run_octave(code)
    if out is None:
        return {"error": "octave fallo", "stderr": err}
    amps = [float(v) for v in out.split()]
    t_vals = [(i + 1) * 50 * dt for i in range(len(amps))]
    log_amps = [math.log(a) for a in amps]
    n = len(t_vals)
    mt = sum(t_vals) / n
    ma = sum(log_amps) / n
    num = sum((t_vals[i] - mt) * (log_amps[i] - ma) for i in range(n))
    den = sum((t_vals[i] - mt) ** 2 for i in range(n))
    slope = num / den

    result = {
        "eigenvector_used": [round(v0, 6), round(v1, 6)],
        "tasa_crecimiento_analitica": round(lam_star, 6),
        "tasa_crecimiento_medida_numericamente": round(slope, 6),
        "error_relativo": round(abs(slope - lam_star) / abs(lam_star), 6),
        "nota": "condicion inicial = autovector del modo mas inestable (no una suposicion arbitraria), por eso el ajuste log-lineal da una exponencial pura",
    }
    result.update(diagnostics)
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(compute_reaction_diffusion("check_turing_instability"), indent=2, ensure_ascii=False))
