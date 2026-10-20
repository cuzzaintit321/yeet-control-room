#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command -v gh >/dev/null || { echo 'Install GitHub CLI first: sudo dnf install gh git'; exit 1; }
gh auth status >/dev/null
account="$(gh api user --jq .login)"
if [[ "$account" != cuzzaintit321 ]]; then
  echo "Expected cuzzaintit321; authenticated as $account. Switch accounts before publishing."
  exit 1
fi
if [[ -e .git ]]; then
  echo 'This folder already has Git history. Inspect its remotes before retrying.'; exit 1
fi
# Explicit allowlist: never publish local telemetry, databases, or reports.
git init -b main
git add core.py server.py web tests README.md publish.sh .gitignore .github
git -c user.name='Jason Edwards' -c user.email='228125969+cuzzaintit321@users.noreply.github.com' commit -m 'Build YEET Control Room observability and incident simulation lab'
gh repo create cuzzaintit321/yeet-control-room --public --source=. --remote=origin \
  --description 'A Linux mission control dashboard with live telemetry, time travel, dependency simulation, and incident reports.' --push
