#!/bin/bash
# pre-push hook: corre run_all_validations.py antes de cada push.
# Si alguna tool con modo validate falla, aborta el push.
# Se puede saltar con: SKIP_VALIDATIONS=1 git push

if [ "$SKIP_VALIDATIONS" = "1" ]; then
    echo "pre-push: SKIP_VALIDATIONS=1, saltando run_all_validations.py"
    exit 0
fi

echo "pre-push: corriendo run_all_validations.py (puede tardar ~90s)..."
echo "          (para saltar: SKIP_VALIDATIONS=1 git push)"
echo ""

cd "$(git rev-parse --show-toplevel)" || exit 1
python3 run_all_validations.py

result=$?
if [ $result -ne 0 ]; then
    echo ""
    echo "pre-push: ABORTADO. run_all_validations.py reporto FAILED o ERROR."
    echo "          Revisar arriba. Push cancelado, nada se subio al remoto."
    exit 1
fi

echo ""
echo "pre-push: todas las validaciones OK, continuando con el push."
exit 0
