#!/usr/bin/env bash
# Publish the current commit to a Hugging Face Space (Docker SDK).
#   deploy/push_to_hf.sh https://huggingface.co/spaces/<user>/<space>
# Exports HEAD (no git history, no untracked files), swaps in the Space's
# README (which carries the YAML config), and force-pushes it. The Space's
# build then runs the Dockerfile, which downloads the data release.
set -euo pipefail
[ $# -eq 1 ] || { echo "usage: $0 <space git url>"; exit 1; }
root="$(git rev-parse --show-toplevel)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git -C "$root" archive HEAD | tar -x -C "$tmp"
cp "$root/deploy/hf_README.md" "$tmp/README.md"
cd "$tmp"
git init -q -b main
git add -A
git -c user.name="deploy" -c user.email="deploy@localhost" commit -qm "Deploy $(git -C "$root" rev-parse --short HEAD)"
git push --force "$1" main
