#!/usr/bin/env bash
set -euo pipefail
REPO_NAME="multiagent-manager"
GITHUB_USER="${GITHUB_USER:-}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
RENDER_API_KEY="${RENDER_API_KEY:-}"
RENDER_OWNER_ID="${RENDER_OWNER_ID:-}"
if [ -z "$GITHUB_USER" ] || [ -z "$GITHUB_TOKEN" ]; then
  echo "GITHUB_USER and GITHUB_TOKEN required"
  exit 1
fi
TMPDIR=$(mktemp -d)
cp -r . "$TMPDIR/"
cd "$TMPDIR"
git init
git config user.email "automation@local"
git config user.name "$GITHUB_USER"
git add .
git commit -m "Initial commit - manager"
git branch -M main
git remote add origin "https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git"
git push -u origin main
if [ -n "$RENDER_API_KEY" ] && [ -n "$RENDER_OWNER_ID" ]; then
  PAYLOAD=$(cat <<JSON
{
  "ownerId": "${RENDER_OWNER_ID}",
  "serviceDetails": {
    "name": "multiagent-manager",
    "env": "python",
    "plan": "starter",
    "repo": "https://github.com/${GITHUB_USER}/${REPO_NAME}.git",
    "branch": "main",
    "buildCommand": "pip install -r requirements.txt",
    "startCommand": "bash start.sh"
  }
}
JSON
)
  curl -s -X POST "https://api.render.com/v1/services" -H "Authorization: Bearer ${RENDER_API_KEY}" -H "Content-Type: application/json" -d "$PAYLOAD" || true
else
  echo "Skipping Render creation - missing RENDER_API_KEY/RENDER_OWNER_ID"
fi
cd -
rm -rf "$TMPDIR"
echo "Done."
