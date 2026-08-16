import json, subprocess

inp = {
    "mode": "lid_driven_cavity",
    "geometry": {"width": 1.0, "height": 1.0, "nx": 41, "ny": 41},
    "fluid": {"reynolds": 100.0},
    "lid_velocity": 1.0,
    "solver": {"dt": 0.001, "max_steps": 20000, "tol": 1e-6},
    "run_id": None,
}
r = json.loads(subprocess.run(
    ["./target/release/cfd_cavity"], input=json.dumps(inp),
    capture_output=True, text=True
).stdout)

nx, ny = r["mesh"]["nx"], r["mesh"]["ny"]
u = r["u"]
i_center = (nx - 1) // 2

def u_at(y_frac):
    y_pos = y_frac * (ny - 1)
    j0 = int(y_pos)
    j1 = min(j0 + 1, ny - 1)
    frac = y_pos - j0
    u0 = u[j0 * nx + i_center]
    u1 = u[j1 * nx + i_center]
    return u0 * (1 - frac) + u1 * frac

ghia_y_u = [
    (1.0000, 1.0000), (0.9766, 0.8412), (0.9688, 0.7887), (0.9609, 0.7372),
    (0.9531, 0.6872), (0.8516, 0.2315), (0.7344, 0.0033), (0.6172, -0.1364),
    (0.5000, -0.2058), (0.4531, -0.2109), (0.2813, -0.1566), (0.1719, -0.1015),
    (0.1016, -0.0643), (0.0703, -0.0478), (0.0625, -0.0419), (0.0547, -0.0361),
    (0.0000, 0.0000),
]

print(f"{'y':>8}  {'u_ghia':>9}  {'u_sim':>9}  {'diff':>9}")
for y, u_ghia in ghia_y_u:
    u_sim = u_at(y)
    print(f"{y:8.4f}  {u_ghia:9.4f}  {u_sim:9.4f}  {u_ghia - u_sim:9.4f}")
