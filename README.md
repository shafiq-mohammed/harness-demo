# Agentic delivery harness: Claude Code

plan -> test-first implement -> deterministic checks (hooks) -> independent review (read-only Claude subagent) -> PR -> human merge

Three LLM roles, two human gates, and everything that can be a script is a script.

## Tonight: setup and one full rehearsal (about 30 min)

1. Preflight:  bash scripts/check_env.sh
2. Make it a repo (do this in a fresh folder, not inside another git repo):
       cp -r harness ~/demo && cd ~/demo
       git init -b main && git add -A && git commit -m "chore: agentic harness"
       gh repo create demo-harness --private --source . --push
3. Python env:
       uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
       (or: python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]")
   Launch claude from this activated shell so the hooks find pytest and ruff.
4. claude  -> trust the folder when asked (project hooks and subagent hooks need it).
5. Rehearse:  /plan docs/REQUIREMENTS.md   -> read tasks/, approve
              /implement T-001              -> watch RED, GREEN, review rounds, PR
   Time it. If anything prompts for permission, add a rule to .claude/settings.json permissions.allow.

## Files

    CLAUDE.md                      project memory every agent and subagent loads
    .claude/settings.json          permissions (allow/deny), hooks, agent teams forced off
    .claude/agents/planner.md      requirements -> SPEC.md + tickets; hook restricts writes to docs/ and tasks/
    .claude/agents/test-writer.md  acceptance criteria -> failing tests; hook restricts writes to tests/; runs on sonnet
    .claude/agents/reviewer.md     fresh-context reviewer, no Edit/Write, Bash guarded read-only, re-runs tests
    .claude/skills/plan            /plan <source>        (gate 1: human approves tickets)
    .claude/skills/implement       /implement T-00X      the orchestration, stops at the PR (gate 2: human merges)
    .claude/skills/review          /review <ticket> [base]
    scripts/post_edit_checks.sh    PostToolUse: ruff format + lint every edit; exit 2 feeds errors back to the agent
    scripts/stop_gate.sh           Stop: refuses "done" on a dirty tree with red tests; loop-safe via stop_hook_active
    scripts/restrict_writes.sh     PreToolUse: per-agent write allowlist
    scripts/readonly_bash.sh       PreToolUse: blocks mutating shell commands for the reviewer
    scripts/codex_review.sh        cross-model review via `codex exec -s read-only`, JSON verdict on stdout
    docs/REQUIREMENTS.md           fallback brief if the interviewer gives you nothing
    docs/TICKET_TEMPLATE.md        the ticket shape the planner must follow

## Live demo order (45 to 60 min)

1. Two minutes on the shape: three roles, two gates, scripts for everything deterministic. Show the tree.
2. /plan <their requirements, or docs/REQUIREMENTS.md>. Read the tickets out loud. Approve. (gate 1)
3. /implement T-001. Narrate as it goes: test-writer can only touch tests/, tests go red first, commit,
   implementation, hooks lint every edit, reviewer re-runs the suite, verdict, PR. (gate 2)
4. Optional flourish if claude >= 2.1.154:
       use a workflow to review every file changed in this PR for correctness issues, then merge the per-file findings into one ranked summary
   Then /workflows to show the phases. Orchestration in code, LLM calls only at the leaves.
5. Production story: the same .claude/agents files run under the Claude Agent SDK, triggered by a Jira webhook, in a container, opening the PR.

## Gotchas
- If .claude/agents/ did not exist when claude started, restart claude after creating it.
- Never set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 on the demo machine; named subagents then launch as teammates. settings.json pins it to 0.
- Do not type the word ultracode unless you want a dynamic workflow to start.
- Keep T-001 tiny. Long test suites and long tickets kill demos.
- If a reviewer flags something real, that is the demo working. Say so.
