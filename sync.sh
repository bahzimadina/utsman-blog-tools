#!/bin/bash
# Sinkronisasi blog utsman.works
#   - narik repositori eusi publik (github.com/bahzimadina/utsman-blog)
#   - ngarobih markdown jadi halaman HTML dina /home/ubuntu/utsman-blog/out
#   - CICING lamun euweuh parobahan (aman pikeun cron)
# Aman: repositori ukur DIBACA; euweuh token/kredensial dina kode ieu.
set -euo pipefail

REPO="${BLOG_REPO:-/home/ubuntu/utsman-blog/repo}"
OUT="${BLOG_OUT:-/home/ubuntu/utsman-blog/out}"
REMOTE="${BLOG_REMOTE:-https://github.com/bahzimadina/utsman-blog.git}"
BRANCH="${BLOG_BRANCH:-main}"

if [ ! -d "$REPO/.git" ]; then
  rm -rf "$REPO"
  git clone -q --depth 30 --branch "$BRANCH" "$REMOTE" "$REPO"
else
  # tarik hanca panganyarna sacara paksa (eusi ukur, teu aya éditan lokal)
  git -C "$REPO" fetch -q --depth 30 origin "$BRANCH"
  git -C "$REPO" checkout -q "$BRANCH" 2>/dev/null || git -C "$REPO" checkout -q -b "$BRANCH" "origin/$BRANCH"
  git -C "$REPO" reset -q --hard "origin/$BRANCH"
fi

exec python3 /home/ubuntu/utsman-blog/gen.py --repo "$REPO" --out "$OUT"
