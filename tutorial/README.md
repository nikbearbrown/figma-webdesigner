# Tutorial: redesign your home page

About 45 minutes the first time. You need a copy of your own site on your computer and a Figma account (education plans work).

```bash
git clone https://github.com/nikbearbrown/figma-webdesigner
cd figma-webdesigner
./fwd help
```

`./fwd help` tells you what is missing and the one thing to do next. Fix it, run it again, and when it says to, type `tutorial` in Claude Code.

What happens, in order:

1. **Get set up.** A local copy of your site, Node installed, Figma connected.
2. **Say what to look at.** Your home page, who may approve, and that the site is yours.
3. **Wireframe the page as it is today.** In Figma, as plain boxes and labels, at desktop and phone width.
4. **Read the suggestions.** Each one cites a rule, says how sure Claude is, and lists the options it passed over.
5. **See the rewritten page.** Same frames, with every difference tagged by the change it belongs to.
6. **Accept or reject.** You run `./fwd approve D-0001` (or `reject`, or `defer`) in your own terminal and commit the file. Claude cannot do this for you.
7. **Hand off.** Claude writes a short brief per approved change for Claude Code or Codex. Your site's code is only ever changed by that implementer, in its own session.

Where things are kept: `~/figma-webdesigner-work/<your site>/audit/`. Plain files you can read and commit: findings, decisions, approvals, an append-only ledger. `./fwd ledger verify` checks nobody altered the history.

The tutorial's worked example is the front page of jobs.humanitarians.ai, redesigned on 2026-11-07 with this method.
