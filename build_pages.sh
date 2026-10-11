#!/usr/bin/env bash
# Build the GitHub Pages site in _site/: the static pages in site/, photos for queued posts, and rendered Reels.
# Pages is replaced wholesale on every deploy, so reels/ must already hold Reels for the whole queue
# (python -m bot make-reels), or queued Reel URLs 404.
set -e
rm -rf _site
mkdir -p _site/mugshots _site/reels
cp -r site/. _site/
[ -d mugshots ] && cp -r mugshots/. _site/mugshots/
[ -d reels ] && cp -r reels/. _site/reels/
touch _site/.nojekyll
echo "✅ Pages: $(ls _site/mugshots | wc -l | tr -d ' ') photos, $(ls _site/reels | wc -l | tr -d ' ') Reels"
