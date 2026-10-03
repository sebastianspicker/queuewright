#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

private_paths=(
  token token_full nested/token nested/token_full
  .local/verifier-probe .agent/session.json .agents/session.json .ai/session.json
  .claude/settings.local.json .codex/session.json .cursor/session.json
  .impeccable/design.json .serena/project.local.yml .aider.chat.history.md
  .cache/tool-state .queuewright-z2-implement/session.json
  AGENT.md AGENTS.md agent.md agents.md CLAUDE.md CODEX.md GEMINI.md
  .cursorrules copilot-instructions.md .github/copilot-instructions.md
  agent-notes.md agent-output.json agent-report.md agent-context.md agent-memory.md
  AI_NOTES.md AI_REPORT.md AI_AUDIT.md AI_SUMMARY.md LLM_NOTES.md GPT_NOTES.md
  CHATGPT_NOTES.md CLAUDE_NOTES.md CODEX_NOTES.md ai-report.md
  task-ledger.md task_ledger.md TASK_LEDGER.md plan.md scratchpad.md worklog.md devlog.md
  run.ledger.json cleanup-verify.json prototype-critique.json highend-2026-review.json
  .history-maintenance-provenance
  probe.secrets.json probe.p12 id_ed25519 studio-ui/.npmrc .pypirc .netrc
  sample.credentials.json coverage.xml .coverage htmlcov/index.html
  test-results/results.json playwright-report/index.html blob-report/report.json
  build/probe.txt dist/probe.txt probe.sarif probe.sqlite probe.log probe.tmp
  tests/__pycache__/probe.pyc studio-ui/dist/assets/app.js
)

publishable_paths=(
  token-policy.md .env.example .npmrc.example tests/test_probe.py
  studio-ui/src/probe.ts
)

status=0
for path in "${private_paths[@]}"; do
  if ! git check-ignore --no-index -q -- "$path"; then
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
