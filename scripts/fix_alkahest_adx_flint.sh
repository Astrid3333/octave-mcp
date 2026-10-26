#!/usr/bin/env bash
# fix_alkahest_adx_flint.sh
#
# Fix del SIGILL de alkahest en CPUs sin ADX (Haswell y anteriores).
#
# Causa: el wheel `alkahest-3.12.0-*manylinux_2_28_x86_64.whl` vendoriza
# `alkahest.libs/libflint-*.so.24` compilado con instrucciones ADX
# (adcx/adox, Broadwell+). En una CPU sin ADX (p. ej. i7-4785T Haswell)
# factorint/nextprime/totient grandes abortan el proceso con SIGILL
# dentro del kernel Rust (panic con abort, no capturable con try/except).
#
# Fix: reconstruir MPFR 4.2.2 + FLINT 3.6.0 con baseline x86-64
# (-march=x86-64 -mtune=generic, sin ADX) e instalarlos en un prefijo
# durable, y reemplazar la libflint empaquetada conservando su nombre
# (el loader la pide por NEEDED exacto). El original se respalda en
# ~/.cache/alkahest-adx-fix/ (FUERA de alkahest.libs, para que nunca se
# cargue). El check `nt_libflint_no_adx` de mode=validate de
# alkahest_cas_tool.py falla de forma visible si un `pip install
# --force-reinstall alkahest` reintroduce el wheel con ADX.
#
# Uso:
#   bash scripts/fix_alkahest_adx_flint.sh            # build + swap
#   bash scripts/fix_alkahest_adx_flint.sh --check    # solo verificar ADX
#
# Opciones:
#   --site DIR   site-packages con alkahest.libs (default: .venv del repo)
#   --check      no construye: solo cuenta patrones ADX y sale con
#                codigo 0 (sin ADX) o 1 (ADX presente)
#   --force      reconstruye aunque el prefijo ya tenga libflint instalada
#
# Tras el swap correr:  .venv/bin/python -c "import alkahest_cas_tool as m; \
#                        print(m._validate()['validation_passed'])"
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FLINT_VER="3.6.0"
MPFR_VER="4.2.2"
PREFIX="${PREFIX:-$HOME/.local/opt/alkahest-flint-baseline}"
CACHE="${CACHE:-$HOME/.cache/alkahest-adx-fix}"
FLAGS="-O2 -march=x86-64 -mtune=generic -fPIC"
JOBS="$(nproc 2>/dev/null || echo 4)"
SITE=""
CHECK_ONLY=0
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --site) SITE="$2"; shift 2 ;;
    --check) CHECK_ONLY=1; shift ;;
    --force) FORCE=1; shift ;;
    *) echo "argumento desconocido: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$SITE" ]]; then
  SITE="$(ls -d "$REPO"/.venv/lib/python3*/site-packages 2>/dev/null | head -1 || true)"
fi
if [[ -z "$SITE" || ! -d "$SITE/alkahest.libs" ]]; then
  echo "no encuentro alkahest.libs (pasa --site DIR): SITE=$SITE" >&2
  exit 2
fi

TARGET="$(ls "$SITE"/alkahest.libs/libflint-*.so* 2>/dev/null | head -1 || true)"
if [[ -z "$TARGET" ]]; then
  echo "no hay libflint-* empaquetada en $SITE/alkahest.libs" >&2
  exit 2
fi

adx_count() {
  objdump -d "$1" 2>/dev/null | grep -cE 'adcx|adox' || true
}

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  n="$(adx_count "$TARGET")"
  echo "lib: $TARGET"
  echo "patrones adcx/adox en segmentos ejecutables: $n"
  if [[ "$n" -ge 100 ]]; then
    echo "RESULTADO: ADX presente (wheel original = 2626) -> SIGILL en Haswell" >&2
    exit 1
  fi
  echo "RESULTADO: sin ADX (fix baseline = 0)"
  exit 0
fi

mkdir -p "$CACHE" "$PREFIX"
cd "$CACHE"

fetch() {
  local url="$1" out="$2"
  if [[ ! -f "$out" ]]; then
    echo "descargando $url"
    curl -sSL --retry 3 -o "$out" "$url"
  fi
}

if [[ "$FORCE" -eq 1 || ! -f "$PREFIX/lib/libflint.so.24" ]]; then
  fetch "https://ftp.gnu.org/gnu/mpfr/mpfr-${MPFR_VER}.tar.gz" "mpfr-${MPFR_VER}.tar.gz"
  fetch "https://github.com/flintlib/flint/releases/download/v${FLINT_VER}/flint-${FLINT_VER}.tar.gz" \
        "flint-${FLINT_VER}.tar.gz"

  echo "== MPFR ${MPFR_VER} (baseline, sin ADX)"
  rm -rf "mpfr-${MPFR_VER}"
  tar xzf "mpfr-${MPFR_VER}.tar.gz"
  (
    cd "mpfr-${MPFR_VER}"
    ./configure --prefix="$PREFIX" CFLAGS="$FLAGS"
    make -j"$JOBS"
    make install
  )

  echo "== FLINT ${FLINT_VER} (baseline, sin ADX)"
  rm -rf "flint-${FLINT_VER}"
  tar xzf "flint-${FLINT_VER}.tar.gz"
  (
    cd "flint-${FLINT_VER}"
    ./configure --prefix="$PREFIX" --with-gmp=/usr --with-mpfr="$PREFIX" CFLAGS="$FLAGS"
    make -j"$JOBS"
    make install
  )
else
  echo "prefijo ya construido: $PREFIX (usa --force para reconstruir)"
fi

NEW="$PREFIX/lib/libflint.so.24"
if [[ ! -f "$NEW" ]]; then
  echo "build incompleto: falta $NEW" >&2
  exit 1
fi

n="$(adx_count "$NEW")"
if [[ "$n" -ge 100 ]]; then
  echo "el build nuevo aun tiene ADX (n=$n): revisa CFLAGS/march" >&2
  exit 1
fi

BASE="$(basename "$TARGET")"
if [[ ! -f "$CACHE/${BASE}.orig-adx" ]]; then
  echo "respaldo del original -> $CACHE/${BASE}.orig-adx"
  cp -p "$TARGET" "$CACHE/${BASE}.orig-adx"
fi

echo "swap: $TARGET"
cp "$NEW" "$TARGET"
echo "ADX tras swap: $(adx_count "$TARGET") (esperado 0)"
echo "RUNPATH: $(objdump -p "$TARGET" | awk '/RUNPATH|RPATH/{print $2}')"

echo
echo "listo. verificar con:"
echo "  .venv/bin/python -c \"import alkahest_cas_tool as m; v=m._validate(); print(v['validation_passed'])\""
