# Generado por ancient_numeral_crypto_tool -- historico/educativo

_GERESH, _GERSHAYIM = "\u05f3", "\u05f4"
_LET = {"\u05d0":1,"\u05d1":2,"\u05d2":3,"\u05d3":4,"\u05d4":5,"\u05d5":6,
        "\u05d6":7,"\u05d7":8,"\u05d8":9,"\u05d9":10,"\u05db":20,"\u05dc":30,
        "\u05de":40,"\u05e0":50,"\u05e1":60,"\u05e2":70,"\u05e4":80,"\u05e6":90,
        "\u05e7":100,"\u05e8":200,"\u05e9":300,"\u05ea":400}
_FIN = {"\u05da":500,"\u05dd":600,"\u05df":700,"\u05e3":800,"\u05e5":900}
_FIN_BASE = {"\u05da":20,"\u05dd":40,"\u05df":50,"\u05e3":80,"\u05e5":90}
_HUND = {1:"\u05e7",2:"\u05e8",3:"\u05e9",4:"\u05ea",
         5:"\u05ea\u05e7",6:"\u05ea\u05e8",7:"\u05ea\u05e9",8:"\u05ea\u05ea",
         9:"\u05ea\u05ea\u05e7"}
_TENS = {1:"\u05d9",2:"\u05db",3:"\u05dc",4:"\u05de",5:"\u05e0",
         6:"\u05e1",7:"\u05e2",8:"\u05e4",9:"\u05e6"}
_ONES = {1:"\u05d0",2:"\u05d1",3:"\u05d2",4:"\u05d3",5:"\u05d4",
         6:"\u05d5",7:"\u05d6",8:"\u05d7",9:"\u05d8"}

_THOUS = {1:"\u05d0",2:"\u05d1",3:"\u05d2",4:"\u05d3",5:"\u05d4",
          6:"\u05d5",7:"\u05d6",8:"\u05d7",9:"\u05d8"}

def encode(n, gershayim=True):
    if not (1 <= n <= 9999): raise ValueError("rango [1,9999]")
    prefix = ""
    if n >= 1000:
        prefix = _THOUS[n // 1000] + _GERESH
        n %= 1000
    h, r = divmod(n, 100)
    t, o = divmod(r, 10)
    parts = []
    if h: parts.append(_HUND[h])
    if t == 1 and o in (5, 6):
        parts.append(_ONES[9] + _ONES[o + 1])  # 15=ט+ו, 16=ט+ז
    else:
        if t: parts.append(_TENS[t])
        if o: parts.append(_ONES[o])
    tail = "".join(parts)
    if gershayim and len(tail) >= 2:
        tail = tail[:-1] + _GERSHAYIM + tail[-1]
    return prefix + tail

def decode(text):
    s = text.strip().replace(_GERSHAYIM, "")
    tot, i = 0, 0
    while i < len(s):
        ch = s[i]
        nxt = s[i+1] if i+1 < len(s) else ""
        if ch in _FIN and nxt == _GERESH:
            tot += _FIN[ch]; i += 2
        elif nxt == _GERESH:
            tot += _LET[ch] * 1000; i += 2
        elif ch in _FIN:
            tot += _FIN_BASE[ch]; i += 1
        elif ch in _LET:
            tot += _LET[ch]; i += 1
        elif ch == _GERESH:
            i += 1
        else:
            raise ValueError(ch)
    return tot


if __name__ == '__main__':
    assert decode(encode(1234)) == 1234
    assert decode(encode(376)) == 376
    assert encode(15) == '\u05d8\u05f4\u05d5'  # ט״ו
    assert encode(16) == '\u05d8\u05f4\u05d6'  # ט״ז
    assert encode(900, gershayim=False) == '\u05ea\u05ea\u05e7'  # תתק
    assert encode(2026, gershayim=False) == '\u05d1\u05f3\u05db\u05d5'  # ב׳כו
    assert encode(2001) == '\u05d1\u05f3\u05d0'  # ב׳א (una sola letra tras miles: sin ״)
    assert decode('\u05e9\u05dc\u05d5\u05dd') == 376  # שלום
    print('PYTHON_CODEGEN_OK')
