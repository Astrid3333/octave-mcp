"""
glosario_tecnico — glosario técnico-científico multilingüe.

Diseño: cada término se guarda como string COMPLETO por idioma
(mismo patrón que carpentries/glosario), no se compone por columnas
de "adjetivo" + "sustantivo" + regla de orden. Esto evita dos problemas
a la vez:

1. Tokenizador roto en chino/japonés (no hay espacios que cortar,
   porque no se parte nada).
2. Concordancia (género/caso/número) imposible de derivar por regla
   general en alemán/ruso/afrikáans — cada forma flexionada se
   guarda ya resuelta.

Un idioma ausente en un término significa "no verificado todavía".
Nunca se completa por inferencia desde otro idioma.
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
TERMINOS_PATH = BASE_DIR / "terminos.json"
IDIOMAS_PATH = BASE_DIR / "idiomas.json"


def cargar_terminos(path: Path = TERMINOS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["terminos"]


def cargar_idiomas(path: Path = IDIOMAS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["idiomas"]


def termino(slug: str, idioma: str, terminos: dict | None = None) -> str | None:
    """Devuelve la traducción de un término a un idioma, o None si no
    está verificada todavía (nunca inventa ni deriva una)."""
    terminos = terminos or cargar_terminos()
    entrada = terminos.get(slug)
    if entrada is None:
        raise KeyError(f"término no encontrado: {slug!r}")
    valor = entrada.get(idioma)
    if valor is None:
        return None
    return valor["valor"] if isinstance(valor, dict) else valor


def fuente(slug: str, idioma: str, terminos: dict | None = None) -> str | None:
    """Devuelve la fuente citada para una traducción, si la tiene."""
    terminos = terminos or cargar_terminos()
    entrada = terminos.get(slug, {})
    valor = entrada.get(idioma)
    return valor.get("fuente") if isinstance(valor, dict) else None


def agregar_traduccion(
    slug: str,
    idioma: str,
    valor: str,
    fuente: str | None = None,
    path: Path = TERMINOS_PATH,
) -> None:
    """Agrega/actualiza la traducción verificada de un término, con
    fuente opcional para trazabilidad. No hace ninguna validación
    gramatical automática — la verificación de que el valor es
    correcto queda del lado de quien lo escribe."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if slug not in data["terminos"]:
        raise KeyError(f"término no encontrado: {slug!r}")
    data["terminos"][slug][idioma] = (
        {"valor": valor, "fuente": fuente} if fuente else valor
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def reporte_cobertura(
    terminos: dict | None = None, idiomas: dict | None = None
) -> str:
    """Tabla de qué término tiene qué idiomas verificados y cuáles
    faltan. Pensado para correr antes de publicar/exportar, no para
    ocultar los huecos."""
    terminos = terminos or cargar_terminos()
    idiomas = idiomas or cargar_idiomas()
    activos = [
        codigo
        for codigo, meta in idiomas.items()
        if meta.get("estado") != "excluido"
    ]

    lineas = []
    ancho_slug = max(len(s) for s in terminos) + 2
    encabezado = "término".ljust(ancho_slug) + " ".join(
        c.ljust(4) for c in activos
    )
    lineas.append(encabezado)
    lineas.append("-" * len(encabezado))

    for slug, traducciones in terminos.items():
        fila = slug.ljust(ancho_slug)
        for codigo in activos:
            marca = "OK" if traducciones.get(codigo) else "--"
            fila += marca.ljust(5)
        lineas.append(fila)

    faltantes = sum(
        1
        for traducciones in terminos.values()
        for codigo in activos
        if not traducciones.get(codigo)
    )
    lineas.append("")
    lineas.append(
        f"{faltantes} traducciones pendientes de {len(terminos) * len(activos)} casillas totales"
    )
    return "\n".join(lineas)


if __name__ == "__main__":
    print(reporte_cobertura())
