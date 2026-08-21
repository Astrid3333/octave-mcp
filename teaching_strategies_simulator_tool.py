"""
teaching_strategies_simulator_tool.py

Simulador de metodos de ensenanza: un "aprendiz" (red neuronal de juguete,
MLP con backprop manual en numpy) cuyo aprendizaje/retencion por concepto
esta modulado por una capa de repeticion espaciada (curva de olvido tipo
Ebbinghaus, R(t) = exp(-t/S), con S creciendo en cada repaso).

Las estrategias de ensenanza son una lista ABIERTA: cada estrategia es un
dict con los campos que el usuario quiera (nombre, cronograma explicito de
repasos por sesion, o parametros para generar uno round-robin). No hay un
enum fijo de "spaced" vs "massed" -- eso lo define el usuario armando el
cronograma que quiera; el motor solo necesita 'schedule' o
'concepts_per_session'/'n_sessions'/'session_interval'.

Sigue el patron del resto de octave-mcp: dispatcher
compute_teaching_strategies_simulator(mode, params=None), con modos
'simulate' y 'validate'. Sin dependencias externas mas alla de numpy.

Nota de alcance: esto es un modelo de juguete para explorar el efecto del
espaciado de repasos sobre la retencion en un aprendiz artificial simple,
no una implementacion clinica/validada de SM-2 ni un modelo pedagogico
empirico -- las constantes (crecimiento de estabilidad, forma de la
curva de olvido) son ilustrativas.
"""

import numpy as np


# ---------------------------------------------------------------------------
# Red neuronal de juguete (MLP de una capa oculta, backprop manual)
# ---------------------------------------------------------------------------

class ToyLearner:
    """MLP minimo: cada concepto es una clase de salida. El forward/backward
    es estandar (ReLU + softmax + cross-entropy), pero la tasa de
    aprendizaje efectiva POR CONCEPTO se pasa desde afuera (modulada por la
    capa de repeticion espaciada) antes de cada actualizacion."""

    def __init__(self, n_inputs, n_hidden, n_concepts, seed=0):
        rng = np.random.default_rng(seed)
        scale1 = np.sqrt(2.0 / n_inputs)
        scale2 = np.sqrt(2.0 / n_hidden)
        self.W1 = rng.normal(0, scale1, size=(n_inputs, n_hidden))
        self.b1 = np.zeros(n_hidden)
        self.W2 = rng.normal(0, scale2, size=(n_hidden, n_concepts))
        self.b2 = np.zeros(n_concepts)

    @staticmethod
    def _relu(x):
        return np.maximum(0, x)

    @staticmethod
    def _relu_grad(x):
        return (x > 0).astype(float)

    @staticmethod
    def _softmax(x):
        z = x - np.max(x, axis=-1, keepdims=True)
        e = np.exp(z)
        return e / np.sum(e, axis=-1, keepdims=True)

    def forward(self, x):
        z1 = x @ self.W1 + self.b1
        a1 = self._relu(z1)
        z2 = a1 @ self.W2 + self.b2
        p = self._softmax(z2)
        return p, (x, z1, a1, z2, p)

    def backward(self, cache, y_true, lr_per_concept):
        """lr_per_concept: array (n_concepts,) con la tasa de aprendizaje
        efectiva de CADA concepto en este batch. Asi el "olvido" (retencion
        baja) se traduce en updates mas grandes para conceptos poco
        repasados, y la practica de un concepto ya fresco mueve poco los
        pesos (rendimientos decrecientes)."""
        x, z1, a1, z2, p = cache
        n = x.shape[0]
        dz2 = (p - y_true) / n
        dW2 = a1.T @ dz2
        db2 = dz2.sum(axis=0)
        da1 = dz2 @ self.W2.T
        dz1 = da1 * self._relu_grad(z1)
        dW1 = x.T @ dz1
        db1 = dz1.sum(axis=0)

        self.W2 -= dW2 * lr_per_concept[np.newaxis, :]
        self.b2 -= db2 * lr_per_concept
        lr_hidden = float(np.mean(lr_per_concept))
        self.W1 -= dW1 * lr_hidden
        self.b1 -= db1 * lr_hidden

    @staticmethod
    def loss(p, y_true):
        eps = 1e-12
        return -np.mean(np.sum(y_true * np.log(p + eps), axis=-1))

    @staticmethod
    def accuracy(p, y_true):
        return float(np.mean(np.argmax(p, axis=-1) == np.argmax(y_true, axis=-1)))


# ---------------------------------------------------------------------------
# Capa de repeticion espaciada
# ---------------------------------------------------------------------------

class SpacedRepetitionLayer:
    """R(t) = exp(-elapsed/S) por concepto. Cada repaso escala la
    estabilidad S de ese concepto -- pero NO por un factor fijo: el
    crecimiento depende de cuanto se habia olvidado el concepto en el
    momento del repaso (principio de "dificultad deseable" / efecto de
    espaciado: re-estudiar algo que ya casi se olvido consolida mucho mas
    la memoria a largo plazo que re-estudiar algo todavia fresco). Un
    repaso con retencion=1 (justo despues del anterior) casi no suma
    estabilidad; un repaso con retencion~0 (mucho tiempo despues) suma
    hasta `stability_growth` completo."""

    def __init__(self, n_concepts, base_stability=1.0, stability_growth=1.5):
        self.n_concepts = n_concepts
        self.stability = np.full(n_concepts, float(base_stability))
        # se inicializa "muy en el pasado" para que el PRIMER repaso de
        # cada concepto cuente como maximo olvido (consolidacion plena)
        self.last_review = np.full(n_concepts, -1.0e4)
        self.stability_growth = float(stability_growth)

    def retention(self, t_now):
        elapsed = np.maximum(t_now - self.last_review, 0.0)
        return np.exp(-elapsed / self.stability)

    def review(self, concept_idx, t_now):
        r_before = self.retention(t_now)[concept_idx]
        effective_growth = 1.0 + (self.stability_growth - 1.0) * (1.0 - r_before)
        self.stability[concept_idx] *= effective_growth
        self.last_review[concept_idx] = t_now

    def effective_lr(self, t_now, base_lr):
        r = self.retention(t_now)
        # +0.05 evita lr=0 exacto cuando r=1 (repaso instantaneo)
        return base_lr * (1.0 - r + 0.05)


# ---------------------------------------------------------------------------
# Dataset sintetico
# ---------------------------------------------------------------------------

def _synthetic_dataset(n_concepts, n_features, samples_per_concept, seed):
    rng = np.random.default_rng(seed)
    centers = rng.normal(0, 3.0, size=(n_concepts, n_features))
    X, y_idx = [], []
    for c in range(n_concepts):
        pts = centers[c] + rng.normal(0, 0.8, size=(samples_per_concept, n_features))
        X.append(pts)
        y_idx += [c] * samples_per_concept
    X = np.vstack(X)
    y_idx = np.array(y_idx)
    Y = np.eye(n_concepts)[y_idx]
    return X, Y, y_idx


# ---------------------------------------------------------------------------
# Motor: corre UNA estrategia (dict abierto) sobre el aprendiz
# ---------------------------------------------------------------------------

def _run_strategy(strategy, n_concepts, n_hidden, base_lr, seed, dataset,
                   retention_probe_time=None):
    """
    Campos reconocidos en `strategy` (todos opcionales salvo que se note):
      - name: str, etiqueta libre
      - schedule: lista de listas de indices de concepto, una lista por
        sesion (ej. [[0,1],[0,1],[2,3],...]). Si se da, manda sobre
        concepts_per_session/n_sessions para esas sesiones.
      - n_sessions: int, default 10
      - session_interval: tiempo simulado entre sesiones, default 1.0
      - concepts_per_session: cuantos conceptos entran por sesion cuando
        no hay `schedule` explicito (round-robin), default: todos
    Cualquier otro campo se ignora (asi el usuario puede anotar la
    estrategia con metadata propia sin romper nada).

    `retention_probe_time`: si se pasa (viene de params.retention_probe_time
    en _simulate), la retencion final se mide en ese instante ABSOLUTO,
    igual para todas las estrategias que se comparen -- necesario para una
    comparacion justa, porque si no cada estrategia queda medida "recien
    terminada de estudiar" y el cramming (que termina en segundos) siempre
    parece ganar en retencion aunque haya aprendido peor (ver accuracy).
    Si no se pasa, se usa el instante en que la propia estrategia termina
    su cronograma (retencion "al cerrar el libro", no comparable entre
    estrategias con duraciones distintas).
    """
    X, Y, y_idx = dataset
    learner = ToyLearner(X.shape[1], n_hidden, n_concepts, seed=seed)
    spacer = SpacedRepetitionLayer(n_concepts)

    n_sessions = int(strategy.get("n_sessions", 10))
    interval = float(strategy.get("session_interval", 1.0))
    schedule = strategy.get("schedule")
    per_session = int(strategy.get("concepts_per_session", n_concepts))

    acc_history = []
    t = 0.0
    for s in range(n_sessions):
        if schedule is not None and s < len(schedule):
            concepts_today = list(schedule[s])
        else:
            start = (s * per_session) % n_concepts
            concepts_today = [(start + k) % n_concepts for k in range(per_session)]

        mask = np.isin(y_idx, concepts_today)
        if np.any(mask):
            Xb, Yb = X[mask], Y[mask]
            lr_per_concept = spacer.effective_lr(t, base_lr)
            p, cache = learner.forward(Xb)
            learner.backward(cache, Yb, lr_per_concept)
            for c in concepts_today:
                spacer.review(c, t)
            p_all, _ = learner.forward(X)
            acc_history.append(round(learner.accuracy(p_all, Y), 4))
        t += interval

    probe_t = retention_probe_time if retention_probe_time is not None else t
    final_retention = spacer.retention(probe_t)
    p_all, _ = learner.forward(X)

    return {
        "name": strategy.get("name", "sin_nombre"),
        "acc_history": acc_history,
        "final_accuracy": round(learner.accuracy(p_all, Y), 4),
        "final_loss": round(float(learner.loss(p_all, Y)), 4),
        "retention_probe_time_used": round(float(probe_t), 4),
        "final_mean_retention": round(float(np.mean(final_retention)), 4),
        "final_retention_by_concept": [round(float(r), 4) for r in final_retention],
    }


# ---------------------------------------------------------------------------
# Modos publicos
# ---------------------------------------------------------------------------

def _simulate(params):
    n_concepts = int(params.get("n_concepts", 4))
    n_features = int(params.get("n_features", 6))
    n_hidden = int(params.get("n_hidden", max(8, n_concepts * 2)))
    samples_per_concept = int(params.get("samples_per_concept", 30))
    base_lr = float(params.get("base_lr", 0.5))
    seed = int(params.get("seed", 0))
    strategies = params.get("strategies")
    if not strategies:
        raise ValueError("params.strategies es requerido: lista de dicts "
                          "(cada uno define su propio cronograma/parametros)")
    retention_probe_time = params.get("retention_probe_time")

    dataset = _synthetic_dataset(n_concepts, n_features, samples_per_concept, seed)
    results = [
        _run_strategy(strat, n_concepts, n_hidden, base_lr, seed, dataset,
                      retention_probe_time)
        for strat in strategies
    ]
    ranking = sorted(
        results,
        key=lambda r: (r["final_mean_retention"], r["final_accuracy"]),
        reverse=True,
    )
    return {
        "n_concepts": n_concepts,
        "results": results,
        "ranking_by_retention": [r["name"] for r in ranking],
    }


def _validate():
    checks = []

    # 1) La retencion es 1.0 justo despues de un repaso (t_now == last_review)
    sp = SpacedRepetitionLayer(3, base_stability=2.0)
    sp.review(0, t_now=5.0)
    r_immediate = sp.retention(5.0)[0]
    checks.append({
        "name": "retencion_1.0_justo_tras_repaso",
        "passed": bool(abs(r_immediate - 1.0) < 1e-9),
        "detail": f"R={r_immediate:.6f}",
    })

    # 2) La retencion decae monotonamente con el tiempo transcurrido
    r_t1 = sp.retention(6.0)[0]
    r_t5 = sp.retention(10.0)[0]
    r_t20 = sp.retention(25.0)[0]
    monotone = r_immediate > r_t1 > r_t5 > r_t20 >= 0.0
    checks.append({
        "name": "retencion_decae_monotonamente_con_tiempo",
        "passed": bool(monotone),
        "detail": f"R(0)={r_immediate:.4f}, R(1)={r_t1:.4f}, R(5)={r_t5:.4f}, R(20)={r_t20:.4f}",
    })

    # 3) effective_lr crece cuando hay mas olvido (mas tiempo transcurrido)
    sp2 = SpacedRepetitionLayer(1, base_stability=1.0)
    sp2.review(0, t_now=0.0)
    lr_fresh = sp2.effective_lr(0.0, base_lr=1.0)[0]
    lr_stale = sp2.effective_lr(10.0, base_lr=1.0)[0]
    checks.append({
        "name": "lr_efectivo_crece_con_olvido",
        "passed": bool(lr_stale > lr_fresh),
        "detail": f"lr_fresh={lr_fresh:.4f}, lr_stale={lr_stale:.4f}",
    })

    # 4) repasar un concepto aumenta su estabilidad (crecimiento monotono)
    sp3 = SpacedRepetitionLayer(1, base_stability=1.0, stability_growth=1.5)
    s0 = sp3.stability[0]
    sp3.review(0, 0.0)
    s1 = sp3.stability[0]
    sp3.review(0, 1.0)
    s2 = sp3.stability[0]
    checks.append({
        "name": "estabilidad_crece_con_repasos_repetidos",
        "passed": bool(s0 < s1 < s2),
        "detail": f"S0={s0:.4f}, S1={s1:.4f}, S2={s2:.4f}",
    })

    # 5) el aprendizaje reduce la loss de principio a fin (dataset trivial separable)
    dataset = _synthetic_dataset(3, 5, 25, seed=1)
    X, Y, _ = dataset
    learner0 = ToyLearner(5, 10, 3, seed=1)
    p0, _ = learner0.forward(X)
    loss0 = learner0.loss(p0, Y)
    massed = {"name": "massed_test", "n_sessions": 15, "session_interval": 1.0}
    res = _run_strategy(massed, 3, 10, 0.5, 1, dataset)
    checks.append({
        "name": "loss_baja_tras_entrenar",
        "passed": bool(res["final_loss"] < float(loss0)),
        "detail": f"loss_inicial={float(loss0):.4f}, loss_final={res['final_loss']:.4f}",
    })

    # 6) estrategias son un dict abierto: campos custom no reconocidos no rompen nada
    custom = {
        "name": "estrategia_con_metadata_propia",
        "n_sessions": 4,
        "session_interval": 2.0,
        "concepts_per_session": 2,
        "autor": "usuario",          # campo no reconocido por el motor
        "notas": "cualquier cosa",   # idem
    }
    try:
        _run_strategy(custom, 3, 8, 0.5, 2, dataset)
        custom_ok = True
    except Exception as e:  # pragma: no cover - solo para el detail del check
        custom_ok = False
        custom_err = str(e)
    checks.append({
        "name": "estrategia_con_campos_custom_no_rompe",
        "passed": bool(custom_ok),
        "detail": "" if custom_ok else custom_err,
    })

    # 7) el efecto de espaciado: con el MISMO numero de repasos, espaciarlos
    #    en el tiempo da mayor retencion a un mismo horizonte futuro que
    #    amontonarlos todos casi juntos (cramming) -- este es el resultado
    #    que la capa de repeticion espaciada deberia reproducir por diseno
    def _final_retention_after_reviews(review_times, probe_time):
        sp = SpacedRepetitionLayer(1, base_stability=1.0, stability_growth=1.5)
        for t_rev in review_times:
            sp.review(0, t_rev)
        return float(sp.retention(probe_time)[0])

    probe_time = 30.0
    spaced_times = [0.0, 3.0, 6.0, 9.0, 12.0, 15.0]
    massed_times = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05]
    r_spaced = _final_retention_after_reviews(spaced_times, probe_time)
    r_massed = _final_retention_after_reviews(massed_times, probe_time)
    checks.append({
        "name": "efecto_de_espaciado_mismo_n_repasos_mayor_retencion_futura",
        "passed": bool(r_spaced > r_massed),
        "detail": f"a t={probe_time}: retencion_spaced={r_spaced:.6f}, retencion_massed={r_massed:.2e}",
    })

    all_passed = all(c["passed"] for c in checks)
    return {"checks": checks, "validation_passed": all_passed}


def compute_teaching_strategies_simulator(mode, params=None):
    params = params or {}
    if mode == "simulate":
        return _simulate(params)
    elif mode == "validate":
        return _validate()
    else:
        raise ValueError(f"modo desconocido: {mode} (usar simulate/validate)")


TEACHING_STRATEGIES_SIMULATOR_TOOL_SCHEMA = {
    "name": "teaching_strategies_simulator",
    "description": (
        "Simula un aprendiz (red neuronal de juguete) cuya retencion por "
        "concepto esta modulada por una capa de repeticion espaciada "
        "(curva de olvido tipo Ebbinghaus). Compara estrategias de "
        "ensenanza definidas libremente por el usuario (cronograma de "
        "repasos por sesion), sin un enum fijo de estrategias."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["simulate", "validate"]},
            "params": {
                "type": "object",
                "properties": {
                    "n_concepts": {"type": "integer"},
                    "n_features": {"type": "integer"},
                    "n_hidden": {"type": "integer"},
                    "samples_per_concept": {"type": "integer"},
                    "base_lr": {"type": "number"},
                    "seed": {"type": "integer"},
                    "retention_probe_time": {
                        "type": "number",
                        "description": (
                            "Instante absoluto comun para medir la "
                            "retencion final de TODAS las estrategias "
                            "(comparacion justa). Si se omite, cada "
                            "estrategia se mide al terminar su propio "
                            "cronograma, lo que favorece artificialmente "
                            "al cramming en el ranking de retencion."
                        ),
                    },
                    "strategies": {
                        "type": "array",
                        "description": (
                            "Lista abierta de estrategias. Cada una es un "
                            "objeto con campos libres; los reconocidos son "
                            "name, schedule, n_sessions, session_interval, "
                            "concepts_per_session -- cualquier otro campo "
                            "se ignora sin error."
                        ),
                        "items": {"type": "object"},
                    },
                },
            },
        },
        "required": ["mode"],
    },
}


try:
    from tool_registry import register_tool
    register_tool(
        name="teaching_strategies_simulator",
        schema=TEACHING_STRATEGIES_SIMULATOR_TOOL_SCHEMA,
        handler=lambda args: compute_teaching_strategies_simulator(
            args.get("mode"), args.get("params")
        ),
    )
except ImportError:
    pass
