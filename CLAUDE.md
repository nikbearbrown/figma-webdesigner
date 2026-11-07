# CLAUDE.md: figma-webdesigner

This folder is a Claude skill (`SKILL.md`) plus a small command, `./fwd`, that checks a student's setup and runs a first tutorial. Read `SKILL.md` for the audit rules; this file says how to answer the commands.

The student's workspace is outside this folder: `~/figma-webdesigner-work/<site>/audit/` (set by `./fwd init`). The student's site is a separate local clone. Never write into either the site or this folder while running a tutorial.

If the skill is installed (`./fwd install`), run the command by its path: `~/.claude/skills/figma-webdesigner/fwd`.

## When the user types `help` (or "what do you do?", "where do I start?")

1. Run `./fwd help`. It checks git, Node, Claude Code, the Figma connection, the site's local copy, installs and the audit intent, and names one next step.
2. The shell cannot see the Figma seat. If the Figma tools are available, also call `whoami` and report the plan and seat. A view-only seat cannot write wireframes: say so and stop there, because the audit then can only produce JSON records.
3. Answer in exactly this shape, short:
   - **What this is.** Two sentences: it wireframes your own site's current page in Figma, suggests changes with reasons, draws the rewritten page, and you accept or reject each change.
   - **Your setup.** One line per check with its status. Do not flatten missing and fine into one list: missing first.
   - **Next step.** One thing. Give any command in its own code block. If a fix needs the student to do something outside the terminal (sign in to Figma, find the repo in Vercel), say exactly where to click.
   - **Commands.** The list `./fwd help` prints, unedited.
4. If everything required is ready, the next step is: type `tutorial`. Do not start it unprompted.
5. Do not install, clone, sign in or edit anything on the student's behalf during `help`. Say what is missing and how to fix it; do the fix only if they ask.

## When the user types `tutorial`

1. Run `./fwd tutorial`. It shows seven steps and which one is current. Follow the current step only; say what the student does and what you do, as it prints.
2. The audit itself follows `SKILL.md` (phases 0 to 7 and gates G0 to G5). Ask for missing intent one or two fields at a time. The tutorial uses the home page (`routes: ["/"]`).
3. Steps 3 and 5 are marked by you when the wireframes exist and the student has looked at them: `./fwd tutorial done 3`. The other steps are marked by files on disk; do not try to mark them.
4. Step 6 is the student's. You cannot approve, reject or defer, and "approved" typed in chat is not approval. Give the exact command for them to run in their own terminal, in its own code block:
   ```bash
   ./fwd approve D-0001
   ```
   then tell them to commit the file it writes. Never run `./fwd approve`, `reject` or `defer` yourself, and never write into `audit/approvals/`.
5. Step 7: write one handoff brief per approved decision (`SKILL.md`, gate G5), then give the one-line prompt for the implementer. Never edit the student's site.
6. After each step, run `./fwd ledger verify` if you appended ledger events, and report the result in a line.

## Other commands

- `check`: `./fwd check` (add `--json` to parse it). Same checks as `help`, no commentary.
- `init <folder>`: `./fwd init <path to the student's clone>`. Creates the audit folder, copies the starter rulebook, records the commit.
- `ledger verify`: `./fwd ledger verify`. Reports a broken hash chain or an approval file that does not match.

## Always

- Say what you did not do or could not check. The Figma install path was not tested on a machine that lacks Figma.
- Give file paths in full when you point at something.
