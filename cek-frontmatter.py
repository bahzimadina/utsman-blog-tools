#!/usr/bin/env python3
"""Cek frontmatter YAML hiji (atawa sababaraha) berkas markdown blog.

Dipaké ku publish.sh SATEUACAN push: frontmatter anu ruksak (mis. judul ngandung
titik dua tanpa dikutip) nyieun gen.py gagal SENYAP — tulisan en/su kacatet salaku id.

Pamakéan: python3 cek-frontmatter.py <berkas.md> [berkas2.md ...]
Kaluar 0 lamun sadayana beres, 1 lamun aya nu ruksak.
"""
import sys
import pathlib

try:
    import yaml
except ImportError:  # pragma: no cover
    print("! modul yaml teu aya — cek frontmatter dilesotkeun", file=sys.stderr)
    sys.exit(0)

WAJIB = ("title", "date", "lang", "pair")
BASA = ("id", "en", "su")


def cek(path: str) -> bool:
    f = pathlib.Path(path)
    if not f.is_file():
        print(f"✗ {path}: berkas teu kapanggih", file=sys.stderr)
        return False
    teks = f.read_text(encoding="utf-8")
    if not teks.startswith("---"):
        print(f"✗ {path}: teu dimimitian ku frontmatter '---'", file=sys.stderr)
        return False
    bagian = teks.split("---", 2)
    if len(bagian) < 3:
        print(f"✗ {path}: frontmatter teu ditutup ku '---'", file=sys.stderr)
        return False
    try:
        data = yaml.safe_load(bagian[1])
    except yaml.YAMLError as e:
        pesen = str(e).replace("\n", " ")
        print(f"✗ {path}: frontmatter ruksak (YAML): {pesen}", file=sys.stderr)
        print(
            '  → judul anu ngandung ":" kudu dikutip: title: "Judul: kalawan titik dua"',
            file=sys.stderr,
        )
        return False
    if not isinstance(data, dict):
        print(f"✗ {path}: frontmatter lain mapping YAML", file=sys.stderr)
        return False
    kurang = [k for k in WAJIB if not data.get(k)]
    if kurang:
        print(f"✗ {path}: widang wajib kurang: {', '.join(kurang)}", file=sys.stderr)
        return False
    if data.get("lang") not in BASA:
        print(f"✗ {path}: lang '{data.get('lang')}' lain id/en/su", file=sys.stderr)
        return False
    print(f"✓ {path}: frontmatter bener (lang={data['lang']}, pair={data.get('pair')})")
    return True


def main() -> int:
    if len(sys.argv) < 2:
        print("Pamakéan: cek-frontmatter.py <berkas.md> [...]", file=sys.stderr)
        return 1
    return 0 if all(cek(p) for p in sys.argv[1:]) else 1


if __name__ == "__main__":
    sys.exit(main())
