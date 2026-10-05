#!/usr/bin/env python3
"""
susun.py — delegasi panulisan artikel blog utsman.works ka agén spesialis,
tuluy pariksa hasilna (gaya antislop + saringan kaamanan) sateuacan diterbitkeun.

Conto:
  susun.py --profil lemur --tanggal 2026-10-06 --pilar "Produktivitas Pribadi" \
           --topik "Menyusun daftar tugas yang realistis" --pair tugas-realistis \
           --dir /tmp/harian/2026-10-06

Kaluar: 0 = tilu berkas aya sarta lulus duanana saringan; 1 = gagal (tempo alesan).
"""
import argparse
import glob
import os
import subprocess
import sys

TEMPLATE = """Anjeun **{profil}**, anggota tim eusi DKM Masjid AL-HIKMAH. Pak Sudar ukur ngobrol jeung
Utsman; anjeun digawé dina brief ieu. Eusina kudu beres, siap tayang, TANPA peryogi disunting deui.

TUGAS: tulis SATU artikel blog dina **TILU basa** (Indonésia `id`, Inggris `en`, Sunda `su`)
ngeunaan topik di handap, tuluy simpen jadi **tilu berkas markdown** dina polder anu geus ditangtukeun.

PILAR   : {pilar}
TOPIK   : {topik}
TANGGAL : {tanggal}
PAIR    : {pair}
POLDER  : {direktori}
{seri_blok}
ATURAN GAYA (WAJIB — aya saringan otomatis anu NGABATALKEUN):
- Basa sapopoé, hirup, siga jalma nyarita. Paragraf pondok. Maksimal 1 émoji per artikel.
- DILARANG (saringan bakal nyegat): "Tentu!", "Berikut adalah", "Perlu diketahui bahwa",
  "Penting untuk dicatat", "Sebagai asisten", "Saya harap ini membantu", "Jangan ragu untuk",
  "Mari kita", "Secara keseluruhan", "Kesimpulannya", "Dalam dunia yang serba cepat", "Di era digital",
  "It's important to note", "Let's dive in", "In conclusion", "As an AI", "I hope this helps",
  "Feel free to", "game-changer", "unlock the power", "Mangga urang", "Salaku asisten".
- Ulah ngagunakeun daptar pélor kaleuleuwihi: sahenteuna satengah artikel kudu paragraf.
- Panjang 350–600 kecap PER BASA. Katiluna mawa eusi anu sarua (tarjamahan), sanés ringkesan.

ATURAN EUSI (WAJIB — aya saringan kaamanan anu NGABATALKEUN):
- DILARANG: angka/rincian keuangan organisasi, ngaran jeung data pribadi (nomer telepon,
  nomer rekening, alamat, nomor rumah/blok), kredensial (API key, token, password),
  alamat IP atawa ngaran server, jeung eusi percakapan.
- MEUNANG: téhnologi anu dipaké Utsman (agén AI, modél basa/LLM, MCP, kanal WhatsApp/Telegrám/email,
  otomasi kajadwalan), cara gawé, jeung hal umum soal produktivitas, administrasi, organisasi, komunikasi.

FORMAT (saban berkas — id, en, su):
---
title: <judul dina basa éta>
date: {tanggal}
slug: <slug-berkas, hurup leutik, tanda hubung>
lang: <id|en|su>
pair: {pair}
excerpt: <1–2 kalimat ringkesan>
tags: [tag1, tag2]
draft: false
{seri_frontmatter}---
<eusi markdown: paragraf, ## subjudul, daptar sakedik, kutipan upami perlu — tanpa HTML mentah>

Ngaran berkas: `{tanggal}-<slug>.md` (tilu berkas: hiji per basa).

SANGGEUS NULIS — pariksa sorangan, ulah ukur ngandelkeun rarasaan:
1. Jalankeun pikeun saban berkas:
   `python3 /home/ubuntu/utsman-blog/antislop.py <berkas>` → kudu "gaya bersih (antislop)"
   `python3 /home/ubuntu/utsman-blog/guard.py <berkas>` → kudu "bersih"
2. Upami aya nu nyegat, pundut frasana tuluy uji deui. Ulah ngalaporkeun hasil anu can lulus.

BALESAN AKHIR (ringkes, maks 6 baris): judul katilu basa, ngaran berkas, jeung hasil
dua saringan éta pikeun saban berkas.
"""

SERI_BLOK = """
ARTIKEL IEU BAGIAN TI SERI — penting pisan:
- slug seri  : {seri}
- judul seri : {seri_judul}
- bagian ka- : {bagian}
Tulis salaku tutorial praktis, sambungkeun jeung bagian saméméhna upami relevan, jeung tutup
ku pituduh naon anu bakal dibahas dina bagian salanjutna.
"""

SERI_FRONTMATTER = "series: {seri}\nseries_title: {seri_judul}\npart: {bagian}\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profil", required=True)
    ap.add_argument("--tanggal", required=True)
    ap.add_argument("--pilar", required=True)
    ap.add_argument("--topik", required=True)
    ap.add_argument("--pair", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--seri", default="")
    ap.add_argument("--seri-judul", default="")
    ap.add_argument("--bagian", default="")
    ap.add_argument("--timeout", type=int, default=1500)
    a = ap.parse_args()

    os.makedirs(a.dir, exist_ok=True)
    for f in glob.glob(os.path.join(a.dir, "*.md")):
        os.remove(f)

    seri_blok = ""
    seri_frontmatter = ""
    if a.seri:
        seri_blok = SERI_BLOK.format(seri=a.seri, seri_judul=a.seri_judul or a.seri, bagian=a.bagian or "1")
        seri_frontmatter = SERI_FRONTMATTER.format(seri=a.seri, seri_judul=a.seri_judul or a.seri, bagian=a.bagian or "1")

    brief = TEMPLATE.format(profil=a.profil, pilar=a.pilar, topik=a.topik, tanggal=a.tanggal,
                            pair=a.pair, direktori=a.dir, seri_blok=seri_blok,
                            seri_frontmatter=seri_frontmatter)
    berkas_brief = os.path.join(a.dir, ".brief.md")
    open(berkas_brief, "w", encoding="utf-8").write(brief)

    print(f"→ ngirim brief ka agén «{a.profil}» (topik: {a.topik})")
    cmd = ["timeout", str(a.timeout), "hermes", "-p", a.profil, "chat", "-q", brief]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=a.timeout + 60)
        log = (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        log = "TIMEOUT: agén teu réngsé dina wates waktu"
    open(os.path.join(a.dir, ".log-agent.txt"), "w", encoding="utf-8").write(log)
    print("   balasan pamungkas agén:")
    for b in [x for x in log.strip().split("\n") if x.strip()][-6:]:
        print("     " + b[:160])

    berkas = sorted(glob.glob(os.path.join(a.dir, "*.md")))
    if not berkas:
        print(f"\n⛔ GAGAL: euweuh berkas markdown dina {a.dir}. Tempo {a.dir}/.log-agent.txt", file=sys.stderr)
        return 1

    basa = {}
    gagal = []
    print(f"\n→ pariksa {len(berkas)} berkas:")
    for f in berkas:
        isi = open(f, encoding="utf-8").read()
        for saringan in ("antislop.py", "guard.py"):
            r = subprocess.run(["python3", f"/home/ubuntu/utsman-blog/{saringan}", f],
                               capture_output=True, text=True)
            if r.returncode != 0:
                gagal.append((f, saringan, (r.stderr or "").strip().split("\n")[:4]))
        m = [l for l in isi.split("\n")[:12] if l.startswith("lang:")]
        if m:
            basa[m[0].split(":", 1)[1].strip()] = os.path.basename(f)

    for kode in ("id", "en", "su"):
        tanda = "✓" if kode in basa else "✗ kurang"
        print(f"   {kode}: {basa.get(kode, '—')} {tanda}")

    if gagal:
        print("\n⛔ Saringan nyegat — kedah dibenerkeun heula:")
        for f, s, baris in gagal:
            print(f"   {os.path.basename(f)} ({s}):")
            for b in baris:
                print("      " + b[:140])
        return 1
    if len([k for k in basa if k in ("id", "en", "su")]) < 3:
        print("\n⛔ GAGAL: can aya tilu basa (id/en/su).")
        return 1
    print("\n✓ Tilu basa aya, duanana saringan lulus. Siap diterbitkeun.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
