#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

private_paths=(
  token token_full nested/token nested/token_full
  .local/verifier-probe .agents/session.json .claude/settings.local.json
  .codex/session.json .cursor/session.json .impeccable/design.json
  .serena/project.local.yml .aider.chat.history.md
  probe.secrets.json probe.p12 id_ed25519 studio-ui/.npmrc .pypirc .netrc
  sample.credentials.json coverage.xml .coverage htmlcov/index.html
  tests/__pycache__/probe.pyc studio-ui/test-results/failure.png
  studio-ui/playwright-report/index.html
)

publishable_paths=(
  token-policy.md .env.example .npmrc.example tests/test_probe.py
  studio-ui/src/probe.test.ts studio-ui/e2e/probe.spec.ts
)

status=0
for path in "${private_paths[@]}"; do
  if ! git check-ignore -q -- "$path"; then
    printf 'representative private path is not ignored by git: %s\n' "$path" >&2
    status=1
  fi
done

for path in "${publishable_paths[@]}"; do
  if git check-ignore -q -- "$path"; then
    printf 'publishable path is over-broadly ignored by git: %s\n' "$path" >&2
    status=1
  fi
done

if ((status == 0)); then
  printf 'PASS: Git ignore policy verified\n'
fi
exit "$status"
