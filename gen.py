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
        "menit": max(1, round(len(teks.split()) / 200)),
    }


# ---------------------------------------------------------------- tarjamahan UI blog

UI = {
    "id": {"blog": "Blog", "tagline": "Tulisan ringkas soal pekerjaan, organisasi, dan cara memakai asisten AI.",
           "latest": "Tulisan terbaru", "read": "Baca", "back": "← Kembali ke daftar tulisan", "home": "Beranda",
           "min": "menit baca", "newer": "Lebih baru", "older": "Lebih lama", "empty": "Tulisan pertama sedang disiapkan.",
           "skip": "Lompat ke tulisan", "feed": "RSS", "navblog": "Blog", "kontak": "Email"},
    "en": {"blog": "Blog", "tagline": "Short pieces on work, organisations, and using an AI assistant.",
           "latest": "Latest posts", "read": "Read", "back": "← Back to all posts", "home": "Home",
           "min": "min read", "newer": "Newer", "older": "Older", "empty": "The first post is being prepared.",
           "skip": "Skip to content", "feed": "RSS", "navblog": "Blog", "kontak": "Email"},
    "su": {"blog": "Blog", "tagline": "Tulisan ringkes ngeunaan pagawéan, organisasi, jeung cara maké asisten AI.",
           "latest": "Tulisan panganyarna", "read": "Baca", "back": "← Balik ka daptar tulisan", "home": "Beranda",
           "min": "menit maca", "newer": "Leuwih anyar", "older": "Leuwih lami", "empty": "Tulisan munggaran nuju disiapkeun.",
           "skip": "Luncat ka eusi", "feed": "RSS", "navblog": "Blog", "kontak": "Email"},
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
      apply(l); tombol(l); tandaan(l);
    });
  });
  window.addEventListener('storage', function (e) { if (e.key === 'utsman-lang') { var l = norm(e.newValue) || 'id'; apply(l); tombol(l); } });
})();
"""


# ---------------------------------------------------------------- kaca

def kaca(judul, deskripsi, kanonik, eusi, ui, lang="id", ld=None, tambahan=""):
    ui = dict(ui)
    ld = ld or {}
    jam = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>' if ld else ""
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
<meta property="og:type" content="{'article' if ld.get('@type') == 'BlogPosting' else 'website'}">
<meta property="og:site_name" content="Utsman">
<meta property="og:url" content="{kanonik}">
<meta property="og:title" content="{html.escape(judul)}">
<meta property="og:description" content="{html.escape(deskripsi)}">
<meta property="og:image" content="{SITE}/assets/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(judul)}">
<meta name="twitter:description" content="{html.escape(deskripsi)}">
<meta name="twitter:image" content="{SITE}/assets/og-image.png">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<meta name="theme-color" content="#101c33">
<link rel="stylesheet" href="/css/style.css?v={CSS_VER}">
<link rel="stylesheet" href="/blog/blog.css?v=2">
{jam}
{tambahan}
</head>
<body>
{HEADER.format(**ui)}
<main id="main">
{eusi}
</main>
{FOOTER.format(ui_json=json.dumps(UI, ensure_ascii=False), **ui)}
"""


def tgl_id(dt):
    bulan = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
             "Agustus", "September", "Oktober", "November", "Desember"]
    return f"{dt.day} {bulan[dt.month]} {dt.year}"


def kartu(p):
    tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in p["tags"])
    return f"""      <a class="post-card" href="/blog/{p['slug']}/">
        <h2>{html.escape(p['judul'])}</h2>
        <div class="post-meta">
          <time datetime="{p['tanggal']:%Y-%m-%d}" data-post-date>{tgl_id(p['tanggal'])}</time>
          <span class="badge">{p['lang']}</span>
          <span>· {p['menit']} <span data-blog="min">menit baca</span></span>
        </div>
        <p>{html.escape(p['ringkas'])}</p>
        {f'<div class="tagset">{tags}</div>' if tags else ''}
      </a>"""


def halaman_daftar(posts, ui):
    isi = f"""  <section class="blog-hero">
    <div class="wrap">
      <h1 data-blog="blog">Blog</h1>
      <p data-blog="tagline">{ui['tagline']}</p>
    </div>
  </section>
  <section class="blog-list">
    <div class="wrap">
      <h2 style="font-size:20px;margin:0 0 18px" data-blog="latest">{ui['latest']}</h2>
{chr(10).join(kartu(p) for p in posts) if posts else f'      <p class="post-meta" data-blog="empty">{ui["empty"]}</p>'}
    </div>
  </section>"""
    ld = {"@context": "https://schema.org", "@type": "Blog", "name": "Blog Utsman",
          "url": f"{SITE}/blog/", "inLanguage": "id-ID",
          "blogPost": [{"@type": "BlogPosting", "headline": p["judul"],
                        "url": f"{SITE}/blog/{p['slug']}/",
                        "datePublished": p["tanggal"].strftime("%Y-%m-%d"),
                        "inLanguage": p["lang"]} for p in posts[:10]]}
    return kaca("Blog — Utsman", "Tulisan ringkas soal pekerjaan kantor, urusan pribadi, dan organisasi — serta cara memakai asisten AI.",
                f"{SITE}/blog/", isi, ui, ld=ld)


def halaman_tulisan(p, prev_p, next_p, ui, lain=None):
    tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in p["tags"])
    nav = ""
    if next_p or prev_p:
        kiri = f'<a href="/blog/{next_p["slug"]}/" data-blog="newer">Lebih baru</a> → {html.escape(next_p["judul"])}' if next_p else ""
        kanan = f'← {html.escape(prev_p["judul"])}' if prev_p else ""
        nav = f'<div class="post-nav"><span>{kiri}</span><span>{kanan}</span></div>'
    lain = lain or []
    # label tautan antarbasa, ditingali tina basa tulisan anu keur dibuka
    LABEL_KE = {
        ("id", "en"): "Baca vérsi basa Inggris",
        ("id", "su"): "Baca vérsi basa Sunda",
        ("en", "id"): "Read in Indonesian",
        ("en", "su"): "Read in Sundanese",
        ("su", "id"): "Baca vérsi basa Indonésia",
        ("su", "en"): "Baca vérsi basa Inggris",
    }
    NAMA_BASA = {"id": "Bahasa Indonesia", "en": "English", "su": "Basa Sunda"}
    tautan_basa = ""
    if lain:
        kel = " · ".join(
            f'<a href="/blog/{q["slug"]}/">{LABEL_KE.get((p["lang"], q["lang"]), "Baca vérsi " + NAMA_BASA[q["lang"]])}</a>'
            for q in lain)
        tautan_basa = f'<p class="post-lang" style="margin:14px 0 0;font-size:15.5px">{kel}</p>'
    alt = "".join(f'\n<link rel="alternate" hreflang="{q["lang"]}" href="{SITE}/blog/{q["slug"]}/">' for q in [p] + lain)
    alt += f'\n<link rel="alternate" hreflang="x-default" href="{SITE}/blog/{[q for q in [p] + lain if q["lang"] == "id"][0]["slug"] if any(q["lang"] == "id" for q in [p] + lain) else p["slug"]}/">'
    cover = f'<img src="{html.escape(str(p["cover"]))}" alt="" width="1200" height="630" style="width:100%;height:auto;border-radius:16px;margin-bottom:26px">' if p["cover"] else ""
    isi = f"""  <article class="post">
    <div class="wrap">
      <div class="post-head">
        <div class="post-meta">
          <time datetime="{p['tanggal']:%Y-%m-%d}" data-post-date>{tgl_id(p['tanggal'])}</time>
          <span class="badge">{p['lang']}</span>
          <span>· {p['menit']} <span data-blog="min">menit baca</span></span>
        </div>
        <h1 style="margin-top:14px">{html.escape(p['judul'])}</h1>
        {tautan_basa}
        {cover}
      </div>
      <div class="post-body">
{p['isi']}
      </div>
      <div class="post-foot">
        {f'<div class="tagset">{tags}</div>' if tags else ''}
        <p style="margin:18px 0 0"><a href="/blog/" data-blog="back">← Kembali ke daftar tulisan</a></p>
        {nav}
      </div>
    </div>
  </article>"""
    ld = {"@context": "https://schema.org", "@type": "BlogPosting", "headline": p["judul"],
          "description": p["ringkas"], "datePublished": p["tanggal"].strftime("%Y-%m-%d"),
          "inLanguage": p["lang"], "mainEntityOfPage": f"{SITE}/blog/{p['slug']}/",
          "author": {"@type": "Organization", "name": "Utsman", "url": SITE},
          "publisher": {"@type": "Organization", "name": "Utsman", "logo": {"@type": "ImageObject", "url": f"{SITE}/assets/favicon.svg"}},
          "image": p["cover"] or f"{SITE}/assets/og-image.png"}
    if p["tags"]:
        ld["keywords"] = ", ".join(p["tags"])
    return kaca(f"{p['judul']} — Blog Utsman", p["ringkas"], f"{SITE}/blog/{p['slug']}/", isi, ui,
                lang=p["lang"], ld=ld, tambahan=alt)


def sitemap(posts):
    tgl_index = (posts[0]["tanggal"] if posts else datetime.now()).strftime("%Y-%m-%d")
    baris = [f'  <url><loc>{SITE}/blog/</loc><lastmod>{tgl_index}</lastmod>'
             f'<changefreq>daily</changefreq><priority>0.8</priority></url>']
    grup = {}
    for p in posts:
        if p["pair"]:
            grup.setdefault(p["pair"], []).append(p)
    for p in posts:
        alt = ""
        for q in [p] + [x for x in grup.get(p["pair"], []) if x is not p]:
            alt += f'\n    <xhtml:link rel="alternate" hreflang="{q["lang"]}" href="{SITE}/blog/{q["slug"]}/"/>'
        baris.append(f'  <url><loc>{SITE}/blog/{p["slug"]}/</loc><lastmod>{p["tanggal"]:%Y-%m-%d}</lastmod>'
                     f'<changefreq>monthly</changefreq><priority>0.7</priority>{alt}\n  </url>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + "\n".join(baris) + "\n</urlset>\n")


def feed(posts, ui):
    # deterministik: maké tanggal tulisan panganyarna (sanes waktos kiwari)
    dasar = posts[0]["tanggal"] if posts else datetime.now()
    now = dasar.strftime("%a, %d %b %Y 07:00:00 +0700")
    item = "\n".join(f"""    <item>
      <title>{html.escape(p['judul'])}</title>
      <link>{SITE}/blog/{p['slug']}/</link>
      <guid isPermaLink="true">{SITE}/blog/{p['slug']}/</guid>
      <pubDate>{p['tanggal'].strftime('%a, %d %b %Y 07:00:00 +0700')}</pubDate>
      <description>{html.escape(p['ringkas'])}</description>
    </item>""" for p in posts[:30])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Blog Utsman</title>
  <link>{SITE}/blog/</link>
  <description>{html.escape(ui['tagline'])}</description>
  <language>id-ID</language>
  <lastBuildDate>{now}</lastBuildDate>
{item}
</channel></rss>
"""


# ---------------------------------------------------------------- utama

def main():
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
            p = parse_post(os.path.join(folder, nama), nama)
        except Exception as e:
            print(f"! {nama} gagal diolah: {e}", file=sys.stderr)
            continue
        (dilewatan if p["draft"] else posts).append(p)
    posts.sort(key=lambda p: (p["tanggal"], p["berkas"]), reverse=True)

    # --- hasil dihitung di memori, ditulis ukur lamun robah
    hasil = {}
    hasil["index.html"] = halaman_daftar(posts, UI["id"])
    grup = {}
    for q in posts:
        if q["pair"]:
            grup.setdefault(q["pair"], []).append(q)
    for i, p in enumerate(posts):
        lain = [q for q in grup.get(p["pair"], []) if q is not p] if p["pair"] else []
        hasil[f"{p['slug']}/index.html"] = halaman_tulisan(p, posts[i + 1] if i + 1 < len(posts) else None,
                                                           posts[i - 1] if i > 0 else None, UI["id"], lain)
    hasil["sitemap.xml"] = sitemap(posts)
    hasil["feed.xml"] = feed(posts, UI["id"])
    hasil["blog.css"] = CSS
    hasil["blog.js"] = JS

    sidik = hashlib.sha256(json.dumps({k: v for k, v in sorted(hasil.items())}).encode()).hexdigest()
    berkas_sidik = os.path.join(a.out, ".build-hash")
    sidik_lama = open(berkas_sidik).read().strip() if os.path.exists(berkas_sidik) else ""

    # gambar (disalin saban jalan — murah)
    src_img = os.path.join(a.repo, "images")
    ada_gambar = os.path.isdir(src_img)
    if ada_gambar:
        os.makedirs(os.path.join(a.out, "images"), exist_ok=True)
        for f in os.listdir(src_img):
            if not f.startswith("."):
                shutil.copy2(os.path.join(src_img, f), os.path.join(a.out, "images", f))

    if sidik == sidik_lama and not a.verbose:
        return 0                                    # cicing — teu aya parobahan

    # bersihkeun kaca tulisan anu tos teu aya
    for d in os.listdir(a.out) if os.path.isdir(a.out) else []:
        p = os.path.join(a.out, d)
        if os.path.isdir(p) and d != "images" and f"{d}/index.html" not in hasil:
            shutil.rmtree(p)

    os.makedirs(a.out, exist_ok=True)
    for path, isi in hasil.items():
        tujuan = os.path.join(a.out, path)
        os.makedirs(os.path.dirname(tujuan), exist_ok=True)
        open(tujuan, "w", encoding="utf-8").write(isi)
    open(berkas_sidik, "w").write(sidik)

    print(f"Blog diropéa: {len(posts)} tulisan dipedalkeun"
          + (f", {len(dilewatan)} draf ditingaleun" if dilewatan else "")
          + f". Kaca: /blog/ + {len(posts)} tulisan, sitemap + feed.")
    for p in posts[:5]:
        print(f"  · {p['tanggal']:%Y-%m-%d} [{p['lang']}] {p['judul']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
