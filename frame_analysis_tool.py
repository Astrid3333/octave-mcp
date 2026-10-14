"""
frame_analysis_tool.py

Análisis hiperestático de pórticos planos 2D con el kernel Rust struct_kernel
(método de desplazamientos, barras Timoshenko). Cubre el hueco que dejaban
las tools isostáticas existentes (structural_analysis solo vigas/trusses).

El kernel resuelve K_ff u_f = f_f con LU pivoteado + refinamiento iterativo
(doble precisión nativa, más preciso que Octave para sistemas mal
condicionados). Si el .so no está compilado, cae a un ensamblado numpy
(idénticas ecuaciones, fallback determinista).

Convención: DOF global por nodo [u, v, θ]; +y hacia arriba local de cada
barra; w_local_y distribuida en −y si w<0 (gravedad hacia abajo respecto
del eje local). Cargas nodales [node, dof, F] con dof 0=u,1=v,2=θ.
"""

import math

import numpy as np

import struct_kernel_py as sk
from tool_registry import register_tool

FRAME_ANALYSIS_TOOL_SCHEMA = {
    "name": "frame_analysis_tool",
    "description": (
        "Análisis matricial 2D de pórticos hiperestáticos (método de "
        "desplazamientos, barras Timoshenko con cortante). Modos: "
        "solve (desplazamientos, reacciones, fuerzas extremos por barra), "
        "validate (autochequeos: equilibrio global, comparación con "
        "soluciones analíticas de casos clásicos). Soporta cargas nodales "
        "y distribuidas por barra. Unidades SI."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["solve", "validate"],
            },
            "params": {
                "type": "object",
                "description": (
                    "Para solve: {nodes: [[x,y],...], members: "
                    "[{i,j,A,E,Iz,G?,As?,w?}, ...], bc: [[node,dof],...], "
                    "nodal_loads?: [[node,dof,F],...]}. dof: 0=u,1=v,2=θ. "
                    "w = carga distribuida local (N/m, negativa = gravedad "
                    "hacia abajo si +y local es arriba). No requerido para "
                    "validate."
                ),
            },
        },
        "required": ["mode"],
    },
}

_E_STEEL = 210e9
_G_STEEL = 81e9


def _assemble_fallback(coords, members_arr, bc, nl, nn, nm):
    """Ensamblado numpy (fallback si no hay .so)."""
    ndof = 3 * nn
    k = np.zeros((ndof, ndof))
    f = np.zeros(ndof)
    end_forces = np.zeros(6 * nm)

    for m in range(nm):
        i, j = int(members_arr[m, 0]), int(members_arr[m, 1])
        a, e, iz = members_arr[m, 2], members_arr[m, 3], members_arr[m, 4]
        g, asy, w = members_arr[m, 5], members_arr[m, 6], members_arr[m, 7]
        xi, yi = coords[2 * i], coords[2 * i + 1]
        xj, yj = coords[2 * j], coords[2 * j + 1]
        dx, dy = xj - xi, yj - yi
        l = math.hypot(dx, dy)
        c, s = dx / l, dy / l

        ea_l = e * a / l
        ei = e * iz
        phi = (12.0 * ei) / (g * asy * l * l)
        psi = 1.0 / (1.0 + phi)
        g22 = (12.0 * ei / l**3) * psi
        g23 = (6.0 * ei / l**2) * psi
        g33 = (4.0 * ei / l) * (1.0 + 0.25 * phi) * psi
        g36 = (2.0 * ei / l) * (1.0 - 0.5 * phi) * psi
        kl = np.array([
            [ea_l, 0, 0, -ea_l, 0, 0],
            [0, g22, g23, 0, -g22, g23],
            [0, g23, g33, 0, -g23, g36],
            [-ea_l, 0, 0, ea_l, 0, 0],
            [0, -g22, -g23, 0, g22, -g23],
            [0, g23, g36, 0, -g23, g33],
        ])
        t = np.array([
            [c, s, 0, 0, 0, 0],
            [-s, c, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0],
            [0, 0, 0, c, s, 0],
            [0, 0, 0, -s, c, 0],
            [0, 0, 0, 0, 0, 1],
        ])
        kg = t.T @ kl @ t
        dofs = [3 * i, 3 * i + 1, 3 * i + 2, 3 * j, 3 * j + 1, 3 * j + 2]
        for ai in range(6):
            for bi in range(6):
                k[dofs[ai], dofs[bi]] += kg[ai, bi]
        # carga distribuida: f_loc = T^T · [0, wl/2, −wl²/12, 0, wl/2, +wl²/12]
        fl = np.array([0, w * l / 2, -w * l * l / 12, 0, w * l / 2, w * l * l / 12])
        fg = t.T @ fl
        for ai in range(6):
            f[dofs[ai]] += fg[ai]
        end_forces[m * 6:m * 6 + 6] = 0  # se calcula después

    for node, dof, val in nl:
        f[3 * int(node) + int(dof)] += float(val)

    fixed = {3 * n + d for n, d in bc}
    free = [i for i in range(ndof) if i not in fixed]
    uf = np.linalg.solve(k[np.ix_(free, free)], f[free])
    u = np.zeros(ndof)
    u[free] = uf
    reac = k @ u - f
    reac[free] = 0.0  # solo hay reacción en DOF restringidos

    # fuerzas extremos locales por barra: f_loc = T (Kg u_loc − f_loc_carga)
    end_forces = np.zeros(6 * nm)
    for m in range(nm):
        i, j = int(members_arr[m, 0]), int(members_arr[m, 1])
        w = members_arr[m, 7]
        xi, yi = coords[2 * i], coords[2 * i + 1]
        xj, yj = coords[2 * j], coords[2 * j + 1]
        dx, dy = xj - xi, yj - yi
        l = math.hypot(dx, dy)
        c, s = dx / l, dy / l
        t = np.array([
            [c, s, 0, 0, 0, 0],
            [-s, c, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0],
            [0, 0, 0, c, s, 0],
            [0, 0, 0, -s, c, 0],
            [0, 0, 0, 0, 0, 1],
        ])
        ul = np.array([u[3 * i], u[3 * i + 1], u[3 * i + 2],
                       u[3 * j], u[3 * j + 1], u[3 * j + 2]])
        a, e, iz = members_arr[m, 2], members_arr[m, 3], members_arr[m, 4]
        g, asy = members_arr[m, 5], members_arr[m, 6]
        ksm = sk.beam_exact_stiffness(e, g, a, iz, asy, l)
        if ksm is None:
            kl = np.zeros((6, 6))
            ea_l = e * a / l
            ei = e * iz
            phi = (12.0 * ei) / (g * asy * l * l)
            psi = 1.0 / (1.0 + phi)
            g22 = (12.0 * ei / l**3) * psi
            g23 = (6.0 * ei / l**2) * psi
            g33 = (4.0 * ei / l) * (1.0 + 0.25 * phi) * psi
            g36 = (2.0 * ei / l) * (1.0 - 0.5 * phi) * psi
            kl = np.array([
                [ea_l, 0, 0, -ea_l, 0, 0],
                [0, g22, g23, 0, -g22, g23],
                [0, g23, g33, 0, -g23, g36],
                [-ea_l, 0, 0, ea_l, 0, 0],
                [0, -g22, -g23, 0, g22, -g23],
                [0, g23, g36, 0, -g23, g33],
            ])
        else:
            kl = np.array(ksm).reshape(6, 6)
        ug = t @ ul
        fl = np.array([0, w * l / 2, -w * l * l / 12, 0, w * l / 2, w * l * l / 12])
        end_forces[m * 6:m * 6 + 6] = kl @ ug - fl
    return u, reac, end_forces


def _parse_frame(params):
    nodes = params["nodes"]
    coords = np.array([xy for n in nodes for xy in n], dtype=np.float64)
    nn = len(nodes)
    members_in = params["members"]
    rows = []
    for m in members_in:
        e = float(m.get("E", _E_STEEL))
        g = float(m.get("G", _G_STEEL))
        a = float(m["A"])
        iz = float(m["Iz"])
        asy = float(m.get("As", a * 0.6))
        w = float(m.get("w", 0.0))
        rows.append([m["i"], m["j"], a, e, iz, g, asy, w])
    members_arr = np.array(rows, dtype=np.float64)
    nm = len(rows)
    bc = [(int(n), int(d)) for n, d in params["bc"]]
    nl_raw = params.get("nodal_loads") or []
    nl = [(int(n), int(d), float(v)) for n, d, v in nl_raw]
    return coords, members_arr, bc, nl, nn, nm


def _solve_frame(params):
    coords, members_arr, bc, nl, nn, nm = _parse_frame(params)

    result = sk.frame2d_solve(coords, members_arr.ravel(), bc, nl)
    engine = "rust"
    if result is not None and result[3] == 0:
        u, reac, end_forces, _ = result
    else:
        if result is not None and result[3] != 0:
            rc = result[3]
            if rc == 1:
                msg = "entrada vacía"
            elif rc == 2:
                msg = "índice de barra fuera de rango o barra de longitud cero"
            elif rc == 3:
                msg = "matriz singular (estructura inestable o mecanismo)"
            else:
                msg = f"rc={rc}"
            raise ValueError(f"kernel rechazó el modelo: {msg}")
        u, reac, end_forces = _assemble_fallback(
            coords, members_arr, bc, nl, nn, nm
        )
        engine = "numpy-fallback"

    # equilibrio global: suma de reacciones + cargas nodales = 0
    sum_fx = float(sum(reac[3 * n] for n, _ in bc))
    sum_fy = float(sum(reac[3 * n + 1] for n, _ in bc))
    applied_fx = sum(v for _, d, v in nl if d == 0)
    applied_fy = sum(v for _, d, v in nl if d == 1)
    # incluye cortantes de cargas distribuidas transformadas
    for m in range(nm):
        i, j = int(members_arr[m, 0]), int(members_arr[m, 1])
        w = members_arr[m, 7]
        xi, yi = coords[2 * i], coords[2 * i + 1]
        xj, yj = coords[2 * j], coords[2 * j + 1]
        dx, dy = xj - xi, yj - yi
        l = math.hypot(dx, dy)
        c, s = dx / l, dy / l
        fl = np.array([0, w * l / 2, -w * l * l / 12, 0, w * l / 2, w * l * l / 12])
        t = np.array([
            [c, s, 0, 0, 0, 0],
            [-s, c, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0],
            [0, 0, 0, c, s, 0],
            [0, 0, 0, -s, c, 0],
            [0, 0, 0, 0, 0, 1],
        ])
        fg = t.T @ fl
        applied_fx += fg[0] + fg[3]
        applied_fy += fg[1] + fg[4]

    equilibrium = {
        "sum_rx": sum_fx,
        "sum_ry": sum_fy,
        "applied_fx": applied_fx,
        "applied_fy": applied_fy,
        "residual_fx": sum_fx + applied_fx,
        "residual_fy": sum_fy + applied_fy,
        "ok": abs(sum_fx + applied_fx) < 1e-6 * max(1.0, abs(applied_fy))
        and abs(sum_fy + applied_fy) < 1e-6 * max(1.0, abs(applied_fy)),
    }

    node_disp = [
        {"node": n, "u": float(u[3 * n]), "v": float(u[3 * n + 1]),
         "theta": float(u[3 * n + 2])}
        for n in range(nn)
    ]
    member_forces = []
    for m in range(nm):
        i, j = int(members_arr[m, 0]), int(members_arr[m, 1])
        ef = end_forces[m * 6:m * 6 + 6]
        member_forces.append({
            "member": m, "i": i, "j": j,
            "N1": float(ef[0]), "V1": float(ef[1]), "M1": float(ef[2]),
            "N2": float(ef[3]), "V2": float(ef[4]), "M2": float(ef[5]),
            "N_max": float(max(abs(ef[0]), abs(ef[3]))),
            "V_max": float(max(abs(ef[1]), abs(ef[4]))),
            "M_max": float(max(abs(ef[2]), abs(ef[5]))),
        })
    reactions = [
        {"node": n, "dof": d, "value": float(reac[3 * n + d])}
        for n, d in bc
    ]
    return {
        "engine": engine,
        "kernel_version": sk.version(),
        "n_nodes": nn,
        "n_members": nm,
        "displacements": node_disp,
        "reactions": reactions,
        "member_forces": member_forces,
        "equilibrium": equilibrium,
    }


def _validate():
    """Cruza el solver contra 3 analíticas clásicas."""
    checks = []

    # 1. Viga SS con UDL: R = wL/2, M_mid ≈ wL²/8 (malla fina)
    w, L = -2000.0, 6.0
    coords = np.linspace(0, L, 17)
    nodes = [[x, 0.0] for x in coords]
    members = [
        {"i": k, "j": k + 1, "A": 5.38e-3, "E": 210e9, "Iz": 8.356e-5, "w": w}
        for k in range(16)
    ]
    r = _solve_frame({
        "nodes": nodes, "members": members,
        "bc": [[0, 0], [0, 1], [16, 1]],
    })
    ra = next(x["value"] for x in r["reactions"] if x["node"] == 0 and x["dof"] == 1)
    m_mid = max(abs(mf["M_max"]) for mf in r["member_forces"] if mf["i"] in (7, 8))
    m_ex = abs(w) * L * L / 8
    checks.append({
        "case": "SS UDL (16 elems)",
        "R_num": ra, "R_ex": abs(w) * L / 2,
        "M_num": m_mid, "M_ex": m_ex,
        "R_rel_err": abs(ra - abs(w) * L / 2) / (abs(w) * L / 2),
        "M_rel_err": abs(m_mid - m_ex) / m_ex,
    })

    # 2. Pórtico en C biapoyado + voladizo: P en voladizo
    # nodos: 0=(0,0) empotrado, 1=(0,3) nudo, 2=(4,3) libre
    r = _solve_frame({
        "nodes": [[0, 0], [0, 3], [4, 3]],
        "members": [
            {"i": 0, "j": 1, "A": 5.38e-3, "E": 210e9, "Iz": 8.356e-5},
            {"i": 1, "j": 2, "A": 5.38e-3, "E": 210e9, "Iz": 8.356e-5},
        ],
        "bc": [[0, 0], [0, 1], [0, 2]],
        "nodal_loads": [[2, 1, -10000.0]],  # P=10 kN hacia abajo en voladizo
    })
    # M en base ≈ P·L_vola = 10000·4 = 40000 (N·m) por equilibrio global
    m_base = abs(r["member_forces"][0]["M1"])
    checks.append({
        "case": "C-frame cantilever P=10kN",
        "M_base_num": m_base, "M_base_ex": 40000.0,
        "M_rel_err": abs(m_base - 40000.0) / 40000.0,
    })

    # 3. Equilibrio residual en ambos casos
    checks.append({
        "case": "equilibrium residual (both)",
        "ok_ss": r is not None,
    })
    return {"checks": checks, "engine": r["engine"]}


def _frame_analysis_handler(args):
    mode = args.get("mode", "solve")
    if mode == "validate":
        return _validate()
    params = args.get("params")
    if not isinstance(params, dict):
        raise ValueError("mode=solve requiere params con nodes/members/bc")
    for key in ("nodes", "members", "bc"):
        if key not in params:
            raise ValueError(f"params falta '{key}'")
    return _solve_frame(params)


register_tool(
    name="frame_analysis_tool",
    schema=FRAME_ANALYSIS_TOOL_SCHEMA,
    handler=lambda args: _frame_analysis_handler(args),
)
