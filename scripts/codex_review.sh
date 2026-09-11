#!/usr/bin/env bash
# Cross-model review. Codex (OpenAI) reviews the branch diff against the ticket in a read-only sandbox and
# returns a JSON verdict on stdout. Claude Code runs this as an ordinary Bash tool call and reads the result,
# so the two models exchange work without a human copy-pasting between terminals.
#
# usage: scripts/codex_review.sh tasks/T-001.md [base-branch]
# env:   CODEX_SANDBOX=read-only (default) | workspace-write   (use workspace-write only if pytest cannot
#        run under read-only on your machine; the prompt still forbids edits and git diff will show any)
#        CODEX_MODEL=<model> to override your ~/.codex/config.toml default
set -uo pipefail
TICKET="${1:?usage: codex_review.sh <ticket-file> [base-branch]}"
BASE="${2:-main}"
SANDBOX="${CODEX_SANDBOX:-read-only}"
cd "$(git rev-parse --show-toplevel)" || exit 1
mkdir -p .review
git diff "${BASE}...HEAD" > .review/diff.patch
cp "$TICKET" .review/ticket.md
if [ ! -s .review/diff.patch ]; then
  echo "{\"verdict\":\"REQUEST_CHANGES\",\"blocking\":[{\"file\":\"-\",\"line\":0,\"issue\":\"no diff against ${BASE}\",\"fix\":\"commit your work on a branch first\"}],\"non_blocking\":[],\"ac_coverage\":{},\"tests_run\":\"none\"}"
  exit 0
fi

read -r -d '' PROMPT << 'PEOF'
You are an independent senior code reviewer from a different model family than the author. Do not trust the author's claims; verify them.
Read .review/ticket.md (the ticket with acceptance criteria) and .review/diff.patch (the complete diff under review).
You may read any file in the repository and run `python -m pytest -q` to check claims. Do not modify anything.
Review for: every acceptance criterion proven by a test; tests that assert behavior rather than mirror the implementation;
weakened, skipped, or tautological tests; unhandled error paths; input validation; security issues; scope creep beyond the ticket.
Blocking means a user or a test could observe the defect. Style is non-blocking.
Respond with ONLY a single JSON object as the last line of your output, no prose after it:
{"verdict":"APPROVE" or "REQUEST_CHANGES","blocking":[{"file":"path","line":0,"issue":"...","fix":"..."}],"non_blocking":[{"file":"path","issue":"..."}],"ac_coverage":{"AC1":"test_name or UNPROVEN"},"tests_run":"command and observed result"}
PEOF

MODEL_ARGS=()
[ -n "${CODEX_MODEL:-}" ] && MODEL_ARGS=(-m "$CODEX_MODEL")

# codex exec = non-interactive mode. -s sets the sandbox. Progress goes to stderr (kept in a log); the verdict to stdout.
codex exec -s "$SANDBOX" "${MODEL_ARGS[@]}" "$PROMPT" 2> .review/codex_stderr.log | tee .review/codex_verdict.txt
echo
echo "codex_review: verdict saved to .review/codex_verdict.txt (stderr in .review/codex_stderr.log)"
