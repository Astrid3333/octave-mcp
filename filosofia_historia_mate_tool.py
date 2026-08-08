"""
filosofia_historia_mate_tool.py

Presets de referencia sobre filosofia e historia de la matematica.
A diferencia de ancestral_octave (que corre .m reales en Octave), esto es
contenido curado -- no hay computo numerico que validar, asi que el
criterio de calidad es otro: marcar explicitamente que esta establecido
academicamente vs. que es disputado vs. que es reconstruccion moderna.

Mismo espiritu que ya se aplico con el aviso de disputa de la yupana:
no ocultar la incertidumbre, dejarla visible en el dato.

Conecta directo con las herramientas ya construidas:
- sutras_vedicos       -> vedic_multiply (ethnomath)
- yupana_disputa       -> yupana (calculadora HTML) / grid Fibonacci
- quipu_khipu          -> contraparte "no disputada" de la yupana
- etnomatematica_campo -> el marco general bajo el que se armaron
                          suanpan, soroban, abaco romano, yupana, ifa,
                          etak, madhava, sutras vedicos

Uso (mismo patron que ancestral_octave):
    compute_math_philosophy_history()                  -> lista topics
    compute_math_philosophy_history("sutras_vedicos")   -> preset puntual
"""

import json

PRESETS = {

    "sutras_vedicos": {
        "titulo": "Los 'sutras vedicos' de Bharati Krishna Tirthaji",
        "periodo_o_contexto": "Publicado 1965 (compuesto ca. 1911-1918 segun el propio autor); atribuido a la Antiguedad vedica",
        "resumen": (
            "Swami Bharati Krishna Tirthaji (1884-1960), Shankaracharya de Puri, publico "
            "'Vedic Mathematics' de forma postuma, presentando 16 sutras (aforismos) y 13 "
            "sub-sutras -- entre ellos 'Urdhva-Tiryagbhyam' ('verticalmente y en cruz', la base "
            "del vedic_multiply ya implementado) -- que afirmo haber reconstruido a partir de un "
            "apendice perdido del Atharvaveda (los 'Ganita Sutras'). Ningun sanscritista ni "
            "historiador de la matematica ha podido localizar ese apendice en ningun corpus "
            "vedico conocido."
        ),
        "estado_academico": (
            "Reconstruccion/invencion moderna. Los algoritmos en si son correctos y en varios "
            "casos genuinamente ingeniosos como atajos de calculo mental -- eso no esta en "
            "duda. Lo que esta descartado por consenso academico (ver S.G. Dani, matematico "
            "del TIFR, quien escribio la critica de referencia) es el origen vedico: no hay "
            "base textual verificada, y el propio termino 'sutra' se usa aqui en un sentido "
            "libre, no en el sentido tecnico-gramatical que tiene en los textos vedicos reales."
        ),
        "por_que_importa": (
            "Es un caso de manual de 'invencion de tradicion' (concepto de Hobsbawm & Ranger) "
            "aplicado a la matematica: una tecnica moderna, legitima como matematica, se viste "
            "de aforismo sanscrito y se le atribuye antiguedad para darle autoridad cultural. "
            "En India es ademas un tema politicamente cargado -- promovido en curricula con "
            "agenda nacionalista, resistido por historiadores de la ciencia."
        ),
        "conexion_herramientas": ["vedic_multiply (ethnomath)"],
        "fuentes_sugeridas": [
            "S.G. Dani, 'Myth and reality: On 'Vedic mathematics'' (Frontline, 1993, y version ampliada posterior)",
            "Bharati Krishna Tirthaji, 'Vedic Mathematics' (Motilal Banarsidass, 1965) -- la fuente primaria en disputa"
        ]
    },

    "yupana_disputa": {
        "titulo": "La yupana: tablero de calculo andino y la hipotesis Fibonacci",
        "periodo_o_contexto": "Objetos arqueologicos incaicos y preincaicos; hipotesis moderna publicada ca. 2001",
        "resumen": (
            "La yupana es una bandeja de madera o piedra con compartimentos/pozos, hallada en "
            "varios sitios incaicos. Nicolino De Pasquale (ingeniero italiano, no arqueologo) "
            "propuso que el tamano de los pozos sigue una progresion tipo Fibonacci (1,1,2,3,5) "
            "por fila, combinada con potencias de diez por columna, lo que permitiria no solo "
            "contar sino multiplicar y dividir en base a ese esquema."
        ),
        "estado_academico": (
            "Disputado, sin evidencia textual ni etnografica que confirme ese esquema especifico "
            "como el uso real. Hipotesis alternativas serias: tablero de conteo simple (los pozos "
            "como casilleros, sin proporcion fija), tablero de juego, o recipiente ceremonial de "
            "ofrendas. A diferencia del quipu (ver quipu_khipu), no hay cronica colonial que "
            "describa el uso preciso de la yupana con el detalle suficiente para zanjar la duda."
        ),
        "por_que_importa": (
            "Buen contraste metodologico con sutras_vedicos: aca no hay ni siquiera alguien "
            "afirmando falsamente un origen antiguo verificado -- el objeto antiguo es real, lo "
            "disputado es la interpretacion funcional que se le da hoy."
        ),
        "conexion_herramientas": ["calculadora HTML yupana (grilla De Pasquale, con aviso de disputa visible)"],
        "fuentes_sugeridas": [
            "Nicolino De Pasquale, articulos en revistas de divulgacion (ca. 2001) -- fuente de la hipotesis",
            "Marcia Ascher & Robert Ascher, 'Mathematics of the Incas: Code of the Quipu' -- contexto comparativo con el quipu"
        ]
    },

    "quipu_khipu": {
        "titulo": "El quipu (khipu): el registro incaico que si esta bien documentado",
        "periodo_o_contexto": "Imperio incaico y culturas andinas anteriores; descifrado moderno desde 1912",
        "resumen": (
            "Sistema de cuerdas anudadas usado para contabilidad y registro administrativo "
            "incaico. Leland Locke establecio en 1912 que los nudos codifican numeros en base "
            "10 de forma posicional segun tipo de nudo y posicion en la cuerda -- esto si esta "
            "solidamente establecido, a diferencia de la yupana."
        ),
        "estado_academico": (
            "La codificacion numerica: establecida. Lo que sigue abierto (Gary Urton y el Khipu "
            "Database Project, Harvard) es si algunos quipus codifican ademas informacion "
            "narrativa o logografica -- no solo numeros -- a traves del color de la fibra, "
            "direccion del hilado y forma de union de las cuerdas. Esa capa narrativa sigue sin "
            "descifrarse de forma concluyente."
        ),
        "por_que_importa": (
            "Sirve como control de calidad para yupana_disputa: mismo contexto cultural andino, "
            "pero aca la funcion basica del dispositivo no esta en duda. Util para no tratar "
            "'incaico' como sinonimo de 'incierto' -- la incertidumbre es especifica de cada "
            "objeto, no del contexto cultural en general."
        ),
        "conexion_herramientas": ["contraparte conceptual de la calculadora yupana ya construida"],
        "fuentes_sugeridas": [
            "Gary Urton, 'Signs of the Inca Khipu: Binary Coding in the Andean Knotted-String Records' (2003)",
            "L. Leland Locke, 'The Ancient Quipu, a Peruvian Counting Device' (1912) -- el desciframiento original"
        ]
    },

    "cero_historia": {
        "titulo": "Las invenciones independientes del cero",
        "periodo_o_contexto": "Babilonia (ca. siglo III a.C.), Mesoamerica (a mas tardar siglo IV d.C.), India (siglo VII d.C.)",
        "resumen": (
            "El cero se inventa al menos tres veces de forma independiente. Babilonia usa un "
            "simbolo posicional para 'posicion vacia' en su sistema sexagesimal (periodo "
            "seleucida) pero nunca opera aritmeticamente con el. Los mayas tienen un glifo "
            "('concha') para el cero en su Cuenta Larga, atestiguado con certeza hacia el siglo "
            "IV d.C. En India, Brahmagupta formula en el Brahmasphutasiddhanta (628 d.C.) las "
            "primeras reglas aritmeticas explicitas para el cero como numero -- incluida la "
            "division por cero, que deja sin resolver correctamente."
        ),
        "estado_academico": (
            "Establecido en sus lineas generales; el debate academico activo es sobre fechas "
            "precisas de primeras inscripciones (ej. Gwalior 876 d.C. como primer cero indio "
            "inequivoco en piedra vs. testimonios textuales anteriores) y sobre el grado de "
            "contacto/influencia entre tradiciones."
        ),
        "por_que_importa": (
            "El cero babilonico y el maya son placeholder (notacion posicional); el cero indio "
            "de Brahmagupta es el salto conceptual real -- tratarlo como numero con el que se "
            "opera. La transmision India -> mundo arabe (Al-Juarismi, siglo IX) -> Europa "
            "(Fibonacci, Liber Abaci, 1202) es la ruta que termina en el cero que usamos hoy."
        ),
        "conexion_herramientas": [],
        "fuentes_sugeridas": [
            "Robert Kaplan, 'The Nothing That Is: A Natural History of Zero' (2000)",
            "Georges Ifrah, 'The Universal History of Numbers' (2000)"
        ]
    },

    "crisis_fundamentos": {
        "titulo": "La crisis de fundamentos: Russell, Hilbert, Godel",
        "periodo_o_contexto": "1901-1931",
        "resumen": (
            "1901: la paradoja de Russell (el conjunto de todos los conjuntos que no se "
            "contienen a si mismos) rompe la teoria de conjuntos ingenua de Frege/Cantor. "
            "Respuesta: axiomatizacion (Zermelo-Fraenkel) y teoria de tipos (Russell & "
            "Whitehead, Principia Mathematica). Hilbert propone en los anos 1920 un programa "
            "para formalizar toda la matematica y probar su consistencia con metodos "
            "finitistas. En 1931, Godel publica sus teoremas de incompletitud: todo sistema "
            "formal consistente lo bastante potente como para codificar la aritmetica contiene "
            "enunciados verdaderos que no puede demostrar, y no puede demostrar su propia "
            "consistencia desde adentro."
        ),
        "estado_academico": (
            "Establecido y sin controversia matematica seria desde hace decadas. Lo que sigue "
            "abierto es filosofico/practico: que axiomas adicionales adoptar mas alla de ZFC "
            "(axiomas de cardinales grandes, etc.), dado que la Hipotesis del Continuo se probo "
            "independiente de ZFC (Godel 1940 + Cohen 1963)."
        ),
        "por_que_importa": (
            "Godel no arruina la matematica ni la vuelve 'poco confiable' para el uso practico "
            "-- acota que hay que elegir: ningun sistema formal puede ser a la vez completo, "
            "consistente y capaz de probarse consistente a si mismo."
        ),
        "conexion_herramientas": [],
        "fuentes_sugeridas": [
            "Ernest Nagel & James R. Newman, 'Godel's Proof' (1958) -- la exposicion clasica accesible",
            "Morris Kline, 'Mathematics: The Loss of Certainty' (1980)"
        ]
    },

    "escuelas_filosoficas": {
        "titulo": "Escuelas de filosofia de la matematica: existe o se inventa?",
        "periodo_o_contexto": "Debate activo desde fines del siglo XIX, sin resolucion",
        "resumen": (
            "Platonismo: los objetos matematicos existen independientemente de la mente, se "
            "descubren (Godel mismo era platonista). Logicismo: la matematica es reducible a "
            "logica pura (Frege, Russell) -- debilitado por la paradoja de Russell y por Godel. "
            "Formalismo: la matematica es manipulacion de simbolos segun reglas, sin necesidad "
            "de 'significado' externo (Hilbert). Intuicionismo: la matematica es una "
            "construccion mental, rechaza el principio del tercero excluido para conjuntos "
            "infinitos y las pruebas de existencia no constructivas (Brouwer). Constructivismo: "
            "familia mas amplia que exige construccion explicita para cualquier afirmacion de "
            "existencia."
        ),
        "estado_academico": (
            "Ninguna escuela 'gano' -- es un desacuerdo filosofico vigente, no una cuestion "
            "matematica resuelta. La practica matematica cotidiana funciona en gran medida con "
            "supuestos platonistas/formalistas implicitos sin que la mayoria de matematicos "
            "tome partido de forma explicita."
        ),
        "por_que_importa": (
            "Da marco para leer discusiones como sutras_vedicos o etnomatematica_campo: si uno "
            "es formalista puro, 'de donde viene' un algoritmo importa menos que si funciona; "
            "si uno le da peso al contexto cultural/historico, la procedencia si es parte de lo "
            "que se esta evaluando."
        ),
        "conexion_herramientas": [],
        "fuentes_sugeridas": [
            "Paul Benacerraf & Hilary Putnam (eds.), 'Philosophy of Mathematics: Selected Readings' (1983)"
        ]
    },

    "etnomatematica_campo": {
        "titulo": "Etnomatematica como campo academico",
        "periodo_o_contexto": "Fundado/formalizado por Ubiratan D'Ambrosio, decadas 1970-1980",
        "resumen": (
            "Ubiratan D'Ambrosio (matematico brasileno) acuna y formaliza el termino "
            "'etnomatematica' a mediados de los 1980, proponiendola como el estudio de las "
            "practicas e ideas matematicas incorporadas en las practicas cotidianas de grupos "
            "culturales -- no solo sistemas numericos 'exoticos' no occidentales, sino tambien "
            "practicas de grupos profesionales (carpinteros, tejedores, navegantes)."
        ),
        "estado_academico": (
            "Campo academico establecido, con debate interno activo: el riesgo de relativismo "
            "(tratar cualquier practica cultural como 'igualmente matematica' sin criterio) "
            "versus el riesgo de erasure (tratar solo la matematica formal occidental como la "
            "'matematica real' y todo lo demas como folklore). No hay consenso cerrado sobre "
            "donde trazar esa linea."
        ),
        "por_que_importa": (
            "Es literalmente el marco bajo el que se armaron suanpan, soroban, abaco romano, "
            "yupana, ifa, etak y madhava -- y el campo mismo exige (por su propio debate "
            "interno) ser explicito sobre que es practica historica verificada y que es "
            "reconstruccion moderna razonable. Es la razon de ser de sutras_vedicos y "
            "yupana_disputa como presets separados en vez de presentarlo todo con el mismo "
            "grado de certeza."
        ),
        "conexion_herramientas": [
            "suanpan", "soroban", "abaco romano", "yupana", "ifa_cast_random",
            "etak_deadreckoning", "madhava_pi_series", "vedic_multiply"
        ],
        "fuentes_sugeridas": [
            "Ubiratan D'Ambrosio, 'Ethnomathematics: Link between Traditions and Modernity' (2001)"
        ]
    },

    "infinito_historia": {
        "titulo": "El infinito: de la incomodidad griega a Cantor",
        "periodo_o_contexto": "Zenon (siglo V a.C.) a Cantor (1870s-1880s)",
        "resumen": (
            "Los paradojas de Zenon (Aquiles y la tortuga, la dicotomia) expresan una "
            "incomodidad griega antigua con el infinito actual -- Aristoteles solo acepta "
            "infinito 'potencial', nunca 'actual', y esa postura domina durante siglos. Cantor "
            "rompe con eso: desarrolla una teoria rigurosa de conjuntos infinitos actuales, "
            "muestra que hay distintos tamanos de infinito (cardinalidad), y con el argumento "
            "diagonal prueba que los numeros reales son no numerables -- estrictamente 'mas "
            "infinitos' que los naturales."
        ),
        "estado_academico": (
            "La matematica de Cantor esta completamente establecida y es fundamento de la "
            "matematica moderna via ZFC. Historicamente notable: la resistencia que enfrento "
            "fue feroz -- Kronecker ('Dios hizo los enteros, todo lo demas es obra del hombre') "
            "se opuso con dureza personal, y esa oposicion probablemente perjudico la carrera "
            "academica de Cantor; Poincare llego a llamar a la teoria de conjuntos 'una "
            "enfermedad'."
        ),
        "por_que_importa": (
            "Buen ejemplo de que 'establecido academicamente hoy' no significa 'aceptado sin "
            "conflicto en su momento' -- utilizable como contraste con crisis_fundamentos, que "
            "es la generacion siguiente de la misma discusion sobre que fundamentos sostienen "
            "la matematica."
        ),
        "conexion_herramientas": [],
        "fuentes_sugeridas": [
            "Joseph Dauben, 'Georg Cantor: His Mathematics and Philosophy of the Infinite' (1979)"
        ]
    },

    "numerales_levante_antiguo": {
        "titulo": "Numerales en el Levante antiguo: Israel/Juda, cananeos, filisteos",
        "periodo_o_contexto": "Edad del Hierro (ca. 1000-586 a.C.) para los ostraca; periodo helenistico (siglo II-I a.C.) para el numeral alfabetico hebreo",
        "resumen": (
            "En los ostraca administrativos israelitas/judaitas (Samaria, Arad, Laquis) los "
            "numeros no se escriben con letras del alefato hebreo sino con numerales hieraticos "
            "egipcios adaptados -- signos tomados del hieratico de Egipto, usados para anotar "
            "cantidades de vino, aceite y grano en registros de intendencia. El sistema numeral "
            "alfabetico hebreo (alef=1, yod=10, qof=100) que suele asociarse a 'los hebreos' es "
            "en realidad mucho mas tardio: primera evidencia solida en monedas asmoneas "
            "(siglo II-I a.C.), en paralelo a la misma practica que adoptan el griego "
            "(isopsefia) y luego el arameo. El Levante en general comparte ademas una "
            "convencion numeral aditiva de trazos verticales (uno para '1', ligaduras para "
            "'10'), emparentada con los jeroglificos numerales egipcios, usada en fenicio, "
            "arameo y nabateo -- Israel/Juda formaban parte de esa orbita, no eran un sistema "
            "aislado."
        ),
        "estado_academico": (
            "Los numerales hieraticos en ostraca estan bien establecidos (excavaciones de "
            "Aharoni en Arad, recogidos en el Handbook of Ancient Hebrew Inscriptions de "
            "Ahituv). El numeral alfabetico hebreo como sistema tardio-helenistico tambien esta "
            "establecido -- el error comun es proyectarlo hacia atras, como si hubiera existido "
            "en el periodo de los reinos. El caso filisteo es evidencia fragmentaria: hay "
            "algunos signos tempranos en Ecrón y Ascalón posiblemente emparentados con "
            "escrituras egeas/chipro-minoicas sin descifrar, pero no hay un sistema numeral "
            "filisteo propio bien documentado -- es insuficiencia de evidencia, no ausencia "
            "confirmada."
        ),
        "por_que_importa": (
            "Buen caso para etnomatematica_campo: separa 'sistema de escritura' de 'sistema "
            "para contar' -- un pueblo puede escribir en su propia lengua y a la vez contar con "
            "una convencion numerica prestada de otra cultura, sin que eso sea raro o "
            "excepcional. Tambien es un recordatorio metodologico util junto a "
            "sutras_vedicos/yupana_disputa: la ausencia de evidencia (filisteos) no es lo mismo "
            "que evidencia de ausencia, y conviene no tratarlas igual."
        ),
        "conexion_herramientas": ["etnomatematica_campo"],
        "fuentes_sugeridas": [
            "Shmuel Ahituv, 'Handbook of Ancient Hebrew Inscriptions' (2008)",
            "Yohanan Aharoni, informes de excavacion de Arad (ostraca)",
            "Denise Schmandt-Besserat, 'How Writing Came About' (1996) -- contexto de las fichas/calculi del Cercano Oriente en general"
        ]
    },

}


def compute_math_philosophy_history(topic: str = "", params: dict = None) -> str:
    """
    Punto de entrada, mismo patron que compute_ancestral_octave.

    topic="" -> devuelve la lista de topics disponibles.
    topic=<uno de PRESETS> -> devuelve el preset completo.
    topic invalido -> error con sugerencias, no adivina.
    """
    if not topic:
        return json.dumps({
            "topics_disponibles": list(PRESETS.keys()),
            "uso": "llamar de nuevo con topic=<uno de los anteriores>",
            "nota": (
                "Cada preset trae 'estado_academico' explicito: establecido, "
                "disputado, o reconstruccion moderna. No se presenta todo con "
                "el mismo nivel de certeza."
            )
        }, ensure_ascii=False, indent=2)

    if topic not in PRESETS:
        return json.dumps({
            "error": f"topic '{topic}' no reconocido",
            "topics_disponibles": list(PRESETS.keys())
        }, ensure_ascii=False, indent=2)

    return json.dumps(PRESETS[topic], ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # smoke test local, sin MCP ni Octave de por medio
    print(compute_math_philosophy_history())
    print(compute_math_philosophy_history("sutras_vedicos"))
    print(compute_math_philosophy_history("topic_que_no_existe"))
