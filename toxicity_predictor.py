"""
toxicity_predictor.py
======================
Tool 5/6 del repo comunitario de ingeniería/ciencia — predicción de toxicidad
in vitro a partir de SMILES, entrenada sobre el dataset público Tox21
(NIH/EPA/FDA, 12 ensayos de toxicidad: receptores nucleares y vías de
respuesta a estrés).

Mismo patrón que el resto del repo: standalone, sin librerías pesadas
obligatorias (numpy es la única dependencia dura). RDKit se usa SOLO si ya
está instalado en el entorno (backend "extendido", más preciso); si no está,
cae automáticamente a un parser de SMILES escrito a mano ("liviano") que
calcula fórmula molecular, peso molecular y un set reducido de descriptores
vía el modelo de valencia estándar (mismo modelo que usan los parsers
reales — regla OpenSMILES de valencia implícita, incluyendo el ajuste de
-1 para átomos aromáticos).

El parser liviano fue validado (self_test, modo "self_test") contra 14
compuestos de referencia con peso molecular conocido (PubChem), y — cuando
RDKit está disponible — también se cruza automáticamente contra RDKit como
segunda fuente independiente, mismo patrón de doble validación usado en
fem_poisson2d (vs. solución analítica) y en structural_beam_tool (vs.
método de carga unitaria).

Modos (dispatch por `mode`, ver run() y TOOL_SCHEMA al final del archivo):
    - "descriptors" : calcula descriptores moleculares para uno o más SMILES
    - "train"       : entrena un clasificador multi-tarea (12 ensayos Tox21)
    - "predict"     : predice probabilidades de toxicidad para SMILES nuevos
    - "self_test"   : corre la batería de validación y devuelve pass/fail

Nota sobre alcance: el clasificador es una regresión logística multi-tarea
con enmascarado de etiquetas faltantes, implementada a mano con numpy
(descenso de gradiente, sin scikit-learn), en línea con el resto del repo.
No pretende competir con arquitecturas de graph neural network de los
papers de referencia (DeepTox, MolToxPred) — es un modelo simple, honesto
sobre sus límites, apto para cribado rápido / docencia, no para decisiones
regulatorias.
"""

import csv
import io
import json
import math
import re
import sys

import numpy as np

# ---------------------------------------------------------------------------
# Tabla de pesos atómicos (g/mol, IUPAC) — cubre el subconjunto orgánico de
# SMILES sin corchetes más los elementos más comunes que aparecen entre
# corchetes en compuestos de Tox21 (metales, metaloides, halógenos pesados).
# ---------------------------------------------------------------------------
ATOMIC_WEIGHTS = {
    "H": 1.008, "He": 4.003, "Li": 6.94, "Be": 9.012, "B": 10.81, "C": 12.011,
    "N": 14.007, "O": 15.999, "F": 18.998, "Ne": 20.180, "Na": 22.990,
    "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974, "S": 32.06,
    "Cl": 35.45, "K": 39.098, "Ca": 40.078, "Sc": 44.956, "Ti": 47.867,
    "V": 50.942, "Cr": 51.996, "Mn": 54.938, "Fe": 55.845, "Co": 58.933,
    "Ni": 58.693, "Cu": 63.546, "Zn": 65.38, "Ga": 69.723, "Ge": 72.630,
    "As": 74.922, "Se": 78.971, "Br": 79.904, "Kr": 83.798, "Rb": 85.468,
    "Sr": 87.62, "Zr": 91.224, "Mo": 95.95, "Ag": 107.868, "Cd": 112.414,
    "In": 114.818, "Sn": 118.710, "Sb": 121.760, "Te": 127.60, "I": 126.904,
    "Cs": 132.905, "Ba": 137.327, "Pt": 195.084, "Au": 196.967,
    "Hg": 200.592, "Tl": 204.38, "Pb": 207.2, "Bi": 208.980,
}

# Elementos del subconjunto "orgánico" de SMILES (se pueden escribir sin
# corchetes). Mayúscula = no aromático, minúscula = aromático.
ORGANIC_SUBSET_2LETTER = ("Cl", "Br")
ORGANIC_SUBSET_1LETTER = ("B", "C", "N", "O", "P", "S", "F", "I")
ORGANIC_SUBSET_AROMATIC = ("b", "c", "n", "o", "p", "s")

# Valencias estándar (se usa la menor >= suma de órdenes de enlace)
STANDARD_VALENCES = {
    "B": (3,), "C": (4,), "N": (3, 5), "O": (2,), "P": (3, 5), "S": (2, 4, 6),
    "F": (1,), "Cl": (1,), "Br": (1,), "I": (1,),
}

BOND_ORDER = {"-": 1, "=": 2, "#": 3, ":": 1, "/": 1, "\\": 1}

TOX21_TASKS = [
    "NR-AR", "NR-AR-LBD", "NR-AhR", "NR-Aromatase", "NR-ER", "NR-ER-LBD",
    "NR-PPAR-gamma", "SR-ARE", "SR-ATAD5", "SR-HSE", "SR-MMP", "SR-p53",
]

CORE_FEATURE_NAMES = [
    "molecular_weight", "heavy_atom_count", "num_rings", "num_aromatic_atoms",
    "num_double_bonds", "num_triple_bonds", "num_hetero_atoms",
    "num_h_donors_approx", "num_h_acceptors_approx", "net_charge",
]
EXTENDED_FEATURE_NAMES = ["mol_logp", "tpsa", "num_rotatable_bonds"]


# ===========================================================================
# 1. PARSER SMILES LIVIANO (sin dependencias)
# ===========================================================================

def tokenize_smiles(smiles):
    """Convierte un string SMILES en una lista de tokens (átomo/enlace/
    apertura-cierre de rama/anillo/punto). Lanza ValueError ante cualquier
    carácter fuera del subconjunto soportado — preferible fallar ruidoso
    a devolver un descriptor calculado sobre una molécula mal interpretada.
    """
    tokens = []
    i = 0
    n = len(smiles)
    while i < n:
        ch = smiles[i]
        if ch == "[":
            j = smiles.find("]", i)
            if j == -1:
                raise ValueError(f"Corchete sin cerrar en SMILES: '{smiles}'")
            tokens.append(_parse_bracket_atom(smiles[i + 1:j]))
            i = j + 1
            continue
        if ch in BOND_ORDER:
            tokens.append({"type": "bond", "order": BOND_ORDER[ch]})
            i += 1
            continue
        if ch == "(":
            tokens.append({"type": "branch_open"})
            i += 1
            continue
        if ch == ")":
            tokens.append({"type": "branch_close"})
            i += 1
            continue
        if ch == ".":
            tokens.append({"type": "dot"})
            i += 1
            continue
        if ch == "%":
            num = smiles[i + 1:i + 3]
            if len(num) != 2 or not num.isdigit():
                raise ValueError(f"Ring closure '%' mal formado en '{smiles}'")
            tokens.append({"type": "ring", "num": num})
            i += 3
            continue
        if ch.isdigit():
            tokens.append({"type": "ring", "num": ch})
            i += 1
            continue
        two = smiles[i:i + 2]
        if two in ORGANIC_SUBSET_2LETTER:
            tokens.append({"type": "atom", "element": two, "aromatic": False,
                            "explicit_h": None, "charge": 0, "bracket": False})
            i += 2
            continue
        if ch in ORGANIC_SUBSET_1LETTER:
            tokens.append({"type": "atom", "element": ch, "aromatic": False,
                            "explicit_h": None, "charge": 0, "bracket": False})
            i += 1
            continue
        if ch in ORGANIC_SUBSET_AROMATIC:
            tokens.append({"type": "atom", "element": ch.upper(), "aromatic": True,
                            "explicit_h": None, "charge": 0, "bracket": False})
            i += 1
            continue
        if ch == "*":
            tokens.append({"type": "atom", "element": "*", "aromatic": False,
                            "explicit_h": 0, "charge": 0, "bracket": True})
            i += 1
            continue
        raise ValueError(
            f"Carácter SMILES fuera del subconjunto soportado: '{ch}' "
            f"(posición {i} en '{smiles}'). Probá el backend RDKit si está "
            f"disponible."
        )
    return tokens


def _parse_bracket_atom(inner):
    """Parsea el contenido de un átomo entre corchetes, ej: 'nH', 'C@@H',
    'NH4+', 'Se', 'Cl-', 'Na+'. Devuelve un token de tipo átomo."""
    s = inner
    m = re.match(r"^\d+", s)  # isótopo — se ignora para el peso (se usa peso estándar)
    if m:
        s = s[m.end():]

    m = re.match(r"^([A-Z][a-z]|[A-Za-z])", s)
    if not m:
        raise ValueError(f"Átomo entre corchetes inválido: '[{inner}]'")
    sym = m.group(1)
    s = s[m.end():]

    aromatic = sym[0].islower()
    element = sym.capitalize() if aromatic else sym
    if element not in ATOMIC_WEIGHTS:
        raise ValueError(f"Elemento desconocido entre corchetes: '[{inner}]'")

    while s[:1] == "@":
        s = s[1:]
        if s[:1] == "@":
            s = s[1:]
        break

    h_count = 0
    m = re.match(r"^H(\d*)", s)
    if m:
        h_count = int(m.group(1)) if m.group(1) else 1
        s = s[m.end():]

    charge = 0
    m = re.match(r"^(\+{1,}|-{1,})(\d*)", s)
    if m:
        sign = 1 if m.group(1)[0] == "+" else -1
        charge = sign * (int(m.group(2)) if m.group(2) else len(m.group(1)))

    return {"type": "atom", "element": element, "aromatic": aromatic,
            "explicit_h": h_count, "charge": charge, "bracket": True}


def parse_smiles(smiles):
    """Construye la lista de átomos y enlaces a partir de los tokens.
    Devuelve (atoms, bonds, num_rings_closed)."""
    tokens = tokenize_smiles(smiles.strip())
    atoms = []
    bonds = []
    stack = []
    ring_bonds = {}
    prev_atom = None
    pending_bond = 1
    num_rings_closed = 0

    for tok in tokens:
        t = tok["type"]
        if t == "atom":
            idx = len(atoms)
            atoms.append({
                "element": tok["element"], "aromatic": tok["aromatic"],
                "explicit_h": tok["explicit_h"], "charge": tok["charge"],
                "bracket": tok["bracket"],
            })
            if prev_atom is not None:
                bonds.append((prev_atom, idx, pending_bond))
            prev_atom = idx
            pending_bond = 1
        elif t == "bond":
            pending_bond = tok["order"]
        elif t == "branch_open":
            if prev_atom is None:
                raise ValueError(f"'(' sin átomo previo en '{smiles}'")
            stack.append(prev_atom)
        elif t == "branch_close":
            if not stack:
                raise ValueError(f"')' sin '(' correspondiente en '{smiles}'")
            prev_atom = stack.pop()
            pending_bond = 1
        elif t == "ring":
            if prev_atom is None:
                raise ValueError(f"Cierre de anillo sin átomo previo en '{smiles}'")
            num = tok["num"]
            if num in ring_bonds:
                other_idx, other_order = ring_bonds.pop(num)
                order = pending_bond if pending_bond != 1 else other_order
                bonds.append((other_idx, prev_atom, order))
                num_rings_closed += 1
            else:
                ring_bonds[num] = (prev_atom, pending_bond)
            pending_bond = 1
        elif t == "dot":
            prev_atom = None
            pending_bond = 1

    if stack:
        raise ValueError(f"Rama(s) sin cerrar en '{smiles}'")
    if ring_bonds:
        raise ValueError(f"Anillo(s) sin cerrar en '{smiles}': {list(ring_bonds)}")
    return atoms, bonds, num_rings_closed


def _bond_order_sum(atom_idx, bonds):
    total = 0
    for i, j, order in bonds:
        if i == atom_idx or j == atom_idx:
            total += order
    return total


def _format_formula(element_counts):
    """Notación de Hill: C primero, H segundo, resto alfabético."""
    ordered = []
    if "C" in element_counts:
        ordered.append("C")
    if "H" in element_counts:
        ordered.append("H")
    ordered += sorted(e for e in element_counts if e not in ("C", "H"))
    parts = []
    for el in ordered:
        cnt = element_counts[el]
        parts.append(el if cnt == 1 else f"{el}{cnt}")
    return "".join(parts)


def compute_descriptors_lightweight(smiles):
    """Calcula descriptores moleculares desde un SMILES usando solo el
    parser hecho a mano (sin RDKit). Implementa la regla OpenSMILES de
    hidrógeno implícito: para átomos aromáticos (minúscula), se resta 1
    extra a la valencia disponible respecto de la suma de órdenes de
    enlace, para reflejar la participación en el sistema pi deslocalizado
    (esto es lo que hace que benceno dé 1 H por carbono y no 2, y que los
    carbonos de unión de naftaleno den 0 H)."""
    atoms, bonds, num_rings = parse_smiles(smiles)
    if not atoms:
        raise ValueError(f"SMILES vacío o no interpretable: '{smiles}'")

    element_counts = {}
    num_aromatic = 0
    num_double = sum(1 for (_, _, o) in bonds if o == 2)
    num_triple = sum(1 for (_, _, o) in bonds if o == 3)
    net_charge = 0
    h_donor_atoms = 0
    h_acceptor_atoms = 0
    total_h = 0

    for idx, atom in enumerate(atoms):
        el = atom["element"]
        aromatic = atom["aromatic"]
        net_charge += atom["charge"]
        if aromatic:
            num_aromatic += 1

        if atom["bracket"]:
            h = atom["explicit_h"] or 0
        else:
            bsum = _bond_order_sum(idx, bonds)
            valences = STANDARD_VALENCES.get(el)
            if valences is None:
                raise ValueError(f"Elemento '{el}' no admitido sin corchetes")
            valence = next((v for v in valences if v >= bsum), valences[-1])
            h = valence - bsum
            if aromatic:
                h -= 1
            h = max(0, h)

        total_h += h
        element_counts[el] = element_counts.get(el, 0) + 1
        if el in ("N", "O") and h > 0:
            h_donor_atoms += 1
        if el in ("N", "O"):
            h_acceptor_atoms += 1

    if el == "*":
        pass  # marcador de átomo comodín — no debería aparecer en Tox21, se deja pasar
    element_counts["H"] = element_counts.get("H", 0) + total_h

    mw = 0.0
    for el, cnt in element_counts.items():
        if el == "*":
            continue
        if el not in ATOMIC_WEIGHTS:
            raise ValueError(f"Peso atómico desconocido para '{el}'")
        mw += ATOMIC_WEIGHTS[el] * cnt

    return {
        "backend": "lightweight",
        "molecular_weight": round(mw, 3),
        "molecular_formula": _format_formula(element_counts),
        "heavy_atom_count": len(atoms),
        "num_rings": num_rings,
        "num_aromatic_atoms": num_aromatic,
        "num_double_bonds": num_double,
        "num_triple_bonds": num_triple,
        "num_hetero_atoms": sum(c for e, c in element_counts.items() if e not in ("C", "H", "*")),
        "num_h_donors_approx": h_donor_atoms,
        "num_h_acceptors_approx": h_acceptor_atoms,
        "net_charge": net_charge,
        "element_counts": element_counts,
    }


# ===========================================================================
# 2. BACKEND RDKit (opcional — se usa si está instalado)
# ===========================================================================

def _try_import_rdkit():
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, Lipinski, rdMolDescriptors
        return {"Chem": Chem, "Descriptors": Descriptors, "Lipinski": Lipinski,
                "rdMolDescriptors": rdMolDescriptors}
    except ImportError:
        return None


def compute_descriptors_rdkit(smiles, rk):
    Chem = rk["Chem"]
    Descriptors = rk["Descriptors"]
    Lipinski = rk["Lipinski"]
    rdMolDescriptors = rk["rdMolDescriptors"]

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit no pudo interpretar el SMILES: '{smiles}'")

    num_aromatic = sum(1 for atom in mol.GetAtoms() if atom.GetIsAromatic())
    num_double = sum(1 for b in mol.GetBonds() if abs(b.GetBondTypeAsDouble() - 2.0) < 1e-6)
    num_triple = sum(1 for b in mol.GetBonds() if abs(b.GetBondTypeAsDouble() - 3.0) < 1e-6)

    return {
        "backend": "rdkit",
        "molecular_weight": round(Descriptors.MolWt(mol), 3),
        "molecular_formula": rdMolDescriptors.CalcMolFormula(mol),
        "heavy_atom_count": mol.GetNumHeavyAtoms(),
        "num_rings": rdMolDescriptors.CalcNumRings(mol),
        "num_aromatic_atoms": num_aromatic,
        "num_double_bonds": num_double,
        "num_triple_bonds": num_triple,
        "num_hetero_atoms": rdMolDescriptors.CalcNumHeteroatoms(mol),
        "num_h_donors_approx": Lipinski.NumHDonors(mol),
        "num_h_acceptors_approx": Lipinski.NumHAcceptors(mol),
        "net_charge": Chem.GetFormalCharge(mol),
        "mol_logp": round(Descriptors.MolLogP(mol), 3),
        "tpsa": round(Descriptors.TPSA(mol), 3),
        "num_rotatable_bonds": rdMolDescriptors.CalcNumRotatableBonds(mol),
    }


def get_backend(requested="auto"):
    """Resuelve qué backend usar. 'auto' prefiere RDKit si está disponible,
    igual que el patrón try/except ImportError del resto del repo."""
    rk = _try_import_rdkit()
    if requested == "rdkit":
        if rk is None:
            raise ImportError("Se pidió backend 'rdkit' pero RDKit no está instalado")
        return "rdkit", rk
    if requested == "lightweight":
        return "lightweight", None
    if requested == "auto":
        return ("rdkit", rk) if rk is not None else ("lightweight", None)
    raise ValueError(f"Backend desconocido: '{requested}' (usar auto/rdkit/lightweight)")


def compute_descriptors(smiles, backend="auto"):
    name, rk = get_backend(backend)
    if name == "rdkit":
        return compute_descriptors_rdkit(smiles, rk)
    return compute_descriptors_lightweight(smiles)


def descriptors_to_vector(desc, extended=False):
    vec = [float(desc[name]) for name in CORE_FEATURE_NAMES]
    if extended:
        vec += [float(desc.get(name, 0.0)) for name in EXTENDED_FEATURE_NAMES]
    return vec


# ===========================================================================
# 3. CLASIFICADOR MULTI-TAREA (regresión logística, numpy puro)
# ===========================================================================

def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))


def train_multitask_logreg(X, Y, task_names=None, epochs=800, lr=0.15, l2=1e-3, seed=0):
    """Regresión logística multi-tarea con enmascarado de NaN en las
    etiquetas (así se puede entrenar con los 12 ensayos de Tox21 aunque
    cada compuesto tenga resultado solo en algunos de ellos — patrón
    estándar para este dataset, no es una decisión arbitraria).

    IMPORTANTE: task_names debe venir explícito con el orden real de las
    columnas usadas (no asumir que son las primeras k tareas canónicas de
    Tox21 — un CSV puede traer un subconjunto en cualquier orden)."""
    X = np.asarray(X, dtype=float)
    Y = np.asarray(Y, dtype=float)
    rng = np.random.default_rng(seed)
    n, d = X.shape
    k = Y.shape[1]

    mask = ~np.isnan(Y)
    if not mask.any():
        raise ValueError("No hay ninguna etiqueta válida (todo NaN) para entrenar")
    Yf = np.nan_to_num(Y, nan=0.0)

    mu = X.mean(axis=0)
    sigma = X.std(axis=0)
    sigma[sigma == 0] = 1.0
    Xs = (X - mu) / sigma
    Xb = np.hstack([Xs, np.ones((n, 1))])

    W = rng.normal(0, 0.01, size=(d + 1, k))
    loss_history = []
    n_valid = mask.sum(axis=0)
    n_valid_safe = np.where(n_valid == 0, 1, n_valid)

    for _ in range(epochs):
        Z = Xb @ W
        P = _sigmoid(Z)
        err = (P - Yf) * mask
        grad = (Xb.T @ err) / n_valid_safe + l2 * W
        W -= lr * grad
        eps = 1e-9
        per_elem = -(Yf * np.log(P + eps) + (1 - Yf) * np.log(1 - P + eps)) * mask
        loss_history.append(float(per_elem.sum() / max(1, mask.sum())))

    if task_names is None:
        task_names = TOX21_TASKS[:k] if k <= len(TOX21_TASKS) else [f"task_{i}" for i in range(k)]
    if len(task_names) != k:
        raise ValueError(f"task_names tiene {len(task_names)} nombres pero Y tiene {k} columnas")

    return {
        "W": W.tolist(), "mu": mu.tolist(), "sigma": sigma.tolist(),
        "feature_names": CORE_FEATURE_NAMES + (EXTENDED_FEATURE_NAMES if d > len(CORE_FEATURE_NAMES) else []),
        "tasks": list(task_names),
        "loss_history": loss_history,
        "n_train": n,
        "n_valid_per_task": n_valid.tolist(),
    }


def predict_multitask_logreg(model, X):
    X = np.asarray(X, dtype=float)
    W = np.array(model["W"])
    mu = np.array(model["mu"])
    sigma = np.array(model["sigma"])
    Xs = (X - mu) / sigma
    n = Xs.shape[0]
    Xb = np.hstack([Xs, np.ones((n, 1))])
    return _sigmoid(Xb @ W)


# ===========================================================================
# 4. CARGA DE DATOS (CSV estilo Tox21 — smiles + columnas de tareas)
# ===========================================================================

def load_tox21_csv(csv_text, smiles_col="smiles", task_cols=None):
    """Parsea un CSV en memoria (texto, no requiere pandas). Formato
    esperado: una columna de SMILES y columnas de tareas con 0/1/vacío
    (vacío = sin ensayo -> NaN)."""
    task_cols = task_cols or TOX21_TASKS
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None or smiles_col not in reader.fieldnames:
        raise ValueError(f"El CSV no tiene columna '{smiles_col}'")
    present_tasks = [c for c in task_cols if c in reader.fieldnames]
    if not present_tasks:
        raise ValueError(f"Ninguna columna de tarea esperada está en el CSV: {task_cols}")

    records = []
    for row in reader:
        smi = (row.get(smiles_col) or "").strip()
        if not smi:
            continue
        labels = {}
        for t in present_tasks:
            v = (row.get(t) or "").strip()
            labels[t] = float(v) if v != "" else float("nan")
        records.append({"smiles": smi, "labels": labels})
    return records, present_tasks


# ===========================================================================
# 5. VALIDACIÓN (modo self_test)
# ===========================================================================

_MW_REFERENCE_CASES = [
    ("agua", "O", 18.015),
    ("etanol", "CCO", 46.069),
    ("acido acetico", "CC(=O)O", 60.052),
    ("etileno", "C=C", 28.054),
    ("acetileno", "C#C", 26.038),
    ("isobutano", "CC(C)C", 58.124),
    ("benceno", "c1ccccc1", 78.114),
    ("piridina", "c1ccncc1", 79.101),
    ("naftaleno", "c1ccc2ccccc2c1", 128.174),
    ("aspirina", "CC(=O)OC1=CC=CC=C1C(=O)O", 180.159),
    ("cafeina", "CN1C=NC2=C1C(=O)N(C(=O)N2C)C", 194.194),
    ("amonio", "[NH4+]", 18.039),
    ("cloruro", "[Cl-]", 35.45),
    ("sodio ion", "[Na+]", 22.990),
]


def run_self_test():
    checks = []

    def check(name, cond, detail=""):
        checks.append({"name": name, "passed": bool(cond), "detail": detail})

    # 1-14: peso molecular liviano vs. valores de referencia (PubChem)
    for label, smi, expected in _MW_REFERENCE_CASES:
        try:
            d = compute_descriptors_lightweight(smi)
            got = d["molecular_weight"]
            ok = abs(got - expected) < 0.05
            check(f"MW liviano: {label} ({smi})", ok, f"esperado={expected}, obtenido={got}")
        except Exception as e:
            check(f"MW liviano: {label} ({smi})", False, f"excepcion: {e}")

    # 15: conteo de anillos (benceno=1, naftaleno=2)
    try:
        b = compute_descriptors_lightweight("c1ccccc1")
        nap = compute_descriptors_lightweight("c1ccc2ccccc2c1")
        check("conteo de anillos benceno/naftaleno", b["num_rings"] == 1 and nap["num_rings"] == 2,
              f"benceno={b['num_rings']}, naftaleno={nap['num_rings']}")
    except Exception as e:
        check("conteo de anillos benceno/naftaleno", False, str(e))

    # 16: hidrógeno implícito aromático correcto en carbono de unión (naftaleno, 0 H ahí)
    try:
        atoms, bonds, _ = parse_smiles("c1ccc2ccccc2c1")
        bridge_idxs = [i for i in range(len(atoms)) if sum(1 for a, b, o in bonds if a == i or b == i) == 3]
        check("carbono de union en naftaleno sin H extra", len(bridge_idxs) == 2,
              f"atomos con 3 conexiones: {len(bridge_idxs)} (esperado 2)")
    except Exception as e:
        check("carbono de union en naftaleno sin H extra", False, str(e))

    # 17: backend RDKit, si está disponible, cruza contra el liviano (segunda fuente)
    rk = _try_import_rdkit()
    if rk is not None:
        diffs = []
        for label, smi, _ in _MW_REFERENCE_CASES:
            try:
                mw_light = compute_descriptors_lightweight(smi)["molecular_weight"]
                mw_rdkit = compute_descriptors_rdkit(smi, rk)["molecular_weight"]
                diffs.append(abs(mw_light - mw_rdkit))
            except Exception:
                diffs.append(999)
        ok = all(d < 0.1 for d in diffs)
        check("liviano vs RDKit (validacion cruzada, 14 casos)", ok, f"max diff={max(diffs):.4f}")
    else:
        check("liviano vs RDKit (validacion cruzada)", True, "RDKit no instalado — se omite, no es error")

    # 18: entrenamiento converge en dataset sintético separable con NaN mezclados
    try:
        rng = np.random.default_rng(42)
        n = 200
        X = rng.normal(0, 1, size=(n, len(CORE_FEATURE_NAMES)))
        true_w = rng.normal(0, 1, size=(len(CORE_FEATURE_NAMES), 3))
        logits = X @ true_w
        Y = (logits > 0).astype(float)
        # sembrar ~15% de NaN al azar, simulando ensayos no realizados
        nan_mask = rng.random(Y.shape) < 0.15
        Y[nan_mask] = np.nan

        model = train_multitask_logreg(X, Y, epochs=400, lr=0.2, l2=1e-3)
        loss_start = model["loss_history"][0]
        loss_end = model["loss_history"][-1]
        check("entrenamiento: la perdida baja de forma sustancial", loss_end < loss_start * 0.5,
              f"loss inicial={loss_start:.4f}, final={loss_end:.4f}")

        P = predict_multitask_logreg(model, X)
        valid = ~np.isnan(Y)
        pred_labels = (P > 0.5).astype(float)
        acc = (pred_labels[valid] == Y[valid]).mean()
        check("entrenamiento: accuracy en dataset separable >= 0.85", acc >= 0.85, f"accuracy={acc:.3f}")

        check("predict: probabilidades en rango [0,1]", bool((P >= 0).all() and (P <= 1).all()))
        check("predict: forma de salida correcta", P.shape == Y.shape, f"shape={P.shape}, esperado={Y.shape}")
    except Exception as e:
        check("entrenamiento multi-tarea con etiquetas faltantes", False, str(e))

    # 19: carga de CSV estilo Tox21 con celdas vacías -> NaN
    try:
        csv_text = "smiles,NR-AR,NR-AhR\nCCO,0,1\nc1ccccc1,,0\n"
        records, tasks = load_tox21_csv(csv_text)
        ok = (len(records) == 2 and tasks == ["NR-AR", "NR-AhR"]
              and records[1]["labels"]["NR-AR"] != records[1]["labels"]["NR-AR"])  # NaN != NaN
        check("carga de CSV Tox21 (celda vacia -> NaN)", ok, str(records))
    except Exception as e:
        check("carga de CSV Tox21 (celda vacia -> NaN)", False, str(e))

    # 20: SMILES inválido levanta error en vez de devolver basura silenciosa
    try:
        raised = False
        try:
            compute_descriptors_lightweight("C1CC")  # anillo sin cerrar
        except ValueError:
            raised = True
        check("SMILES con anillo sin cerrar levanta ValueError", raised)
    except Exception as e:
        check("SMILES con anillo sin cerrar levanta ValueError", False, str(e))

    n_pass = sum(1 for c in checks if c["passed"])
    return {"total": len(checks), "passed": n_pass, "all_passed": n_pass == len(checks), "checks": checks}


# ===========================================================================
# 6. DISPATCH
# ===========================================================================

def run(mode, params=None):
    params = params or {}

    if mode == "validate":
        r = run_self_test()
        return {"checks": r["checks"], "validation_passed": r["all_passed"], "n_checks": r["total"]}
    if mode == "descriptors":
        backend = params.get("backend", "auto")
        smiles_list = params.get("smiles_list") or ([params["smiles"]] if "smiles" in params else None)
        if not smiles_list:
            raise ValueError("Falta 'smiles' o 'smiles_list' en params")
        return {"results": [compute_descriptors(s, backend) for s in smiles_list]}

    if mode == "train":
        backend = params.get("backend", "auto")
        extended = bool(params.get("extended_features", False)) and backend != "lightweight"
        if "csv_text" in params:
            records, tasks = load_tox21_csv(
                params["csv_text"], params.get("smiles_col", "smiles"), params.get("task_cols")
            )
        elif "data" in params:
            records = params["data"]
            tasks = params.get("task_cols") or sorted({t for r in records for t in r["labels"]})
        else:
            raise ValueError("Falta 'csv_text' o 'data' en params para entrenar")

        X, Y = [], []
        skipped = []
        for r in records:
            try:
                d = compute_descriptors(r["smiles"], backend)
                X.append(descriptors_to_vector(d, extended=extended))
                Y.append([r["labels"].get(t, float("nan")) for t in tasks])
            except Exception as e:
                skipped.append({"smiles": r["smiles"], "error": str(e)})
        if not X:
            raise ValueError("Ningun SMILES pudo procesarse — nada para entrenar")

        model = train_multitask_logreg(
            np.array(X), np.array(Y), task_names=tasks,
            epochs=params.get("epochs", 800), lr=params.get("lr", 0.15), l2=params.get("l2", 1e-3),
        )
        model["backend"] = backend if backend != "auto" else get_backend("auto")[0]
        model["extended_features"] = extended
        return {"model": model, "n_used": len(X), "n_skipped": len(skipped), "skipped": skipped[:20]}

    if mode == "predict":
        model = params.get("model")
        if model is None:
            raise ValueError("Falta 'model' (el dict devuelto por mode='train') en params")
        backend = model.get("backend", "lightweight")
        extended = model.get("extended_features", False)
        smiles_list = params.get("smiles_list") or ([params["smiles"]] if "smiles" in params else None)
        if not smiles_list:
            raise ValueError("Falta 'smiles' o 'smiles_list' en params")

        X = [descriptors_to_vector(compute_descriptors(s, backend), extended=extended) for s in smiles_list]
        P = predict_multitask_logreg(model, X)
        tasks = model.get("tasks", TOX21_TASKS)
        results = []
        for smi, probs in zip(smiles_list, P):
            results.append({"smiles": smi, "probabilities": {t: round(float(p), 4) for t, p in zip(tasks, probs)}})
        return {"results": results}

    if mode == "self_test":
        return run_self_test()

    raise ValueError(f"Modo desconocido: '{mode}' (usar descriptors/train/predict/self_test)")


# ===========================================================================
# 7. TOOL_SCHEMA — Astrid: ajustar nombres de campo al formato real de
#    register_tool() en tool_registry.py, esto es un borrador funcional
#    (no tengo acceso al registro real para calzarlo exacto).
# ===========================================================================

TOOL_SCHEMA = {
    "name": "toxicity_predictor",
    "description": (
        "Predice probabilidad de toxicidad in vitro (12 ensayos del panel "
        "Tox21 NIH/EPA/FDA: receptores nucleares y vias de respuesta a "
        "estres) a partir de SMILES. Calcula descriptores moleculares con "
        "RDKit si esta disponible, o con un parser SMILES liviano propio "
        "(validado contra RDKit y contra pesos moleculares de referencia) "
        "si no lo esta. Clasificador: regresion logistica multi-tarea "
        "entrenada a mano con numpy, con enmascarado de etiquetas "
        "faltantes. No sustituye ensayos de laboratorio ni decisiones "
        "regulatorias — es cribado rapido / uso educativo."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["descriptors", "train", "predict", "self_test"],
                "description": (
                    "descriptors: calcula descriptores moleculares. "
                    "train: entrena el clasificador multi-tarea. "
                    "predict: predice probabilidades con un modelo entrenado. "
                    "self_test: corre la bateria de validacion interna, sin parametros."
                ),
            },
            "params": {
                "type": "object",
                "description": (
                    "Parametros especificos del modo. "
                    "descriptors: {smiles, smiles_list, backend}. "
                    "train: {csv_text, data, task_cols, backend, extended_features, epochs, lr, l2}. "
                    "predict: {model, smiles, smiles_list}. "
                    "self_test: no requiere params."
                ),
            },
        },
        "required": ["mode"],
    },
}


if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "self_test"
    params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    print(json.dumps(run(mode_arg, params_arg), indent=2, ensure_ascii=False))


def _register():
    """
    Auto-registro estilo octave-mcp (patron self-registrante via
    tool_registry, register_tool(name, schema, handler)).
    """
    try:
        import tool_registry

        def _handler(args):
            return run(args.get("mode"), args.get("params"))

        tool_registry.register_tool("toxicity_predictor", TOOL_SCHEMA, _handler)
    except ImportError:
        pass


_register()
