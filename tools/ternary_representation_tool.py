"""
ternary_representation_tool.py
Aritmetica en base 3, ternario balanceado (digitos -1,0,1) y ternario
estandar (digitos 0,1,2). El ternario balanceado usa el algoritmo real
de suma con acarreo digito a digito (el mismo principio que la
computadora sovietica Setun, 1958) y multiplicacion tipo "shift-add"
construida sobre esa suma -- no es una envoltura de aritmetica decimal
con conversion cosmetica al final: la suma/resta/multiplicacion se
calculan digito a digito en base 3 y el resultado decimal se deriva de
ahi (validate cruza ese resultado contra a+b/a-b/a*b en Python como
chequeo de correccion, no como el metodo de calculo).

Convencion de digitos:
  - Balanceado: lista LSD-primero, cada digito en {-1,0,1}. Representacion
    en string MSD-primero usa '1','0','T' (T = -1), ej. 5 = "1TT".
  - Estandar: lista LSD-primero, cada digito en {0,1,2}, mas un signo
    aparte (no hay digito de signo en la representacion misma).

Modes:
  - to_balanced: entero -> digitos + string en ternario balanceado
  - to_standard: entero -> digitos + string en ternario estandar (+ signo)
  - from_balanced: string en ternario balanceado -> entero
  - from_standard: string en ternario estandar (+ signo) -> entero
  - add / subtract / multiply: dos enteros, calculados digito a digito
    en ternario balanceado, resultado devuelto en balanceado y decimal
  - validate: self-tests
"""
from typing import Dict, List, Any

TOOL_NAME = 'ternary_representation_tool'
TOOL_MODES = ['to_balanced', 'to_standard', 'from_balanced', 'from_standard',
              'add', 'subtract', 'multiply', 'validate']

_BALANCED_SYMBOLS = {-1: 'T', 0: '0', 1: '1'}
_BALANCED_PARSE = {'1': 1, '0': 0, 'T': -1, 't': -1}


# ============================================================================
# CONVERSION
# ============================================================================
def _int_to_balanced(n: int) -> List[int]:
    """Entero -> digitos ternario balanceado, LSD-primero, cada uno en {-1,0,1}."""
    if n == 0:
        return [0]
    digits = []
    x = n
    while x != 0:
        r = x % 3          # Python: % siempre no-negativo con divisor positivo
        x = x // 3         # floor division, consistente con negativos
        if r == 2:
            r = -1
            x += 1
        digits.append(r)
    return digits


def _balanced_to_int(digits_lsd: List[int]) -> int:
    return sum(d * (3 ** i) for i, d in enumerate(digits_lsd))


def _int_to_standard(n: int):
    """Entero -> (digitos LSD-primero en {0,1,2}, signo +1/-1)."""
    sign = 1
    if n < 0:
        sign = -1
        n = -n
    if n == 0:
        return [0], 1
    digits = []
    x = n
    while x > 0:
        digits.append(x % 3)
        x //= 3
    return digits, sign


def _standard_to_int(digits_lsd: List[int], sign: int = 1) -> int:
    return sign * sum(d * (3 ** i) for i, d in enumerate(digits_lsd))


def _format_balanced(digits_lsd: List[int]) -> str:
    return ''.join(_BALANCED_SYMBOLS[d] for d in reversed(digits_lsd))


def _format_standard(digits_lsd: List[int], sign: int) -> str:
    body = ''.join(str(d) for d in reversed(digits_lsd))
    return ('-' if sign < 0 else '') + body


def _parse_balanced_string(s: str) -> List[int]:
    digits_msd = []
    for ch in s:
        if ch not in _BALANCED_PARSE:
            raise ValueError(f"Simbolo invalido en ternario balanceado: '{ch}' (validos: 0,1,T)")
        digits_msd.append(_BALANCED_PARSE[ch])
    return list(reversed(digits_msd))


def _parse_standard_string(s: str):
    sign = 1
    if s.startswith('-'):
        sign = -1
        s = s[1:]
    digits_msd = []
    for ch in s:
        if ch not in '012':
            raise ValueError(f"Simbolo invalido en ternario estandar: '{ch}' (validos: 0,1,2)")
        digits_msd.append(int(ch))
    return list(reversed(digits_msd)), sign


# ============================================================================
# ARITMETICA BALANCEADA (digito a digito, con acarreo real)
# ============================================================================
def _add_balanced_digits(da: List[int], db: List[int]) -> List[int]:
    """Suma ternaria balanceada real: para cada posicion, s = da[i]+db[i]+carry
    (s en [-3,3]) se reduce a un digito d en {-1,0,1} mas un acarreo c en
    {-1,0,1} tal que s = d + 3c. Es el algoritmo genuino de la Setun, no
    una suma decimal disfrazada."""
    n = max(len(da), len(db))
    da = da + [0] * (n - len(da))
    db = db + [0] * (n - len(db))
    result = []
    carry = 0
    for i in range(n):
        s = da[i] + db[i] + carry
        if s > 1:
            d = s - 3
            carry = 1
        elif s < -1:
            d = s + 3
            carry = -1
        else:
            d = s
            carry = 0
        result.append(d)
    if carry != 0:
        result.append(carry)
    while len(result) > 1 and result[-1] == 0:
        result.pop()
    return result


def _negate_balanced(digits_lsd: List[int]) -> List[int]:
    return [-d for d in digits_lsd]


def _subtract_balanced_digits(da: List[int], db: List[int]) -> List[int]:
    return _add_balanced_digits(da, _negate_balanced(db))


def _multiply_balanced_digits(da: List[int], db: List[int]) -> List[int]:
    """Multiplicacion tipo escuela primaria en base 3: cada digito de db
    es -1, 0 o 1, asi que 'multiplicar por un digito' es trivial (negar,
    anular, o copiar); se desplaza segun la posicion (potencia de 3) y se
    suma todo con el sumador balanceado real de arriba."""
    result = [0]
    for i, db_i in enumerate(db):
        if db_i == 0:
            continue
        term = da[:] if db_i == 1 else _negate_balanced(da)
        shifted = [0] * i + term
        result = _add_balanced_digits(result, shifted)
    return result


# ============================================================================
# DISPATCH
# ============================================================================
def _dispatch(mode: str, params: Dict) -> Dict:
    if mode == 'to_balanced':
        value = params.get('value')
        if value is None:
            return {'error': 'value es requerido'}
        digits = _int_to_balanced(int(value))
        return {
            'value': value,
            'balanced_digits_lsd': digits,
            'balanced_string': _format_balanced(digits),
        }

    elif mode == 'to_standard':
        value = params.get('value')
        if value is None:
            return {'error': 'value es requerido'}
        digits, sign = _int_to_standard(int(value))
        return {
            'value': value,
            'standard_digits_lsd': digits,
            'sign': sign,
            'standard_string': _format_standard(digits, sign),
        }

    elif mode == 'from_balanced':
        s = params.get('digits')
        if s is None:
            return {'error': 'digits (string, ej. "1TT") es requerido'}
        try:
            digits = _parse_balanced_string(s)
        except ValueError as e:
            return {'error': str(e)}
        return {'input': s, 'value': _balanced_to_int(digits)}

    elif mode == 'from_standard':
        s = params.get('digits')
        if s is None:
            return {'error': 'digits (string, ej. "12" o "-21") es requerido'}
        try:
            digits, sign = _parse_standard_string(s)
        except ValueError as e:
            return {'error': str(e)}
        return {'input': s, 'value': _standard_to_int(digits, sign)}

    elif mode in ('add', 'subtract', 'multiply'):
        a = params.get('a')
        b = params.get('b')
        if a is None or b is None:
            return {'error': 'a y b (enteros) son requeridos'}
        a, b = int(a), int(b)
        da, db = _int_to_balanced(a), _int_to_balanced(b)
        if mode == 'add':
            dr = _add_balanced_digits(da, db)
            expected = a + b
        elif mode == 'subtract':
            dr = _subtract_balanced_digits(da, db)
            expected = a - b
        else:
            dr = _multiply_balanced_digits(da, db)
            expected = a * b
        result_value = _balanced_to_int(dr)
        return {
            'a': a, 'b': b, 'operation': mode,
            'result': result_value,
            'result_balanced_string': _format_balanced(dr),
            'verified_against_decimal': result_value == expected,
        }

    elif mode == 'validate':
        return run_self_test()

    else:
        return {'error': f'Unknown mode: {mode}'}


def run(arguments: Dict) -> Dict:
    """Punto de entrada para handler de servidor."""
    mode = arguments.get('mode', 'validate')
    params = arguments.get('params', {})
    return _dispatch(mode, params)


# ============================================================================
# SELF-TEST
# ============================================================================
def run_self_test() -> Dict:
    tests_passed = 0
    tests_total = 0
    errors = []

    # Test 1: 5 en balanceado es "1TT" (1*9 - 1*3 - 1*1 = 5)
    tests_total += 1
    try:
        digits = _int_to_balanced(5)
        assert _format_balanced(digits) == '1TT', f"Esperado 1TT, dio {_format_balanced(digits)}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 1 (5 -> 1TT): {e}")

    # Test 2: roundtrip balanceado para un rango de enteros (incluye negativos)
    tests_total += 1
    try:
        for n in range(-50, 51):
            d = _int_to_balanced(n)
            assert _balanced_to_int(d) == n, f"Roundtrip fallo para n={n}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 2 (roundtrip balanceado -50..50): {e}")

    # Test 3: roundtrip estandar para un rango de enteros (incluye negativos)
    tests_total += 1
    try:
        for n in range(-50, 51):
            d, sign = _int_to_standard(n)
            assert _standard_to_int(d, sign) == n, f"Roundtrip fallo para n={n}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 3 (roundtrip estandar -50..50): {e}")

    # Test 4: suma balanceada digito a digito coincide con suma decimal (rango amplio)
    tests_total += 1
    try:
        for a in range(-30, 31, 3):
            for b in range(-30, 31, 5):
                da, db = _int_to_balanced(a), _int_to_balanced(b)
                dr = _add_balanced_digits(da, db)
                assert _balanced_to_int(dr) == a + b, f"Suma fallo: {a}+{b}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 4 (suma balanceada vs decimal): {e}")

    # Test 5: resta balanceada digito a digito coincide con resta decimal
    tests_total += 1
    try:
        for a in range(-30, 31, 3):
            for b in range(-30, 31, 5):
                da, db = _int_to_balanced(a), _int_to_balanced(b)
                dr = _subtract_balanced_digits(da, db)
                assert _balanced_to_int(dr) == a - b, f"Resta fallo: {a}-{b}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 5 (resta balanceada vs decimal): {e}")

    # Test 6: multiplicacion balanceada (shift-add) coincide con multiplicacion decimal
    tests_total += 1
    try:
        for a in range(-15, 16):
            for b in range(-15, 16):
                da, db = _int_to_balanced(a), _int_to_balanced(b)
                dr = _multiply_balanced_digits(da, db)
                assert _balanced_to_int(dr) == a * b, f"Multiplicacion fallo: {a}*{b}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 6 (multiplicacion balanceada vs decimal): {e}")

    # Test 7: parseo de string balanceado ida y vuelta
    tests_total += 1
    try:
        assert _parse_balanced_string('1TT') == list(reversed([1, -1, -1]))
        assert _balanced_to_int(_parse_balanced_string('1TT')) == 5
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 7 (parseo balanceado '1TT'): {e}")

    # Test 8: parseo de string estandar con signo
    tests_total += 1
    try:
        digits, sign = _parse_standard_string('-21')
        assert _standard_to_int(digits, sign) == -7, f"Esperado -7, dio {_standard_to_int(digits, sign)}"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 8 (parseo estandar '-21'): {e}")

    # Test 9: simbolo invalido debe dar error controlado, no crash
    tests_total += 1
    try:
        result = _dispatch('from_balanced', {'digits': '1X0'})
        assert 'error' in result, "Simbolo invalido deberia devolver error"
        tests_passed += 1
    except Exception as e:
        errors.append(f"Test 9 (simbolo invalido controlado): {e}")

    return {
        'tool': TOOL_NAME,
        'tests_passed': tests_passed,
        'tests_total': tests_total,
        'errors': errors,
        'status': 'PASSED' if tests_passed == tests_total else 'FAILED',
        'validation_passed': tests_passed == tests_total,
    }


TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Aritmetica en base 3: ternario balanceado (digitos -1,0,1, algoritmo "
        "real de suma con acarreo tipo Setun) y ternario estandar (digitos "
        "0,1,2). Modos: to_balanced, to_standard, from_balanced, from_standard, "
        "add, subtract, multiply (calculadas digito a digito en balanceado), validate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": TOOL_MODES},
            "params": {
                "type": "object",
                "properties": {
                    "value": {"type": "integer", "description": "Entero a convertir (to_balanced/to_standard)"},
                    "digits": {"type": "string", "description": "String de digitos (from_balanced: '1TT'; from_standard: '-21')"},
                    "a": {"type": "integer", "description": "Primer operando (add/subtract/multiply)"},
                    "b": {"type": "integer", "description": "Segundo operando (add/subtract/multiply)"},
                },
                "description": "Parametros segun el modo"
            }
        },
        "required": ["mode", "params"]
    }
}

try:
    from tool_registry import register_tool
    register_tool(TOOL_NAME, TOOL_SCHEMA, run)
except ImportError:
    pass

if __name__ == '__main__':
    import json
    print(json.dumps(run_self_test(), indent=2, default=str))
