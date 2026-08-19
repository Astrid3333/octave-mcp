"""
structural_analysis_tool.py

Tool MCP: structural_analysis
Análisis estructural preliminar: vigas, cerchas 2D, propiedades de sección, chequeo de esfuerzo.

ADVERTENCIA: herramienta de estimación preliminar (educativa / cubicación temprana).
No reemplaza el cálculo y timbre de un ingeniero estructural para obra real.

Operaciones soportadas (parámetro `mode`):
  - beam_analysis      : reacciones, corte V(x), momento M(x) y deflexión (casos simples)
  - truss_analysis     : método de nudos (forma matricial) para cerchas 2D isostáticas
  - section_properties  : área, inercia, módulo de sección, radio de giro
  - stress_check        : esfuerzo simple vs esfuerzo admisible, factor de seguridad

Dependencias: numpy únicamente (sin scipy).
"""

import numpy as np

STRUCTURAL_ANALYSIS_TOOL_SCHEMA = {
    "name": "structural_analysis",
    "description": (
        "Análisis estructural preliminar: reacciones/corte/momento/deflexión de vigas "
        "(simplemente apoyada o en voladizo), fuerzas axiales en cerchas 2D isostáticas "
        "(método de nudos), propiedades de sección (área, inercia, módulo, radio de giro), "
        "y chequeo de esfuerzo simple vs. esfuerzo admisible. Estimación preliminar, no "
        "reemplaza cálculo certificado por ingeniero estructural."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["beam_analysis", "truss_analysis", "section_properties", "stress_check", "validate"],
            },
            "support": {"type": "string", "enum": ["simply_supported", "cantilever"]},
            "length": {"type": "number", "description": "Luz L de la viga (m). beam_analysis."},
            "point_loads": {"type": "array", "description": "Lista de {x, P} (P positivo hacia abajo). beam_analysis."},
            "distributed_load": {"type": "number", "description": "Carga uniforme w (fuerza/longitud) sobre todo el tramo. beam_analysis."},
            "E": {"type": "number", "description": "Módulo de elasticidad (Pa). Opcional, para deflexión."},
            "I": {"type": "number", "description": "Momento de inercia de la sección (m^4). Opcional, para deflexión."},
            "n_points": {"type": "integer", "default": 100, "description": "Puntos de discretización. beam_analysis."},
            "nodes": {"type": "object", "description": "{'A': [x,y], ...}. truss_analysis."},
            "members": {"type": "array", "description": "Lista de [nodo_i, nodo_j]. truss_analysis."},
            "supports": {"type": "object", "description": "{'A': 'pin'|'roller_x'|'roller_y'}. truss_analysis."},
            "loads": {"type": "object", "description": "{'C': [Fx, Fy]}, Fy negativo=hacia abajo. truss_analysis."},
            "shape": {"type": "string", "enum": ["rectangular", "circular", "hollow_rectangular", "hollow_circular"], "description": "section_properties."},
            "dims": {"type": "object", "description": "Dimensiones según 'shape'. section_properties."},
            "force": {"type": "number", "description": "stress_check."},
            "area": {"type": "number", "description": "stress_check."},
            "allowable_stress": {"type": "number", "description": "stress_check."},
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# beam_analysis
# ---------------------------------------------------------------------------

def _beam_analysis(support, length, point_loads=None, distributed_load=0.0,
                    E=None, I=None, n_points=100):
    L = float(length)
    point_loads = point_loads or []
    w = float(distributed_load)
    total_load = sum(p["P"] for p in point_loads) + w * L

    if support == "simply_supported":
        # Momento respecto de A (x=0): R_B*L = sum(P_i*x_i) + w*L^2/2
        moment_about_A = sum(p["P"] * p["x"] for p in point_loads) + w * L**2 / 2
        R_B = moment_about_A / L
        R_A = total_load - R_B
        M0 = 0.0
        reactions = {"R_A": round(R_A, 4), "R_B": round(R_B, 4)}
    elif support == "cantilever":
        # Empotrado en x=0, libre en x=L
        R_A = total_load
        M_A = sum(p["P"] * p["x"] for p in point_loads) + w * L**2 / 2
        M0 = -M_A
        reactions = {"R_A": round(R_A, 4), "M_A": round(M_A, 4)}
    else:
        raise ValueError("support debe ser 'simply_supported' o 'cantilever'")

    x = np.linspace(0, L, int(n_points))
    V = np.full_like(x, R_A) - w * x
    M = M0 + R_A * x - w * x**2 / 2
    for p in point_loads:
        mask = x >= p["x"]
        V[mask] -= p["P"]
        M[mask] -= p["P"] * (x[mask] - p["x"])

    # --- Picos exactos (fix: el maximo del arreglo linspace subestima el
    # pico real cuando cae fuera de la grilla, ej. bajo carga puntual) ---
    def _M_at(xv):
        Mv = M0 + R_A * xv - w * xv**2 / 2
        for p in point_loads:
            if xv >= p["x"] - 1e-12:
                Mv -= p["P"] * (xv - p["x"])
        return Mv

    def _V_left(xv):
        Vv = R_A - w * xv
        for p in point_loads:
            if xv > p["x"] + 1e-12:
                Vv -= p["P"]
        return Vv

    def _V_right(xv):
        Vv = R_A - w * xv
        for p in point_loads:
            if xv >= p["x"] - 1e-12:
                Vv -= p["P"]
        return Vv

    boundaries = sorted(set([0.0, L] + [p["x"] for p in point_loads]))

    # Momento: candidatos = extremos + cada carga puntual + ceros de V(x)
    # (donde M(x) es estacionario) dentro de cada tramo, si hay carga distribuida
    m_candidates = set(boundaries)
    if w != 0.0:
        for i in range(len(boundaries) - 1):
            x_left, x_right = boundaries[i], boundaries[i + 1]
            v_left = _V_right(x_left)
            x_zero = x_left + v_left / w
            if x_left - 1e-9 <= x_zero <= x_right + 1e-9:
                m_candidates.add(min(max(x_zero, x_left), x_right))
    m_evals = [(xc, _M_at(xc)) for xc in sorted(m_candidates)]
    max_moment_x, max_moment = max(m_evals, key=lambda t: abs(t[1]))
    max_moment = float(max_moment)
    max_moment_x = float(max_moment_x)

    # Corte: maximo |V| ocurre siempre en un extremo de tramo (V es lineal
    # a trozos), evaluado a izquierda y derecha de cada frontera por los saltos
    v_evals = []
    for xb in boundaries:
        v_evals.append(abs(_V_left(xb)))
        v_evals.append(abs(_V_right(xb)))
    max_shear = float(max(v_evals))

    result = {
        "mode": "beam_analysis",
        "support": support,
        "length": L,
        "reactions": reactions,
        "max_moment": round(max_moment, 4),
        "max_moment_location": round(max_moment_x, 4),
        "max_shear": round(max_shear, 4),
        "shear_diagram": {"x": [round(v, 4) for v in x.tolist()], "V": [round(v, 4) for v in V.tolist()]},
        "moment_diagram": {"x": [round(v, 4) for v in x.tolist()], "M": [round(v, 4) for v in M.tolist()]},
    }

    # Deflexión: solo casos validados con fórmula cerrada (una sola carga, no combinada)
    n_point = len(point_loads)
    has_udl = w != 0.0
    if E and I and n_point <= 1 and not (has_udl and n_point == 1):
        EI = E * I
        deflection = None
        deflection_location = None
        if support == "simply_supported":
            if has_udl and n_point == 0:
                deflection = 5 * w * L**4 / (384 * EI)
                deflection_location = L / 2
            elif n_point == 1 and abs(point_loads[0]["x"] - L / 2) < 1e-9:
                P = point_loads[0]["P"]
                deflection = P * L**3 / (48 * EI)
                deflection_location = L / 2
        elif support == "cantilever":
            if has_udl and n_point == 0:
                deflection = w * L**4 / (8 * EI)
                deflection_location = L
            elif n_point == 1 and abs(point_loads[0]["x"] - L) < 1e-9:
                P = point_loads[0]["P"]
                deflection = P * L**3 / (3 * EI)
                deflection_location = L
        if deflection is not None:
            result["max_deflection"] = round(deflection, 6)
            result["max_deflection_location"] = deflection_location
        else:
            result["deflection_note"] = (
                "Combinación de cargas no cubierta por fórmula cerrada validada; "
                "omitida para evitar reportar un valor no verificado."
            )
    elif E and I:
        result["deflection_note"] = (
            "Deflexión solo disponible para una única carga (UDL sola, o carga puntual "
            "en el punto característico: medio vano en simplemente apoyada, extremo libre en voladizo)."
        )

    return result


# ---------------------------------------------------------------------------
# truss_analysis
# ---------------------------------------------------------------------------

def _truss_analysis(nodes, members, supports, loads=None):
    loads = loads or {}
    node_ids = list(nodes.keys())
    n_nodes = len(node_ids)
    idx = {nid: i for i, nid in enumerate(node_ids)}

    unknown_names = []  # ('member', (i,j)) o ('reaction', node_id, 'x'/'y')
    for m in members:
        unknown_names.append(("member", tuple(m)))
    for nid, sup in supports.items():
        if sup == "pin":
            unknown_names.append(("reaction", nid, "x"))
            unknown_names.append(("reaction", nid, "y"))
        elif sup == "roller_x":
            unknown_names.append(("reaction", nid, "x"))
        elif sup == "roller_y":
            unknown_names.append(("reaction", nid, "y"))
        else:
            raise ValueError(f"Tipo de apoyo no soportado: {sup}")

    n_unknowns = len(unknown_names)
    n_eqs = 2 * n_nodes
    A = np.zeros((n_eqs, n_unknowns))
    b = np.zeros(n_eqs)

    for nid, (fx, fy) in loads.items():
        b[2 * idx[nid]] -= fx
        b[2 * idx[nid] + 1] -= fy

    for col, u in enumerate(unknown_names):
        if u[0] == "member":
            ni, nj = u[1]
            xi, yi = nodes[ni]
            xj, yj = nodes[nj]
            dx, dy = xj - xi, yj - yi
            Lm = np.hypot(dx, dy)
            c, s = dx / Lm, dy / Lm
            # Tensión positiva: tira del nudo i hacia j, y del nudo j hacia i.
            A[2 * idx[ni], col] += c
            A[2 * idx[ni] + 1, col] += s
            A[2 * idx[nj], col] += -c
            A[2 * idx[nj] + 1, col] += -s
        else:
            _, nid, axis = u
            row = 2 * idx[nid] + (0 if axis == "x" else 1)
            A[row, col] += 1.0

    determinate = n_unknowns == n_eqs
    if determinate:
        try:
            x = np.linalg.solve(A, b)
            method_note = "sistema determinado, resuelto exacto"
        except np.linalg.LinAlgError:
            x, *_ = np.linalg.lstsq(A, b, rcond=None)
            method_note = "matriz singular (mecanismo/inestable) — solución mínimos cuadrados, revisar geometría"
    else:
        x, *_ = np.linalg.lstsq(A, b, rcond=None)
        method_note = (
            f"sistema NO determinado (incógnitas={n_unknowns}, ecuaciones={n_eqs}); "
            "solución por mínimos cuadrados, no confiable para diseño"
        )

    member_forces = []
    reactions = {}
    for col, u in enumerate(unknown_names):
        if u[0] == "member":
            ni, nj = u[1]
            member_forces.append({
                "member": f"{ni}-{nj}",
                "force": round(float(x[col]), 4),
                "type": "tensión" if x[col] > 1e-9 else ("compresión" if x[col] < -1e-9 else "nulo"),
            })
        else:
            _, nid, axis = u
            reactions.setdefault(nid, {})[f"R_{axis}"] = round(float(x[col]), 4)

    # Autoverificación de equilibrio global
    total_fx = sum(fx for fx, _ in loads.values())
    total_fy = sum(fy for _, fy in loads.values())
    reaction_fx = sum(r.get("R_x", 0.0) for r in reactions.values())
    reaction_fy = sum(r.get("R_y", 0.0) for r in reactions.values())
    equilibrium_check = {
        "sum_fx_residual": round(total_fx + reaction_fx, 6),
        "sum_fy_residual": round(total_fy + reaction_fy, 6),
    }

    return {
        "mode": "truss_analysis",
        "determinate": determinate,
        "solver_note": method_note,
        "member_forces": member_forces,
        "reactions": reactions,
        "equilibrium_check": equilibrium_check,
    }


# ---------------------------------------------------------------------------
# section_properties
# ---------------------------------------------------------------------------

def _section_properties(shape, dims):
    if shape == "rectangular":
        b, h = dims["b"], dims["h"]
        area = b * h
        I_ = b * h**3 / 12
    elif shape == "circular":
        d = dims["d"]
        area = np.pi * d**2 / 4
        I_ = np.pi * d**4 / 64
    elif shape == "hollow_rectangular":
        b, h, t = dims["b"], dims["h"], dims["t"]
        bi, hi = b - 2 * t, h - 2 * t
        area = b * h - bi * hi
        I_ = (b * h**3 - bi * hi**3) / 12
    elif shape == "hollow_circular":
        d, t = dims["d"], dims["t"]
        di = d - 2 * t
        area = np.pi * (d**2 - di**2) / 4
        I_ = np.pi * (d**4 - di**4) / 64
    else:
        raise ValueError(f"shape no soportado: {shape}")

    c = dims.get("c")  # distancia a la fibra extrema, si no se da se asume h/2 o d/2
    if c is None:
        c = dims.get("h", dims.get("d", 0)) / 2
    Z = I_ / c if c else None
    r = np.sqrt(I_ / area)

    return {
        "shape": shape,
        "area_m2": round(area, 6),
        "moment_of_inertia_m4": round(I_, 8),
        "section_modulus_m3": round(Z, 6) if Z else None,
        "radius_of_gyration_m": round(r, 6),
    }


# ---------------------------------------------------------------------------
# stress_check
# ---------------------------------------------------------------------------

def _stress_check(force, area, allowable_stress):
    stress = force / area
    safety_factor = allowable_stress / stress if stress != 0 else float("inf")
    return {
        "stress": round(stress, 4),
        "allowable_stress": allowable_stress,
        "safety_factor": round(safety_factor, 3) if safety_factor != float("inf") else "inf",
        "pass": bool(abs(stress) <= allowable_stress),
    }



def _validate_structural():
    """Autochequeo con 5 casos de solucion cerrada, uno por sub-modo."""
    checks = []

    # --- 1) beam_analysis, simplemente apoyada, carga puntual ---
    r1 = _beam_analysis(
        support="simply_supported", length=3.0,
        point_loads=[{"P": 1500.0, "x": 1.5}],
    )
    exp_M1, exp_R1 = 1125.0, 750.0
    checks.append({
        "name": "beam_simply_supported_max_moment",
        "expected": exp_M1, "got": r1["max_moment"],
        "passed": abs(abs(r1["max_moment"]) - exp_M1) < 1e-3,
    })
    checks.append({
        "name": "beam_simply_supported_reactions",
        "expected": exp_R1, "got": r1["reactions"],
        "passed": (
            abs(r1["reactions"]["R_A"] - exp_R1) < 1e-3
            and abs(r1["reactions"]["R_B"] - exp_R1) < 1e-3
        ),
    })
    checks.append({
        "name": "beam_simply_supported_max_shear",
        "expected": exp_R1, "got": r1["max_shear"],
        "passed": abs(r1["max_shear"] - exp_R1) < 1e-3,
    })

    # --- 2) beam_analysis, voladizo, carga en la punta ---
    r2 = _beam_analysis(
        support="cantilever", length=2.0,
        point_loads=[{"P": 1000.0, "x": 2.0}],
    )
    exp_M2, exp_R2 = 2000.0, 1000.0
    checks.append({
        "name": "beam_cantilever_max_moment",
        "expected": exp_M2, "got": r2["max_moment"],
        "passed": abs(abs(r2["max_moment"]) - exp_M2) < 1e-3,
    })
    checks.append({
        "name": "beam_cantilever_reactions",
        "expected": {"R_A": exp_R2, "M_A": exp_M2}, "got": r2["reactions"],
        "passed": (
            abs(r2["reactions"]["R_A"] - exp_R2) < 1e-3
            and abs(r2["reactions"]["M_A"] - exp_M2) < 1e-3
        ),
    })
    checks.append({
        "name": "beam_cantilever_max_shear",
        "expected": exp_R2, "got": r2["max_shear"],
        "passed": abs(r2["max_shear"] - exp_R2) < 1e-3,
    })

    # --- 3) truss_analysis, triangulo isostatico simple ---
    r3 = _truss_analysis(
        nodes={"A": (0.0, 0.0), "B": (4.0, 0.0), "C": (2.0, 2.0)},
        members=[("A", "B"), ("A", "C"), ("B", "C")],
        supports={"A": "pin", "B": "roller_y"},
        loads={"C": (0.0, -1000.0)},
    )
    forces = {m["member"]: m["force"] for m in r3["member_forces"]}
    exp_AB, exp_AC_BC = 500.0, -707.107
    tol_truss = 0.05
    checks.append({
        "name": "truss_member_force_AB",
        "expected": exp_AB, "got": forces.get("A-B"),
        "passed": forces.get("A-B") is not None and abs(forces["A-B"] - exp_AB) < tol_truss,
    })
    checks.append({
        "name": "truss_member_force_AC",
        "expected": exp_AC_BC, "got": forces.get("A-C"),
        "passed": forces.get("A-C") is not None and abs(forces["A-C"] - exp_AC_BC) < tol_truss,
    })
    checks.append({
        "name": "truss_member_force_BC",
        "expected": exp_AC_BC, "got": forces.get("B-C"),
        "passed": forces.get("B-C") is not None and abs(forces["B-C"] - exp_AC_BC) < tol_truss,
    })
    exp_reac = 500.0
    r_ay = r3["reactions"].get("A", {}).get("R_y")
    r_by = r3["reactions"].get("B", {}).get("R_y")
    checks.append({
        "name": "truss_reactions_symmetric",
        "expected": exp_reac, "got": {"R_Ay": r_ay, "R_By": r_by},
        "passed": (
            r_ay is not None and r_by is not None
            and abs(r_ay - exp_reac) < tol_truss
            and abs(r_by - exp_reac) < tol_truss
        ),
    })
    checks.append({
        "name": "truss_equilibrium_residual",
        "expected": 0.0, "got": r3["equilibrium_check"],
        "passed": (
            abs(r3["equilibrium_check"]["sum_fx_residual"]) < 1e-6
            and abs(r3["equilibrium_check"]["sum_fy_residual"]) < 1e-6
        ),
    })

    # --- 4) section_properties, rectangular exacta ---
    r4 = _section_properties("rectangular", {"b": 0.2, "h": 0.4})
    exp_I = 0.2 * 0.4 ** 3 / 12
    exp_area = 0.08
    checks.append({
        "name": "section_rectangular_area",
        "expected": exp_area, "got": r4["area_m2"],
        "passed": abs(r4["area_m2"] - exp_area) < 1e-6,
    })
    checks.append({
        "name": "section_rectangular_moment_of_inertia",
        "expected": round(exp_I, 8), "got": r4["moment_of_inertia_m4"],
        "passed": abs(r4["moment_of_inertia_m4"] - exp_I) < 1e-8,
    })

    # --- 5) stress_check ---
    r5 = _stress_check(force=10000.0, area=0.01, allowable_stress=2e6)
    exp_stress, exp_sf = 1_000_000.0, 2.0
    checks.append({
        "name": "stress_check_value",
        "expected": exp_stress, "got": r5["stress"],
        "passed": abs(r5["stress"] - exp_stress) < 1e-3,
    })
    checks.append({
        "name": "stress_check_safety_factor",
        "expected": exp_sf, "got": r5["safety_factor"],
        "passed": abs(r5["safety_factor"] - exp_sf) < 1e-3,
    })
    checks.append({
        "name": "stress_check_pass_flag",
        "expected": True, "got": r5["pass"],
        "passed": r5["pass"] is True,
    })

    all_passed = all(c["passed"] for c in checks)
    return {
        "mode": "validate",
        "checks": checks,
        "all_passed": all_passed,
    }


def compute_structural_analysis(mode, **params):
    """Entry point del tool. Despacha según `mode`. Retorna un dict serializable a JSON."""
    if mode == "validate":
        return _validate_structural()
    if mode == "beam_analysis":
        return _beam_analysis(
            support=params["support"],
            length=params["length"],
            point_loads=params.get("point_loads"),
            distributed_load=params.get("distributed_load", 0.0),
            E=params.get("E"),
            I=params.get("I"),
            n_points=params.get("n_points", 100),
        )
    if mode == "truss_analysis":
        return _truss_analysis(
            nodes=params["nodes"],
            members=params["members"],
            supports=params["supports"],
            loads=params.get("loads"),
        )
    if mode == "section_properties":
        return _section_properties(params["shape"], params["dims"])
    if mode == "stress_check":
        return _stress_check(params["force"], params["area"], params["allowable_stress"])

    raise ValueError(
        f"mode no soportado: {mode}. Usar: beam_analysis | truss_analysis | "
        "section_properties | stress_check"
    )

try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass

register_tool("structural_analysis", STRUCTURAL_ANALYSIS_TOOL_SCHEMA, lambda args, _f=compute_structural_analysis: _f(**args))
