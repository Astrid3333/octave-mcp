"""
math_humanizer_tool.py

Tool MCP: math_humanizer_tool
Convierte conceptos matemáticos en historias/analogías accesibles, conectando
con la filosofía y la vida cotidiana. Contenido curado (referencia), no cálculo
-- mismo espíritu que math_philosophy_history o ethnomath dentro del ecosistema.

Operaciones soportadas (parámetro `mode`):
  - explain_concept  : analogía cotidiana + conexión filosófica para un concepto matemático
  - list_concepts    : lista los conceptos disponibles
"""

MATH_HUMANIZER_TOOL_SCHEMA = {
    "name": "math_humanizer_tool",
    "description": (
        "Convierte conceptos matemáticos complejos en historias e ideas accesibles, conectando "
        "con la filosofía y la vida cotidiana (analogía cotidiana + conexión filosófica + nota "
        "más profunda para quien quiera seguir tirando del hilo). Contenido de referencia curado, "
        "no un cálculo — pensado para divulgación y enseñanza."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["explain_concept", "list_concepts"]},
            "concept": {"type": "string", "description": "Nombre del concepto (ver list_concepts). explain_concept."},
        },
        "required": ["mode"],
    },
}

_CONCEPTS = {
    "derivada": {
        "everyday_analogy": (
            "Vas manejando y miras el velocímetro: no te dice dónde estás, te dice qué tan rápido "
            "está cambiando tu posición en este instante. La derivada es exactamente eso: la "
            "'velocidad de cambio' de cualquier cosa, en cualquier instante."
        ),
        "philosophical_connection": (
            "Zenón de Elea ya se topaba con esto hace 2500 años en su paradoja de la flecha: si en "
            "cada instante la flecha está quieta en un punto, ¿cómo se mueve? La derivada es, en "
            "cierto sentido, la respuesta matemática que tardó dos mil años en llegar: el movimiento "
            "vive en el límite, no en el instante congelado."
        ),
        "deeper_note": "Formalmente: f'(x) = lim(h->0) [f(x+h)-f(x)]/h — el límite es lo que rescata la idea de 'instante' sin caer en la paradoja.",
    },
    "integral": {
        "everyday_analogy": (
            "Llenás un balde con una manguera de caudal variable. No sabés cuánta agua entró mirando "
            "el caudal en un solo instante — tenés que sumar todo lo que entró a lo largo del tiempo. "
            "La integral es esa suma acumulada."
        ),
        "philosophical_connection": (
            "Es el espejo de la derivada: si la derivada pregunta 'qué tan rápido cambia', la integral "
            "pregunta 'cuánto se acumuló'. El teorema fundamental del cálculo dice que son la misma "
            "pregunta vista al derecho y al revés — una idea que a Newton y Leibniz les tomó años de "
            "trabajo independiente para formalizar, casi en simultáneo, sin saber uno del otro."
        ),
        "deeper_note": "∫f(x)dx es el límite de una suma de rectángulos infinitamente angostos bajo la curva.",
    },
    "entropía": {
        "everyday_analogy": (
            "Un cuarto ordenado tiene una sola forma de estar ordenado, pero mil formas de estar "
            "desordenado. Por eso los cuartos tienden solos al desorden: hay estadísticamente muchas "
            "más maneras de estar desordenado que ordenado."
        ),
        "philosophical_connection": (
            "La entropía conecta la física (segunda ley de la termodinámica: el desorden del universo "
            "solo puede crecer) con la teoría de la información (Shannon): la incertidumbre sobre un "
            "mensaje es matemáticamente la misma fórmula que el desorden de un gas. Es una de las "
            "unificaciones más inesperadas de la ciencia del siglo XX."
        ),
        "deeper_note": "H = -Σ p_i log(p_i). Misma fórmula en termodinámica estadística (Boltzmann) y en teoría de la información (Shannon).",
    },
    "caos": {
        "everyday_analogy": (
            "Dos hojas casi idénticas caen de un árbol, separadas apenas por un milímetro al empezar. "
            "Diez segundos después pueden estar a metros de distancia una de otra, arrastradas por "
            "remolinos de aire minúsculamente distintos. No hay magia ni azar — es física determinista "
            "que amplifica diferencias diminutas exponencialmente."
        ),
        "philosophical_connection": (
            "El caos desafía la idea laplaciana de que conociendo las leyes físicas y las condiciones "
            "iniciales con precisión, se puede predecir el futuro con certeza total. En sistemas "
            "caóticos, ningún instrumento real es lo bastante preciso — la predictibilidad tiene un "
            "horizonte, no importa cuánto mejores tus instrumentos."
        ),
        "deeper_note": "Cuantificado por el exponente de Lyapunov (λ): λ>0 significa que la distancia entre trayectorias vecinas crece como e^(λt).",
    },
    "número primo": {
        "everyday_analogy": (
            "Los números primos son los 'átomos' de la aritmética: todo número entero mayor que 1 se "
            "arma multiplicando primos, igual que toda molécula se arma combinando átomos. Y así como "
            "no hay una fórmula simple para predecir qué elemento vendrá después en la tabla periódica, "
            "tampoco hay una fórmula simple para predecir el próximo primo."
        ),
        "philosophical_connection": (
            "Los primos parecen distribuirse de forma casi aleatoria, y sin embargo obedecen patrones "
            "estadísticos profundos (el teorema de los números primos). Es la tensión central de la "
            "teoría de números: aparente caos individual, orden estadístico colectivo — el mismo tipo "
            "de tensión que aparece en termodinámica o en la mecánica estadística."
        ),
        "deeper_note": "El teorema de los números primos dice que la cantidad de primos menores a N se aproxima a N/ln(N).",
    },
    "infinito": {
        "everyday_analogy": (
            "Un hotel con infinitas habitaciones, todas ocupadas, puede igual alojar a un huésped más: "
            "basta con correr a cada huésped de la habitación n a la n+1 (la paradoja del Hotel de "
            "Hilbert). Con el infinito, 'lleno' no significa lo mismo que en la vida cotidiana."
        ),
        "philosophical_connection": (
            "Cantor demostró que hay infinitos de distinto 'tamaño' — los números reales son un infinito "
            "estrictamente más grande que los números naturales, aunque ambos son infinitos. Esto rompió "
            "siglos de intuición filosófica (desde Aristóteles) de que el infinito era una sola idea "
            "indivisible, y le costó a Cantor un rechazo académico feroz en su época."
        ),
        "deeper_note": "|ℕ| = ℵ₀ (infinito numerable); |ℝ| = 2^ℵ₀ (infinito no numerable), demostrado por el argumento diagonal de Cantor.",
    },
    "probabilidad": {
        "everyday_analogy": (
            "Cuando decís 'hay 30% de probabilidad de lluvia', no estás describiendo el clima de hoy "
            "(que va a llover o no llover, sin términos medios) — estás describiendo cuántas veces, de "
            "cien días con condiciones parecidas a las de hoy, terminó lloviendo."
        ),
        "philosophical_connection": (
            "La probabilidad tiene dos interpretaciones filosóficas en tensión: la frecuentista (es un "
            "límite de frecuencias observadas en repeticiones) y la bayesiana (es un grado de creencia "
            "personal, actualizable con evidencia). No es solo un debate académico — cambia cómo se "
            "interpretan resultados científicos y cómo se toman decisiones bajo incertidumbre."
        ),
        "deeper_note": "El teorema de Bayes formaliza la actualización bayesiana: P(H|E) = P(E|H)P(H) / P(E).",
    },
    "vector": {
        "everyday_analogy": (
            "Decirle a alguien 'caminá 5' no le dice nada útil — necesita saber para dónde. Un vector "
            "es justamente eso: una cantidad que no está completa sin una dirección, a diferencia de "
            "cosas como la temperatura o el precio, que son solo un número."
        ),
        "philosophical_connection": (
            "La idea de que algunas cantidades del mundo necesitan más que un número para describirse "
            "completamente fue un salto conceptual — separar 'cuánto' de 'hacia dónde' permitió describir "
            "fuerzas, velocidades y campos de forma unificada, y sentó las bases de gran parte de la "
            "física moderna."
        ),
        "deeper_note": "Un vector en ℝⁿ es un elemento de un espacio vectorial: magnitud + dirección, sumable y escalable con reglas precisas.",
    },
    "matriz": {
        "everyday_analogy": (
            "Una matriz es como una máquina que toma una lista de números y la transforma en otra lista "
            "de forma predecible y repetible — como una receta que siempre estira, rota o aplasta el "
            "espacio de la misma manera, sin importar qué ingrediente (vector) le metas."
        ),
        "philosophical_connection": (
            "Detrás de la notación tediosa hay una idea elegante: cualquier transformación lineal del "
            "espacio (rotar, escalar, reflejar, proyectar) se puede codificar en una tabla de números. "
            "Es la base de que las computadoras puedan 'entender' geometría, gráficos 3D, e incluso "
            "cómo Google ordena resultados de búsqueda (PageRank es álgebra de matrices)."
        ),
        "deeper_note": "Los autovalores/autovectores de una matriz revelan las direcciones que la transformación deja invariantes salvo escala.",
    },
    "logaritmo": {
        "everyday_analogy": (
            "La escala Richter de terremotos, los decibeles del sonido, el pH de una solución: todos "
            "usan logaritmos porque nuestros sentidos perciben el mundo de forma logarítmica, no lineal. "
            "Un terremoto de magnitud 6 no es 'un poco más fuerte' que uno de magnitud 5 — es 10 veces "
            "más fuerte."
        ),
        "philosophical_connection": (
            "El logaritmo convierte multiplicaciones en sumas — una idea que antes de las calculadoras "
            "electrónicas ahorraba semanas de cálculo a astrónomos y navegantes (de ahí las reglas de "
            "cálculo). Es un recordatorio de que gran parte de las matemáticas nacieron de la necesidad "
            "práctica de calcular más rápido, no de la abstracción pura."
        ),
        "deeper_note": "log_b(x) es el exponente al que hay que elevar la base b para obtener x. log(a·b) = log(a) + log(b).",
    },
    "fractal": {
        "everyday_analogy": (
            "Un helecho: cada hoja chica se parece a la hoja grande de la que cuelga, y cada hojita de "
            "esa hoja se parece a su vez a la hoja chica. Un fractal es una forma que repite su propio "
            "patrón a cualquier escala en la que lo mires."
        ),
        "philosophical_connection": (
            "Antes de Mandelbrot, la geometría clásica (Euclides) describía formas 'suaves': líneas, "
            "círculos, esferas. Pero la costa de un país, una montaña, un pulmón — la naturaleza real "
            "es rugosa y autosimilar, no suave. Los fractales fueron el primer lenguaje matemático "
            "capaz de describir esa rugosidad con precisión."
        ),
        "deeper_note": "La dimensión fractal (ej. por box-counting) puede dar un número no entero — ni 1D ni 2D, algo intermedio que cuantifica la rugosidad.",
    },
    "límite": {
        "everyday_analogy": (
            "Te acercás a una pared caminando, cada vez dando pasos más chicos: la mitad de la distancia "
            "que te queda, y después la mitad de eso, y así. Nunca 'llegás' con un paso, pero tu "
            "distancia a la pared se acerca a cero tanto como quieras. El límite formaliza esa idea de "
            "'acercarse tanto como se quiera' sin necesariamente tocar."
        ),
        "philosophical_connection": (
            "Es la herramienta que finalmente resolvió las paradojas de Zenón, dos milenios después de "
            "planteadas: se puede hablar rigurosamente de un proceso infinito (infinitos pasos, cada vez "
            "más chicos) sin caer en contradicción, siempre que se defina con precisión qué significa "
            "'acercarse'."
        ),
        "deeper_note": "lim(x->a) f(x) = L significa: para todo ε>0 existe δ>0 tal que |x-a|<δ implica |f(x)-L|<ε (definición ε-δ de Cauchy/Weierstrass).",
    },
}


def _explain_concept(concept):
    key = concept.strip().lower()
    if key not in _CONCEPTS:
        raise ValueError(
            f"Concepto no disponible: '{concept}'. Usar list_concepts para ver las opciones."
        )
    data = _CONCEPTS[key]
    return {
        "mode": "explain_concept",
        "concept": key,
        "everyday_analogy": data["everyday_analogy"],
        "philosophical_connection": data["philosophical_connection"],
        "deeper_note": data["deeper_note"],
    }


def _list_concepts():
    return {"mode": "list_concepts", "concepts": sorted(_CONCEPTS.keys())}


def compute_math_humanizer(mode, **params):
    """Entry point del tool. Despacha según `mode`. Retorna un dict serializable a JSON."""
    if mode == "explain_concept":
        return _explain_concept(params["concept"])
    if mode == "list_concepts":
        return _list_concepts()

    raise ValueError(f"mode no soportado: {mode}. Usar: explain_concept | list_concepts")
