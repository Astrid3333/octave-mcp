#!/usr/bin/env python3
"""
Corrige un bug real de orientacion de matriz en integrate_stiff_ode,
expuesto por _validate_stiff_ode (agregado en el patch anterior): para
sistemas de UNA sola dimension (numel(y0)==1) con solver ode15s/ode23s,
interp1() sobre un vector columna (sol.y') sigue la orientacion de t_out
(fila, via linspace) en vez de comportarse como en el caso matricial
(numel(y0)>1), asi que la transposicion final del codigo original deja
Yi con forma [n_output_points x 1] en lugar de [1 x n_output_points].

El chequeo de edge-case existente (`rows(Yi)==1 && numel(y0)>1`) nunca
cubre este caso porque pide justo lo contrario (numel(y0)>1). Resultado
rio abajo: el parseo en Python arma y_vals con forma (n_output_points, 1)
en vez de (1, n_output_points), asi que integrate_stiff_ode(system=1D)
devuelve solo el valor inicial repetido como "y[0]" en vez de la
trayectoria completa.

Fix: interpolar explicitamente dimension por dimension, sin depender de
si Octave trata sol.y' como vector o como matriz.
"""
import ast
import shutil
import sys
from datetime import datetime

TARGET = "stiff_ode_tool.py"

OLD = """            Yi = interp1(sol.x, sol.y', t_out)';
            if rows(Yi) == 1 && numel(y0) > 1
              Yi = Yi';  % edge case: 1 punto de salida
            end"""

NEW = """            n_dims_out = numel(y0);
            Yi = zeros(n_dims_out, numel(t_out));
            for i_dim = 1:n_dims_out
              Yi(i_dim,:) = interp1(sol.x, sol.y(i_dim,:), t_out);
            end"""


def main():
    with open(TARGET, encoding="utf-8") as f:
        src = f.read()

    count = src.count(OLD)
    assert count == 1, f"[Yi orientation fix] se esperaba 1 ocurrencia, se encontraron {count} -- revisar a mano."

    backup = f"{TARGET}.bak.{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy(TARGET, backup)

    new_src = src.replace(OLD, NEW, 1)

    try:
        ast.parse(new_src)
    except SyntaxError as e:
        print(f"ERROR: el resultado no parsea como Python valido: {e}", file=sys.stderr)
        sys.exit(1)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(new_src)

    print(f"Patch aplicado OK. Backup: {backup}")
    print("Confirmar con:")
    print('  python3 -c "from stiff_ode_tool import integrate_stiff_ode as c; import json; print(json.dumps(c(mode=\'validate\'), indent=2, ensure_ascii=False))"')
    print("Los dos checks deberian pasar ahora (1D exponencial via ode15s, y el oscilador 2D via lsode que ya pasaba).")


if __name__ == "__main__":
    main()
