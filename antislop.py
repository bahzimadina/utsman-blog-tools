#!/usr/bin/env python3
"""
Saringan gaya "bau AI" (antislop) pikeun eusi blog utsman.works.

Dijalankeun ku publish.sh — tulisan anu ngandung frasa AI anu kuat DIBATALKEUN.
Frasa anu lemah ukur dipikanyahoan (peringatan), henteu ngabatalkeun.

Kaluar: 0 = lulus, 1 = aya palanggaran kuat.
"""
import re
import sys

# frasa anu kuat "bau AI" — ngabatalkeun
KERAS = [
    # Indonésia
    r"\bTentu[!,]\s", r"\bBaik,? dengan senang hati", r"\bBerikut adalah\b", r"\bBerikut informasinya\b",
    r"\bPerlu diketahui bahwa\b", r"\bPenting untuk dicatat\b", r"\bSebagai asisten\b",
    r"\bSaya (AI|adalah AI|asisten AI)\b", r"\bSaya harap ini membantu\b", r"\bJangan ragu untuk\b",
    r"\bMari kita\b", r"\bSecara keseluruhan\b", r"\bKesimpulannya\b", r"\bDalam dunia yang serba cepat\b",
    r"\bDi era digital\b", r"\bSolusi tepat\b", r"\bSangat penting untuk\b", r"\bTak hanya .{0,40}?tetapi juga\b",
    r"\bMari kita telusuri\b", r"\bTanpa basa-basi lagi\b",
    # Inggris
    r"\bIn today'?s (fast-paced|digital)\b", r"\bIt'?s important to note\b", r"\bLet'?s dive in\b",
    r"\bIn conclusion\b", r"\bAs an AI\b", r"\bI hope this helps\b", r"\bFeel free to\b",
    r"\b(delve|delving) into\b", r"\bgame-?changer\b", r"\bunlock the power\b", r"\belevate your\b",
    r"\btake it to the next level\b", r"\bWhether you'?re .{0,40}? or \b",
    # Sunda
    r"\bMangga urang\b", r"\bSalaku asisten\b", r"\bPerlu dipikanyaho yén\b",
]
# frasa anu lemah — ukur peringatan
LEMBUT = [
    r"\bSelain itu\b", r"\bDengan demikian\b", r"\bOleh karena itu\b", r"\bPada akhirnya\b",
    r"\bFurthermore\b", r"\bMoreover\b", r"\bAdditionally\b", r"\bUltimately\b",
]

EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def periksa(path):
    teks = open(path, encoding="utf-8").read()
    baris = teks.split("\n")
    keras, lembut = [], []
    for n, b in enumerate(baris, 1):
        for pola in KERAS:
            for m in re.finditer(pola, b, re.I):
                keras.append((n, m.group(0).strip()))
        for pola in LEMBUT:
            for m in re.finditer(pola, b, re.I):
                lembut.append((n, m.group(0).strip()))

    # émoji tumpuk (maks 1 per tulisan)
    emo = EMOJI.findall(teks)
    if len(emo) > 1:
        keras.append((0, f"{len(emo)} émoji (maks 1): {' '.join(emo[:5])}"))

    # daptar pélor anu kaleuleuwihi (tulisan kudu loba paragraf)
    baris_eusi = [b for b in baris if b.strip() and not b.startswith("---")]
    pelor = [b for b in baris_eusi if re.match(r"^\s*([-*+]|\d+\.)\s", b)]
    if baris_eusi and len(pelor) / len(baris_eusi) > 0.55 and len(pelor) > 8:
        keras.append((0, f"{len(pelor)} baris daptar tina {len(baris_eusi)} baris — teuing listy, tambihkeun paragraf"))
    return keras, lembut


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Pamakéan: antislop.py <berkas.md> [...]", file=sys.stderr)
        sys.exit(2)
    total = 0
    for f in sys.argv[1:]:
        keras, lembut = periksa(f)
        if keras:
            total += len(keras)
            print(f"⛔ {f}: kapendak {len(keras)} frasa bau AI:", file=sys.stderr)
            for n, t in keras[:12]:
                print(f"   · {'baris ' + str(n) if n else 'umum'}: “{t}”", file=sys.stderr)
        if lembut:
            print(f"⚠️  {f}: peringatan ({len(lembut)}): " +
                  ", ".join(f"“{t}”" for _n, t in lembut[:6]), file=sys.stderr)
        if not keras:
            print(f"✓ {f}: gaya bersih (antislop)")
    if total:
        print("\nTulisan DIBATALKEUN — jalankeun pass antislop (pundut frasa di luhur, tuluy cobian deui).", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)
