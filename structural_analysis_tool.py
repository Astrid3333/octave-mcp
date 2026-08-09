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
                "enum": ["beam_analysis", "truss_analysis", "section_properties", "stress_check"],
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

    i_max = int(np.argmax(np.abs(M)))
    max_moment = float(M[i_max])
    max_moment_x = float(x[i_max])
    max_shear = float(np.max(np.abs(V)))

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


def compute_structural_analysis(mode, **params):
    """Entry point del tool. Despacha según `mode`. Retorna un dict serializable a JSON."""
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
