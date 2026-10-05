#!/bin/bash
# Terbitkeun hiji tulisan ka blog.
#
#   publish.sh <berkas.md>                    # berkas lokal
#   publish.sh <berkas.md> "Pesan commit"     # kalawan pesen commit
#
# Prosés: salin ka pos/posts dina repositori → commit → push.
# Situsna nyokot sorangan dina ±10 menit (cron blog-sync).
set -euo pipefail

REPO="${BLOG_REPO:-/home/ubuntu/utsman-blog/repo}"
BRANCH="${BLOG_BRANCH:-main}"
f="${1:-}"
pesen="${2:-}"

if [ -z "$f" ] || [ ! -f "$f" ]; then
  echo "Pamakéan: publish.sh <berkas.md> [pesen-commit]" >&2
  exit 1
fi
if [ ! -d "$REPO/.git" ]; then
  echo "Repositori can aya di $REPO — jalankeun sync.sh heula." >&2
  exit 1
fi

nama="$(basename "$f")"
case "$nama" in
  *.md) ;;
  *) echo "Berkas kudu .md" >&2; exit 1 ;;
esac

# frontmatter dasar kudu aya
if ! head -1 "$f" | grep -q -- '^---'; then
  echo "Peringatan: berkas teu dimimitian ku frontmatter '---' (title, date, lang)." >&2
fi

# 0) saringan kaamanan eusi — tulisan anu ngandung data rahasia DIBATALKEUN
if ! python3 /home/ubuntu/utsman-blog/guard.py "$f"; then
  echo "Publikasi dibatalkeun ku saringan kaamanan eusi." >&2
  exit 1
fi

cp "$f" "$REPO/posts/$nama"
cd "$REPO"
# singkronkeun heula (bisi aya parobahan ti tempat séjén) supaya push teu ditolak
git fetch -q origin "$BRANCH"
git reset -q --hard "origin/$BRANCH"
cp "$f" "$REPO/posts/$nama"
git add "posts/$nama"
if git diff --cached --quiet; then
  echo "Euweuh parobahan: $nama geus sarua jeung anu aya di repositori."
  exit 0
fi
git commit -q -m "${pesen:-Tulisan anyar: $nama}"
git push -q origin "$BRANCH"
echo "Tos diterbitkeun: $nama — muncul dina situs saenggeus sinkronisasi (maks ±10 menit)."
