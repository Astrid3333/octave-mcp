use serde::{Deserialize, Serialize};
use sprs::{CsMat, TriMat};
use std::io::{self, Read, Write};
use ndarray::Array1;

#[derive(Deserialize)]
struct Geometry {
    #[serde(rename = "type")]
    kind: String, // solo "rectangle" por ahora
    width: f64,
    height: f64,
    nx: usize,
    ny: usize,
}

#[derive(Deserialize)]
struct BoundaryCondition {
    edge: String,   // "left" | "right" | "top" | "bottom"
    #[serde(rename = "type")]
    kind: String,   // "dirichlet" | "neumann" (solo neumann=0 soportado por ahora)
    value: f64,
}

#[derive(Deserialize)]
struct Source {
    #[serde(rename = "type")]
    kind: String, // "constant" por ahora
    value: f64,
}

#[derive(Deserialize)]
struct Input {
    mode: String,
    geometry: Geometry,
    boundary_conditions: Vec<BoundaryCondition>,
    source: Source,
    run_id: Option<String>,
}

#[derive(Serialize)]
struct SolverInfo {
    method: String,
    iterations: usize,
    residual: f64,
}

#[derive(Serialize)]
struct MeshOut {
    nodes: Vec<[f64; 2]>,
    triangles: Vec<[usize; 3]>,
}

#[derive(Serialize)]
struct Output {
    mode: String,
    n_nodes: usize,
    n_elements: usize,
    potential: Vec<f64>,
    mesh: MeshOut,
    solver: SolverInfo,
    workspace_saved: bool,
}

/// Genera grilla estructurada nx*ny nodos sobre un rectangulo, cada celda
/// partida en 2 triangulos (diagonal fija, sin mallador Delaunay).
fn build_mesh(g: &Geometry) -> (Vec<[f64; 2]>, Vec<[usize; 3]>) {
    let (nx, ny) = (g.nx, g.ny);
    let (dx, dy) = (g.width / nx as f64, g.height / ny as f64);
    let mut nodes = Vec::with_capacity((nx + 1) * (ny + 1));
    for j in 0..=ny {
        for i in 0..=nx {
            nodes.push([i as f64 * dx, j as f64 * dy]);
        }
    }
    let idx = |i: usize, j: usize| j * (nx + 1) + i;
    let mut tris = Vec::with_capacity(nx * ny * 2);
    for j in 0..ny {
        for i in 0..nx {
            let (a, b, c, d) = (idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1));
            tris.push([a, b, c]);
            tris.push([a, c, d]);
        }
    }
    (nodes, tris)
}

/// Matriz de rigidez local 3x3 para un triangulo P1, via formula de gradientes
/// constantes (integracion exacta para Poisson lineal).
fn local_stiffness(nodes: &[[f64; 2]], tri: &[usize; 3]) -> ([[f64; 3]; 3], f64) {
    let (p0, p1, p2) = (nodes[tri[0]], nodes[tri[1]], nodes[tri[2]]);
    let area2 = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1]);
    let area = area2.abs() / 2.0;
    // gradientes de las funciones de forma (constantes por elemento, P1)
    let b = [p1[1] - p2[1], p2[1] - p0[1], p0[1] - p1[1]];
    let c = [p2[0] - p1[0], p0[0] - p2[0], p1[0] - p0[0]];
    let mut k = [[0.0; 3]; 3];
    for i in 0..3 {
        for j in 0..3 {
            k[i][j] = (b[i] * b[j] + c[i] * c[j]) / (4.0 * area);
        }
    }
    (k, area)
}

/// CG basico sobre matriz CSR simetrica positiva definida.
fn conjugate_gradient(a: &CsMat<f64>, b: &[f64], tol: f64, max_iter: usize) -> (Vec<f64>, usize, f64) {
    let n = b.len();
    let b_arr = Array1::from(b.to_vec());
    let mut x = Array1::<f64>::zeros(n);
    let mut r = b_arr.clone();
    let mut p = r.clone();
    let mut rs_old: f64 = r.dot(&r);
    let b_norm = rs_old.sqrt().max(1e-30);

    for iter in 0..max_iter {
        let ap = a * &p;
        let alpha = rs_old / p.dot(&ap);
        x = &x + &(&p * alpha);
        r = &r - &(&ap * alpha);
        let rs_new: f64 = r.dot(&r);
        let resid = rs_new.sqrt() / b_norm;
        if resid < tol {
            return (x.to_vec(), iter + 1, resid);
        }
        let beta = rs_new / rs_old;
        p = &r + &(&p * beta);
        rs_old = rs_new;
    }
    let resid = rs_old.sqrt() / b_norm;
    (x.to_vec(), max_iter, resid)
}

fn solve_poisson2d(inp: &Input) -> Output {
    let (nodes, tris) = build_mesh(&inp.geometry);
    let n = nodes.len();
    let (w, h) = (inp.geometry.width, inp.geometry.height);
    let eps = 1e-9;

    // ensamblado global (triplets -> CSR)
    let mut trip = TriMat::new((n, n));
    let mut rhs = vec![0.0; n];
    for tri in &tris {
        let (k_local, area) = local_stiffness(&nodes, tri);
        for a in 0..3 {
            for b in 0..3 {
                trip.add_triplet(tri[a], tri[b], k_local[a][b]);
            }
            // fuente constante: integracion consistente, area/3 por nodo
            rhs[tri[a]] += inp.source.value * area / 3.0;
        }
    }
    let mut k: CsMat<f64> = trip.to_csr();

    // clasificar nodos de borde
    let is_left = |p: &[f64; 2]| p[0] < eps;
    let is_right = |p: &[f64; 2]| (p[0] - w).abs() < eps;
    let is_bottom = |p: &[f64; 2]| p[1] < eps;
    let is_top = |p: &[f64; 2]| (p[1] - h).abs() < eps;

    let mut dirichlet: Vec<(usize, f64)> = Vec::new();
    for bc in &inp.boundary_conditions {
        if bc.kind != "dirichlet" {
            continue; // neumann=0 es natural, no requiere accion en la forma debil
        }
        for (idx, p) in nodes.iter().enumerate() {
            let on_edge = match bc.edge.as_str() {
                "left" => is_left(p),
                "right" => is_right(p),
                "bottom" => is_bottom(p),
                "top" => is_top(p),
                _ => false,
            };
            if on_edge {
                dirichlet.push((idx, bc.value));
            }
        }
    }

    // eliminacion de Dirichlet: ajustar rhs de vecinos antes de anular fila/columna
    let k_dense_rows: Vec<Vec<(usize, f64)>> = (0..n)
        .map(|r| k.outer_view(r).unwrap().iter().map(|(c, v)| (c, *v)).collect())
        .collect();
    for &(dof, val) in &dirichlet {
        for r in 0..n {
            if r == dof {
                continue;
            }
            if let Some(&(_, kval)) = k_dense_rows[r].iter().find(|(c, _)| *c == dof) {
                rhs[r] -= kval * val;
            }
        }
    }
    let mut trip2 = TriMat::new((n, n));
    let dirichlet_set: std::collections::HashMap<usize, f64> = dirichlet.into_iter().collect();
    for r in 0..n {
        if let Some(&val) = dirichlet_set.get(&r) {
            trip2.add_triplet(r, r, 1.0);
            rhs[r] = val;
            continue;
        }
        for &(c, v) in &k_dense_rows[r] {
            if dirichlet_set.contains_key(&c) {
                continue; // columna anulada, ya se aplico el ajuste al rhs arriba
            }
            trip2.add_triplet(r, c, v);
        }
    }
    k = trip2.to_csr();

    let (phi, iters, resid) = conjugate_gradient(&k, &rhs, 1e-9, 5000);

    Output {
        mode: "poisson_2d".to_string(),
        n_nodes: n,
        n_elements: tris.len(),
        potential: phi,
        mesh: MeshOut { nodes, triangles: tris },
        solver: SolverInfo { method: "cg".to_string(), iterations: iters, residual: resid },
        workspace_saved: false, // el puente Python decide si guarda en workspace
    }
}

fn main() {
    let mut buf = String::new();
    io::stdin().read_to_string(&mut buf).expect("no pude leer stdin");
    let inp: Input = serde_json::from_str(&buf).expect("JSON de entrada invalido");

    let out = match inp.mode.as_str() {
        "poisson_2d" => solve_poisson2d(&inp),
        other => {
            eprintln!("modo desconocido: {}", other);
            std::process::exit(1);
        }
    };

    io::stdout()
        .write_all(serde_json::to_string(&out).unwrap().as_bytes())
        .unwrap();
}
