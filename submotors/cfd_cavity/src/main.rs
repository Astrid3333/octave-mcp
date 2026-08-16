use ndarray::Array1;
use serde::{Deserialize, Serialize};
use sprs::{CsMat, TriMat};
use std::io::{self, Read, Write};

#[derive(Deserialize)]
struct Geometry {
    width: f64,
    height: f64,
    nx: usize,
    ny: usize,
}

#[derive(Deserialize)]
struct Fluid {
    reynolds: f64,
}

#[derive(Deserialize)]
struct SolverParams {
    dt: f64,
    max_steps: usize,
    tol: f64,
}

#[derive(Deserialize)]
struct Input {
    mode: String,
    geometry: Geometry,
    fluid: Fluid,
    lid_velocity: f64,
    solver: SolverParams,
    run_id: Option<String>,
}

#[derive(Serialize)]
struct MeshOut {
    nx: usize,
    ny: usize,
    width: f64,
    height: f64,
}

#[derive(Serialize)]
struct Output {
    mode: String,
    n_nodes: usize,
    reynolds: f64,
    steps_run: usize,
    converged: bool,
    residual: f64,
    u: Vec<f64>,
    v: Vec<f64>,
    psi: Vec<f64>,
    omega: Vec<f64>,
    mesh: MeshOut,
    workspace_saved: bool,
}

fn idx(i: usize, j: usize, nx: usize) -> usize {
    j * nx + i
}

/// Laplaciano por diferencias finitas (5 puntos) SOLO sobre nodos interiores,
/// con psi=0 en el borde (Dirichlet homogeneo, convencion estandar en cavidad
/// con tapa deslizante). Matriz SPD -- misma estructura que uso CG en
/// fem_poisson2d, solo cambia el ensamblado (FD en vez de P1).
fn build_interior_laplacian(nx: usize, ny: usize, dx: f64, dy: f64) -> CsMat<f64> {
    let nix = nx - 2;
    let niy = ny - 2;
    let n = nix * niy;
    let int_idx = |i: usize, j: usize| (j - 1) * nix + (i - 1);
    let cx = 1.0 / (dx * dx);
    let cy = 1.0 / (dy * dy);
    let diag = 2.0 * (cx + cy);

    let mut trip = TriMat::new((n, n));
    for j in 1..ny - 1 {
        for i in 1..nx - 1 {
            let k = int_idx(i, j);
            trip.add_triplet(k, k, diag);
            if i - 1 >= 1 {
                trip.add_triplet(k, int_idx(i - 1, j), -cx);
            }
            if i + 1 <= nx - 2 {
                trip.add_triplet(k, int_idx(i + 1, j), -cx);
            }
            if j - 1 >= 1 {
                trip.add_triplet(k, int_idx(i, j - 1), -cy);
            }
            if j + 1 <= ny - 2 {
                trip.add_triplet(k, int_idx(i, j + 1), -cy);
            }
        }
    }
    trip.to_csr()
}

fn conjugate_gradient(a: &CsMat<f64>, b: &[f64], tol: f64, max_iter: usize) -> Vec<f64> {
    let n = b.len();
    let b_arr = Array1::from(b.to_vec());
    let mut x = Array1::<f64>::zeros(n);
    let mut r = b_arr.clone();
    let mut p = r.clone();
    let mut rs_old: f64 = r.dot(&r);

    // RHS practicamente cero (tipico en el primer paso, antes de que la
    // vorticidad de pared difunda al interior) -- solucion trivial x=0.
    // Sin esta guarda, alpha = rs_old/p.dot(ap) = 0/0 = NaN, y f64::max
    // ignora NaN silenciosamente, lo que producia falsa convergencia
    // (residual reportado como 0.0 en vez de propagar el NaN real).
    if rs_old.sqrt() < 1e-14 {
        return x.to_vec();
    }
    let b_norm = rs_old.sqrt();

    for _ in 0..max_iter {
        let ap = a * &p;
        let denom = p.dot(&ap);
        if denom.abs() < 1e-300 {
            break;
        }
        let alpha = rs_old / denom;
        x = &x + &(&p * alpha);
        r = &r - &(&ap * alpha);
        let rs_new: f64 = r.dot(&r);
        if rs_new.sqrt() / b_norm < tol {
            break;
        }
        let beta = rs_new / rs_old;
        p = &r + &(&p * beta);
        rs_old = rs_new;
    }
    x.to_vec()
}

/// Formula de Thom: vorticidad de pared a partir de psi (que es 0 en todo el
/// borde) y del nodo adyacente interior. La tapa superior ademas mete el
/// termino de velocidad tangencial U (condicion deslizante).
fn apply_thom_bc(omega: &mut [f64], psi: &[f64], nx: usize, ny: usize, dx: f64, dy: f64, lid_u: f64) {
    for i in 1..nx - 1 {
        omega[idx(i, 0, nx)] = -2.0 * psi[idx(i, 1, nx)] / (dy * dy);
        omega[idx(i, ny - 1, nx)] =
            -2.0 * psi[idx(i, ny - 2, nx)] / (dy * dy) - 2.0 * lid_u / dy;
    }
    for j in 1..ny - 1 {
        omega[idx(0, j, nx)] = -2.0 * psi[idx(1, j, nx)] / (dx * dx);
        omega[idx(nx - 1, j, nx)] = -2.0 * psi[idx(nx - 2, j, nx)] / (dx * dx);
    }
}

fn compute_velocities(psi: &[f64], nx: usize, ny: usize, dx: f64, dy: f64, lid_u: f64) -> (Vec<f64>, Vec<f64>) {
    let mut u = vec![0.0; nx * ny];
    let mut v = vec![0.0; nx * ny];
    for j in 1..ny - 1 {
        for i in 1..nx - 1 {
            u[idx(i, j, nx)] = (psi[idx(i, j + 1, nx)] - psi[idx(i, j - 1, nx)]) / (2.0 * dy);
            v[idx(i, j, nx)] = -(psi[idx(i + 1, j, nx)] - psi[idx(i - 1, j, nx)]) / (2.0 * dx);
        }
    }
    // condiciones de pared exactas (no derivadas de psi en el borde)
    for i in 0..nx {
        u[idx(i, ny - 1, nx)] = lid_u; // tapa deslizante
    }
    (u, v)
}

fn vorticity_step(
    omega: &[f64],
    u: &[f64],
    v: &[f64],
    nx: usize,
    ny: usize,
    dx: f64,
    dy: f64,
    dt: f64,
    re: f64,
) -> (Vec<f64>, f64) {
    let mut new_omega = omega.to_vec();
    let mut max_diff: f64 = 0.0;
    for j in 1..ny - 1 {
        for i in 1..nx - 1 {
            let o = omega[idx(i, j, nx)];
            let domega_dx = (omega[idx(i + 1, j, nx)] - omega[idx(i - 1, j, nx)]) / (2.0 * dx);
            let domega_dy = (omega[idx(i, j + 1, nx)] - omega[idx(i, j - 1, nx)]) / (2.0 * dy);
            let lap = (omega[idx(i + 1, j, nx)] - 2.0 * o + omega[idx(i - 1, j, nx)]) / (dx * dx)
                + (omega[idx(i, j + 1, nx)] - 2.0 * o + omega[idx(i, j - 1, nx)]) / (dy * dy);
            let advect = u[idx(i, j, nx)] * domega_dx + v[idx(i, j, nx)] * domega_dy;
            let new_val = o + dt * (-advect + lap / re);
            max_diff = max_diff.max((new_val - o).abs());
            new_omega[idx(i, j, nx)] = new_val;
        }
    }
    (new_omega, max_diff)
}

fn solve_lid_driven_cavity(inp: &Input) -> Output {
    let (nx, ny) = (inp.geometry.nx, inp.geometry.ny);
    let (w, h) = (inp.geometry.width, inp.geometry.height);
    let dx = w / (nx - 1) as f64;
    let dy = h / (ny - 1) as f64;
    let re = inp.fluid.reynolds;
    let lid_u = inp.lid_velocity;
    let n = nx * ny;

    let laplacian = build_interior_laplacian(nx, ny, dx, dy);
    let mut psi = vec![0.0; n];
    let mut omega = vec![0.0; n];

    let nix = nx - 2;
    let niy = ny - 2;
    let mut steps_run = 0;
    let mut residual = f64::INFINITY;
    let mut converged = false;

    for step in 0..inp.solver.max_steps {
        apply_thom_bc(&mut omega, &psi, nx, ny, dx, dy, lid_u);

        let mut rhs = vec![0.0; nix * niy];
        for j in 1..ny - 1 {
            for i in 1..nx - 1 {
                rhs[(j - 1) * nix + (i - 1)] = omega[idx(i, j, nx)];
            }
        }
        let psi_int = conjugate_gradient(&laplacian, &rhs, 1e-8, 2000);
        for j in 1..ny - 1 {
            for i in 1..nx - 1 {
                psi[idx(i, j, nx)] = psi_int[(j - 1) * nix + (i - 1)];
            }
        }

        let (u, v) = compute_velocities(&psi, nx, ny, dx, dy, lid_u);
        let (new_omega, max_diff) = vorticity_step(&omega, &u, &v, nx, ny, dx, dy, inp.solver.dt, re);
        omega = new_omega;
        residual = max_diff;
        steps_run = step + 1;

        if residual < inp.solver.tol {
            converged = true;
            break;
        }
    }

    apply_thom_bc(&mut omega, &psi, nx, ny, dx, dy, lid_u);
    let (u, v) = compute_velocities(&psi, nx, ny, dx, dy, lid_u);

    Output {
        mode: "lid_driven_cavity".to_string(),
        n_nodes: n,
        reynolds: re,
        steps_run,
        converged,
        residual,
        u,
        v,
        psi,
        omega,
        mesh: MeshOut { nx, ny, width: w, height: h },
        workspace_saved: false,
    }
}

fn main() {
    let mut buf = String::new();
    io::stdin().read_to_string(&mut buf).expect("no pude leer stdin");
    let inp: Input = serde_json::from_str(&buf).expect("JSON de entrada invalido");

    let out = match inp.mode.as_str() {
        "lid_driven_cavity" => solve_lid_driven_cavity(&inp),
        other => {
            eprintln!("modo desconocido: {}", other);
            std::process::exit(1);
        }
    };

    io::stdout()
        .write_all(serde_json::to_string(&out).unwrap().as_bytes())
        .unwrap();
}
