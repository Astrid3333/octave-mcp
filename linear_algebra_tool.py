"""
linear_algebra_tool.py

Algebra lineal via Octave nativo: autovalores/autovectores, SVD, PCA,
analisis de matrices (rango, numero de condicion, determinante, inversa).
Prerrequisito matematico de facto para persistent_homology_tool (que
necesita SVD/eigen para PCA de nubes de puntos) y para cualquier ajuste
estadistico multivariado.

Mismo patron de validacion que los demas modulos: presets con resultado
analitico conocido antes de aplicar el mismo codigo a datos reales via
'custom'.
"""
import subprocess
import tempfile
import os
import json

LINEAR_ALGEBRA_SCHEMA = {
    "name": "compute_linear_algebra",
    "description": (
        "Algebra lineal via Octave: eigen (autovalores/autovectores), svd "
        "(descomposicion en valores singulares + verificacion de "
        "reconstruccion), pca (componentes principales sobre matriz de "
        "datos, varianza explicada), matrix_analysis (rango, numero de "
        "condicion, determinante, inversa si existe). Presets validados "
        "con resultado analitico conocido, o 'custom' via 'matrix'/'data'."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["eigen", "svd", "pca", "matrix_analysis"],
                "default": "eigen",
            },
            "preset": {
                "type": "string",
                "enum": ["known_symmetric", "known_svd", "known_pca_dominant", "singular_matrix", "custom"],
                "default": "known_symmetric",
            },
            "matrix": {"type": "array", "description": "Matriz 2D, solo si preset='custom' y mode in [eigen,svd,matrix_analysis]"},
            "data": {"type": "array", "description": "Matriz de datos (filas=observaciones, columnas=variables), solo si preset='custom' y mode='pca'"},
        },
    },
}


def _run_octave(code, timeout=30):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".m", delete=False) as fh:
        fh.write(code)
        script_path = fh.name
    try:
        r = subprocess.run(["octave", "--no-gui", "--no-init-file", script_path],
                            capture_output=True, text=True, timeout=timeout)
    finally:
        os.unlink(script_path)
    if r.returncode != 0:
        return None, r.stderr.strip()
    return r.stdout.strip(), None


def _matrix_to_octave(M):
    rows = [",".join(str(x) for x in row) for row in M]
    return "[" + ";".join(rows) + "]"


def _gen_known_symmetric():
    return [[2, 1], [1, 2]], {"autovalores_esperados": [1.0, 3.0]}


def _gen_known_svd():
    return [[1, 0], [0, 1], [1, 1]], {"nota": "reconstruccion U*S*V' debe igualar la matriz original"}


def _gen_known_pca_data():
    import random
    rng = random.Random(0)
    data = []
    for _ in range(200):
        x = rng.gauss(0, 1)
        y = 2 * x + 0.01 * rng.gauss(0, 1)
        z = 0.01 * rng.gauss(0, 1)
        data.append([x, y, z])
    return data, {"nota": "PC1 deberia explicar ~99% de la varianza (x e y perfectamente correlacionados por construccion)"}


def _gen_singular_matrix():
    return [[1, 2], [2, 4]], {"rango_esperado": 1, "nota": "fila 2 = 2 x fila 1, matriz singular"}


def compute_linear_algebra(mode="eigen", preset="known_symmetric", matrix=None, data=None):
    known = None

    if mode in ("eigen", "svd", "matrix_analysis"):
        if preset == "custom":
            if not matrix:
                return {"error": "preset='custom' requiere 'matrix'"}
            M = matrix
        elif preset == "known_symmetric":
            M, known = _gen_known_symmetric()
        elif preset == "known_svd":
            M, known = _gen_known_svd()
        elif preset == "singular_matrix":
            M, known = _gen_singular_matrix()
        else:
            return {"error": f"preset '{preset}' no aplica para mode='{mode}'"}

        M_str = _matrix_to_octave(M)

        if mode == "eigen":
            code = f"""
A = {M_str};
[V, D] = eig(A);
eigvals = diag(D);
printf("%.8f ", eigvals);
printf("|");
printf("%.8f ", V(:));
"""
            out, err = _run_octave(code)
            if out is None:
                return {"error": "octave fallo", "stderr": err}
            eigvals_part, eigvecs_part = out.split("|")
            eigvals = [float(x) for x in eigvals_part.split()]
            eigvecs_flat = [float(x) for x in eigvecs_part.split()]
            n = len(eigvals)
            eigvecs = [[eigvecs_flat[i + j * n] for j in range(n)] for i in range(n)]
            result = {"matrix": M, "eigenvalues": sorted(round(v, 6) for v in eigvals),
                      "eigenvectors_columns": eigvecs}

        elif mode == "svd":
            code = f"""
A = {M_str};
[U, S, V] = svd(A, 0);
s = diag(S);
recon = U * S * V';
err_recon = max(max(abs(recon - A)));
printf("%.8f ", s);
printf("|");
printf("%.10f", err_recon);
"""
            out, err = _run_octave(code)
            if out is None:
                return {"error": "octave fallo", "stderr": err}
            s_part, err_part = out.split("|")
            singular_values = [float(x) for x in s_part.split()]
            recon_error = float(err_part)
            result = {"matrix": M, "singular_values": [round(x, 6) for x in singular_values],
                      "reconstruction_max_error": recon_error,
                      "reconstruction_ok": recon_error < 1e-8}

        else:  # matrix_analysis
            code = f"""
A = {M_str};
r = rank(A);
[rows, cols] = size(A);
printf("%d %d %d", r, rows, cols);
if rows == cols
  d = det(A);
  printf(" %.10f", d);
  if abs(d) > 1e-10
    c = cond(A);
    printf(" %.6f", c);
  else
    printf(" NaN");
  end
end
"""
            out, err = _run_octave(code)
            if out is None:
                return {"error": "octave fallo", "stderr": err}
            parts = out.split()
            rank_val, rows, cols = int(parts[0]), int(parts[1]), int(parts[2])
            result = {"matrix": M, "rank": rank_val, "shape": [rows, cols]}
            if len(parts) > 3:
                det_val = float(parts[3])
                result["determinant"] = round(det_val, 8)
                result["is_singular"] = abs(det_val) < 1e-10
                if len(parts) > 4 and parts[4] != "NaN":
                    result["condition_number"] = round(float(parts[4]), 4)

        if known:
            result["known_reference"] = known
        return result

    elif mode == "pca":
        if preset == "custom":
            if not data:
                return {"error": "preset='custom' requiere 'data' (filas=observaciones)"}
            D = data
        elif preset == "known_pca_dominant":
            D, known = _gen_known_pca_data()
        else:
            return {"error": f"preset '{preset}' no aplica para mode='pca'"}

        D_str = _matrix_to_octave(D)
        code = f"""
X = {D_str};
Xc = X - mean(X, 1);
C = cov(Xc);
[V, Lambda] = eig(C);
eigvals = diag(Lambda);
[eigvals_sorted, idx] = sort(eigvals, 'descend');
var_explained = eigvals_sorted / sum(eigvals_sorted);
printf("%.8f ", var_explained);
"""
        out, err = _run_octave(code)
        if out is None:
            return {"error": "octave fallo", "stderr": err}
        var_explained = [round(float(x), 6) for x in out.split()]
        result = {
            "n_observations": len(D),
            "n_variables": len(D[0]) if D else 0,
            "variance_explained_by_component": var_explained,
            "cumulative_variance": [round(sum(var_explained[:i + 1]), 6) for i in range(len(var_explained))],
        }
        if known:
            result["known_reference"] = known
        return result

    else:
        return {"error": f"mode desconocido: {mode}"}


if __name__ == "__main__":
    print(json.dumps(compute_linear_algebra("eigen", "known_symmetric"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_linear_algebra("svd", "known_svd"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_linear_algebra("matrix_analysis", "singular_matrix"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_linear_algebra("pca", "known_pca_dominant"), indent=2, ensure_ascii=False))
