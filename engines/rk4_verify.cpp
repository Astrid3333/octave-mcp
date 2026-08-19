// rk4_verify.cpp -- RK4 de paso fijo, sin dependencias externas.
// Uso: rk4_verify <beta> <z_final> <n_steps>
// Salida: JSON {"rho_m":..., "rho_de":...} a stdout
#include <cstdio>
#include <cstdlib>
#include <utility>

std::pair<double,double> deriv(double rho_m, double z, double c_m, double c_de) {
    double inv = 1.0 / (1.0 + z);
    return {c_m * rho_m * inv, c_de * rho_m * inv};
}

int main(int argc, char** argv) {
    double beta = std::atof(argv[1]);
    double z_final = std::atof(argv[2]);
    long n_steps = std::atol(argv[3]);

    double c_m = 3.0 * (1.0 - beta);
    double c_de = 3.0 * beta;
    double dz = z_final / (double)n_steps;

    double z = 0.0, rho_m = 0.3, rho_de = 0.7;

    for (long i = 0; i < n_steps; i++) {
        auto [k1m, k1d] = deriv(rho_m, z, c_m, c_de);
        auto [k2m, k2d] = deriv(rho_m + 0.5*dz*k1m, z + 0.5*dz, c_m, c_de);
        auto [k3m, k3d] = deriv(rho_m + 0.5*dz*k2m, z + 0.5*dz, c_m, c_de);
        auto [k4m, k4d] = deriv(rho_m + dz*k3m, z + dz, c_m, c_de);
        rho_m += dz/6.0 * (k1m + 2*k2m + 2*k3m + k4m);
        rho_de += dz/6.0 * (k1d + 2*k2d + 2*k3d + k4d);
        z += dz;
    }

    std::printf("{\"rho_m\": %.17g, \"rho_de\": %.17g}\n", rho_m, rho_de);
    return 0;
}
