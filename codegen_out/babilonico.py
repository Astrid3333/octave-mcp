# Generado por ancient_numeral_crypto_tool -- historico/educativo

BAB_ONE, BAB_TEN, BAB_ZERO = "\U00012079", "\U0001230B", "\u00b7"

def encode(n):
    if n < 0: raise ValueError("rango [0,inf)")
    if n == 0: return BAB_ZERO
    groups = []
    while n > 0:
        n, d = divmod(n, 60); groups.append(d)
    groups.reverse(); out = []
    for d in groups:
        if d == 0: out.append(BAB_ZERO)
        else:
            if d >= 60: raise ValueError("grupo mixto >=60")
            t, o = divmod(d, 10); out.append(BAB_TEN * t + BAB_ONE * o)
    return " ".join(out)

def decode(text):
    if text.strip() == BAB_ZERO: return 0
    total = 0
    for g in text.split():
        d = g.count(BAB_TEN) * 10 + g.count(BAB_ONE)
        if d >= 60: raise ValueError("grupo mixto >=60")
        total = total * 60 + d
    return total


if __name__ == '__main__':
    assert len(BAB_ONE) == 1 and ord(BAB_ONE) == 0x12079
    assert len(BAB_TEN) == 1 and ord(BAB_TEN) == 0x1230B
    assert len(BAB_ZERO) == 1 and ord(BAB_ZERO) == 0x00B7
    assert decode(encode(1234)) == 1234
    assert decode(encode(0)) == 0
    for n in range(0, 100000):
        assert decode(encode(n)) == n, n
    print('PYTHON_CODEGEN_OK')
