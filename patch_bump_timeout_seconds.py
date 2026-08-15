"""
Sube TIMEOUT_SECONDS en run_all_validations.py. Segunda vez que se pega
al techo (180->300 con 58 tools validate, ahora 300 casi lo revienta con
73 tools en 279.6s). En vez de otro ajuste chico que vuelva a quedar
corto en unas pocas tools mas, se sube con margen generoso.

Uso:
    python3 patch_bump_timeout_seconds.py
"""
import ast
import shutil
from datetime import datetime

PATH = "run_all_validations.py"

OLD = 'TIMEOUT_SECONDS = 300  # subido de 180: con 58 tools validate (vs 53 original) + enzyme_kinetics ~55-60s, el margen viejo quedaba justo'
NEW = 'TIMEOUT_SECONDS = 900  # subido de 300: con 73 tools validate llego a 279.6s (casi al limite). 900 da margen para que la suite siga creciendo sin repetir este ajuste cada pocas tools.'


def main():
    with open(PATH, "r", encoding="utf-8") as f:
        src = f.read()

    backup = f"{PATH}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(PATH, backup)

    count = src.count(OLD)
    assert count == 1, f"se esperaba 1 ocurrencia, se encontraron {count} -- revisar a mano (¿cambio el comentario?)."
    src = src.replace(OLD, NEW, 1)

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)

    ast.parse(src)
    print(f"Patch aplicado OK. Backup: {backup}")


if __name__ == "__main__":
    main()
