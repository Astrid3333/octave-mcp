"""
number_theory_tool.py

Teoria de numeros con aplicacion criptografica: test de primalidad
Miller-Rabin, RSA de juguete (par de claves, cifrado/descifrado), y
aritmetica de curvas elipticas (suma/duplicacion de puntos sobre un cuerpo
finito). Implementado en Python puro -- no via Octave, porque necesita
aritmetica de enteros de precision arbitraria (Octave usa floats de 64 bits,
insuficiente mas alla de ~2^53) que Python trae nativa.

Conecta directo con chinese_remainder (ya en ethnomath_tool): el CRT es la
base de la optimizacion RSA-CRT usada en implementaciones reales para
acelerar el descifrado, y los sistemas de residuos numericos (RNS) que
motivan chinese_remainder tienen aplicacion directa en hardware
criptografico moderno.

Mismo patron de validacion: presets contra casos de libro de texto
conocidos (numero de Carmichael 561, ejemplo RSA clasico n=3233/d=2753,
ejemplo de curva eliptica de Hankerson et al.) antes de aplicar a datos
custom.
"""
import random

NUMBER_THEORY_SCHEMA = {
    "name": "compute_number_theory",
    "description": (
        "Teoria de numeros con aplicacion criptografica: primality_test "
        "(Miller-Rabin, detecta incluso numeros de Carmichael como 561), "
        "rsa_toy (genera par de claves con primos dados, cifra/descifra un "
        "mensaje, valida contra el ejemplo clasico del paper RSA original), "
        "elliptic_curve_add (suma/duplicacion de puntos sobre y^2=x^3+ax+b "
        "mod p, validado contra ejemplo de libro de texto Hankerson et al)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["primality_test", "rsa_toy", "elliptic_curve_add"],
                "default": "primality_test",
            },
            "preset": {
                "type": "string",
                "enum": ["known_cases", "classic_rsa_example", "hankerson_curve_example", "custom"],
                "default": "known_cases",
            },
            "n": {"type": "integer", "description": "Para primality_test custom: numero a testear"},
            "p": {"type": "integer", "description": "Para rsa_toy custom: primo 1"},
            "q": {"type": "integer", "description": "Para rsa_toy custom: primo 2"},
            "e": {"type": "integer", "default": 17, "description": "Para rsa_toy: exponente publico"},
            "message": {"type": "integer", "description": "Para rsa_toy: mensaje a cifrar (debe ser < n)"},
            "curve_a": {"type": "integer", "description": "Para elliptic_curve_add custom"},
            "curve_b": {"type": "integer", "description": "Para elliptic_curve_add custom"},
            "curve_p": {"type": "integer", "description": "Para elliptic_curve_add custom: modulo primo"},
            "point1": {"type": "array", "description": "Para elliptic_curve_add custom: [x,y]"},
            "point2": {"type": "array", "description": "Para elliptic_curve_add custom: [x,y], None para duplicar point1"},
        },
    },
}


def _miller_rabin(n, k=20, seed=1):
    if n < 2:
        return False
    small_primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31]
    for p in small_primes:
        if n % p == 0:
            return n == p
    r, d = 0, n - 1
    while d % 2 == 0:
        r += 1
        d //= 2
    rng = random.Random(seed)
    for _ in range(k):
        a = rng.randrange(2, n - 1)
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _egcd(a, b):
    if a == 0:
        return (b, 0, 1)
    g, x1, y1 = _egcd(b % a, a)
    return (g, y1 - (b // a) * x1, x1)


def _modinv(a, m):
    g, x, _ = _egcd(a, m)
    if g != 1:
        return None
    return x % m


def _ec_add(P, Q, a, p):
    if P is None:
        return Q
    if Q is None:
        return P
    x1, y1 = P
    x2, y2 = Q
    if x1 == x2 and (y1 + y2) % p == 0:
        return None  # punto en el infinito
    if P == Q:
        denom = _modinv(2 * y1 % p, p)
        if denom is None:
            return None
        m = (3 * x1 * x1 + a) * denom % p
    else:
        denom = _modinv((x2 - x1) % p, p)
        if denom is None:
            return None
        m = (y2 - y1) * denom % p
    x3 = (m * m - x1 - x2) % p
    y3 = (m * (x1 - x3) - y1) % p
    return (x3, y3)


def compute_number_theory(mode="primality_test", preset="known_cases", n=None,
                           p=None, q=None, e=17, message=None,
                           curve_a=None, curve_b=None, curve_p=None,
                           point1=None, point2=None):

    if mode == "primality_test":
        if preset == "custom":
            if n is None:
                return {"error": "preset='custom' requiere 'n'"}
            is_prime = _miller_rabin(n)
            return {"n": n, "es_primo_miller_rabin": is_prime, "confianza": "20 rondas, probabilidad de error < 4^-20"}
        elif preset == "known_cases":
            cases = [
                (97, True, "primo pequeno"),
                (100, False, "compuesto obvio"),
                (7919, True, "primo (1000-esimo primo)"),
                (561, False, "numero de Carmichael -- pasa el test de Fermat simple pero Miller-Rabin lo detecta correctamente"),
                (2**31 - 1, True, "primo de Mersenne conocido (2^31-1)"),
            ]
            results = []
            for num, expected, nota in cases:
                result = _miller_rabin(num)
                results.append({"n": num, "es_primo": result, "esperado": expected,
                                "coincide": result == expected, "nota": nota})
            return {"casos": results, "todos_correctos": all(r["coincide"] for r in results)}
        else:
            return {"error": f"preset '{preset}' no aplica para mode='primality_test'"}

    elif mode == "rsa_toy":
        if preset == "custom":
            if p is None or q is None:
                return {"error": "preset='custom' requiere 'p' y 'q' (primos)"}
            if not (_miller_rabin(p) and _miller_rabin(q)):
                return {"error": "p y q deben ser primos"}
        elif preset == "classic_rsa_example":
            p, q, e = 61, 53, 17
        else:
            return {"error": f"preset '{preset}' no aplica para mode='rsa_toy'"}

        n_val = p * q
        phi = (p - 1) * (q - 1)
        if _egcd(e, phi)[0] != 1:
            return {"error": f"e={e} no es coprimo con phi={phi}, elegir otro e"}
        d = _modinv(e, phi)

        result = {
            "p": p, "q": q, "n": n_val, "phi": phi, "public_key_e": e, "private_key_d": d,
        }
        if preset == "classic_rsa_example":
            result["known_reference"] = {"d_esperado": 2753, "nota": "ejemplo clasico del paper RSA original (Rivest-Shamir-Adleman 1978)"}

        msg = message if message is not None else 65
        if msg >= n_val:
            return {"error": f"message={msg} debe ser menor que n={n_val}"}
        cipher = pow(msg, e, n_val)
        decrypted = pow(cipher, d, n_val)
        result["mensaje_original"] = msg
        result["mensaje_cifrado"] = cipher
        result["mensaje_descifrado"] = decrypted
        result["roundtrip_ok"] = msg == decrypted
        return result

    elif mode == "elliptic_curve_add":
        if preset == "custom":
            if curve_a is None or curve_b is None or curve_p is None or point1 is None:
                return {"error": "preset='custom' requiere 'curve_a', 'curve_b', 'curve_p', 'point1'"}
            a, b, pmod = curve_a, curve_b, curve_p
            P = tuple(point1)
            Q = tuple(point2) if point2 else P
        elif preset == "hankerson_curve_example":
            a, b, pmod = 2, 2, 17
            P = (5, 1)
            Q = P  # duplicar G
        else:
            return {"error": f"preset '{preset}' no aplica para mode='elliptic_curve_add'"}

        lhs = (P[1] ** 2) % pmod
        rhs = (P[0] ** 3 + a * P[0] + b) % pmod
        on_curve = lhs == rhs

        R = _ec_add(P, Q, a, pmod)
        result = {
            "curve": f"y^2 = x^3 + {a}x + {b} mod {pmod}",
            "point1": P, "point2": Q, "point1_on_curve": on_curve,
            "result": R, "operation": "duplicacion (2P)" if P == Q else "suma (P+Q)",
        }
        if preset == "hankerson_curve_example":
            result["known_reference"] = {"resultado_esperado_2G": [6, 3], "nota": "ejemplo de Hankerson, Menezes & Vanstone, Guide to Elliptic Curve Cryptography"}
        return result

    else:
        return {"error": f"mode desconocido: {mode}"}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_number_theory("primality_test", "known_cases"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_number_theory("rsa_toy", "classic_rsa_example"), indent=2, ensure_ascii=False))
    print(json.dumps(compute_number_theory("elliptic_curve_add", "hankerson_curve_example"), indent=2, ensure_ascii=False))
