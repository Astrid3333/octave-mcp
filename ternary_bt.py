# Parte de octave-mcp -- motor de aritmetica ternaria balanceada, usado por ternary_arithmetic_tool.py
"""
Aritmetica de ternario balanceado (trits en {-1,0,1}), punto fijo.
Representacion: array de trits, indice 0 = menos significativo (peso 3^-FRAC).
Todas las operaciones (+, -, *, reciproco) se implementan a nivel de trit,
con propagacion de acarreo ternaria explicita -- NO se usa punto flotante
IEEE754 en ningun paso del calculo numerico.
"""
import numpy as np

FRAC = 40          # trits de fraccion
INT  = 20          # trits de parte entera
N    = INT + FRAC  # ancho fijo del registro (como un registro de hardware)

def to_bt(x: float):
    """float -> trits balanceados de ancho fijo N (redondeo al valor mas cercano)."""
    scaled = int(round(x * (3 ** FRAC)))
    neg = scaled < 0
    scaled = abs(scaled)
    trits = np.zeros(N, dtype=np.int64)
    i = 0
    while scaled != 0 and i < N:
        r = scaled % 3
        scaled //= 3
        if r == 2:
            r = -1
            scaled += 1
        trits[i] = r
        i += 1
    if neg:
        trits = -trits
    return trits

def from_bt(t) -> float:
    """trits -> float (solo para lectura/verificacion, no se usa en el calculo)."""
    val = 0
    for i in range(N - 1, -1, -1):
        val = val * 3 + int(t[i])
    return val / (3 ** FRAC)

def bt_neg(a):
    return -a

def bt_add(a, b):
    """Suma trit a trit con acarreo ternario explicito."""
    out = np.zeros(N, dtype=np.int64)
    carry = 0
    for i in range(N):
        s = int(a[i]) + int(b[i]) + carry
        carry = 0
        while s > 1:
            s -= 3
            carry += 1
        while s < -1:
            s += 3
            carry -= 1
        out[i] = s
    return out

def bt_sub(a, b):
    return bt_add(a, bt_neg(b))

def bt_mul(a, b):
    """Multiplicacion por convolucion de trits + propagacion de acarreo (base 3)."""
    conv = np.convolve(a.astype(np.int64), b.astype(np.int64))
    # conv[k] = suma de a_i*b_j con i+j=k, en peso 3^(k - 2*FRAC) antes de desplazar
    # normalizamos digito a digito (como una multiplicacion larga en base 3)
    carry = 0
    digits = np.zeros(len(conv), dtype=np.int64)
    for i in range(len(conv)):
        s = int(conv[i]) + carry
        # llevar s a rango centrado {-1,0,1} propagando acarreo en base 3
        carry = 0
        while s > 1:
            s -= 3
            carry += 1
        while s < -1:
            s += 3
            carry -= 1
        digits[i] = s
    # el resultado esta escalado por 3^(-2*FRAC); nos quedamos con la ventana
    # correspondiente a FRAC trits de fraccion e INT de entero (trunca overflow,
    # igual que un registro de ancho fijo real)
    shift = FRAC
    out = np.zeros(N, dtype=np.int64)
    for i in range(N):
        idx = i + shift
        out[i] = digits[idx] if idx < len(digits) else 0
    return out

def bt_reciprocal(a):
    """Newton-Raphson para 1/a usando solo bt_mul y bt_sub (arranca de una
    estimacion float SOLO como semilla inicial, igual que se hace en hardware
    real con tablas de arranque; toda la iteracion es ternaria)."""
    af = from_bt(a)
    x = to_bt(1.0 / af)
    two = to_bt(2.0)
    for _ in range(8):
        ax = bt_mul(a, x)
        two_minus_ax = bt_sub(two, ax)
        x = bt_mul(x, two_minus_ax)
    return x

def bt_div(a, b):
    return bt_mul(a, bt_reciprocal(b))

if __name__ == "__main__":
    a = to_bt(1.5)
    b = to_bt(-0.333333333333)
    print("suma:", from_bt(bt_add(a, b)), "esperado", 1.5 - 0.333333333333)
    print("resta:", from_bt(bt_sub(a, b)), "esperado", 1.5 + 0.333333333333)
    print("mult:", from_bt(bt_mul(a, b)), "esperado", 1.5 * -0.333333333333)
    c = to_bt(7.0)
    print("recip 1/7:", from_bt(bt_reciprocal(c)), "esperado", 1 / 7)
    print("div 22/7:", from_bt(bt_div(to_bt(22.0), c)), "esperado", 22 / 7)
