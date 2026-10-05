# utsman-blog-tools — pakakas blog utsman.works

Pakakas anu ngarobih eusi markdown ti repositori publik
[`bahzimadina/utsman-blog`](https://github.com/bahzimadina/utsman-blog) jadi
halaman blog statik dina <https://utsman.works/blog/>.

## Eusi folder

| Berkas | Guna |
|---|---|
| `sync.sh` | narik repositori eusi + ngalakukeun panerap. **Cicing lamun euweuh parobahan** (aman pikeun cron). |
| `gen.py` | panerap markdown → HTML (python-markdown + panyaring HTML). Nulis `out/` ukur lamun aya parobahan. |
| `guard.py` | **saringan kaamanan**: ngabatalkeun tulisan anu ngandung angka duit, nomer telepon/rekening, kredensial, IP, atawa email pribadi. |
| `publish.sh` | nerbitkeun hiji tulisan (`publish.sh <berkas.md> "pesen"`) — saringan → commit → push. |
| `topics.md` | daptar ide tulisan harian (ditandaan sanggeus dipaké). |
| `repo/` | klon repositori eusi (henteu dilacak ku git). |
| `out/` | hasil HTML anu disajikan nginx (henteu dilacak ku git). |

## Alur

```
posts/*.md (GitHub)  →  sync.sh  →  gen.py  →  out/  --(volume read-only)-->  /usr/share/nginx/html/blog
```

- Cron `blog-sync` (tiap 10 menit): maparin eusi anyar kana situs.
- Cron `tulisan harian` (05:30 WIB): nulis hiji tulisan **bilingual** (ID + EN) saban poé.

## Kaamanan

- Situs ukur **maca** repositori; teu aya token dina kode ieu.
- HTML hasil markdown dibersihkeun (daptar bodas tag/atribut) — script/iframe/on* dipiceun.
- `guard.py` wajib lulus sateuacan publikasi. Repositori eusina **publik** — ulah nulis data pribadi.

## Pitfalls

- Ulah nambihan `datetime.now()` kana kaluaran `gen.py` — ngajadikeun hash sok robah, cron jadi ribut.
- Nginx ulah maké fallback `/index.html` pikeun URL anu teu aya (ngahasilkeun soft 404).
- `publish.sh` sok nga-fetch/reset heula supaya push teu ditolak.
