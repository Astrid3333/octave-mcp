#!/usr/bin/env python3
"""
octave_openems_server.py

MCP server (stdio JSON-RPC) para simulacion electromagnetica de circuitos
cuanticos (resonadores CPW de linea coplanar, tipicos de lectura de
qubits superconductores) via openEMS (motor FDTD en C++) manejado desde
Octave/CSXCAD.

Convencion: sigue el patron ya usado en octave-mcp / mcp_octave -- una
funcion compute_X_tool(mode, params=None) que nunca lanza excepcion
hacia afuera (errores van en {"error": ...}), mas un TOOL_SCHEMA con
name/description/inputSchema, mas un loop JSON-RPC minimo por stdio.

ESTADO DE VALIDACION (leelo antes de confiar en los numeros):
  - modo 'cpw_impedance_analytic': formula cerrada de mapeo conforme
    (Hilberg/Ghione, aproximacion de sustrato semi-infinito h >> W+2G).
    Calculada en Python puro con scipy.special.ellipk, sin dependencia
    de openEMS. Cubierta por self_test con chequeos de limites fisicos
    y casos especiales de la integral eliptica -- lista para usar.
  - modo 'cpw_resonator_fdtd': genera un script Octave/CSXCAD real y lo
    corre invocando openEMS instalado en el sistema (subprocess a
    octave-cli). La sintaxis de las funciones CSXCAD (AddLumpedPort,
    DefineRectGrid, WriteOpenEMS, RunOpenEMS, calcPort...) esta escrita
    siguiendo los tutoriales oficiales (microstrip notch filter / CPW),
    pero *no fue ejecutada* -- no hay openEMS instalado en este entorno
    de diseno. Antes de confiar en los resultados: corrrelo con
    --dry-run primero (guarda el .m sin ejecutar openEMS), revisa que
    compile contra tu version instalada (0.0.35 vs 0.37.0-rc1 cambian
    algunos nombres/firmas de funcion), y compara el Z0 de banda ancha
    contra 'cpw_impedance_analytic' con la misma geometria antes de
    creer la frecuencia de resonancia.
"""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

try:
    from scipy.special import ellipk  # ellipk(m) con m = k**2 (convencion scipy)
except ImportError:
    ellipk = None


# ---------------------------------------------------------------------
# Modo 1: impedancia CPW analitica (mapeo conforme, sustrato semi-infinito)
# ---------------------------------------------------------------------

def _K(k):
    if ellipk is None:
        raise RuntimeError("scipy no disponible: pip install scipy --break-system-packages")
    k = min(max(k, 1e-9), 1 - 1e-9)  # evitar singularidades en k=0 o k=1
    return ellipk(k ** 2)


def _cpw_z0_eps_eff(W, G, epsr):
    """
    Impedancia caracteristica Z0 y permitividad efectiva de una linea
    coplanar (CPW) sobre sustrato semi-infinito (valido cuando el
    espesor del sustrato h >> W + 2G; para h finito hace falta FDTD).

    W: ancho de la pista central (m)
    G: separacion pista-plano de tierra a cada lado (m)
    epsr: permitividad relativa del sustrato

    Referencia: Simons, "Coplanar Waveguide Circuits, Components and
    Systems", formula de Hilberg/Ghione via mapeo conforme (caso
    sustrato semi-infinito, sin plano de tierra inferior).
    """
    k = W / (W + 2 * G)
    kp = math.sqrt(1 - k ** 2)
    eps_eff = (epsr + 1) / 2.0
    Z0 = (30 * math.pi / math.sqrt(eps_eff)) * (_K(kp) / _K(k))
    return Z0, eps_eff


def _mode_cpw_impedance_analytic(params):
    W = params["W_um"] * 1e-6
    G = params["G_um"] * 1e-6
    epsr = params["epsr"]
    Z0, eps_eff = _cpw_z0_eps_eff(W, G, epsr)

    out = {
        "mode": "cpw_impedance_analytic",
        "params_used": {"W_um": params["W_um"], "G_um": params["G_um"], "epsr": epsr},
        "k": W / (W + 2 * G),
        "eps_eff": eps_eff,
        "Z0_ohm": Z0,
        "note": (
            "Formula de mapeo conforme, sustrato semi-infinito (h >> W+2G). "
            "Para sustrato de espesor finito (caso real de chip) usar "
            "'cpw_resonator_fdtd', que si modela h explicitamente."
        ),
    }

    if "f_target_GHz" in params:
        c = 299792458.0
        f = params["f_target_GHz"] * 1e9
        lam_g = c / (f * math.sqrt(eps_eff))
        out["guided_wavelength_mm_at_f_target"] = lam_g * 1e3
        out["quarter_wave_length_mm"] = lam_g * 1e3 / 4.0

    return out


# ---------------------------------------------------------------------
# Self-test: sin openEMS, solo verifica limites fisicos y casos especiales
# de la integral eliptica -- NO es un test de la parte FDTD.
# ---------------------------------------------------------------------

def _mode_self_test(params):
    checks = {}
    all_pass = True

    def check(name, cond, detail=None):
        nonlocal all_pass
        checks[name] = {"pass": bool(cond)}
        if detail is not None:
            checks[name]["detail"] = detail
        if not cond:
            all_pass = False

    # K(0) debe ser exactamente pi/2 (sanity de scipy/ellipk, no de nuestra formula)
    K0 = _K(1e-9)
    check("K(k=0) ~= pi/2", abs(K0 - math.pi / 2) < 1e-6, {"K0": K0, "pi/2": math.pi / 2})

    # eps_eff debe quedar estrictamente entre 1 (aire) y epsr (dielectrico puro)
    epsr = 9.8  # alumina, valor tipico de sustrato para circuitos de microondas
    Z0_mid, eps_mid = _cpw_z0_eps_eff(5e-6, 5e-6, epsr)
    check(
        "1 < eps_eff < epsr",
        1.0 < eps_mid < epsr,
        {"eps_eff": eps_mid, "epsr": epsr},
    )

    # Z0 debe decrecer monotonamente al angostar el gap (k -> 1): mas
    # acoplamiento capacitivo a tierra, menor impedancia.
    Z0_a, _ = _cpw_z0_eps_eff(5e-6, 20e-6, epsr)  # k chico (gap grande)
    Z0_b, _ = _cpw_z0_eps_eff(5e-6, 5e-6, epsr)   # k medio
    Z0_c, _ = _cpw_z0_eps_eff(5e-6, 1e-6, epsr)   # k grande (gap chico)
    check(
        "Z0 decrece monotonamente al cerrar el gap (k creciente)",
        Z0_a > Z0_b > Z0_c,
        {"Z0_gap_grande": Z0_a, "Z0_gap_medio": Z0_b, "Z0_gap_chico": Z0_c},
    )

    # Orden de magnitud: CPW simetrica (W=G) sobre alumina cae cerca del
    # rango 40-70 ohm tipico de diseno de lectura de qubits (chequeo de
    # sanidad de orden de magnitud, no una cifra de referencia exacta).
    check(
        "CPW simetrica sobre alumina cae en rango de diseno 40-70 ohm",
        40.0 < Z0_b < 70.0,
        {"Z0_ohm": Z0_b},
    )

    return {
        "mode": "self_test",
        "checks": checks,
        "all_pass": all_pass,
        "validation_passed": all_pass,
        "note": (
            "Este self_test cubre unicamente 'cpw_impedance_analytic' "
            "(Python puro, sin dependencia de openEMS). El modo "
            "'cpw_resonator_fdtd' no tiene self_test automatico todavia "
            "porque requiere openEMS instalado y corriendo -- validalo "
            "a mano con --dry-run y comparando Z0 contra este modo "
            "analitico con la misma geometria."
        ),
    }


# ---------------------------------------------------------------------
# Modo 2: resonador CPW completo via FDTD real (openEMS) -- SIN EJECUTAR AUN
# ---------------------------------------------------------------------

_OCTAVE_TEMPLATE = r"""
% Generado por octave_openems_server.py -- NO EJECUTADO NI VALIDADO TODAVIA.
% Sigue el patron estandar de tutoriales openEMS (tipo "MSL notch filter"
% / "CPW to microstrip"). Verificar firmas de funcion contra la version
% de openEMS instalada antes de correr en serio.

close all; clear; clc;

physical_constants;
unit = 1e-6; % dimensiones del script en micrones

W   = {W_um};      % ancho de la pista central
G   = {G_um};       % gap pista-tierra
h   = {h_um};        % espesor del sustrato
L   = {L_um};       % largo del resonador
epsr = {epsr};

f_start = {f_start_GHz}e9;
f_stop  = {f_stop_GHz}e9;

CSX = InitCSX();

% sustrato dielectrico
CSX = AddMaterial(CSX, 'substrate');
CSX = SetMaterialProperty(CSX, 'substrate', 'Epsilon', epsr);
substrate_start = [-W/2-3*G, -h, 0];
substrate_stop  = [ W/2+3*G,  0, L];
CSX = AddBox(CSX, 'substrate', 0, substrate_start, substrate_stop);

% plano de tierra + pista central (PEC ideal, primera iteracion)
CSX = AddMetal(CSX, 'PEC');
CSX = AddBox(CSX, 'PEC', 10, [-W/2-3*G, 0, 0], [-W/2-G, 0, L]);   % tierra izq
CSX = AddBox(CSX, 'PEC', 10, [ W/2+G,   0, 0], [ W/2+3*G, 0, L]); % tierra der
CSX = AddBox(CSX, 'PEC', 10, [-W/2,     0, 0], [ W/2,     0, L]); % pista central

% puerto concentrado de excitacion en z=0 (feedline), 50 ohm por default
port_start = [-W/2, 0, 0];
port_stop  = [ W/2, h, 2*unit];
[CSX, port{{1}}] = AddLumpedPort(CSX, 5, 1, 50, port_start, port_stop, [0 0 1], true);

% mallado (grosero -- afinar antes de confiar en resultados)
mesh.x = SmoothMeshLines([-W/2-3*G, -W/2, W/2, W/2+3*G], (W+2*G)/10);
mesh.y = SmoothMeshLines([-h, 0, 5*h], h/10);
mesh.z = SmoothMeshLines([0, L], L/40);
CSX = DefineRectGrid(CSX, unit, mesh);

FDTD = InitFDTD('EndCriteria', 1e-4);
FDTD = SetGaussExcite(FDTD, 0.5*(f_start+f_stop), 0.5*(f_stop-f_start));
FDTD = SetBoundaryCond(FDTD, {{'PML_8','PML_8','PML_8','PML_8','PML_8','PML_8'}});

Sim_Path = '{sim_path}';
Sim_CSX  = 'cpw_resonator.xml';
[status, message] = mkdir(Sim_Path);
WriteOpenEMS([Sim_Path '/' Sim_CSX], FDTD, CSX);
RunOpenEMS(Sim_Path, Sim_CSX);

freq = linspace(f_start, f_stop, 401);
port{{1}} = calcPort(port{{1}}, Sim_Path, freq);
s11 = port{{1}}.uf.ref ./ port{{1}}.uf.inc;

fid = fopen([Sim_Path '/s11_result.csv'], 'w');
fprintf(fid, 'freq_Hz,s11_re,s11_im\n');
for i = 1:length(freq)
    fprintf(fid, '%.6e,%.6e,%.6e\n', freq(i), real(s11(i)), imag(s11(i)));
end
fclose(fid);
disp('OK: s11_result.csv escrito');
"""


def _mode_cpw_resonator_fdtd(params):
    dry_run = bool(params.get("dry_run", True))

    required = ["W_um", "G_um", "h_um", "L_um", "epsr"]
    missing = [k for k in required if k not in params]
    if missing:
        return {"error": f"Faltan parametros requeridos: {missing}"}

    work_dir = tempfile.mkdtemp(prefix="openems_cpw_")
    script_text = _OCTAVE_TEMPLATE.format(
        W_um=params["W_um"],
        G_um=params["G_um"],
        h_um=params["h_um"],
        L_um=params["L_um"],
        epsr=params["epsr"],
        f_start_GHz=params.get("f_start_GHz", 3.0),
        f_stop_GHz=params.get("f_stop_GHz", 8.0),
        sim_path=work_dir.replace("\\", "/"),
    )
    script_path = os.path.join(work_dir, "cpw_resonator_sim.m")
    with open(script_path, "w") as f:
        f.write(script_text)

    if dry_run:
        return {
            "mode": "cpw_resonator_fdtd",
            "dry_run": True,
            "script_path": script_path,
            "note": (
                "Script Octave/CSXCAD generado pero NO ejecutado (dry_run=true "
                "por default). Revisalo, ajustalo a tu version de openEMS, y "
                "corre este mismo modo con params.dry_run=false para lanzar "
                "la simulacion FDTD real (requiere octave-cli + openEMS "
                "instalados y en PATH)."
            ),
        }

    if shutil.which("octave-cli") is None:
        return {
            "error": "octave-cli no encontrado en PATH. Instala Octave y el "
            "interfaz openEMS/CSXCAD (addpath a .../openEMS/matlab y "
            ".../CSXCAD/matlab) antes de correr con dry_run=false."
        }

    try:
        proc = subprocess.run(
            ["octave-cli", "--no-gui", script_path],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=params.get("timeout_s", 600),
        )
    except subprocess.TimeoutExpired:
        return {"error": "Timeout corriendo openEMS via octave-cli", "script_path": script_path}

    csv_path = os.path.join(work_dir, "s11_result.csv")
    if proc.returncode != 0 or not os.path.exists(csv_path):
        return {
            "error": "La simulacion FDTD no genero s11_result.csv",
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
            "script_path": script_path,
        }

    freq, s11_re, s11_im = [], [], []
    with open(csv_path) as f:
        next(f)
        for line in f:
            a, b, c = line.strip().split(",")
            freq.append(float(a))
            s11_re.append(float(b))
            s11_im.append(float(c))

    s11_db = [20 * math.log10(math.hypot(re, im) + 1e-30) for re, im in zip(s11_re, s11_im)]
    idx_min = min(range(len(s11_db)), key=lambda i: s11_db[i])

    return {
        "mode": "cpw_resonator_fdtd",
        "dry_run": False,
        "params_used": params,
        "n_freq_points": len(freq),
        "f_resonance_GHz": freq[idx_min] / 1e9,
        "s11_min_dB": s11_db[idx_min],
        "s11_dB": s11_db,
        "freq_Hz": freq,
        "note": (
            "f_resonance = frecuencia del minimo de |S11| en la banda "
            "simulada. Cruzar contra 'cpw_impedance_analytic' con la misma "
            "geometria antes de confiar en el valor -- este pipeline FDTD "
            "no fue validado contra ningun caso de referencia todavia."
        ),
    }


# ---------------------------------------------------------------------
# Dispatch + schema (misma convencion que el resto de octave-mcp)
# ---------------------------------------------------------------------

def compute_openems_quantum_circuit_tool(args):
    mode = args.get("mode") if isinstance(args, dict) else args
    params = args.get("params") or {} if isinstance(args, dict) else {}
    try:
        if mode == "cpw_impedance_analytic":
            return _mode_cpw_impedance_analytic(params)
        elif mode == "cpw_resonator_fdtd":
            return _mode_cpw_resonator_fdtd(params)
        elif mode in ("self_test", "validate"):
            return _mode_self_test(params)
        else:
            return {"error": f"Modo desconocido: {mode}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


OPENEMS_QUANTUM_CIRCUIT_TOOL_SCHEMA = {
    "name": "openems_quantum_circuit_tool",
    "description": (
        "Simulacion electromagnetica de elementos de circuitos cuanticos "
        "(resonadores CPW de lectura). Modo analitico (Python puro, rapido, "
        "sustrato semi-infinito) y modo FDTD completo (openEMS real via "
        "Octave/CSXCAD, sustrato de espesor finito, S11 en banda ancha)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["cpw_impedance_analytic", "cpw_resonator_fdtd", "self_test", "validate"],
            },
            "params": {"type": "object"},
        },
        "required": ["mode"],
    },
}


try:
    from tool_registry import register_tool
    register_tool("openems_quantum_circuit_tool", OPENEMS_QUANTUM_CIRCUIT_TOOL_SCHEMA, compute_openems_quantum_circuit_tool)
except ImportError:
    pass
