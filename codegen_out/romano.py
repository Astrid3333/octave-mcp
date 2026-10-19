# Generado por ancient_numeral_crypto_tool -- historico/educativo

_VALS = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),
         (50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
_ROM = {"I":1,"V":5,"X":10,"L":50,"C":100,"D":500,"M":1000}

def encode(n):
    if not (1 <= n <= 3999): raise ValueError("rango [1,3999]")
    out = []
    for v, s in _VALS:
        while n >= v: out.append(s); n -= v
    return "".join(out)

def decode(text):
    text = text.upper()
    if any(c not in _ROM for c in text): raise ValueError("letra romana inválida")
    vals = [_ROM[c] for c in text]
    t = 0
    for i, v in enumerate(vals):
        t += -v if v < (vals[i+1] if i+1 < len(vals) else 0) else v
    # canonicidad: re-encode debe dar el mismo texto
    if encode(t) != text: raise ValueError("forma romana no canónica")
    return t


if __name__ == '__main__':
    assert decode(encode(1234)) == 1234
    for n in range(1, 4000):
        assert decode(encode(n)) == n, n
    try:
        decode('IC'); assert False
    except ValueError: pass
    try:
        decode('IIII'); assert False
    except ValueError: pass
    print('PYTHON_CODEGEN_OK')
