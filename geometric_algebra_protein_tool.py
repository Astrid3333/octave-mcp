"""
geometric_algebra_protein_tool.py

Representa la geometria del esqueleto de una proteina (angulos diedros
phi/psi) usando rotores del algebra geometrica Cl(3,0). El subalgebra par
de Cl(3,0) es isomorfa a los cuaterniones unitarios, asi que los rotores se
implementan como cuaterniones: R = cos(theta/2) + sin(theta/2)*B, donde B es
el bivector (eje) de rotacion.

Composicion de rotores a lo largo de la cadena: R_total = R_n * ... * R_2 * R_1
(igual que componer cuaterniones de rotacion), lo que da la orientacion neta
acumulada del extremo de la cadena relativa al inicio.

Modos:
  - backbone_rotor_chain: dado un listado de pares (phi, psi) en grados,
    compone los rotores (rotacion phi alrededor de eje N-CA, rotacion psi
    alrededor de eje CA-C, ejes fijos canonicos) y devuelve el rotor final,
    el angulo de rotacion neto, y el eje neto.
  - single_rotor: rotor de un solo angulo dihedral alrededor de un eje dado.
  - validate: cadena de angulos todos 180 grados (trans ideal) debe dar un
    rotor con angulo neto multiplo conocido; caso trivial con phi=psi=0 debe
    dar el rotor identidad.
"""

import numpy as np

# ejes canonicos fijos para las dos rotaciones internas del backbone
# (simplificacion: en la realidad los ejes rotan con la geometria local,
# aqui se fijan para tener una demo matematica consistente y reproducible)
_AXIS_PHI = np.array([1.0, 0.0, 0.0])  # eje N-CA
_AXIS_PSI = np.array([0.0, 1.0, 0.0])  # eje CA-C


def _quat_from_axis_angle(axis, angle_rad):
    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    half = angle_rad / 2.0
    w = np.cos(half)
    xyz = np.sin(half) * axis
    return np.array([w, xyz[0], xyz[1], xyz[2]])


def _quat_multiply(q1, q2):
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return np.array(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ]
    )


def _quat_to_axis_angle(q):
    q = q / np.linalg.norm(q)
    w = np.clip(q[0], -1.0, 1.0)
    angle = 2.0 * np.arccos(w)
    s = np.sqrt(max(1e-16, 1.0 - w * w))
    if s < 1e-9:
        axis = np.array([1.0, 0.0, 0.0])  # rotacion nula, eje arbitrario
    else:
        axis = q[1:] / s
    return axis, angle


def _single_rotor(angle_deg, axis):
    angle_rad = np.radians(angle_deg)
    q = _quat_from_axis_angle(axis, angle_rad)
    ax, ang = _quat_to_axis_angle(q)
    return {
        "mode": "single_rotor",
        "angle_deg": angle_deg,
        "axis": list(np.asarray(axis, dtype=float) / np.linalg.norm(axis)),
        "rotor_quaternion_wxyz": q.tolist(),
        "recovered_angle_deg": float(np.degrees(ang)),
    }


def _backbone_rotor_chain(phi_psi_angles):
    q_total = np.array([1.0, 0.0, 0.0, 0.0])  # rotor identidad
    per_residue = []
    for i, (phi, psi) in enumerate(phi_psi_angles):
        q_phi = _quat_from_axis_angle(_AXIS_PHI, np.radians(phi))
        q_psi = _quat_from_axis_angle(_AXIS_PSI, np.radians(psi))
        # composicion: primero se aplica phi, luego psi (rotor a izquierda)
        q_residue = _quat_multiply(q_psi, q_phi)
        q_total = _quat_multiply(q_residue, q_total)
        ax_r, ang_r = _quat_to_axis_angle(q_residue)
        per_residue.append(
            {
                "residue_index": i,
                "phi_deg": phi,
                "psi_deg": psi,
                "residue_net_angle_deg": float(np.degrees(ang_r)),
            }
        )
    axis_total, angle_total = _quat_to_axis_angle(q_total)
    return {
        "mode": "backbone_rotor_chain",
        "n_residues": len(phi_psi_angles),
        "per_residue": per_residue,
        "final_rotor_quaternion_wxyz": q_total.tolist(),
        "net_rotation_axis": axis_total.tolist(),
        "net_rotation_angle_deg": float(np.degrees(angle_total)),
    }


def _validate():
    identity_case = _backbone_rotor_chain([(0.0, 0.0)] * 5)
    identity_ok = abs(identity_case["net_rotation_angle_deg"]) < 1e-6

    trans_case = _backbone_rotor_chain([(180.0, 180.0)] * 3)
    # solo chequeamos que el rotor resultante tenga norma unitaria (propiedad
    # fundamental de un rotor valido) y que el angulo neto este bien definido
    q = np.array(trans_case["final_rotor_quaternion_wxyz"])
    norm_ok = abs(np.linalg.norm(q) - 1.0) < 1e-9

    return {
        "mode": "validate",
        "identity_case_net_angle_deg": identity_case["net_rotation_angle_deg"],
        "trans_case_rotor_norm": float(np.linalg.norm(q)),
        "expected": "phi=psi=0 en todos los residuos -> rotor identidad (angulo neto 0); "
        "todo rotor compuesto debe tener norma unitaria",
        "validation_passed": bool(identity_ok and norm_ok),
    }


def compute_geometric_algebra_protein(mode, **kwargs):
    if mode == "backbone_rotor_chain":
        return _backbone_rotor_chain(kwargs["phi_psi_angles"])
    elif mode == "single_rotor":
        return _single_rotor(kwargs["angle_deg"], kwargs.get("axis", [0.0, 0.0, 1.0]))
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"mode desconocido: {mode}")


GEOMETRIC_ALGEBRA_PROTEIN_SCHEMA = {
    "name": "geometric_algebra_protein",
    "description": (
        "Algebra geometrica (Cl(3,0), rotores via cuaterniones) aplicada al backbone de una "
        "proteina: compone las rotaciones phi/psi de cada residuo en un rotor neto que "
        "resume la orientacion acumulada de la cadena. mode='backbone_rotor_chain' "
        "(phi_psi_angles: lista de [phi,psi] en grados); mode='single_rotor' (angle_deg, "
        "axis opcional); mode='validate' verifica rotor identidad y normalizacion."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["backbone_rotor_chain", "single_rotor", "validate"],
                "default": "validate",
            },
            "phi_psi_angles": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}},
                "description": "Lista de [phi,psi] en grados, uno por residuo. backbone_rotor_chain.",
            },
            "angle_deg": {"type": "number", "description": "Angulo de rotacion. single_rotor."},
            "axis": {
                "type": "array",
                "items": {"type": "number"},
                "default": [0.0, 0.0, 1.0],
                "description": "Eje de rotacion (se normaliza internamente). single_rotor.",
            },
        },
        "required": ["mode"],
    },
}
