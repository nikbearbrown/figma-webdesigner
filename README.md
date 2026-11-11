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
| `./fwd palettes [id]` | The four default color sets, or one in full with its contrast worked out |
| `./fwd templates [kind]` | Open-licensed website templates (portfolio, blog, docs, ...), with credits |
| `./fwd approve <D-id>` (also `reject`, `defer`) | **You** decide a change, in your own terminal |
| `./fwd ledger verify` | Checks the record has not been altered |
| `./fwd install` | Links this folder as a Claude skill for every project |

Needs Python 3.9+ (standard library only), git, and for your site, Node 18+.

## Colors

The wireframes are drawn in one of four default color sets, each read from the site it is named for:

| id | Read from | Ground | Ink | Accent |
|---|---|---|---|---|
| `bear-brown` (default) | [bearbrown.co](https://www.bearbrown.co/) | `#FAF9F5` | `#3D3929` | `#8B3A0F` |
| `brutalist` | [brutalist.art](https://www.brutalist.art/) | `#FFFFFF` | `#020817` | `#000000` |
| `northeastern` | [Northeastern Brand Center, color](https://brand.northeastern.edu/design-and-experiences/design/color/) | `#FFFFFF` | `#000000` | `#C8102E` |
| `humanitarians` | [humanitarians.ai](https://www.humanitarians.ai/) | `#FFFFFF` | `#1B1B1B` | `#7A0000` |

`./fwd palettes bear-brown` prints every role, light and dark, and works out the contrast of each text and button pairing. Choose one with `palette:` in `audit/intent.yaml`, or `./fwd init <site> --palette northeastern`. The values live in [palettes/palettes.json](palettes/palettes.json); the app-design sibling, figma-appdesigner, ships the same file.

The Northeastern set is the university's published palette. It is not permission to use its name or logos.

## Templates

`./fwd templates` lists 360 open-licensed website templates, themes and starters on GitHub, and `./fwd templates portfolio` (or `blog`, `documentation`, `astro`, any word) narrows it. They are for someone who has no site yet, or whose audit ends in "start again from something sound": a template gives the implementer a working base, and the audit and wireframes still decide what the pages say.

| | |
|---|---|
| Kinds of site | blog 59, documentation 35, portfolio 29, landing page 27, dashboard 24, SaaS marketing 23, personal site 18, and 21 more kinds |
| Built with | Next.js 57, Jekyll 51, Hugo 50, Astro 45, Bootstrap 31, Gatsby 16, Eleventy 15, plain HTML 14, and others |
| Licences | 340 copy with credit (MIT for most), 20 copyleft (your site's code must be shared the same way) |

Only templates with a confirmed licence that allows reuse are listed, each with a credit line; [templates/CREDITS.md](templates/CREDITS.md) lists them all. The search found 22 more with no licence file, a custom or non-commercial licence, or a README that restricts reuse. Those are kept out of this repository. This tool links to templates; it does not contain copies of them.

How far to trust the list, as of 2026-11-10: every repository was looked up twice through GitHub's API. All exist, and licence, archived flag and stars match. What pages each template really has, and whether its demo link still works, was not checked. A template's demo photos, fonts and icons often carry their own terms; where its README says so, the entry says so. Open a template's licence before you build on it.

Thin spots: one job-board template, three for newsletters (all need Ghost), three for restaurants, and few for nonprofits and clubs.

## Status: early

- The skill has been run by hand once, on the front page of [jobs.humanitarians.ai](https://jobs.humanitarians.ai/): audit, Figma wireframes, Vercel preview, production.
- The `fwd` command and tutorial are new and have been tested here only: 27 unit tests, a real run of `help` against a machine that has everything but a site, and the ledger check against the jobs audit (43 events, valid). **Not yet tested:** a clean machine without Node or Figma, a student running the whole tutorial, Windows.
- `./fwd approve` refuses to run unless a person is at a terminal. That prevents accidents; it is not a lock. The real control is that you commit the approval file and someone can review it.
- The color sets were read from the four sites on 2026-11-10 and are not re-read automatically. The script that puts them into Figma as variables (`./fwd palettes --figma`) was run once, in the sibling tool figma-appdesigner, and the colors read back correctly. Drawing this tool's wireframe kit in each set has not been tried yet.
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
