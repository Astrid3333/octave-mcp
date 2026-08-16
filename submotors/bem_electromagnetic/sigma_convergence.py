import json, subprocess, math

r_int, r_ext = 0.3, 1.0
v_inner = 1.0

def circle_points(r, n):
    return [[r * math.cos(2*math.pi*k/n), r * math.sin(2*math.pi*k/n)] for k in range(n)]

dphidn_inner = v_inner / (r_int * math.log(r_int / r_ext))
sigma_analitico_inner = -dphidn_inner

for n_per_circle in [40, 80, 160, 320]:
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
    sigma_inner_val = r["sigma"][0]
    rel_err = (sigma_inner_val - sigma_analitico_inner) / sigma_analitico_inner
    print(f"n_per_circle={n_per_circle:4d}  sigma_bem={sigma_inner_val:.6f}  rel_err={rel_err*100:.4f}%")
