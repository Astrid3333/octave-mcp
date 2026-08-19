// rk4_verify.rs -- RK4 de paso fijo, cero dependencias externas, en Rust puro.
// Uso: rk4_verify <beta> <z_final> <n_steps>
// Salida: JSON {"rho_m":..., "rho_de":...} a stdout
use std::env;

fn deriv(rho_m: f64, z: f64, c_m: f64, c_de: f64) -> (f64, f64) {
    let inv = 1.0 / (1.0 + z);
    (c_m * rho_m * inv, c_de * rho_m * inv)
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let beta: f64 = args[1].parse().unwrap();
    let z_final: f64 = args[2].parse().unwrap();
    let n_steps: usize = args[3].parse().unwrap();

    let c_m = 3.0 * (1.0 - beta);
    let c_de = 3.0 * beta;
    let dz = z_final / n_steps as f64;

    let mut z = 0.0_f64;
    let mut rho_m = 0.3_f64;
    let mut rho_de = 0.7_f64;

    for _ in 0..n_steps {
        let (k1m, k1d) = deriv(rho_m, z, c_m, c_de);
        let (k2m, k2d) = deriv(rho_m + 0.5 * dz * k1m, z + 0.5 * dz, c_m, c_de);
        let (k3m, k3d) = deriv(rho_m + 0.5 * dz * k2m, z + 0.5 * dz, c_m, c_de);
        let (k4m, k4d) = deriv(rho_m + dz * k3m, z + dz, c_m, c_de);
        rho_m += dz / 6.0 * (k1m + 2.0 * k2m + 2.0 * k3m + k4m);
        rho_de += dz / 6.0 * (k1d + 2.0 * k2d + 2.0 * k3d + k4d);
        z += dz;
    }

    println!("{{\"rho_m\": {}, \"rho_de\": {}}}", rho_m, rho_de);
}
