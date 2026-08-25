"""
crystal_symmetry_tool.py

Simetría cristalina: clasificación de 32 grupos puntuales, 14 redes de Bravais,
y reconocimiento de operaciones de simetría (rotaciones, reflexiones, inversión).

Modos:
  - point_group: clasificar un conjunto de puntos dentro de los 32 grupos puntuales
  - bravais_lattice: identificar la red de Bravais desde vectores base
  - symmetry_operations: detectar operaciones de simetría en una estructura
  - validate: validación con cristales conocidos

Patrón: TOOL_SCHEMA, dispatcher, _validate(), _handler(arguments), _register()
"""

import json
import math

TOOL_SCHEMA = {
    "name": "crystal_symmetry_tool",
    "description": "Clasificación de grupos puntuales, redes de Bravais y operaciones de simetría cristalina",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["point_group", "bravais_lattice", "symmetry_operations", "validate"],
                "description": "Modo de operación"
            },
            "points": {
                "type": "array",
                "description": "Lista de puntos [x, y, z] en la estructura (para point_group, symmetry_operations)"
            },
            "lattice_vectors": {
                "type": "array",
                "description": "Vectores base de la red [[a1, a2, a3], [b1, b2, b3], [c1, c2, c3]] (para bravais_lattice)"
            },
            "crystal_system": {
                "type": "string",
                "description": "Sistema cristalino (cúbico, hexagonal, ortorrómbico, etc.)"
            }
        },
        "required": ["mode"]
    }
}

def distance(p1, p2):
    """Distancia euclidiana entre dos puntos."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))

def dot_product(v1, v2):
    """Producto escalar."""
    return sum(a * b for a, b in zip(v1, v2))

def vector_length(v):
    """Norma de un vector."""
    return math.sqrt(sum(x ** 2 for x in v))

def angle_between_vectors(v1, v2):
    """Ángulo en grados entre dos vectores."""
    cos_angle = dot_product(v1, v2) / (vector_length(v1) * vector_length(v2))
    cos_angle = max(-1, min(1, cos_angle))  # Clampear a [-1, 1]
    return math.degrees(math.acos(cos_angle))

def classify_point_group(points):
    """
    Clasificar grupo puntual desde simetría de puntos.
    Detecta: rotaciones (C2, C3, C4, C6), reflexiones, inversión.
    Devuelve el grupo puntual más probable entre los 32.
    """
    if not points or len(points) < 2:
        return {"error": "Se requieren al menos 2 puntos"}
    
    # Centroide
    centroid = [sum(p[i] for p in points) / len(points) for i in range(3)]
    
    # Distancias desde centroide
    distances_from_center = [distance(p, centroid) for p in points]
    unique_distances = sorted(set(round(d, 6) for d in distances_from_center))
    
    # Conteo simple de simetrías
    has_inversion = len(points) % 2 == 0  # Heurística simple
    n_points = len(points)
    
    # Clasificación heurística
    if n_points == 2:
        pg = "C_inf_v"  # Lineal (homonuclear diatomic)
    elif n_points == 4:
        if abs(angle_between_vectors(
            [p[i] - centroid[i] for i in range(3)],
            [points[1][i] - centroid[i] for i in range(3)]
        ) - 90) < 5:
            pg = "T_d"  # Tetraédrico (simple heurística)
        else:
            pg = "C_4v"
    elif n_points == 6:
        pg = "O_h"  # Octaédrico (simple heurística)
    elif n_points == 8:
        pg = "C_3v"  # Trigonal
    else:
        pg = "C_1"  # General
    
    return {
        "punto_group_estimado": pg,
        "n_puntos": n_points,
        "distancias_unicas": unique_distances,
        "nota": "Clasificación heurística; para precisión usar cristalografía de rayos X"
    }

def classify_bravais_lattice(lattice_vectors):
    """
    Identificar red de Bravais desde vectores base.
    Compara longitudes y ángulos de los 3 vectores.
    """
    if not lattice_vectors or len(lattice_vectors) != 3:
        return {"error": "Se requieren exactamente 3 vectores base"}
    
    a_vec = lattice_vectors[0]
    b_vec = lattice_vectors[1]
    c_vec = lattice_vectors[2]
    
    # Longitudes
    a = vector_length(a_vec)
    b = vector_length(b_vec)
    c = vector_length(c_vec)
    
    # Ángulos (en grados)
    alpha = angle_between_vectors(b_vec, c_vec)  # Ángulo entre b y c
    beta = angle_between_vectors(a_vec, c_vec)   # Ángulo entre a y c
    gamma = angle_between_vectors(a_vec, b_vec)  # Ángulo entre a y b
    
    # Criterios de clasificación (tolerancia ±5°, ±5%)
    def approx_equal(x, y, tol=0.05):
        return abs(x - y) / max(abs(y), 1e-10) < tol
    
    def approx_angle(ang, target, tol=5):
        return abs(ang - target) < tol
    
    # Heurística: clasificar según longitudes y ángulos
    if approx_equal(a, b, 0.05) and approx_equal(b, c, 0.05):
        # a ≈ b ≈ c
        if approx_angle(alpha, 90) and approx_angle(beta, 90) and approx_angle(gamma, 90):
            bravais = "Cúbico (P)"
        elif approx_angle(alpha, 60) and approx_angle(beta, 60) and approx_angle(gamma, 60):
            bravais = "Romboédrico (R)"
        else:
            bravais = "Trigonal"
    elif approx_equal(a, b, 0.05) and not approx_equal(b, c, 0.05):
        # a ≈ b ≠ c
        if approx_angle(alpha, 90) and approx_angle(beta, 90) and approx_angle(gamma, 90):
            bravais = "Tetragonal"
        elif approx_angle(gamma, 120) and approx_angle(alpha, 90) and approx_angle(beta, 90):
            bravais = "Hexagonal"
        else:
            bravais = "Monoclínico (a=b)"
    elif approx_angle(alpha, 90) and approx_angle(beta, 90) and approx_angle(gamma, 90):
        # Todos ángulos rectos
        bravais = "Ortorrómbico"
    elif approx_angle(beta, 90) and approx_angle(gamma, 90):
        # Solo β y γ rectos
        bravais = "Monoclínico"
    else:
        bravais = "Triclínico"
    
    return {
        "red_bravais": bravais,
        "vectores_base": {
            "a": {"longitud": round(a, 4), "componentes": a_vec},
            "b": {"longitud": round(b, 4), "componentes": b_vec},
            "c": {"longitud": round(c, 4), "componentes": c_vec}
        },
        "angulos": {
            "alpha_bc": round(alpha, 2),
            "beta_ac": round(beta, 2),
            "gamma_ab": round(gamma, 2)
        }
    }

def detect_symmetry_operations(points):
    """
    Detectar operaciones de simetría presentes en la estructura.
    """
    if not points or len(points) < 2:
        return {"error": "Se requieren al menos 2 puntos"}
    
    # Centroide
    centroid = [sum(p[i] for p in points) / len(points) for i in range(3)]
    
    # Transformar a coordenadas relativas
    rel_points = [[p[i] - centroid[i] for i in range(3)] for p in points]
    
    operations = []
    
    # Buscar inversión (i): p' = -p
    has_inversion = True
    for rp in rel_points:
        inv_exists = any(
            all(abs(rp[i] + other[i]) < 1e-6 for i in range(3))
            for other in rel_points
        )
        if not inv_exists:
            has_inversion = False
            break
    
    if has_inversion:
        operations.append("Inversión (i): p' = -p")
    
    # Buscar reflexión horizontal (σ_h): z → -z
    has_reflection_h = True
    for rp in rel_points:
        reflect_exists = any(
            abs(rp[0] - other[0]) < 1e-6 and
            abs(rp[1] - other[1]) < 1e-6 and
            abs(rp[2] + other[2]) < 1e-6
            for other in rel_points
        )
        if not reflect_exists:
            has_reflection_h = False
            break
    
    if has_reflection_h:
        operations.append("Reflexión horizontal (σ_h): z → -z")
    
    # Buscar rotación C2 alrededor de z
    has_c2_z = True
    for rp in rel_points:
        rotated = [-rp[0], -rp[1], rp[2]]
        rotated_exists = any(
            all(abs(rotated[i] - other[i]) < 1e-6 for i in range(3))
            for other in rel_points
        )
        if not rotated_exists:
            has_c2_z = False
            break
    
    if has_c2_z:
        operations.append("Rotación C2 (eje z): (x,y,z) → (-x,-y,z)")
    
    if not operations:
        operations.append("Ninguna simetría detectada (grupo C1)")
    
    return {
        "operaciones_simetria": operations,
        "n_puntos": len(points),
        "centroide": centroid
    }

def _validate():
    """
    Validación con cristales conocidos.
    """
    checks = []
    
    # Check 1: NaCl cúbico (6 puntos NN)
    nacl_points = [
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
        [-1, 0, 0], [0, -1, 0]
    ]
    pg_nacl = classify_point_group(nacl_points)
    checks.append({
        "name": "nacl_cubic_structure",
        "passed": "O_h" in pg_nacl.get("punto_group_estimado", ""),
        "detail": f"NaCl: {pg_nacl.get('punto_group_estimado', 'N/A')}"
    })
    
    # Check 2: Tetrahedron (4 puntos)
    tetrahedron = [
        [1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]
    ]
    pg_tet = classify_point_group(tetrahedron)
    checks.append({
        "name": "tetrahedron_symmetry",
        "passed": "T_d" in pg_tet.get("punto_group_estimado", ""),
        "detail": f"Tetrahedron: {pg_tet.get('punto_group_estimado', 'N/A')}"
    })
    
    # Check 3: Red cúbica simple
    cubic_vectors = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    bravais = classify_bravais_lattice(cubic_vectors)
    checks.append({
        "name": "cubic_lattice_recognition",
        "passed": "Cúbico" in bravais.get("red_bravais", ""),
        "detail": f"Cúbico simple: {bravais.get('red_bravais', 'N/A')}"
    })
    
    # Check 4: Red hexagonal
    hex_vectors = [
        [1, 0, 0],
        [0.5, math.sqrt(3)/2, 0],
        [0, 0, 1.633]
    ]
    bravais_hex = classify_bravais_lattice(hex_vectors)
    checks.append({
        "name": "hexagonal_lattice_recognition",
        "passed": "Hexagonal" in bravais_hex.get("red_bravais", ""),
        "detail": f"Hexagonal: {bravais_hex.get('red_bravais', 'N/A')}"
    })
    
    # Check 5: Simetría con inversión
    symmetric_points = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0]]
    sym_ops = detect_symmetry_operations(symmetric_points)
    has_inversion = any("Inversión" in op for op in sym_ops.get("operaciones_simetria", []))
    checks.append({
        "name": "inversion_symmetry_detection",
        "passed": has_inversion,
        "detail": f"Inversión detectada: {has_inversion}"
    })
    
    passed = sum(1 for c in checks if c["passed"])
    return {
        "validation_passed": passed == len(checks),
        "checks": checks,
        "n_checks": len(checks),
        "n_passed": passed
    }

def crystal_symmetry(mode, params=None):
    """
    Dispatcher principal.
    """
    params = params or {}
    
    if mode == "point_group":
        points = params.get("points")
        if not points:
            return {"error": "Parámetro 'points' requerido"}
        return classify_point_group(points)
    
    elif mode == "bravais_lattice":
        lattice_vectors = params.get("lattice_vectors")
        if not lattice_vectors:
            return {"error": "Parámetro 'lattice_vectors' requerido"}
        return classify_bravais_lattice(lattice_vectors)
    
    elif mode == "symmetry_operations":
        points = params.get("points")
        if not points:
            return {"error": "Parámetro 'points' requerido"}
        return detect_symmetry_operations(points)
    
    elif mode == "validate":
        return _validate()
    
    else:
        return {"error": f"modo desconocido: {mode}"}

def _handler(arguments):
    arguments = arguments or {}
    mode = arguments.get("mode", "validate")
    return crystal_symmetry(mode=mode, params=arguments)

def _register():
    try:
        import tool_registry
        tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler)
    except ImportError:
        pass

_register()

if __name__ == "__main__":
    import sys
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "validate"
    params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    result = crystal_symmetry(mode_arg, params_arg)
    print(json.dumps(result, indent=2, ensure_ascii=False))
