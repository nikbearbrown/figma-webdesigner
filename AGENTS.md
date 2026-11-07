# AGENTS.md: figma-webdesigner

For Codex and other coding agents: read `CLAUDE.md` in this folder. It describes the `help` and `tutorial` commands and the one rule that matters most: only a person approves, rejects or defers a change, by running `./fwd approve|reject|defer <D-id>` in their own terminal. Do not run those commands or write into `audit/approvals/`.

The audit rules are in `SKILL.md`. Implementing approved changes is the one job an agent does in the student's site, and only from a handoff brief in `audit/handoff/`, one branch per change.
