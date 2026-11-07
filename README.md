# figma-webdesigner

A Claude skill for redesigning your own website with Claude and Figma, with a paper trail.

You point it at a copy of your site. It audits a page against a written rulebook, draws the **current** page as a wireframe in Figma (through the Figma MCP), proposes changes with reasons, draws the **proposed** page, and records every suggestion so you can accept or reject each one. Approved changes are handed to Claude Code or Codex as small implementation briefs.

## Get started

```bash
git clone https://github.com/nikbearbrown/figma-webdesigner
cd figma-webdesigner
./fwd help
```

`./fwd help` checks what you have and what you are missing (git, Node, Claude Code, the Figma connection, a local copy of your site, its installs) and names the one thing to do next. Fix it, run it again. When it says you are ready, open Claude Code in this folder and type `tutorial`.

You can also type `help` inside Claude Code in this folder: Claude runs the same checks, asks Figma which plan and seat you are on, and answers in the same shape.

The first tutorial is the one this was built from: take your home page, wireframe it as it is today, see suggestions with reasons, see the rewritten wireframe, and accept or reject each change. See [tutorial/README.md](tutorial/README.md).

| Command | What it does |
|---|---|
| `./fwd help` | Checks your setup, names the next step |
| `./fwd check [--json]` | The checks alone |
| `./fwd init <site folder>` | Makes an audit folder for your site's local copy |
| `./fwd tutorial` | Shows the seven steps and the current one |
| `./fwd approve <D-id>` (also `reject`, `defer`) | **You** decide a change, in your own terminal |
| `./fwd ledger verify` | Checks the record has not been altered |
| `./fwd install` | Links this folder as a Claude skill for every project |

Needs Python 3.9+ (standard library only), git, and for your site, Node 18+.

## Status: early

- The skill has been run by hand once, on the front page of [jobs.humanitarians.ai](https://jobs.humanitarians.ai/): audit, Figma wireframes, Vercel preview, production.
- The `fwd` command and tutorial are new and have been tested here only: 15 unit tests, a real run of `help` against a machine that has everything but a site, and the ledger check against the jobs audit (43 events, valid). **Not yet tested:** a clean machine without Node or Figma, a student running the whole tutorial, Windows.
- `./fwd approve` refuses to run unless a person is at a terminal. That prevents accidents; it is not a lock. The real control is that you commit the approval file and someone can review it.
- No `LICENSE` file has been chosen yet, so all rights are reserved until the author adds one.

## What you need

- [Claude Code](https://claude.com/claude-code)
- The Figma plugin / MCP server, signed in on a plan whose seat can write (Figma education plans work)
- Git and Node (to run a local copy of your site)
- A site you own or have permission to change, as a Git repo (for example one deployed on Vercel). From Vercel, the project's Settings, then Git, names the repo.

## How it works

1. **Intent.** You say which repo, which pages, who may approve.
2. **Capture.** Real measurements of the page at phone and desktop widths.
3. **Findings.** Each problem cites a rule from a starter rulebook (WCAG 2.2, Nielsen's heuristics, house rules) and is labelled failure, concern, deviation or observation.
4. **Wireframes.** The current page, then the proposed page, in Figma, with numbered notes.
5. **Decisions.** Each proposed change has its reasons, alternatives and the findings it answers. Only a human can approve one.
6. **Handoff.** Approved changes become briefs for Claude Code or Codex, one branch per change.
7. **Verify.** Re-measure the page after the change.

Records live in plain files (`findings.json`, `decisions/D-NNNN.json`, an append-only `ledger.jsonl`), so the history can be diffed and reviewed in Git.

## Known limits (Figma MCP, found on the first run)

- The agent cannot save a named version in Figma, so you save the baseline.
- A Figma file cannot be renamed through the API: name it when it is created.
- Shared plugin data and annotations do work.

See `SKILL.md` for the full rules.
