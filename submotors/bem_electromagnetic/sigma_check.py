import json, subprocess, math

r_int, r_ext = 0.3, 1.0
v_inner = 1.0
n_per_circle = 80

def circle_points(r, n):
    return [[r * math.cos(2*math.pi*k/n), r * math.sin(2*math.pi*k/n)] for k in range(n)]

dphidn_inner = v_inner / (r_int * math.log(r_int / r_ext))
sigma_analitico_inner = -dphidn_inner

inp = {
    "mode": "electrostatics_2d",
    "conductors": [
        {"boundary": circle_points(r_int, n_per_circle), "bc": {"type": "neumann", "value": dphidn_inner}},
        {"boundary": circle_points(r_ext, n_per_circle), "bc": {"type": "dirichlet", "value": 0.0}},
    ],
    "eval_grid": None,
    "run_id": None,
}

r = json.loads(subprocess.run(
    ["./target/release/bem_electromagnetic"], input=json.dumps(inp),
    capture_output=True, text=True
).stdout)

sigma = r["sigma"]
n_inner = n_per_circle
sigma_inner = sigma[:n_inner]
sigma_ext = sigma[n_inner:]

print(f"sigma_analitico_inner (esperado, uniforme): {sigma_analitico_inner:.5f}")
print(f"sigma_inner (BEM) -- min: {min(sigma_inner):.5f}  max: {max(sigma_inner):.5f}  mean: {sum(sigma_inner)/len(sigma_inner):.5f}")
print(f"primeros 5 valores sigma_inner: {[round(s,5) for s in sigma_inner[:5]]}")
print(f"sigma_ext -- min: {min(sigma_ext):.5f}  max: {max(sigma_ext):.5f}  mean: {sum(sigma_ext)/len(sigma_ext):.5f}")
