import json, subprocess, math

r_int, r_ext = 0.3, 1.5
v_inner = 1.0
n_per_circle = 80

def circle_points(r, n):
    return [[r * math.cos(2*math.pi*k/n), r * math.sin(2*math.pi*k/n)] for k in range(n)]

dphidn_inner = v_inner / (r_int * math.log(r_int / r_ext))

inp = {
    "mode": "electrostatics_2d",
    "conductors": [
        {"boundary": circle_points(r_int, n_per_circle), "bc": {"type": "neumann", "value": dphidn_inner}},
        {"boundary": circle_points(r_ext, n_per_circle), "bc": {"type": "dirichlet", "value": 0.0}},
    ],
    "eval_grid": {
        "x_min": r_int + 0.02, "x_max": r_ext - 0.02,
        "y_min": 0.0, "y_max": 0.0,
        "nx": 15, "ny": 1,
    },
    "run_id": None,
}

r = json.loads(subprocess.run(
    ["./target/release/bem_electromagnetic"], input=json.dumps(inp),
    capture_output=True, text=True
).stdout)

grid = r["grid"]
xs = [grid["x_min"] + (grid["x_max"] - grid["x_min"]) * i / (grid["nx"] - 1) for i in range(grid["nx"])]
print(f"dphidn_inner prescrito: {dphidn_inner:.5f}")
print(f"{'r':>8}  {'phi_bem':>10}  {'phi_analitico':>14}  {'diff':>10}")
for i, x in enumerate(xs):
    phi_bem = grid["potential"][i]
    phi_an = v_inner * math.log(x / r_ext) / math.log(r_int / r_ext)
    print(f"{x:8.4f}  {phi_bem:10.5f}  {phi_an:14.5f}  {phi_bem - phi_an:10.5f}")
