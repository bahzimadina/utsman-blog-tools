#!/usr/bin/env python3
"""
Panerap blog utsman.works — markdown (repositori publik) → halaman HTML statik.

Alur:  posts/*.md  →  /home/ubuntu/utsman-blog/out/  (disajikan di /blog)

Kaamanan:
  - Eusina ukur dibaca (repositori publik, tanpa token).
  - HTML hasil markdown DIBERSIHKEUN: tag di luar daptar bodas dipiceun, atribut on*/script/
    iframe/js dihapuп, tautan ukur http/https/mailto/relatif.
  - Laméy `draft: true` teu dipedalkeun.
Silent: lamun euweuh nu robah, henteu nulis nanaon (cocog pikeun cron).
"""
import argparse, hashlib, html, json, os, re, shutil, sys, unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser

import markdown
import yaml

SITE = "https://utsman.works"
DEFAULT_REPO = "/home/ubuntu/utsman-blog/repo"
DEFAULT_OUT = "/home/ubuntu/utsman-blog/out"
CSS_VER = "20261005-6"

# ---------------------------------------------------------------- panyaring HTML

ALLOWED_TAGS = {
    "h1","h2","h3","h4","h5","h6","p","br","hr","ul","ol","li","blockquote",
    "pre","code","em","strong","b","i","a","img","table","thead","tbody","tr","th","td",
    "figure","figcaption","del","ins","sup","sub","dl","dt","dd","span","caption",
}
ALLOWED_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
    "code": {"class"},
    "th": {"align"}, "td": {"align"},
}
VOID = {"br", "hr", "img"}
DROP_CONTENT = {"script", "style", "iframe", "object", "embed", "svg", "math", "form", "noscript"}


def _safe_url(u, kind):
    if u is None:
        return None
    u = u.strip()
    low = u.lower()
    if kind == "img":
        if low.startswith(("http://", "https://", "/", "data:image/")):
            return u
        return None
    if low.startswith(("http://", "https://", "mailto:", "#", "/")):
        return u
    if ":" not in u.split("/")[0]:          # relatif (tugas.md, gambar/x.png)
        return u
    return None


class Sanitizer(HTMLParser):
    """Nyaring HTML hasil markdown — daptar bodas tag + atribut."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_CONTENT:
            self.skip_depth += 1
            return
        if self.skip_depth or tag not in ALLOWED_TAGS:
            return
        allow = ALLOWED_ATTRS.get(tag, set())
        keep = []
        for k, v in attrs:
            k = (k or "").lower()
            if k.startswith("on") or k not in allow or v is None:
                continue
            if k in ("href", "src"):
                v = _safe_url(v, "img" if k == "src" else "link")
                if v is None:
                    continue
            keep.append((k, v))
        if tag == "a":
            href = dict(keep).get("href", "")
            if href.startswith(("http://", "https://")):
                keep += [("target", "_blank"), ("rel", "noopener noreferrer")]
        if tag == "img":
            keep += [("loading", "lazy"), ("decoding", "async")]
        attr = "".join(f' {k}="{html.escape(str(v), quote=True)}"' for k, v in keep)
        self.out.append(f"<{tag}{attr}>" if tag not in VOID else f"<{tag}{attr} />")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in DROP_CONTENT:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth or tag not in ALLOWED_TAGS or tag in VOID:
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self.skip_depth:
            return
        self.out.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        if not self.skip_depth:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if not self.skip_depth:
            self.out.append(f"&#{name};")

    def result(self):
        return "".join(self.out).strip()


def bersihkan(html_text):
    p = Sanitizer()
    p.feed(html_text)
    p.close()
    return p.result()


# ---------------------------------------------------------------- tulisan

def slugify(teks):
    t = unicodedata.normalize("NFKD", teks).encode("ascii", "ignore").decode()
    t = re.sub(r"[^\w\s-]", "", t).strip().lower()
    return re.sub(r"[-\s]+", "-", t)[:60] or "tulisan"


def parse_post(path, nama):
    raw = open(path, encoding="utf-8").read()
    meta, body = {}, raw
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", raw, re.S)
    if m:
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except Exception as e:
            print(f"  ! frontmatter ruksak dina {nama}: {e}", file=sys.stderr)
            meta = {}
        body = m.group(2)

    judul = str(meta.get("title") or nama).strip()
    tgl_raw = str(meta.get("date") or "")
    m2 = re.match(r"(\d{4})-(\d{2})-(\d{2})", tgl_raw)
    if not m2:                                    # fallback: tina ngaran berkas
        m2 = re.match(r"(\d{4})-(\d{2})-(\d{2})", nama)
    tanggal = datetime(int(m2.group(1)), int(m2.group(2)), int(m2.group(3))) if m2 else datetime.now()
    slug = str(meta.get("slug") or re.sub(r"^\d{4}-\d{2}-\d{2}-", "", nama[:-3]))
    slug = slugify(slug)
    lang = str(meta.get("lang") or "id").lower()[:2]
    if lang not in ("id", "en", "su"):
        lang = "id"

    isi = bersihkan(markdown.markdown(body, extensions=["extra", "sane_lists", "toc"], output_format="html5"))
    teks = re.sub(r"<[^>]+>", " ", isi)
    teks = html.unescape(re.sub(r"\s+", " ", teks)).strip()
    ringkas = str(meta.get("excerpt") or "").strip() or (teks[:180].rsplit(" ", 1)[0] + "…" if len(teks) > 180 else teks)
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    return {
        "judul": judul, "tanggal": tanggal, "slug": slug, "lang": lang,
        "ringkas": ringkas, "tags": [str(t) for t in tags], "isi": isi,
        "cover": meta.get("cover") or "", "draft": bool(meta.get("draft")), "berkas": nama,
        "pair": str(meta.get("pair") or "").strip(),
        "series": str(meta.get("series") or "").strip(),
        "series_title": str(meta.get("series_title") or "").strip(),
        "part": int(meta.get("part") or 0),
        "menit": max(1, round(len(teks.split()) / 200)),
    }


# ---------------------------------------------------------------- tarjamahan UI blog

UI = {
    "id": {"blog": "Blog", "tagline": "Tulisan ringkas soal pekerjaan, organisasi, dan cara memakai asisten AI.",
           "latest": "Tulisan terbaru", "read": "Baca", "back": "← Kembali ke daftar tulisan", "home": "Beranda",
           "min": "menit baca", "newer": "Lebih baru", "older": "Lebih lama", "empty": "Tulisan pertama sedang disiapkan.",
           "skip": "Lompat ke tulisan", "feed": "RSS", "navblog": "Blog", "kontak": "Email",
           "prev": "Sebelumnya", "next": "Berikutnya", "page": "Halaman", "of": "dari",
           "series": "Seri", "part": "Bagian", "allparts": "Semua bagian", "prevpart": "← Bagian sebelumnya",
           "nextpart": "Bagian berikutnya →", "allposts": "Semua tulisan", "langlabel": "Baca dalam bahasa lain"},
    "en": {"blog": "Blog", "tagline": "Short pieces on work, organisations, and using an AI assistant.",
           "latest": "Latest posts", "read": "Read", "back": "← Back to all posts", "home": "Home",
           "min": "min read", "newer": "Newer", "older": "Older", "empty": "The first post is being prepared.",
           "skip": "Skip to content", "feed": "RSS", "navblog": "Blog", "kontak": "Email",
           "prev": "Previous", "next": "Next", "page": "Page", "of": "of",
           "series": "Series", "part": "Part", "allparts": "All parts", "prevpart": "← Previous part",
           "nextpart": "Next part →", "allposts": "All posts", "langlabel": "Read in another language"},
    "su": {"blog": "Blog", "tagline": "Tulisan ringkes ngeunaan pagawéan, organisasi, jeung cara maké asisten AI.",
           "latest": "Tulisan panganyarna", "read": "Baca", "back": "← Balik ka daptar tulisan", "home": "Beranda",
           "min": "menit maca", "newer": "Leuwih anyar", "older": "Leuwih lami", "empty": "Tulisan munggaran nuju disiapkeun.",
           "skip": "Luncat ka eusi", "feed": "RSS", "navblog": "Blog", "kontak": "Email",
           "prev": "Saméméhna", "next": "Salanjutna", "page": "Kaca", "of": "ti",
           "series": "Seri", "part": "Bagian", "allparts": "Sadaya bagian", "prevpart": "← Bagian saméméhna",
           "nextpart": "Bagian salanjutna →", "allposts": "Sadaya tulisan", "langlabel": "Baca dina basa séjén"},
}

HEADER = """<a class="skip" href="#main" data-blog="skip">{skip}</a>
<header class="site-header">
  <div class="wrap">
    <a class="brand" href="/" aria-label="Utsman">
      <svg class="brand-mark" viewBox="0 0 32 32" role="img" aria-hidden="true">
        <circle cx="16" cy="16" r="15" fill="#101c33"/>
        <path d="M16 6c1.9 2.2 2.8 4.6 2.8 7.4 0 3-1 5.6-2.8 7.7-1.8-2.1-2.8-4.7-2.8-7.7C13.2 10.6 14.1 8.2 16 6z" fill="#e3c675"/>
        <circle cx="16" cy="24.6" r="2.1" fill="#b98b1e"/>
      </svg>
      <span class="brand-name">Utsman</span>
    </a>
    <nav class="nav">
      <a href="/" data-blog="home">{home}</a>
      <a href="/blog/" class="is-here" data-blog="navblog">{blog}</a>
      <div class="lang-switch" role="group" aria-label="Pilih bahasa">
        <button type="button" class="lang-btn is-on" data-lang="id" aria-pressed="true" title="Bahasa Indonesia">ID</button>
        <button type="button" class="lang-btn" data-lang="en" aria-pressed="false" title="English">EN</button>
        <button type="button" class="lang-btn" data-lang="su" aria-pressed="false" title="Bahasa Sunda">SU</button>
      </div>
      <a href="/blog/feed.xml" class="nav-cta" data-blog="feed">{feed}</a>
    </nav>
  </div>
</header>"""

FOOTER = """<footer class="site-footer">
  <div class="wrap">
    <p>© 2026 Utsman · utsman.works</p>
    <div class="foot-links">
      <a href="/" data-blog="home">{home}</a>
      <a href="/blog/" data-blog="navblog">{blog}</a>
      <a href="mailto:bahzimadina@gmail.com?subject=Utsman.works%20—%20blog">{kontak}</a>
    </div>
  </div>
</footer>
<script>window.BLOG_UI = {ui_json};</script>
<script>window.BLOG_ALTS = {alts_js};</script>
<script src="/blog/blog.js?v=2" defer></script>
</body>
</html>"""

CSS = """/* Blog utsman.works — nambihan gaya di luhur /css/style.css */
.blog-hero { padding: 56px 0 8px; }
.blog-hero h1 { margin-bottom: 10px; }
.blog-hero p { color: var(--muted); font-size: 17.5px; max-width: 38em; margin: 0; }
.blog-list { padding: 34px 0 72px; }
.post-card {
  display: block; background: var(--card); border: 1px solid var(--line); border-radius: var(--radius-lg);
  padding: 26px 28px; box-shadow: var(--shadow-sm); margin-bottom: 18px;
  transition: transform .18s ease, box-shadow .18s ease;
}
.post-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); }
.post-card h2 { font-size: clamp(22px, 2.6vw, 28px); margin: 0 0 8px; }
.post-card p { margin: 0 0 14px; color: var(--muted); }
.post-meta { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; font-size: 14px; color: var(--muted); }
.badge { font-size: 12px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  background: var(--gold-wash); color: var(--gold); border: 1px solid #efe2c2; border-radius: 999px; padding: 4px 10px; }
.tagset { display: flex; flex-wrap: wrap; gap: 8px; }
.tag { font-size: 13px; color: var(--ink-soft); border: 1px solid var(--line); background: var(--cream);
  border-radius: 999px; padding: 3px 10px; }
.nav .is-here { color: var(--ink); font-weight: 650; }

.post { padding: 48px 0 72px; }
.post-head { max-width: 42em; margin-bottom: 30px; }
.post-head h1 { margin-bottom: 12px; }
.post-body { max-width: 42em; font-size: 17.5px; }
.post-body h2 { margin: 40px 0 12px; font-size: clamp(22px, 2.6vw, 28px); }
.post-body h3 { margin: 30px 0 10px; font-size: 20px; }
.post-body p, .post-body li { color: var(--ink-soft); }
.post-body ul, .post-body ol { padding-left: 24px; }
.post-body li { margin-bottom: 8px; }
.post-body blockquote {
  margin: 22px 0; padding: 12px 20px; border-left: 3px solid var(--gold-soft);
  background: #fff; border-radius: 0 12px 12px 0; color: var(--ink); font-style: italic;
}
.post-body code { background: var(--gold-wash); border-radius: 6px; padding: 2px 6px; font-size: 15px; }
.post-body pre { background: #101c33; color: #eef1f7; padding: 18px 20px; border-radius: 14px; overflow-x: auto; }
.post-body pre code { background: none; color: inherit; padding: 0; }
.post-body img { border-radius: 14px; box-shadow: var(--shadow-sm); margin: 8px 0; }
.post-body table { width: 100%; border-collapse: collapse; margin: 18px 0; font-size: 16px; }
.post-body th, .post-body td { border: 1px solid var(--line); padding: 10px 12px; text-align: left; }
.post-body th { background: var(--gold-wash); }
.post-body a { color: var(--gold); border-bottom: 1px solid var(--gold-soft); }
.post-foot { max-width: 42em; margin-top: 44px; padding-top: 24px; border-top: 1px solid var(--line); }
.post-nav { display: flex; flex-wrap: wrap; gap: 16px; justify-content: space-between; margin-top: 18px; font-size: 15.5px; }
@media (max-width: 640px) { .post-card { padding: 22px 20px; } }

/* paginasi */
.pagination { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 26px; }
.page-btn {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 40px; height: 40px; padding: 0 14px; border-radius: 999px;
  border: 1px solid var(--line); background: #fff; color: var(--ink-soft);
  font-size: 15px; font-weight: 600; box-shadow: var(--shadow-sm);
}
.page-btn:hover { color: var(--ink); transform: translateY(-1px); }
.page-btn.is-on { background: var(--ink); border-color: var(--ink); color: #fff; }
.page-btn.is-off { opacity: .45; box-shadow: none; }

/* seri */
.badge-seri { background: var(--ink); color: var(--gold-soft); border-color: var(--ink); }
.seri-box { background: #fff; border: 1px solid var(--line); border-radius: var(--radius-lg);
  padding: 20px 22px; margin-bottom: 26px; box-shadow: var(--shadow-sm); }
.seri-box h2 { font-size: 17px; margin: 0 0 12px; }
.seri-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.seri-item { display: flex; flex-direction: column; gap: 2px; padding: 12px 14px; border: 1px solid var(--line);
  border-radius: 12px; background: var(--cream); font-size: 15px; }
.seri-item span { color: var(--muted); font-size: 13.5px; }
.seri-bar { margin: 16px 0 0; display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center;
  padding: 12px 16px; background: var(--gold-wash); border: 1px solid #efe2c2; border-radius: 14px; font-size: 15px; }
.seri-nav { display: flex; flex-wrap: wrap; gap: 14px; }
"""

JS = """// Blog utsman.works — basa UI + format tanggal (ngabagi setelan jeung situs utama)
(function () {
  var UI = window.BLOG_UI || {};
  var LANGS = ['id', 'en', 'su'];
  function norm(v) { if (!v) return null; var s = String(v).slice(0,2).toLowerCase(); if (s==='in') s='id'; return LANGS.indexOf(s)>=0?s:null; }
  function pick() {
    var q = null; try { q = norm(new URLSearchParams(location.search).get('lang')); } catch(e) {}
    var st = null; try { st = norm(localStorage.getItem('utsman-lang')); } catch(e) {}
    return q || st || 'id';
  }
  function apply(lang) {
    var d = UI[lang] || UI.id; if (!d) return;
    document.documentElement.setAttribute('lang', lang);
    document.querySelectorAll('[data-blog]').forEach(function (el) {
      var k = el.getAttribute('data-blog');
      if (d[k]) el.textContent = d[k];
    });
    var loc = { id: 'id-ID', en: 'en-GB', su: 'id-ID' }[lang] || 'id-ID';
    document.querySelectorAll('time[data-post-date]').forEach(function (t) {
      var raw = t.getAttribute('datetime'); if (!raw) return;
      var dt = new Date(raw + 'T00:00:00');
      if (isNaN(dt)) return;
      try { t.textContent = new Intl.DateTimeFormat(loc, { day: 'numeric', month: 'long', year: 'numeric' }).format(dt); }
      catch (e) {}
    });
  }
  function tandaan(lang) {
    try { localStorage.setItem('utsman-lang', lang); } catch (e) {}
    try {
      var u = new URL(location.href);
      if (lang === 'id') u.searchParams.delete('lang'); else u.searchParams.set('lang', lang);
      history.replaceState(null, '', u.pathname + (u.search ? u.search : '') + u.hash);
    } catch (e) {}
  }
  function tombol(lang) {
    document.querySelectorAll('.lang-btn').forEach(function (b) {
      var on = b.getAttribute('data-lang') === lang;
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.classList.toggle('is-on', on);
    });
  }
  var lang = pick();
  apply(lang); tombol(lang);
  document.querySelectorAll('.lang-btn').forEach(function (b) {
    b.addEventListener('click', function () {
      var l = norm(b.getAttribute('data-lang')) || 'id';
      var alts = window.BLOG_ALTS || {};
      tandaan(l);
      // Upami kaca ieu boga vérsi dina basa éta → pindah ka dinya (eusi robah)
      if (alts[l] && alts[l] !== location.pathname) { location.href = alts[l]; return; }
      apply(l); tombol(l);
    });
  });
  window.addEventListener('storage', function (e) { if (e.key === 'utsman-lang') { var l = norm(e.newValue) || 'id'; apply(l); tombol(l); } });
})();
"""


# ---------------------------------------------------------------- kaca

UKURAN_KACA = 5          # 5 artikel per halaman
OG_LOCALE = {"id": "id_ID", "en": "en_US", "su": "su_ID"}
BASA_URUT = ["id", "en", "su"]


def url_index(lang, page=1):
    dasar = "/blog/" if lang == "id" else f"/blog/{lang}/"
    return dasar if page == 1 else f"{dasar}{page}/"


def url_seri(lang, slug, page=1):
    dasar = f"/blog/seri/{slug}/" if lang == "id" else f"/blog/{lang}/seri/{slug}/"
    return dasar if page == 1 else f"{dasar}{page}/"


def kaca(judul, deskripsi, kanonik, eusi, ui, lang="id", ld=None, tambahan="", alts=None):
    ld = ld or {}
    alts = alts or {}
    jam = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>' if ld else ""
    # hreflang: unggal basa + x-default ka basa Indonésia
    alt = "".join(f'\n<link rel="alternate" hreflang="{l}" href="{SITE}{alts[l]}">'
                  for l in BASA_URUT if l in alts and l != lang)
    alt += f'\n<link rel="alternate" hreflang="{lang}" href="{kanonik}">'
    if "id" in alts:
        alt += f'\n<link rel="alternate" hreflang="x-default" href="{SITE}{alts["id"]}">'
    og_type = "article" if ld.get("@type") == "BlogPosting" else "website"
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(judul)}</title>
<meta name="description" content="{html.escape(deskripsi)}">
<link rel="canonical" href="{kanonik}">
<link rel="alternate" type="application/rss+xml" title="Blog Utsman" href="{SITE}/blog/feed.xml">
<meta name="theme-color" content="#101c33">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="Utsman">
<meta property="og:url" content="{kanonik}">
<meta property="og:title" content="{html.escape(judul)}">
<meta property="og:description" content="{html.escape(deskripsi)}">
<meta property="og:image" content="{SITE}/assets/og-image.png">
<meta property="og:locale" content="{OG_LOCALE.get(lang, 'id_ID')}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(judul)}">
<meta name="twitter:description" content="{html.escape(deskripsi)}">
<meta name="twitter:image" content="{SITE}/assets/og-image.png">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/css/style.css?v={CSS_VER}">
<link rel="stylesheet" href="/blog/blog.css?v=3">
{jam}{alt}
{tambahan}
</head>
<body>
{HEADER.format(**ui)}
<main id="main">
{eusi}
</main>
{FOOTER.format(ui_json=json.dumps(UI, ensure_ascii=False), alts_js=json.dumps(alts, ensure_ascii=False), **ui)}
"""


def tgl_id(dt):
    bulan = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
             "Agustus", "September", "Oktober", "November", "Desember"]
    return f"{dt.day} {bulan[dt.month]} {dt.year}"


def lencana_seri(p):
    if not p.get("series"):
        return ""
    return (f'<span class="badge badge-seri"><span data-blog="series">Seri</span> · '
            f'<span data-blog="part">Bagian</span> {p["part"] or 1}</span>')


def kartu(p):
    tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in p["tags"])
    return f"""      <a class="post-card" href="/blog/{p['slug']}/">
        <h2>{html.escape(p['judul'])}</h2>
        <div class="post-meta">
          <time datetime="{p['tanggal']:%Y-%m-%d}" data-post-date>{tgl_id(p['tanggal'])}</time>
          <span class="badge">{p['lang']}</span>
          {lencana_seri(p)}
          <span>· {p['menit']} <span data-blog="min">menit baca</span></span>
        </div>
        <p>{html.escape(p['ringkas'])}</p>
        {f'<div class="tagset">{tags}</div>' if tags else ''}
      </a>"""


JUDUL_BASA = {"id": "Blog", "en": "Blog", "su": "Blog"}
DESK_BASA = {
    "id": "Tulisan ringkas soal pekerjaan kantor, urusan pribadi, dan organisasi — serta cara memakai asisten AI.",
    "en": "Short pieces on office work, personal matters, and organisations — plus how to use an AI assistant.",
    "su": "Tulisan ringkes ngeunaan pagawéan kantor, urusan pribadi, jeung organisasi — sarta cara maké asisten AI.",
}


def paginasi(lang, page_no, total, ui):
    """Tautan pindah halaman (saméméhna / angka / salanjutna)."""
    if total <= 1:
        return ""
    no = []
    for i in range(1, total + 1):
        if i == page_no:
            no.append(f'<span class="page-btn is-on" aria-current="page">{i}</span>')
        else:
            no.append(f'<a class="page-btn" href="{url_index(lang, i)}">{i}</a>')
    kiri = (f'<a class="page-btn" href="{url_index(lang, page_no - 1)}" data-blog="prev">Sebelumnya</a>'
            if page_no > 1 else '<span class="page-btn is-off" data-blog="prev">Sebelumnya</span>')
    kanan = (f'<a class="page-btn" href="{url_index(lang, page_no + 1)}" data-blog="next">Berikutnya</a>'
             if page_no < total else '<span class="page-btn is-off" data-blog="next">Berikutnya</span>')
    return (f'<nav class="pagination" aria-label="{ui.get("page", "Halaman")}">'
            f'{kiri}{"".join(no)}{kanan}</nav>')


def halaman_daftar(daftar, lang, page_no, total, semua, ui):
    potongan = daftar[(page_no - 1) * UKURAN_KACA: page_no * UKURAN_KACA]
    alts = {l: url_index(l, min(page_no, max(1, -(-len([q for q in semua if q["lang"] == l]) // UKURAN_KACA))))
            for l in BASA_URUT}
    judul = JUDUL_BASA[lang] + (f" — {ui['page']} {page_no}" if page_no > 1 else "")
    seri_tbl = ""
    if page_no == 1:
        # daptar seri (upami aya) dina basa ieu
        grup = {}
        for q in semua:
            if q["lang"] == lang and q.get("series"):
                grup.setdefault(q["series"], {"judul": q.get("series_title") or q["series"], "n": 0})
                grup[q["series"]]["n"] += 1
        if grup:
            item = "".join(f'<a class="seri-item" href="{url_seri(lang, sl)}">'
                           f'<strong>{html.escape(v["judul"])}</strong>'
                           f'<span>{v["n"]} <span data-blog="part">Bagian</span></span></a>'
                           for sl, v in grup.items())
            seri_tbl = (f'<div class="seri-box"><h2 data-blog="series">Seri</h2>'
                        f'<div class="seri-grid">{item}</div></div>')
    isi = f"""  <section class="blog-hero">
    <div class="wrap">
      <h1 data-blog="blog">Blog</h1>
      <p data-blog="tagline">{ui['tagline']}</p>
    </div>
  </section>
  <section class="blog-list">
    <div class="wrap">
      {seri_tbl}
      <h2 style="font-size:20px;margin:0 0 18px" data-blog="latest">{ui['latest']}</h2>
{chr(10).join(kartu(p) for p in potongan) if potongan else f'      <p class="post-meta" data-blog="empty">{ui["empty"]}</p>'}
      {paginasi(lang, page_no, total, ui)}
    </div>
  </section>"""
    ld = {"@context": "https://schema.org", "@type": "Blog", "name": "Blog Utsman",
          "url": f"{SITE}{url_index(lang, page_no)}", "inLanguage": lang,
          "blogPost": [{"@type": "BlogPosting", "headline": q["judul"],
                        "url": f"{SITE}/blog/{q['slug']}/",
                        "datePublished": q["tanggal"].strftime("%Y-%m-%d"),
                        "inLanguage": q["lang"]} for q in potongan[:10]]}
    return kaca(f"{judul} — Utsman", DESK_BASA[lang], f"{SITE}{url_index(lang, page_no)}",
                isi, ui, lang=lang, ld=ld, alts=alts)


def halaman_tulisan(p, prev_p, next_p, lain, seri, ui):
    tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in p["tags"])
    alts = {q["lang"]: f"/blog/{q['slug']}/" for q in [p] + (lain or [])}

    # tautan basa (sadaya vérsi anu aya)
    LABEL_KE = {
        ("id", "en"): "Baca vérsi basa Inggris",
        ("id", "su"): "Baca vérsi basa Sunda",
        ("en", "id"): "Read in Indonesian",
        ("en", "su"): "Read in Sundanese",
        ("su", "id"): "Baca vérsi basa Indonésia",
        ("su", "en"): "Baca vérsi basa Inggris",
    }
    NAMA_BASA = {"id": "Bahasa Indonesia", "en": "English", "su": "Basa Sunda"}
    bagian_basa = ""
    if alts and len(alts) > 1:
        kel = " · ".join(f'<a href="/blog/{q["slug"]}/">{LABEL_KE.get((p["lang"], q["lang"]), "Baca vérsi " + NAMA_BASA[q["lang"]])}</a>'
                         for q in lain or [])
        bagian_basa = (f'<p class="post-lang" style="margin:14px 0 0;font-size:15.5px">'
                       f'<span data-blog="langlabel">Baca dalam bahasa lain</span>: {kel}</p>')

    # bagian seri
    bagian_seri = ""
    if seri and seri.get("slug"):
        total = seri.get("total", 1)
        potongan = " · ".join(t for t in [
            f'<a href="/blog/{seri["sblm"]["slug"]}/" data-blog="prevpart">← Bagian sebelumnya</a>' if seri.get("sblm") else "",
            f'<a href="{url_seri(p["lang"], seri["slug"])}" data-blog="allparts">Semua bagian</a>',
            f'<a href="/blog/{seri["saurna"]["slug"]}/" data-blog="nextpart">Bagian berikutnya →</a>' if seri.get("saurna") else "",
        ] if t)
        bagian_seri = (f'<div class="seri-bar"><span class="badge badge-seri">'
                       f'<span data-blog="series">Seri</span>: {html.escape(seri.get("judul") or seri["slug"])} · '
                       f'<span data-blog="part">Bagian</span> {p["part"] or 1} / {total}</span>'
                       f'<span class="seri-nav">{potongan}</span></div>')

    nav = ""
    if next_p or prev_p:
        kiri = f'<a href="/blog/{next_p["slug"]}/" data-blog="newer">Lebih baru</a> → {html.escape(next_p["judul"])}' if next_p else ""
        kanan = f'← {html.escape(prev_p["judul"])}' if prev_p else ""
        nav = f'<div class="post-nav"><span>{kiri}</span><span>{kanan}</span></div>'
    cover = (f'<img src="{html.escape(str(p["cover"]))}" alt="" width="1200" height="630" '
             f'style="width:100%;height:auto;border-radius:16px;margin-bottom:26px">') if p["cover"] else ""
    isi = f"""  <article class="post">
    <div class="wrap">
      <div class="post-head">
        <div class="post-meta">
          <time datetime="{p['tanggal']:%Y-%m-%d}" data-post-date>{tgl_id(p['tanggal'])}</time>
          <span class="badge">{p['lang']}</span>
          <span>· {p['menit']} <span data-blog="min">menit baca</span></span>
        </div>
        <h1 style="margin-top:14px">{html.escape(p['judul'])}</h1>
        {bagian_basa}
        {bagian_seri}
        {cover}
      </div>
      <div class="post-body">
{p['isi']}
      </div>
      <div class="post-foot">
        {f'<div class="tagset">{tags}</div>' if tags else ''}
        <p style="margin:18px 0 0"><a href="{url_index(p['lang'], 1)}" data-blog="back">← Kembali ke daftar tulisan</a></p>
        {nav}
      </div>
    </div>
  </article>"""
    ld = {"@context": "https://schema.org", "@type": "BlogPosting", "headline": p["judul"],
          "description": p["ringkas"], "datePublished": p["tanggal"].strftime("%Y-%m-%d"),
          "inLanguage": p["lang"], "mainEntityOfPage": f"{SITE}/blog/{p['slug']}/",
          "author": {"@type": "Organization", "name": "Utsman", "url": SITE},
          "publisher": {"@type": "Organization", "name": "Utsman",
                        "logo": {"@type": "ImageObject", "url": f"{SITE}/assets/favicon.svg"}},
          "image": p["cover"] or f"{SITE}/assets/og-image.png"}
    if p["tags"]:
        ld["keywords"] = ", ".join(p["tags"])
    if seri and seri.get("slug"):
        ld["isPartOf"] = {"@type": "CreativeWorkSeries", "name": seri.get("judul") or seri["slug"],
                          "url": f"{SITE}{url_seri(p['lang'], seri['slug'])}"}
    return kaca(f"{p['judul']} — Blog Utsman", p["ringkas"], f"{SITE}/blog/{p['slug']}/", isi, ui,
                lang=p["lang"], ld=ld, alts=alts)


def halaman_seri(slug, judul, bagian, lang, ui, halaman=1):
    total = len(bagian)
    potongan = bagian[(halaman - 1) * UKURAN_KACA:halaman * UKURAN_KACA]
    alts = {}
    for l in BASA_URUT:
        alts[l] = url_seri(l, slug)
    isi = f"""  <section class="blog-hero">
    <div class="wrap">
      <p class="badge badge-seri" style="display:inline-block"><span data-blog="series">Seri</span></p>
      <h1 style="margin-top:14px">{html.escape(judul)}</h1>
      <p>{total} <span data-blog="part">Bagian</span></p>
    </div>
  </section>
  <section class="blog-list">
    <div class="wrap">
{chr(10).join(kartu(p) for p in potongan)}
    </div>
  </section>"""
    ld = {"@context": "https://schema.org", "@type": "CreativeWorkSeries", "name": judul,
          "url": f"{SITE}{url_seri(lang, slug)}", "inLanguage": lang,
          "hasPart": [{"@type": "BlogPosting", "headline": q["judul"], "position": q["part"],
                       "url": f"{SITE}/blog/{q['slug']}/"} for q in bagian]}
    return kaca(f"{judul} — Utsman", f"Seri {judul}: {total} bagian.", f"{SITE}{url_seri(lang, slug)}",
                isi, ui, lang=lang, ld=ld, alts=alts)


def sitemap(hasil_url, grup_basa):
    baris = []
    for u in hasil_url:
        alt = "".join(f'\n    <xhtml:link rel="alternate" hreflang="{l}" href="{SITE}{grup_basa[u][l]}"/>'
                      for l in BASA_URUT if l in grup_basa.get(u, {}))
        if "id" in grup_basa.get(u, {}):
            alt += f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{SITE}{grup_basa[u]["id"]}"/>'
        baris.append(f'  <url><loc>{SITE}{u}</loc><lastmod>{TANGGAL_BUILD}</lastmod>{alt}\n  </url>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + "\n".join(baris) + "\n</urlset>\n")


def feed(posts, lang, ui):
    dasar = posts[0]["tanggal"] if posts else datetime.now()
    now = dasar.strftime("%a, %d %b %Y 07:00:00 +0700")
    item = "\n".join(f"""    <item>
      <title>{html.escape(p['judul'])}</title>
      <link>{SITE}/blog/{p['slug']}/</link>
      <guid isPermaLink="true">{SITE}/blog/{p['slug']}/</guid>
      <pubDate>{p['tanggal'].strftime('%a, %d %b %Y 07:00:00 +0700')}</pubDate>
      <description>{html.escape(p['ringkas'])}</description>
    </item>""" for p in posts[:30])
    judul = {"id": "Blog Utsman", "en": "Utsman Blog", "su": "Blog Utsman"}[lang]
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>{judul}</title>
  <link>{SITE}{url_index(lang, 1)}</link>
  <description>{html.escape(ui['tagline'])}</description>
  <language>{lang}</language>
  <lastBuildDate>{now}</lastBuildDate>
{item}
</channel></rss>
"""


TANGGAL_BUILD = ""


def main():
    global TANGGAL_BUILD
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    folder = os.path.join(a.repo, "posts")
    if not os.path.isdir(folder):
        print(f"! folder posts teu kapendak di {a.repo}", file=sys.stderr)
        return 2

    posts, dilewatan = [], []
    for nama in sorted(os.listdir(folder)):
        if not nama.endswith(".md") or nama.startswith("."):
            continue
        try:
            q = parse_post(os.path.join(folder, nama), nama)
        except Exception as e:
            print(f"! {nama} gagal diolah: {e}", file=sys.stderr)
            continue
        (dilewatan if q["draft"] else posts).append(q)
    posts.sort(key=lambda q: (q["tanggal"], q["berkas"]), reverse=True)
    TANGGAL_BUILD = (posts[0]["tanggal"] if posts else datetime.now()).strftime("%Y-%m-%d")

    # grup tarjamahan (pair) jeung seri
    grup_pair, grup_seri = {}, {}
    for q in posts:
        if q["pair"]:
            grup_pair.setdefault(q["pair"], []).append(q)
        if q.get("series"):
            grup_seri.setdefault((q["series"], q["lang"]), []).append(q)

    hasil, kunci_url, grup_basa = {}, [], {}

    # ---- kaca daptar per basa, dibagi 5 per halaman
    for lang in BASA_URUT:
        daftar = [q for q in posts if q["lang"] == lang]
        total = max(1, -(-len(daftar) // UKURAN_KACA))
        for hal in range(1, total + 1):
            path = f"{url_index(lang, hal).lstrip('/')}index.html"
            hasil[path] = halaman_daftar(daftar, lang, hal, total, posts, UI[lang])
            kunci = url_index(lang, hal)
            kunci_url.append(kunci)
            grup_basa[kunci] = {l: url_index(l, min(hal, max(1, -(-len([z for z in posts if z["lang"] == l]) // UKURAN_KACA))))
                                for l in BASA_URUT}
        # RSS per basa
        hasil[f"{url_index(lang, 1).lstrip('/')}feed.xml"] = feed(daftar, lang, UI[lang])

    # ---- kaca tulisan
    for i, q in enumerate(posts):
        lain = [z for z in grup_pair.get(q["pair"], []) if z is not q] if q["pair"] else []
        seri_info = {}
        if q.get("series"):
            bagian = sorted(grup_seri[(q["series"], q["lang"])], key=lambda z: (z["part"] or 1, z["tanggal"]))
            idx = next((n for n, z in enumerate(bagian) if z is q), 0)
            seri_info = {"slug": q["series"], "judul": q.get("series_title") or q["series"],
                         "total": len(bagian),
                         "sblm": bagian[idx - 1] if idx > 0 else None,
                         "saurna": bagian[idx + 1] if idx + 1 < len(bagian) else None}
        hasil[f"{q['slug']}/index.html"] = halaman_tulisan(
            q, posts[i + 1] if i + 1 < len(posts) else None, posts[i - 1] if i > 0 else None, lain, seri_info, UI[q["lang"]])
        kunci = f"/blog/{q['slug']}/"
        kunci_url.append(kunci)
        grup_basa[kunci] = {z["lang"]: f"/blog/{z['slug']}/" for z in [q] + lain}

    # ---- kaca seri per basa
    seri_urut = sorted({s for (s, _l) in grup_seri})
    for slug in seri_urut:
        for lang in BASA_URUT:
            bagian = sorted(grup_seri.get((slug, lang), []), key=lambda z: (z["part"] or 1, z["tanggal"]))
            if not bagian:
                continue
            judul = bagian[0].get("series_title") or slug
            hal_total = max(1, -(-len(bagian) // UKURAN_KACA))
            for hal in range(1, hal_total + 1):
                path = f"{url_seri(lang, slug, hal).lstrip('/')}index.html"
                hasil[path] = halaman_seri(slug, judul, bagian, lang, UI[lang], hal)
            kunci = url_seri(lang, slug)
            kunci_url.append(kunci)
            grup_basa[kunci] = {l: url_seri(l, slug) for l in BASA_URUT if grup_seri.get((slug, l))}

    # ---- sitemap
    hasil["sitemap.xml"] = sitemap(kunci_url, grup_basa)
    hasil["blog.css"] = CSS
    hasil["blog.js"] = JS

    sidik = hashlib.sha256(json.dumps({k: v for k, v in sorted(hasil.items())}).encode()).hexdigest()
    berkas_sidik = os.path.join(a.out, ".build-hash")
    sidik_lama = open(berkas_sidik).read().strip() if os.path.exists(berkas_sidik) else ""

    src_img = os.path.join(a.repo, "images")
    if os.path.isdir(src_img):
        os.makedirs(os.path.join(a.out, "images"), exist_ok=True)
        for f in os.listdir(src_img):
            if not f.startswith("."):
                shutil.copy2(os.path.join(src_img, f), os.path.join(a.out, "images", f))

    if sidik == sidik_lama and not a.verbose:
        return 0

    # bersihkeun kaca anu tos teu aya (nurut struktur polder)
    if os.path.isdir(a.out):
        dijaga = {os.path.dirname(p) for p in hasil if p.endswith("index.html")}
        leluhur = set()
        for p in dijaga:
            bagian = p.split("/")
            for n in range(1, len(bagian) + 1):
                leluhur.add("/".join(bagian[:n]))
        dijaga |= leluhur | {"images", ""}
        for root, dirs, _files in os.walk(a.out, topdown=False):
            rel = os.path.relpath(root, a.out)
            if rel != "." and rel not in dijaga:
                shutil.rmtree(root, ignore_errors=True)

    for path, isi in hasil.items():
        tujuan = os.path.join(a.out, path)
        os.makedirs(os.path.dirname(tujuan), exist_ok=True)
        open(tujuan, "w", encoding="utf-8").write(isi)
    open(berkas_sidik, "w").write(sidik)

    per_basa = {l: len([q for q in posts if q["lang"] == l]) for l in BASA_URUT}
    print(f"Blog diropéa: {len(posts)} tulisan ({', '.join(f'{k}: {v}' for k, v in per_basa.items())})"
          + (f", {len(dilewatan)} draf ditingaleun" if dilewatan else "")
          + f". Kaca: {len([k for k in kunci_url if k.startswith('/blog/') and 'seri' not in k and k.count('/') <= 3])} daptar"
          + f", {len(seri_urut)} seri, {len(posts)}+ tulisan.")
    for q in posts[:6]:
        print(f"  · {q['tanggal']:%Y-%m-%d} [{q['lang']}] {q['judul']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
