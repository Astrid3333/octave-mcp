"""
moss_lsystem_tool.py

Modelo de crecimiento de musgo (protonema, tipo Physcomitrella patens) basado
en L-systems (sistemas de Lindenmayer), con interpretacion via turtle graphics
y calculo de metricas de forma (area, circularidad, dimension fractal por
conteo de cajas) para comparar fenotipos, siguiendo el enfoque descrito en la
literatura de morfogenesis celular protonemal.

--------------------------------------------------------------------------
L-system
--------------------------------------------------------------------------
Un L-system se define por:
    axiom : cadena inicial
    rules : dict de reescritura, p.ej. {"F": "F[+F]F[-F]F"}
    iterations : cuantas veces aplicar las reglas

En cada iteracion, cada simbolo en la cadena actual se reemplaza por su regla
(si existe) o se deja igual (si no hay regla para ese simbolo).

--------------------------------------------------------------------------
Interpretacion turtle (alfabeto soportado)
--------------------------------------------------------------------------
    F : avanzar dibujando un segmento de longitud `step`
    f : avanzar SIN dibujar (mover el "cursor" sin dejar traza)
    + : rotar a la izquierda `angle` grados
    - : rotar a la derecha `angle` grados
    [ : apilar el estado actual (posicion, direccion) -- inicio de rama
    ] : desapilar el ultimo estado guardado -- fin de rama, volver al punto
        de ramificacion (asi es como se generan estructuras ramificadas tipo
        protonema a partir de una cadena lineal)

--------------------------------------------------------------------------
Metricas de forma
--------------------------------------------------------------------------
    area / perimetro (via envolvente convexa de todos los vertices generados)
    circularidad = 4*pi*Area / Perimetro^2   (1.0 = circulo perfecto, < 1 para
                    formas mas irregulares/alargadas -- metrica estandar de
                    "compactness")
    dimension fractal por conteo de cajas (box-counting): se cubre el plano
                    con grillas de tamano decreciente, se cuenta cuantas celdas
                    contienen al menos un punto de la estructura, y se ajusta
                    la pendiente de log(N_cajas) vs log(1/tamano_caja) por
                    minimos cuadrados. La pendiente ES la dimension fractal
                    estimada.

--------------------------------------------------------------------------
Indice de plastocrono (aproximacion)
--------------------------------------------------------------------------
El indice de plastocrono cuantifica la "edad de desarrollo" de la planta en
unidades de eventos de division/ramificacion en vez de tiempo cronologico.
Aqui se aproxima como el numero de simbolos de ramificacion "[" generados
(cada apertura de rama es un evento morfogenetico discreto), normalizado
opcionalmente por una tasa de referencia.

NOTA DE INTEGRACION (ver las 4 tools anteriores de esta serie): firma de
_handler, formato de SCHEMA y exposicion de mode="validate" siguen la misma
convencion generica. Ajustar contra una tool real del repo antes de wire-earlo.
"""

import math


MAX_ITERATIONS = 10          # limite de seguridad: la cadena crece exponencialmente
MAX_STRING_LENGTH = 2_000_000  # limite de seguridad adicional, independiente de iterations


# ---------------------------------------------------------------------------
# Generacion del L-system (reescritura de cadenas)
# ---------------------------------------------------------------------------

def generate_lsystem_string(axiom, rules, iterations):
    """
    Aplica las reglas de reescritura `iterations` veces sobre `axiom`.
    Simbolos sin regla definida se dejan sin cambios (identidad implicita).
    """
    if iterations < 0:
        raise ValueError("iterations debe ser >= 0")
    if iterations > MAX_ITERATIONS:
        raise ValueError(f"iterations excede el limite de seguridad ({MAX_ITERATIONS})")
    if not axiom:
        raise ValueError("axiom no puede estar vacio")

    current = axiom
    for _ in range(iterations):
        if len(current) > MAX_STRING_LENGTH:
            raise ValueError(
                f"La cadena L-system supero el limite de seguridad "
                f"({MAX_STRING_LENGTH} caracteres) antes de completar las iteraciones"
            )
        next_chars = []
        for ch in current:
            next_chars.append(rules.get(ch, ch))
        current = "".join(next_chars)

    if len(current) > MAX_STRING_LENGTH:
        raise ValueError(
            f"La cadena L-system final supero el limite de seguridad "
            f"({MAX_STRING_LENGTH} caracteres)"
        )
    return current


# ---------------------------------------------------------------------------
# Interpretacion turtle
# ---------------------------------------------------------------------------

def turtle_interpret(lsystem_string, step=1.0, angle_degrees=25.0,
                      start_pos=(0.0, 0.0), start_heading_degrees=90.0):
    """
    Interpreta la cadena L-system como comandos de turtle graphics.
    Retorna:
        segments  : lista de ((x0,y0),(x1,y1)) para cada trazo "F"
        vertices  : lista de todos los puntos visitados (incluye los de "f")
        n_branches: cantidad de simbolos "[" (aperturas de rama)
        final_pos : posicion final de la turtle
    """
    x, y = start_pos
    heading = math.radians(start_heading_degrees)
    angle_rad = math.radians(angle_degrees)

    stack = []
    segments = []
    vertices = [(x, y)]
    n_branches = 0

    for ch in lsystem_string:
        if ch == "F":
            x_new = x + step * math.cos(heading)
            y_new = y + step * math.sin(heading)
            segments.append(((x, y), (x_new, y_new)))
            x, y = x_new, y_new
            vertices.append((x, y))
        elif ch == "f":
            x = x + step * math.cos(heading)
            y = y + step * math.sin(heading)
            vertices.append((x, y))
        elif ch == "+":
            heading += angle_rad
        elif ch == "-":
            heading -= angle_rad
        elif ch == "[":
            stack.append((x, y, heading))
            n_branches += 1
        elif ch == "]":
            if not stack:
                raise ValueError("Cadena L-system mal formada: ']' sin '[' correspondiente")
            x, y, heading = stack.pop()
        # cualquier otro simbolo (p.ej. simbolos "no terminales" auxiliares
        # usados solo para la gramatica de reescritura, sin accion grafica
        # asociada, como es comun en L-systems) se ignora silenciosamente
        # en la interpretacion turtle -- es el comportamiento estandar.

    if stack:
        raise ValueError(
            f"Cadena L-system mal formada: {len(stack)} '[' sin su ']' correspondiente"
        )

    return {
        "segments": segments,
        "vertices": vertices,
        "n_branches": n_branches,
        "final_pos": (x, y),
    }


# ---------------------------------------------------------------------------
# Envolvente convexa (Graham scan) y metricas derivadas
# ---------------------------------------------------------------------------

def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def convex_hull(points):
    """
    Envolvente convexa via el algoritmo de Andrew (monotone chain), O(n log n).
    Retorna los vertices del hull en orden antihorario, sin puntos duplicados.
    """
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    lower = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def polygon_area_perimeter(vertices):
    """
    Area (formula del shoelace) y perimetro de un poligono dado por sus
    vertices en orden (se asume ya como salida de convex_hull, orden
    antihorario, sin repetir el primer punto al final).
    """
    n = len(vertices)
    if n < 3:
        return 0.0, 0.0

    area2 = 0.0
    perimeter = 0.0
    for i in range(n):
        x0, y0 = vertices[i]
        x1, y1 = vertices[(i + 1) % n]
        area2 += (x0 * y1 - x1 * y0)
        perimeter += math.hypot(x1 - x0, y1 - y0)

    area = abs(area2) / 2.0
    return area, perimeter


def circularity(area, perimeter):
    """
    Circularidad estandar: 4*pi*Area / Perimetro^2. 1.0 para un circulo
    perfecto, menor a 1.0 para formas mas irregulares o alargadas.
    """
    if perimeter <= 0:
        return 0.0
    return (4.0 * math.pi * area) / (perimeter ** 2)


# ---------------------------------------------------------------------------
# Dimension fractal por conteo de cajas (box-counting)
# ---------------------------------------------------------------------------

def _sample_points_along_segments(segments, samples_per_unit_length=10.0):
    """
    Genera puntos muestreados a lo largo de cada segmento (no solo los
    extremos), necesario para que el box-counting vea la estructura como una
    curva continua y no solo sus vertices -- de lo contrario segmentos largos
    quedarian sub-representados en la grilla.
    """
    points = []
    for (x0, y0), (x1, y1) in segments:
        length = math.hypot(x1 - x0, y1 - y0)
        n_samples = max(2, int(math.ceil(length * samples_per_unit_length)))
        for i in range(n_samples + 1):
            t = i / n_samples
            points.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
    return points


def box_counting_dimension(segments, box_sizes=None):
    """
    Estima la dimension fractal de la estructura (dada como lista de
    segmentos) por conteo de cajas en multiples escalas, ajustando
    log(N_cajas) = -D * log(box_size) + c por minimos cuadrados. La pendiente
    (con signo cambiado) es la dimension fractal estimada.
    """
    if not segments:
        raise ValueError("Se requiere al menos un segmento para estimar la dimension fractal")

    points = _sample_points_along_segments(segments)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    span = max(x_max - x_min, y_max - y_min, 1e-9)

    if box_sizes is None:
        # 6 escalas logaritmicamente espaciadas entre span/2 y span/64
        box_sizes = [span / (2 ** k) for k in range(1, 7)]

    log_inv_size = []
    log_n_boxes = []
    for box_size in box_sizes:
        if box_size <= 0:
            continue
        occupied = set()
        for (px, py) in points:
            cell = (int((px - x_min) / box_size), int((py - y_min) / box_size))
            occupied.add(cell)
        n_boxes = len(occupied)
        if n_boxes > 0:
            log_inv_size.append(math.log(1.0 / box_size))
            log_n_boxes.append(math.log(n_boxes))

    if len(log_inv_size) < 2:
        raise ValueError("Insuficientes escalas validas para ajustar la dimension fractal")

    n = len(log_inv_size)
    x_mean = sum(log_inv_size) / n
    y_mean = sum(log_n_boxes) / n
    Sxx = sum((x - x_mean) ** 2 for x in log_inv_size)
    Sxy = sum((x - x_mean) * (y - y_mean) for x, y in zip(log_inv_size, log_n_boxes))

    if Sxx == 0:
        raise ValueError("Todas las escalas de caja dieron el mismo log(1/size); no se puede ajustar")

    slope = Sxy / Sxx  # esta pendiente ES la dimension fractal (definicion estandar)
    return {
        "fractal_dimension": slope,
        "n_scales_used": n,
        "box_sizes_used": box_sizes[:n],
    }


# ---------------------------------------------------------------------------
# Indice de plastocrono (aproximacion)
# ---------------------------------------------------------------------------

def plastochron_index(n_branches, reference_rate=1.0):
    """
    Aproximacion del indice de plastocrono como numero de eventos de
    ramificacion normalizado por una tasa de referencia (default 1.0,
    es decir el indice crudo = n_branches).
    """
    if reference_rate <= 0:
        raise ValueError("reference_rate debe ser > 0")
    return n_branches / reference_rate


# ---------------------------------------------------------------------------
# Pipeline combinado: generar + interpretar + medir
# ---------------------------------------------------------------------------

def generate_and_measure(axiom, rules, iterations, step=1.0, angle_degrees=25.0):
    lsys_string = generate_lsystem_string(axiom, rules, iterations)
    turtle_result = turtle_interpret(lsys_string, step=step, angle_degrees=angle_degrees)

    hull = convex_hull(turtle_result["vertices"])
    area, perimeter = polygon_area_perimeter(hull)
    circ = circularity(area, perimeter)

    fractal = None
    if turtle_result["segments"]:
        fractal = box_counting_dimension(turtle_result["segments"])

    pi_index = plastochron_index(turtle_result["n_branches"])

    return {
        "lsystem_string_length": len(lsys_string),
        "n_branches": turtle_result["n_branches"],
        "final_pos": turtle_result["final_pos"],
        "convex_hull_area": area,
        "convex_hull_perimeter": perimeter,
        "circularity": circ,
        "fractal_dimension": fractal["fractal_dimension"] if fractal else None,
        "plastochron_index": pi_index,
    }


# ---------------------------------------------------------------------------
# Validacion / self-test
# ---------------------------------------------------------------------------

def _run_validation_cases():
    passed = 0
    failed = 0
    details = []

    # Caso 1: crecimiento de longitud de cadena determinista y predecible para
    # una regla simple "F" -> "FF" (duplica en cada iteracion): tras n
    # iteraciones, len == len(axiom) * 2^n. Chequeo exacto, sin ambiguedad.
    axiom1 = "F"
    rules1 = {"F": "FF"}
    for n_iter in [0, 1, 3, 5]:
        s = generate_lsystem_string(axiom1, rules1, n_iter)
        expected_len = len(axiom1) * (2 ** n_iter)
        ok = len(s) == expected_len
        details.append((f"string_length_doubling_iter{n_iter}", ok, len(s), expected_len))
        passed += int(ok); failed += int(not ok)

    # Caso 2: interpretacion turtle de una linea recta (sin turns), "F" repetido
    # N veces sin "+"/"-": el punto final debe estar exactamente a distancia
    # N*step del origen, en la direccion inicial (heading=90 -> eje Y).
    lsys2 = "F" * 10
    result2 = turtle_interpret(lsys2, step=1.5, angle_degrees=25.0, start_pos=(0.0, 0.0),
                                start_heading_degrees=90.0)
    fx, fy = result2["final_pos"]
    ok2 = math.isclose(fx, 0.0, abs_tol=1e-9) and math.isclose(fy, 10 * 1.5, rel_tol=1e-9)
    details.append(("straight_line_turtle_endpoint", ok2, (fx, fy)))
    passed += int(ok2); failed += int(not ok2)

    # Caso 3: un cuadrado dibujado con turtle (F, giro 90, x4) debe dar area
    # EXACTA = lado^2 via convex hull (chequeo geometrico cerrado, sin
    # tolerancia laxa -- un cuadrado es un caso donde el hull es exacto).
    side = 3.0
    lsys3 = "F+F+F+F"  # con angle=90: avanza, gira, avanza, gira... cierra el cuadrado
    result3 = turtle_interpret(lsys3, step=side, angle_degrees=90.0,
                                start_pos=(0.0, 0.0), start_heading_degrees=0.0)
    hull3 = convex_hull(result3["vertices"])
    area3, perimeter3 = polygon_area_perimeter(hull3)
    ok3 = math.isclose(area3, side ** 2, rel_tol=1e-9) and math.isclose(perimeter3, 4 * side, rel_tol=1e-9)
    details.append(("square_exact_area_and_perimeter", ok3, area3, side ** 2))
    passed += int(ok3); failed += int(not ok3)

    # Caso 4: circularidad de ese mismo cuadrado debe ser pi/4 (~0.785),
    # resultado analitico conocido para un cuadrado exacto.
    circ3 = circularity(area3, perimeter3)
    expected_circ = math.pi / 4.0
    ok4 = math.isclose(circ3, expected_circ, rel_tol=1e-6)
    details.append(("square_circularity_matches_pi_over_4", ok4, circ3, expected_circ))
    passed += int(ok4); failed += int(not ok4)

    # Caso 5: dimension fractal de una linea recta pura debe acercarse a 1.0
    # (dimension topologica de una curva simple, el caso trivial de sanidad
    # para box-counting antes de confiar en el metodo para formas ramificadas).
    lsys5 = "F" * 40
    result5 = turtle_interpret(lsys5, step=0.5, angle_degrees=25.0, start_heading_degrees=0.0)
    fractal5 = box_counting_dimension(result5["segments"])
    ok5 = abs(fractal5["fractal_dimension"] - 1.0) < 0.15
    details.append(("straight_line_fractal_dim_near_1", ok5, fractal5["fractal_dimension"]))
    passed += int(ok5); failed += int(not ok5)

    # Caso 6: rama balanceada -> n_branches cuenta "[" correctamente, y el
    # stack debe quedar vacio (turtle_interpret no debe lanzar excepcion) para
    # una cadena bien formada con ramas anidadas.
    lsys6 = "F[+F[+F]F][-F]F"
    result6 = turtle_interpret(lsys6, step=1.0, angle_degrees=25.0)
    expected_branches6 = lsys6.count("[")
    ok6 = result6["n_branches"] == expected_branches6
    details.append(("branch_count_matches_bracket_count", ok6, result6["n_branches"], expected_branches6))
    passed += int(ok6); failed += int(not ok6)

    # Caso 7: cadena mal formada (brackets desbalanceados) debe lanzar ValueError
    ok7 = False
    try:
        turtle_interpret("F[+F")  # falta el "]"
    except ValueError:
        ok7 = True
    details.append(("rejects_unbalanced_brackets", ok7))
    passed += int(ok7); failed += int(not ok7)

    # Caso 8: iterations excesivo debe ser rechazado por el limite de seguridad
    ok8 = False
    try:
        generate_lsystem_string("F", {"F": "FF"}, MAX_ITERATIONS + 1)
    except ValueError:
        ok8 = True
    details.append(("rejects_excessive_iterations", ok8))
    passed += int(ok8); failed += int(not ok8)

    return passed, failed, details


def validate():
    passed, failed, details = _run_validation_cases()
    return {
        "mode": "validate",
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Handler (JSON-RPC dispatch)
# ---------------------------------------------------------------------------
#
# AJUSTAR el nombre del argumento posicional (arguments / args / params) segun
# convencion real del repo antes de wire-earlo. Se usa "arguments" siguiendo
# el patron de algebraic_curve_tool.py, igual que en las tools anteriores de
# esta serie.

def _handler(arguments):
    mode = arguments.get("mode", "generate_and_measure")

    if mode == "validate":
        return validate()

    if mode == "generate_and_measure":
        required = ["axiom", "rules", "iterations"]
        missing = [k for k in required if k not in arguments]
        if missing:
            raise ValueError(f"Faltan parametros requeridos para mode='generate_and_measure': {missing}")
        step = arguments.get("step", 1.0)
        angle_degrees = arguments.get("angle_degrees", 25.0)
        return generate_and_measure(
            arguments["axiom"], arguments["rules"], arguments["iterations"],
            step=step, angle_degrees=angle_degrees,
        )

    if mode == "generate_string":
        required = ["axiom", "rules", "iterations"]
        missing = [k for k in required if k not in arguments]
        if missing:
            raise ValueError(f"Faltan parametros requeridos para mode='generate_string': {missing}")
        s = generate_lsystem_string(arguments["axiom"], arguments["rules"], arguments["iterations"])
        return {"lsystem_string": s, "length": len(s)}

    raise ValueError(
        f"Modo desconocido: {mode!r}. Usar 'generate_and_measure', "
        f"'generate_string' o 'validate'."
    )


# ---------------------------------------------------------------------------
# Schema JSON-RPC (AJUSTAR formato exacto segun convencion del repo)
# ---------------------------------------------------------------------------

TOOL_SCHEMA = {
    "name": "moss_lsystem_tool",
    "description": (
        "Genera morfologias de musgo (protonema) mediante L-systems, interpreta "
        "la cadena resultante como turtle graphics, y calcula metricas de forma "
        "(area, circularidad, dimension fractal por conteo de cajas) e indice "
        "de plastocrono aproximado, para comparar fenotipos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["generate_and_measure", "generate_string", "validate"],
                "description": "Operacion a realizar.",
            },
            "axiom": {"type": "string", "description": "Cadena inicial del L-system"},
            "rules": {
                "type": "object",
                "description": "Reglas de reescritura, p.ej. {'F': 'F[+F]F[-F]F'}",
            },
            "iterations": {
                "type": "integer",
                "description": f"Numero de iteraciones de reescritura (0-{MAX_ITERATIONS})",
            },
            "step": {"type": "number", "description": "Longitud de avance por 'F' (default 1.0)"},
            "angle_degrees": {"type": "number", "description": "Angulo de giro para '+'/'-' (default 25.0)"},
        },
        "required": ["mode"],
    },
}


# ---------------------------------------------------------------------------
# Auto-test local (correr directo: python3 moss_lsystem_tool.py)
# ---------------------------------------------------------------------------


def _register():
    try:
        import tool_registry
        tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()

if __name__ == "__main__":
    result = validate()
    print(f"PASSED: {result['passed']}/{result['total']}")
    if result["failed"] > 0:
        print("FALLOS:")
        for d in result["details"]:
            print(" ", d)
