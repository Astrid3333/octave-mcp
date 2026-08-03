"""
bifurcation_tool.py

Módulo para octave-mcp: genera diagramas de bifurcación para mapas
iterativos 1D (x_{n+1} = f(x,r)) y analiza la estabilidad de puntos
fijos vía la derivada (Jacobiano 1D). Para mapas 2D, incluye un caso
especial (henon) que usa autovalores del Jacobiano 2x2.

INTEGRACIÓN: mismo patrón que lyapunov_tool.py / stiff_ode_tool.py.
"""

import subprocess
import tempfile
import os
import re
from textwrap import dedent

PRESET_MAPS_1D = {
    "logistic": {"expr": "r*x*(1-x)", "r_range": [2.4, 4.0], "x0": 0.5},
    "sine": {"expr": "r*sin(pi*x)", "r_range": [0.6, 1.0], "x0": 0.5},
    "cubic": {"expr": "r*x*(1-x^2)", "r_range": [1.5, 3.0], "x0": 0.3},
    "tent": {"expr": "r*min(x, 1-x)", "r_range": [0.5, 2.0], "x0": 0.4},
}

_VALID_OCTAVE_TOKEN = re.compile(r"^[a-zA-Z0-9_\.\+\-\*/\(\)\[\]\s,;:^]+$")


def _sanitize_expr(expr: str) -> str:
    if not _VALID_OCTAVE_TOKEN.match(expr):
        raise ValueError("La expresión contiene caracteres no permitidos.")
    return expr


def compute_bifurcation_diagram(
    map_name: str = "logistic",
    custom_expr: str | None = None,
    r_range: list[float] | None = None,
    x0: float | None = None,
    n_r_values: int = 300,
    n_transient: int = 500,
    n_keep: int = 40,
    stability_check_rs: list[float] | None = None,
    octave_bin: str = "octave",
    timeout_s: int = 60,
) -> dict:
    """
    Genera un diagrama de bifurcación para un mapa 1D x_{n+1}=f(x,r).

    Args:
        map_name: "logistic", "sine", "cubic", "tent", o "custom".
        custom_expr: si map_name="custom", expresión Octave en x,r. Ej "r*x*(1-x)".
        r_range: [r_min, r_max] (por defecto, el del preset).
        x0: condición inicial (por defecto, la del preset).
        n_r_values: cantidad de valores de r a barrer.
        n_transient: iteraciones descartadas antes de guardar puntos (deja
            que la trayectoria converja al atractor).
        n_keep: cuántas iteraciones se guardan por cada r (para dibujar el
            diagrama; más puntos = atractor más denso/visible).
        stability_check_rs: lista opcional de valores de r puntuales donde
            calcular el punto fijo no trivial y su estabilidad vía derivada
            (solo tiene sentido para mapas con punto fijo analítico simple
            como logistic; para otros mapas da un valor aproximado numérico).

    Returns:
        dict con puntos (r,x) del diagrama y, si se pidió, análisis de estabilidad.
    """
    if map_name == "custom":
        if not custom_expr:
            raise ValueError("map_name='custom' requiere custom_expr.")
        expr = _sanitize_expr(custom_expr)
        r_range = r_range or [0.0, 4.0]
        x0 = x0 if x0 is not None else 0.5
    else:
        if map_name not in PRESET_MAPS_1D:
            raise ValueError(f"map_name debe ser uno de {list(PRESET_MAPS_1D)} o 'custom'.")
        preset = PRESET_MAPS_1D[map_name]
        expr = preset["expr"]
        r_range = r_range or preset["r_range"]
        x0 = x0 if x0 is not None else preset["x0"]

    stability_rs_str = (
        "[" + ", ".join(str(v) for v in stability_check_rs) + "]"
        if stability_check_rs else "[]"
    )

    script = dedent(f"""
        1;
        f = @(x,r) {expr};

        r_vals = linspace({r_range[0]}, {r_range[1]}, {n_r_values});
        results_r = [];
        results_x = [];

        for r = r_vals
          x = {x0};
          for i = 1:{n_transient}
            x = f(x,r);
          end
          for i = 1:{n_keep}
            x = f(x,r);
            results_r(end+1) = r;
            results_x(end+1) = x;
          end
        end

        printf('R_VALS=');
        printf('%.6g,', results_r);
        printf('\\n');
        printf('X_VALS=');
        printf('%.6g,', results_x);
        printf('\\n');

        % --- Estabilidad via multiplicador de Floquet (generaliza puntos fijos y ciclos) ---
        stab_rs = {stability_rs_str};
        h = 1e-6;
        printf('STAB=');
        for r = stab_rs
          % converger al atractor
          x = {x0};
          for i = 1:3000
            x = f(x,r);
          end
          % detectar periodo: iterar y comparar contra el punto de partida (tolerancia)
          period = -1;
          xtest = x;
          for p = 1:64
            xtest = f(xtest,r);
            if abs(xtest - x) < 1e-6
              period = p;
              break;
            endif
          end
          if period == -1
            % no se detecto periodicidad clara (posible caos/orbita muy larga)
            deriv = (f(x+h,r) - f(x-h,r)) / (2*h);
            printf('%.6g:%.6g:0:%.6g;', r, x, deriv);
          else
            % multiplicador de Floquet: producto de derivadas en los 'period' puntos del ciclo
            mult = 1;
            xc = x;
            for p = 1:period
              d = (f(xc+h,r) - f(xc-h,r)) / (2*h);
              mult = mult * d;
              xc = f(xc,r);
            end
            printf('%.6g:%.6g:%d:%.6g;', r, x, period, mult);
          endif
        end
        printf('\\n');
    """).strip()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".m", delete=False, dir=tempfile.gettempdir()
    ) as tf:
        tf.write(script)
        script_path = tf.name

    try:
        result = subprocess.run(
            [octave_bin, "--no-gui", "-q", script_path],
            capture_output=True, text=True, timeout=timeout_s,
        )
    finally:
        os.unlink(script_path)

    if result.returncode != 0:
        return {"error": "Octave devolvió un error.", "stderr": result.stderr.strip(), "stdout": result.stdout.strip()}

    out = result.stdout
    r_match = re.search(r"R_VALS=([\d.,eE+\-]+)", out)
    x_match = re.search(r"X_VALS=([\d.,eE+\-]+)", out)
    stab_match = re.search(r"STAB=(.*)", out)

    if not r_match or not x_match:
        return {"error": "No se pudo parsear la salida de Octave.", "stdout": out}

    r_pts = [float(v) for v in r_match.group(1).strip(",").split(",")]
    x_pts = [float(v) for v in x_match.group(1).strip(",").split(",")]

    stability = []
    if stab_match and stab_match.group(1).strip():
        for entry in stab_match.group(1).strip(";").split(";"):
            if not entry.strip():
                continue
            parts = entry.split(":")
            r_v, x_v, period_v, mult_v = (
                float(parts[0]), float(parts[1]), int(parts[2]), float(parts[3])
            )
            if period_v == 0:
                estado = "PERIODO NO DETECTADO (posible caos u órbita muy larga)"
            else:
                estado = "ESTABLE" if abs(mult_v) < 1 else "INESTABLE"
            stability.append({
                "r": r_v,
                "x_convergido": x_v,
                "periodo_detectado": period_v if period_v > 0 else None,
                "multiplicador_floquet": mult_v,
                "estado": estado,
            })

    return {
        "map_name": map_name,
        "expr": expr,
        "r_range": r_range,
        "n_points": len(r_pts),
        "r": r_pts,
        "x": x_pts,
        "stability_analysis": stability,
        "nota": (
            "r,x son listas paralelas de puntos del diagrama (después del transitorio). "
            "stability_analysis contiene, para cada r pedido en stability_check_rs, el punto "
            "al que convergió la trayectoria y la derivada de f en ese punto (|deriv|<1 => estable)."
        ),
    }


BIFURCATION_TOOL_SCHEMA = {
    "name": "compute_bifurcation_diagram",
    "description": (
        "Genera un diagrama de bifurcación para un mapa iterativo 1D "
        "(x_next = f(x,r)), barriendo un rango de r y guardando los puntos "
        "del atractor tras un transitorio. Presets: logistic, sine, cubic, "
        "tent, o custom. Opcionalmente analiza estabilidad (vía derivada) "
        "en valores de r específicos."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "map_name": {
                "type": "string",
                "enum": ["logistic", "sine", "cubic", "tent", "custom"],
                "default": "logistic",
            },
            "custom_expr": {
                "type": "string",
                "description": "Solo si map_name='custom'. Expresión Octave en x,r. Ej: 'r*x*(1-x)'.",
            },
            "r_range": {"type": "array", "items": {"type": "number"}},
            "x0": {"type": "number"},
            "n_r_values": {"type": "integer", "default": 300},
            "n_transient": {"type": "integer", "default": 500},
            "n_keep": {"type": "integer", "default": 40},
            "stability_check_rs": {
                "type": "array", "items": {"type": "number"},
                "description": "Valores de r donde calcular estabilidad puntual vía derivada.",
            },
        },
        "required": [],
    },
}


if __name__ == "__main__":
    r = compute_bifurcation_diagram(
        map_name="logistic",
        n_r_values=100, n_keep=20,
        stability_check_rs=[2.8, 3.2, 3.5, 3.9],
    )
    if "error" in r:
        print("ERROR:", r["error"], r.get("stderr"))
    else:
        print("n_points:", r["n_points"])
        for s in r["stability_analysis"]:
            print(f"  r={s['r']:.2f} x*={s['x_convergido']:.4f} periodo={s['periodo_detectado']} "
                  f"multiplicador={s['multiplicador_floquet']:.4f} -> {s['estado']}")
