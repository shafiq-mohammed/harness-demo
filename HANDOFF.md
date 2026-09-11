# Handoff: set up and rehearse the agentic harness

Read this whole file, then `CLAUDE.md` and `README.md`, before doing anything.

## Situation

I have a job interview later today (Fri Sep 11, 2026) for a Senior AI Software Engineer role. The format: I share my desktop, open Claude Code, and build an agentic orchestration pipeline live. This folder is a pre-built starter kit for that demo. Your job right now is to help me get it installed, working, and rehearsed on this Mac. Do not redesign it. Do not add agents or features. Make what is here run.

## What the kit is

Three LLM roles, two human gates, deterministic hooks in between.

- `.claude/agents/planner.md` - `model: fable`, requirements -> `docs/SPEC.md` + `tasks/T-00X.md` tickets with Given/When/Then acceptance criteria. Write-restricted to `docs/` and `tasks/`. Gate 1: I approve the tickets.
- Main session = the orchestrator (runs the skills, dispatches subagents, owns the gates), one ticket per branch.
- `.claude/agents/coder.md` - `model: opus`. Implements under `src/` until the pre-written tests are green, commits. Write-restricted to `src/` and `pyproject.toml`; cannot touch `tests/`.
- `.claude/agents/test-writer.md` - writes failing pytest tests from the ACs BEFORE any implementation exists. Write-restricted to `tests/`. Uses `model: opus`. This is the anti-bias mechanism: the grader is not the author.
- `.claude/agents/reviewer.md` - `model: fable`, read-only (Read/Grep/Glob/Bash, Bash guarded by `scripts/readonly_bash.sh`). Re-runs pytest itself. Fixed verdict format.
- Skills: `/plan <source>`, `/implement T-001`, `/review T-001`. Orchestration lives in the skills; `/implement` runs RED (test-writer) -> GREEN (coder) -> reviewer subagent (max 2 rounds, then escalate to me) -> `gh pr create`, then STOPS. Gate 2: I merge.
- Hooks (`.claude/settings.json`): PostToolUse on Edit/Write runs `scripts/post_edit_checks.sh` (ruff), Stop runs `scripts/stop_gate.sh` (blocks "done" if tree dirty or suite red). Per-agent PreToolUse hooks call `scripts/restrict_writes.sh`. All hooks parse their JSON input with python3, no jq. Exit code 2 = block and feed stderr back to the agent.
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is pinned to `"0"` in settings.json. Leave it that way.

Stack: Python 3.11+, FastAPI, pydantic v2, pytest, ruff, managed with uv. `pyproject.toml` has the dev extras.

## Current machine state (from `bash scripts/check_env.sh`)

- gh 2.92.0 present, git present
- `claude` reported MISSING to bash even though I use Claude Code. Likely an alias or a binary in `~/.local/bin` or `~/.claude/local` that is not on PATH for subprocesses. Diagnose with `which claude; type claude` and fix PATH in `~/.zshrc` so hooks and subagents can find it.
- Codex is NOT used in this run. Ignore `scripts/codex_review.sh`.
- `python3` exists (macOS); bare `python` does not. Scripts already use `python3`.
- No venv yet, so pytest/fastapi/ruff are not installed.

## What I need you to do, in order

1. Run `bash scripts/check_env.sh` and fix each MISSING item as above. Install uv via `brew install uv` if absent.
2. `uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"`, then re-run check_env until everything is green. Confirm `ruff --version` and `python3 -m pytest --version` work inside the venv.
3. `git init -b main`, initial commit, then `gh repo create --private --source . --push` (ask me for the repo name first).
4. Dry-run the hook scripts by hand with fake JSON on stdin so I can see exit codes: `restrict_writes.sh` allowing `tests/foo.py` and blocking `src/foo.py`; `readonly_bash.sh` allowing `git diff` and blocking `git commit`; `stop_gate.sh` with `stop_hook_active` true vs false. Show me the commands you used.
5. Check that `.claude/agents/` and `.claude/skills/` are picked up: tell me to restart the Claude Code session if they were created after it started, and confirm the subagents and skills are listed.
6. Rehearse: I will run `/plan docs/REQUIREMENTS.md` and approve one ticket, then `/implement T-001`. Time it. Any permission prompt that appears, add the matching allow rule to `.claude/settings.json` so it does not appear during the interview. Any hook that misfires, fix the script and tell me exactly what changed.
7. Keep T-001 tiny. If the planner produces a large first ticket, ask it to split it; do not implement a big one.

## Rules for you during this

- Ask before installing anything outside this folder besides uv and the venv.
- Never run `gh pr merge`, force-push, or `rm -rf`. Those are denied in settings.json on purpose.
- Use regular hyphens, never em-dashes, in anything you write into this repo.
- If something in the kit is wrong, fix the smallest thing that makes it work and tell me. Do not refactor.
- Be terse. I am short on time.

## Fallbacks

- No Jira/Atlassian MCP: the demo uses `docs/REQUIREMENTS.md` as the requirements source. In the interview I will say the planner reads Jira via MCP in production.
- Dynamic workflows (`/workflows`, the word "workflow" in a prompt) require Claude Code >= 2.1.154. Check `claude --version`. If older, upgrade; if it cannot upgrade, we skip that flourish.
