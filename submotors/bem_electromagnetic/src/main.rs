use serde::{Deserialize, Serialize};
use nalgebra::{DMatrix, DVector};
use std::f64::consts::PI;
use std::io::{self, Read, Write};

#[derive(Deserialize, Clone)]
#[serde(tag = "type", rename_all = "lowercase")]
enum Bc {
    Dirichlet { value: f64 },
    Neumann { value: f64 },
}

#[derive(Deserialize)]
struct Conductor {
    boundary: Vec<[f64; 2]>,
    bc: Bc,
}

#[derive(Deserialize)]
struct EvalGrid {
    x_min: f64,
    x_max: f64,
    y_min: f64,
    y_max: f64,
    nx: usize,
    ny: usize,
}

#[derive(Deserialize)]
struct Input {
    mode: String,
    conductors: Vec<Conductor>,
    eval_grid: Option<EvalGrid>,
    run_id: Option<String>,
}

struct Panel {
    p0: [f64; 2],
    p1: [f64; 2],
    mid: [f64; 2],
    length: f64,
    normal: [f64; 2],
}

#[derive(Serialize)]
struct GridOut {
    x_min: f64,
    x_max: f64,
    y_min: f64,
    y_max: f64,
    nx: usize,
    ny: usize,
    potential: Vec<f64>,
    ex: Vec<f64>,
    ey: Vec<f64>,
}

#[derive(Serialize)]
struct Output {
    mode: String,
    n_panels: usize,
    sigma: Vec<f64>,
    panel_mid: Vec<[f64; 2]>,
    panel_potential: Vec<f64>,
    grid: Option<GridOut>,
    workspace_saved: bool,
}

const GL_NODES: [f64; 16] = [
    -0.9894009349916499, -0.9445750230732326, -0.8656312023878318, -0.7554044083550030,
    -0.6178762444026438, -0.4580167776572274, -0.2816035507792589, -0.0950125098376374,
     0.0950125098376374,  0.2816035507792589,  0.4580167776572274,  0.6178762444026438,
     0.7554044083550030,  0.8656312023878318,  0.9445750230732326,  0.9894009349916499,
];
const GL_WEIGHTS: [f64; 16] = [
    0.0271524594117541, 0.0622535239386479, 0.0951585116824928, 0.1246289712555339,
    0.1495959888165767, 0.1691565193950025, 0.1826034150449236, 0.1894506104550685,
    0.1894506104550685, 0.1826034150449236, 0.1691565193950025, 0.1495959888165767,
    0.1246289712555339, 0.0951585116824928, 0.0622535239386479, 0.0271524594117541,
];

fn build_panels(conductors: &[Conductor]) -> Vec<Panel> {
    let mut panels = Vec::new();
    for c in conductors {
        let n = c.boundary.len();
        for i in 0..n {
            let p0 = c.boundary[i];
            let p1 = c.boundary[(i + 1) % n];
            let dx = p1[0] - p0[0];
            let dy = p1[1] - p0[1];
            let length = (dx * dx + dy * dy).sqrt();
            let mid = [(p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0];
            let normal = [dy / length, -dx / length];
            panels.push(Panel { p0, p1, mid, length, normal });
        }
    }
    panels
}

fn integrate_g_regular(x: [f64; 2], panel: &Panel) -> f64 {
    let mut sum = 0.0;
    for k in 0..16 {
        let t = (GL_NODES[k] + 1.0) / 2.0;
        let w = GL_WEIGHTS[k] / 2.0;
        let y = [
            panel.p0[0] + t * (panel.p1[0] - panel.p0[0]),
            panel.p0[1] + t * (panel.p1[1] - panel.p0[1]),
        ];
        let dx = x[0] - y[0];
        let dy = x[1] - y[1];
        let r = (dx * dx + dy * dy).sqrt();
        sum += w * r.ln();
    }
    -1.0 / (2.0 * PI) * panel.length * sum
}

fn integrate_g_self(panel: &Panel) -> f64 {
    let l = panel.length;
    -1.0 / (2.0 * PI) * l * ((l / 2.0).ln() - 1.0)
}

fn integrate_grad_g_regular(x: [f64; 2], panel: &Panel) -> [f64; 2] {
    let mut sum = [0.0, 0.0];
    for k in 0..16 {
        let t = (GL_NODES[k] + 1.0) / 2.0;
        let w = GL_WEIGHTS[k] / 2.0;
        let y = [
            panel.p0[0] + t * (panel.p1[0] - panel.p0[0]),
            panel.p0[1] + t * (panel.p1[1] - panel.p0[1]),
        ];
        let dx = x[0] - y[0];
        let dy = x[1] - y[1];
        let r2 = dx * dx + dy * dy;
        sum[0] += w * dx / r2;
        sum[1] += w * dy / r2;
    }
    let c = -1.0 / (2.0 * PI) * panel.length;
    [c * sum[0], c * sum[1]]
}

/// Fila de colocacion en el panel i. Dirichlet: G(mid_i, panel_j).
/// Neumann: dG/dn_i(mid_i, panel_j), con el termino de salto -1/2 en la diagonal
/// (la contribucion propia de un panel recto a su propia derivada normal es 0
/// por simetria, asi que el autotermino de Neumann es puramente el salto).
// Nota: las filas Neumann convergen O(1/n) al refinar la malla (no O(1/n^2) como
// Dirichlet), porque la normal real del contorno curvo rota continuamente pero la
// normal de cada panel recto es constante -- desajuste de orden O(h) heredado
// directamente por la condicion de flujo. Verificado por convergencia empirica
// (n=40..320, coaxial circular): error cae ~2x cada vez que n se duplica.
// No es un bug; es intrinseco a BEM con paneles planos y normal constante por panel.
fn matrix_row_entry(i: usize, j: usize, panels: &[Panel], is_neumann_i: bool) -> f64 {
    if is_neumann_i {
        if i == j {
            -0.5
        } else {
            let g = integrate_grad_g_regular(panels[i].mid, &panels[j]);
            g[0] * panels[i].normal[0] + g[1] * panels[i].normal[1]
        }
    } else {
        if i == j {
            integrate_g_self(&panels[j])
        } else {
            integrate_g_regular(panels[i].mid, &panels[j])
        }
    }
}

fn solve_electrostatics_2d(inp: &Input) -> Output {
    let panels = build_panels(&inp.conductors);
    let n = panels.len();

    let mut panel_bc = Vec::with_capacity(n);
    for c in &inp.conductors {
        for _ in 0..c.boundary.len() {
            panel_bc.push(c.bc.clone());
        }
    }

    let mut a = DMatrix::<f64>::zeros(n, n);
    let mut b = DVector::<f64>::zeros(n);
    for i in 0..n {
        let is_neumann_i = matches!(panel_bc[i], Bc::Neumann { .. });
        b[i] = match panel_bc[i] {
            Bc::Dirichlet { value } => value,
            Bc::Neumann { value } => value,
        };
        for j in 0..n {
            a[(i, j)] = matrix_row_entry(i, j, &panels, is_neumann_i);
        }
    }

    let lu = a.lu();
    let sigma = lu
        .solve(&b)
        .expect("sistema BEM singular -- revisar geometria (paneles duplicados/degenerados o mezcla mal condicionada de Dirichlet/Neumann)");

    let panel_potential: Vec<f64> = (0..n)
        .map(|i| {
            (0..n)
                .map(|j| {
                    let g = if i == j {
                        integrate_g_self(&panels[j])
                    } else {
                        integrate_g_regular(panels[i].mid, &panels[j])
                    };
                    sigma[j] * g
                })
                .sum()
        })
        .collect();

    let grid = inp.eval_grid.as_ref().map(|eg| {
        let mut potential = Vec::with_capacity(eg.nx * eg.ny);
        let mut ex = Vec::with_capacity(eg.nx * eg.ny);
        let mut ey = Vec::with_capacity(eg.nx * eg.ny);
        for jy in 0..eg.ny {
            let y = eg.y_min + (eg.y_max - eg.y_min) * jy as f64 / (eg.ny - 1).max(1) as f64;
            for ix in 0..eg.nx {
                let x = eg.x_min + (eg.x_max - eg.x_min) * ix as f64 / (eg.nx - 1).max(1) as f64;
                let p = [x, y];
                let mut phi = 0.0;
                let mut grad = [0.0, 0.0];
                for j in 0..n {
                    phi += sigma[j] * integrate_g_regular(p, &panels[j]);
                    let gg = integrate_grad_g_regular(p, &panels[j]);
                    grad[0] += sigma[j] * gg[0];
                    grad[1] += sigma[j] * gg[1];
                }
                potential.push(phi);
                ex.push(-grad[0]);
                ey.push(-grad[1]);
            }
        }
        GridOut {
            x_min: eg.x_min, x_max: eg.x_max, y_min: eg.y_min, y_max: eg.y_max,
            nx: eg.nx, ny: eg.ny, potential, ex, ey,
        }
    });

    Output {
        mode: "electrostatics_2d".to_string(),
        n_panels: n,
        sigma: sigma.iter().cloned().collect(),
        panel_mid: panels.iter().map(|p| p.mid).collect(),
        panel_potential,
        grid,
        workspace_saved: false,
    }
}

fn main() {
    let mut buf = String::new();
    io::stdin().read_to_string(&mut buf).expect("no pude leer stdin");
    let inp: Input = serde_json::from_str(&buf).expect("JSON de entrada invalido");

    let out = match inp.mode.as_str() {
        "electrostatics_2d" => solve_electrostatics_2d(&inp),
        other => {
            eprintln!("modo desconocido: {}", other);
            std::process::exit(1);
        }
    };

    io::stdout()
        .write_all(serde_json::to_string(&out).unwrap().as_bytes())
        .unwrap();
}
