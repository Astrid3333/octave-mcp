#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenera skill_content.py a partir de SKILL.md (mismo directorio).

Uso:
    python3 regenerate_skill_content.py

SKILL.md es la fuente de verdad. Este script emite skill_content.py con la
copia embebida en r-string, y FALLA con error claro (exit 1) si el .md
contiene algo que romperia o falsaria el literal o su comprobacion:

- backslash          -> en r-string se interpretaria o duplicaria el valor
- tres comillas dobles seguidas -> cerrarian el literal r-string por medio
- CR (CRLF)          -> check_sync() es binario; el .md debe ser LF

Despues de regenerar, check_sync() debe dar True en el directorio del repo.
Solo stdlib.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MD = HERE / "SKILL.md"
OUT = HERE / "skill_content.py"


def fail(msg):
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main():
    raw = MD.read_bytes()
    if b"\r" in raw:
        fail(
            f"{MD.name} contiene CR (lineas CRLF). Conviertelo a LF antes de "
            "regenerar: check_sync() compara bytes y el r-string solo "
            "representa LF correctamente."
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        fail(f"{MD.name} no es utf-8 valido: {e}")

    if "\\" in text:
        i = text.index("\\")
        fail(
            f"{MD.name} contiene un backslash en la posicion {i} "
            f"(contexto: {text[max(0, i - 30):i + 30]!r}). El literal embebido "
            "es r-string: un backslash futuro del markdown no puede "
            "representarse sin duplicarlo a mano. Elimina ese backslash del "
            ".md (escapalo como texto plano) o cambia el esquema del generador."
        )
    if '"""' in text:
        i = text.index('"""')
        fail(
            f"{MD.name} contiene tres comillas dobles seguidas en la posicion "
            f"{i} (contexto: {text[max(0, i - 30):i + 30]!r}). Cerrarian el "
            "literal r-string por medio. Reformula esa frase del .md (p. ej. "
            "'comillas triple seguidas' sin escribirlas)."
        )

    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        fail(f"{MD.name} no tiene frontmatter (--- ... ---) al principio.")
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    if fm.get("name") != "octave-mcp":
        fail(f"frontmatter name es {fm.get('name')!r}, se esperaba 'octave-mcp'.")
    if not fm.get("description", "").startswith("Use when"):
        fail("frontmatter description vacia o sin el prefijo esperado 'Use when'.")

    out = _TEMPLATE.replace("__MD__", text)
    OUT.write_text(out, encoding="utf-8")
    print(f"regenerado {OUT} ({len(out)} bytes) desde {MD.name}")
    return 0


_TEMPLATE = '''# -*- coding: utf-8 -*-
"""Copia de la skill de opencode ``octave-mcp`` empaquetada como Python, para
que otra IA pueda consumirla/revisarla sin leer el .md del repo.

Uso:
    python3 skill_content.py               # imprime el SKILL.md vigente
    python3 skill_content.py --metadata    # imprime solo nombre/descripcion
    import skill_content as sc; sc.SKILL_MD; sc.check_sync()

Fuente de verdad: SKILL.md (mismo directorio). Al importar, SKILL_MD se lee
de ese archivo si existe; si el .py esta solo (copiado a otra maquina), usa
la copia embebida ``_SKILL_MD_EMBEDDED``, que se regenera desde SKILL.md y
esta en r-string para que ningun backslash futuro del markdown se interprete.
SKILL_NAME/SKILL_DESCRIPTION se derivan del frontmatter de SKILL_MD: no hay
ningun valor duplicado a mano. Solo stdlib.

Nota: SKILL_MD en si nunca esta desincronizado (siempre refleja el disco o,
en su defecto, el embebido); lo que puede envejecer es el fallback
``_SKILL_MD_EMBEDDED``, y eso es lo que vigila check_sync(). Regenerar con
``regenerate_skill_content.py`` (mismo directorio).
"""

import os
import re

SKILL_PATH = "skills/octave-mcp/SKILL.md"

# Copia byte a byte de SKILL.md (ver check_sync()). No editar a mano:
# regenerar con regenerate_skill_content.py.
_SKILL_MD_EMBEDDED = r"""__MD__"""


def _md_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "SKILL.md")


def _read_disk():
    """Contenido del .md vecino como str (bytes exactos, utf-8), o None."""
    path = _md_path()
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8")


SKILL_MD = _read_disk()
if SKILL_MD is None:
    SKILL_MD = _SKILL_MD_EMBEDDED


def _frontmatter(text):
    """Extrae {name, description, ...} del frontmatter de un SKILL.md.

    Limitacion: solo claves de una linea en formato ``clave: valor``; no
    entiende YAML multilineo (``>``/``|``) ni valores entre comillas (se
    los devolveria tal cual). Vale para el frontmatter de este skill; si
    alguna vez crece, parsear con PyYAML en vez de ampliar esto.
    """
    m = re.match(r"^---\\n(.*?)\\n---", text.replace("\\r\\n", "\\n"), re.S)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\\t")):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


_fm = _frontmatter(SKILL_MD)
SKILL_NAME = _fm.get("name", "")
SKILL_DESCRIPTION = _fm.get("description", "")


def check_sync():
    """Comprueba la copia embebida contra el SKILL.md vecino, en binario.

    Returns:
        True: el .md existe y es byte a byte igual a _SKILL_MD_EMBEDDED.
        None: no hay .md al lado del .py (copia suelta; nada que comprobar).

    Raises:
        AssertionError: el .md existe pero difiere de la copia embebida
        (incluye cambios CRLF/LF: se comparan bytes, no texto normalizado).
        En ese caso SKILL_MD sigue leyendo el .md vigente del disco; hay que
        regenerar skill_content.py con regenerate_skill_content.py.
    """
    path = _md_path()
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw != _SKILL_MD_EMBEDDED.encode("utf-8"):
        raise AssertionError(
            "skill_content.py esta desincronizado de SKILL.md "
            "(regenera con regenerate_skill_content.py)"
        )
    return True


def main(argv):
    if "--metadata" in argv:
        print("name:", SKILL_NAME)
        print("description:", SKILL_DESCRIPTION)
        return 0
    print(SKILL_MD, end="")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
'''


if __name__ == "__main__":
    raise SystemExit(main())
