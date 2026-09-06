import json, traceback

def probe(label, fn):
    print(f"\n[{label}]")
    try:
        r = fn()
        print(json.dumps(r, indent=2, default=str))
    except Exception:
        traceback.print_exc()

import aminoacid_tool as amt
probe("aminoacid_tool.validate", lambda: amt.aminoacid_tool('validate', {}))
probe("aminoacid_tool.composition", lambda: amt.aminoacid_tool('composition', {'sequence': 'ACDEFGHIKLMNPQRSTVWY'}))

import hormone_tool as ht
probe("hormone_tool.validate", lambda: ht.hormone_tool('validate', {}))

import ion_chemistry_tool as ict
probe("ion_chemistry_tool.validate", lambda: ict.validate())
