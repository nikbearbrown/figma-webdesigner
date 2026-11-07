# figma-webdesigner

A Claude skill for redesigning your own website with Claude and Figma, with a paper trail.

You point it at a copy of your site. It audits a page against a written rulebook, draws the **current** page as a wireframe in Figma (through the Figma MCP), proposes changes with reasons, draws the **proposed** page, and records every suggestion so you can accept or reject each one. Approved changes are handed to Claude Code or Codex as small implementation briefs.

## Status: early

- This repo is the skill (`SKILL.md`) only. It has been run by hand once, on one site: the front page of [jobs.humanitarians.ai](https://jobs.humanitarians.ai/). The audit, the Figma wireframes and the redesign shipped to a Vercel preview and then production.
- **Next:** a `help` command that checks what you are missing (a local copy of your site, installs, the Figma connection) and walks you through the first steps, and a built-in first tutorial: take your home page, wireframe it, see suggestions, accept or reject them.
- No `LICENSE` file has been chosen yet, so all rights are reserved until the author adds one.

## What you need

- [Claude Code](https://claude.com/claude-code)
- The Figma plugin / MCP server, signed in on a plan whose seat can write (Figma education plans work)
- Git and Node (to run a local copy of your site)
- A site you own or have permission to change, as a Git repo (for example one deployed on Vercel)

## Install

```bash
git clone https://github.com/nikbearbrown/figma-webdesigner ~/.claude/skills/figma-webdesigner
```

Then, in Claude Code, ask it to use the `figma-webdesigner` skill on your site.

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
