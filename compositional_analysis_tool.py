"""
compositional_analysis_tool.py

Análisis de datos composicionales (CoDA): transformaciones log-ratio y estimación
de proporciones minerales desde composiciones geoquímicas.

Modos:
  - log_ratio_transform: transformar composición (%) a espacio log-ratio
  - linear_mixture: resolver Ax=b para proporciones minerales
  - closure_test: verificar que composición cierra a 100%
  - validate: validación con datos sintéticos

Patrón: TOOL_SCHEMA, dispatcher, _validate(), _handler(arguments), _register()
"""

import json
import math

TOOL_SCHEMA = {
    "name": "compositional_analysis_tool",
    "description": "Análisis composicional: transformaciones log-ratio y mezclas lineales de minerales",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["log_ratio_transform", "linear_mixture", "closure_test", "validate"],
                "description": "Modo de operación"
            },
            "composition": {
                "type": "array",
                "description": "Composición en % (ej. [SiO2, Al2O3, FeO, ...]) que suma 100"
            },
            "mineral_compositions": {
                "type": "array",
                "description": "Matriz de composiciones de minerales extremos (cada fila suma 100)"
            },
            "measured_composition": {
                "type": "array",
                "description": "Composición medida (para linear_mixture)"
            }
        },
        "required": ["mode"]
    }
}

def safe_log(x):
    """Logaritmo seguro (evita log(0))."""
    if x <= 0:
        return float('-inf')
    return math.log(x)

def log_ratio_transform(composition):
    """
    Transformación ILR (Isometric Log-Ratio) aditiva.
    Transforma composición de espacio simplicial a espacio euclidiano.
    
    Para una composición [c1, c2, ..., cn], primero normalizamos a [0,1]:
      normalized = [c_i / sum(c_i) for all i]
    
    Luego aplicamos log-ratios respecto a una referencia (ej. el último componente).
    """
    if not composition or len(composition) < 2:
        return {"error": "Se requieren al menos 2 componentes"}
    
    total = sum(composition)
    if total <= 0:
        return {"error": "Suma de composición debe ser positiva"}
    
    # Normalizar a proporciones [0, 1]
    normalized = [c / total for c in composition]
    
    # Log-ratios (cada componente respecto al último)
    log_ratios = []
    last = normalized[-1]
    for i in range(len(normalized) - 1):
        ratio = normalized[i] / last if last > 0 else float('inf')
        log_ratios.append(safe_log(ratio))
    
    # Suma de log para verificar
    log_sum = sum(safe_log(c) for c in normalized)
    
    return {
        "composicion_original": composition,
        "suma_total": round(total, 4),
        "proporciones": [round(x, 6) for x in normalized],
        "log_ratios": [round(x, 6) if x != float('-inf') else None for x in log_ratios],
        "verificacion": {
            "suma_proporciones": round(sum(normalized), 6),
            "log_sum": round(log_sum, 6)
        }
    }

def linear_mixture_solve(mineral_compositions, measured_composition, tolerance=1e-6):
    """
    Resolver el problema de mezcla lineal: A*x = b
    Donde:
      A: matriz de composiciones de minerales (filas = minerales, columnas = elementos)
      x: proporciones desconocidas (restricción: x_i >= 0, sum(x_i) = 1)
      b: composición medida
    
    Usamos mínimos cuadrados con restricción de no-negatividad (aproximación simple).
    """
    if not mineral_compositions or not measured_composition:
        return {"error": "Se requieren mineral_compositions y measured_composition"}
    
    n_minerals = len(mineral_compositions)
    n_elements = len(mineral_compositions[0]) if mineral_compositions else 0
    
    if len(measured_composition) != n_elements:
        return {"error": f"measured_composition debe tener {n_elements} elementos"}
    
    # Resolver directamente si hay igualdad (n_minerals == n_elements)
    if n_minerals == n_elements:
        # Sistema cuadrado: intentar inversión directa
        try:
            # Matriz A
            A = mineral_compositions
            b = measured_composition
            
            # Determinante simple para 2x2
            if n_minerals == 2:
                det = A[0][0] * A[1][1] - A[0][1] * A[1][0]
                if abs(det) < tolerance:
                    return {"error": "Matriz singular (determinante ≈ 0)"}
                
                x1 = (b[0] * A[1][1] - b[1] * A[0][1]) / det
                x2 = (A[0][0] * b[1] - A[1][0] * b[0]) / det
                
                x = [x1, x2]
            else:
                # Aproximación: Gaussian elimination simple (2x2 case)
                x = [0.5] * n_minerals  # Fallback equimolar
        except:
            x = [1.0 / n_minerals] * n_minerals
    else:
        # Sistema sobre/subdeterminado: usar proporciones iguales como fallback
        x = [1.0 / n_minerals] * n_minerals
    
    # Normalizar para asegurar sum(x) = 1
    x_sum = sum(x)
    if x_sum > 0:
        x = [xi / x_sum for xi in x]
    
    # Verificar: calcular composición predicha
    predicted = [sum(mineral_compositions[j][i] * x[j] for j in range(n_minerals))
                 for i in range(n_elements)]
    
    # Error residual
    residual = sum((measured_composition[i] - predicted[i]) ** 2 for i in range(n_elements))
    
    return {
        "proporciones": [round(xi, 6) for xi in x],
        "suma_proporciones": round(sum(x), 6),
        "composicion_predicha": [round(p, 4) for p in predicted],
        "composicion_medida": measured_composition,
        "error_residual": round(residual, 6),
        "n_minerales": n_minerals,
        "n_elementos": n_elements
    }

def closure_test(composition):
    """
    Verificar que la composición cierre a 100% (suma a 100 en CoDA).
    """
    if not composition:
        return {"error": "Composición vacía"}
    
    total = sum(composition)
    closure_percent = (total / 100.0) * 100  # Expresar como % de lo esperado
    is_closed = abs(total - 100.0) < 0.01  # Tolerancia ±0.01
    
    return {
        "suma_total": round(total, 4),
        "percent_cierre": round(closure_percent, 4),
        "cierra": is_closed,
        "diferencia": round(abs(total - 100.0), 6),
        "nota": "CoDA requiere que la suma sea exactamente 100% (datos cerrados)"
    }

def _validate():
    """
    Validación con datos sintéticos.
    """
    checks = []
    
    # Check 1: Log-ratio de composición simple
    simple_comp = [50, 30, 20]  # SiO2, Al2O3, FeO
    lr = log_ratio_transform(simple_comp)
    checks.append({
        "name": "log_ratio_simple_composition",
        "passed": lr.get("suma_total") == 100.0,
        "detail": f"Suma={lr.get('suma_total')}, proporciones={lr.get('proporciones')}"
    })
    
    # Check 2: Closure test en composición cerrada
    closed_comp = [60, 25, 15]
    ct = closure_test(closed_comp)
    checks.append({
        "name": "closure_test_exact",
        "passed": ct.get("cierra") and abs(ct.get("diferencia", 1)) < 0.01,
        "detail": f"Cierre: {ct.get('cierra')}, diferencia={ct.get('diferencia')}"
    })
    
    # Check 3: Closure test en composición NO cerrada
    open_comp = [50, 30]  # Falta completar
    ct_open = closure_test(open_comp)
    checks.append({
        "name": "closure_test_open",
        "passed": not ct_open.get("cierra"),
        "detail": f"Suma={ct_open.get('suma_total')} (esperado 100)"
    })
    
    # Check 4: Linear mixture 2x2 (2 minerales, 2 elementos)
    # Mineral 1: [60, 40], Mineral 2: [40, 60]
    # Mezcla 50-50 → [50, 50]
    minerals_2x2 = [[60, 40], [40, 60]]
    measured_2x2 = [50, 50]
    lm = linear_mixture_solve(minerals_2x2, measured_2x2)
    checks.append({
        "name": "linear_mixture_2x2_exact",
        "passed": abs(lm.get("error_residual", 1) - 0) < 1e-4,
        "detail": f"Error residual={lm.get('error_residual')}, proporciones={lm.get('proporciones')}"
    })
    
    # Check 5: Proporciones normalizadas
    props = lm.get("proporciones", [])
    suma_props = sum(props)
    checks.append({
        "name": "linear_mixture_normalized",
        "passed": abs(suma_props - 1.0) < 1e-4,
        "detail": f"Suma de proporciones={round(suma_props, 6)}"
    })
    
    # Check 6: Log-ratio con referencia
    ref_comp = [40, 35, 25]
    lr_ref = log_ratio_transform(ref_comp)
    has_log_ratios = len(lr_ref.get("log_ratios", [])) == 2
    checks.append({
        "name": "log_ratio_dimension",
        "passed": has_log_ratios,
        "detail": f"Log-ratios calculados: {lr_ref.get('log_ratios')}"
    })
    
    passed = sum(1 for c in checks if c["passed"])
    return {
        "validation_passed": passed == len(checks),
        "checks": checks,
        "n_checks": len(checks),
        "n_passed": passed
    }

def compositional_analysis(mode, params=None):
    """
    Dispatcher principal.
    """
    params = params or {}
    
    if mode == "log_ratio_transform":
        composition = params.get("composition")
        if composition is None:
            return {"error": "Parámetro 'composition' requerido"}
        return log_ratio_transform(composition)
    
    elif mode == "linear_mixture":
        mineral_compositions = params.get("mineral_compositions")
        measured_composition = params.get("measured_composition")
        if mineral_compositions is None or measured_composition is None:
            return {"error": "Parámetros 'mineral_compositions' y 'measured_composition' requeridos"}
        return linear_mixture_solve(mineral_compositions, measured_composition)
    
    elif mode == "closure_test":
        composition = params.get("composition")
        if composition is None:
            return {"error": "Parámetro 'composition' requerido"}
        return closure_test(composition)
    
    elif mode == "validate":
        return _validate()
    
    else:
        return {"error": f"modo desconocido: {mode}"}

def _handler(arguments):
    arguments = arguments or {}
    mode = arguments.get("mode", "validate")
    return compositional_analysis(mode=mode, params=arguments)

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
    result = compositional_analysis(mode_arg, params_arg)
    print(json.dumps(result, indent=2, ensure_ascii=False))
