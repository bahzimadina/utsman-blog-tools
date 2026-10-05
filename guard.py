#!/usr/bin/env python3
"""
Panyaring kaamanan eusi blog — dijalankeun otomatis ku publish.sh sateuacan push.

Tujuan: mastikeun tulisan anu medal di blog PUBLIK teu ngandung data rahasia/penting:
angka duit, nomer telepon/rekening, kredensial, alamat IP, atawa email pribadi.

Kaluar: kode 0 = aman, kode 1 = kapendak (tulisan DIBATALKEUN).
"""
import re
import sys

PUBLIK = {"bahzimadina@gmail.com", "utsman.works", "example.com"}

POLA = [
    ("nomer telepon", r"(?<!\d)(?:\+?62|0)8\d{1,3}[\s.\-]?\d{3,4}[\s.\-]?\d{3,5}(?!\d)"),
    ("angka uang", r"(?i)\b(?:rp|idr)\s*\.?\s*\d[\d.,]*"),
    ("kredensial/rahasia", r"(?i)(?:api[_\-\s]?key|secret\s*key|access[_\-\s]?token|password|passwd|bearer\s+[A-Za-z0-9._\-]{12,}|sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z\-_]{20,}|xox[baprs]-[A-Za-z0-9\-]{10,})"),
    ("alamat IP", r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])"),
    ("nomer rekening/urut panjang", r"(?<!\d)\d{10,}(?!\d)"),
    ("nomor rumah/blok", r"(?i)\b(?:blok|blk)\s*[A-Z0-9]{1,3}[\s\-]?(?:no\.?|nomor)?\s*\d{1,2}\b"),
]


def email_pribadi(teks):
    for m in re.finditer(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+", teks):
        alamat = m.group(0).rstrip(".,;:!?").lower()
        if alamat not in PUBLIK:
            yield m.group(0)


def periksa(path):
    teks = open(path, encoding="utf-8").read()
    temuan = []
    for nama, pola in POLA:
        for m in re.finditer(pola, teks):
            baris = teks[:m.start()].count("\n") + 1
            temuan.append((nama, baris, m.group(0)[:60]))
    for alamat in email_pribadi(teks):
        baris = teks[: teks.find(alamat)].count("\n") + 1
        temuan.append(("email pribadi", baris, alamat))
    return temuan


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Pamakéan: guard.py <berkas.md> [...]", file=sys.stderr)
        sys.exit(2)
    total = 0
    for f in sys.argv[1:]:
        temuan = periksa(f)
        if temuan:
            total += len(temuan)
            print(f"⛔ {f}: kapendak {len(temuan)} hal anu teu kenging dipedalkeun:", file=sys.stderr)
            for nama, baris, cuplik in temuan[:12]:
                print(f"   · baris {baris}: {nama} → “{cuplik}”", file=sys.stderr)
        else:
            print(f"✓ {f}: bersih")
    if total:
        print("\nTulisan DIBATALKEUN. Pundut/robih bagian di luhur, tuluy cobian deui.", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)
