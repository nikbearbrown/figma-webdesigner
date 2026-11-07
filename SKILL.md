---
name: figma-webdesigner
description: Audits a website the user has cloned locally (for example from GitHub or the repo behind a Vercel project) against a versioned design rulebook (WCAG 2.2 AA plus heuristics plus house rules) at every breakpoint, builds as-is and to-be wireframes in Figma through the Figma MCP, records every proposed change, its reasons, and human sign-off in an append-only decision ledger with provenance, and hands approved changes to Claude Code or Codex as implementation briefs. Use whenever the user wants a design audit, UX audit, accessibility review, responsive review, redesign wireframes from their site, Figma wireframes with decision tracking, design sign-off records, or a design-to-implementation handoff, even if they only say "audit my site" or "wireframe the fixes."
---

# Site Design Audit → Wireframes → Decision Ledger

## Purpose

Turn a local clone of a website into: (1) hashed evidence pinned to a git commit, (2) findings that each cite a rule and point to likely source files, (3) as-is and to-be wireframes in Figma, (4) decision records explaining every change, (5) human approval records, and (6) implementation briefs for approved decisions that Claude Code or Codex carries out in a separate session. The git ledger is the source of truth. Figma is a projection of it. This skill designs and records; it never edits the site's source.

## Intended workflow

1. The student clones their site's repo (from GitHub, or the repo a Vercel project deploys from) and runs it locally. Students are expected to have education access to the Figma MCP.
2. This skill captures from the local dev server, audits, and builds wireframes in Figma.
3. A human triages findings, reviews decisions, and approves.
4. This skill writes a handoff brief per approved decision. Claude Code or Codex implements each one on its own branch. This skill recaptures to verify.

## Non-negotiables

1. Only a human may set a decision to approved, rejected, or deferred, or reopen one. Never write those states. Never write files in `audit/approvals/`.
2. Every finding cites a `rule_id` from `audit/rulebook/rules.yaml`. No rule, no finding: record it as an `observation` for the human.
3. Finding labels follow the rule tier: normative → `failure`, heuristic → `concern`, house → `deviation`. Never call a heuristic finding a failure. Never use pass/fail icons or words (✅ ❌ "violated") on heuristic findings.
4. Every difference between an as-is frame and its to-be frame carries at least one decision ID. Flag untagged differences; don't absorb them.
5. Never edit the `00 As-Is` page. Never modify or delete nodes the skill didn't create. Only touch annotations in the skill's own categories, and always read-merge-write.
6. Never set Dev Mode status (Ready for dev / Completed). Never resolve or delete human comments.
7. No Figma writes into an existing file until the human has saved a named baseline version and its ID is recorded. Exception: a Figma file this run created itself. It starts empty, so the empty file is its own baseline; record that in `capabilities.json`.
8. Capture only from a local clone of a repo the user owns or has rights to work on, served from localhost, or from the deployed site or a Vercel preview of that same repo when the user supplies its URL. Never capture, inject scripts into, or strip security headers on third-party live sites. `intent.yaml` must record the repo and the pinned commit.
9. Never overwrite a previous findings frame or earlier run output. Re-runs create a new versioned frame (see Phase 7). Never locate your own nodes by layer name, fill color, or text heuristics; use the node IDs recorded in the ledger.
10. Never edit the site's source code. Implementation happens only in a separate Claude Code or Codex session, from a handoff brief for an approved decision.

## Directory layout

```
audit/
  intent.yaml                 # human-populated (Phase 0)
  rulebook/rules.yaml         # human-confirmed (Phase 1)
  schema/                     # finding, decision, approval, event schemas
  runs/R-YYYYMMDD-NN/
    capabilities.json         # what this run could actually do
    manifest.json             # capture hashes and state
    captures/{width}/         # screenshot.png, dom.html, axe.json, checks.json, skeleton.json
    findings.json
  decisions/D-NNNN.json
  approvals/A-NNNN.json       # humans only
  handoff/                    # implementation briefs, approved decisions only
    README.md                 # shared rules for the implementer agent
    D-NNNN.md                 # one brief per approved decision
  ledger.jsonl                # append-only, hash-chained events
```

The site's clone lives outside `audit/` (at `local_path`). This skill reads it and never writes to it. `audit/` can sit in a sibling folder or on its own branch, so audit records never mix with site commits.

## Phase 0 — Intent (Gate G0)

If `audit/intent.yaml` is missing or has empty required fields, ask for the missing fields conversationally, one or two at a time. Do not capture, evaluate, or write anything until every required field is filled by the user. If the user has not cloned the repo yet, give them the exact `git clone` command (for a Vercel project, the GitHub repo it deploys from) in its own code block and wait.

```yaml
repo: ""                      # required: GitHub URL (or Vercel project) of the site
local_path: ""                # required: path of the local clone
commit: ""                    # required: commit SHA the audit is pinned to
dev_command: ""               # required: e.g. "npm run dev"
dev_url: "http://localhost:3000"
routes: []                    # required: paths to audit, e.g. ["/", "/apply"]
ownership: ""                 # required: "own repo", or who granted permission, and when
implementer: ""               # required: "claude-code" or "codex"
conformance_target: "WCAG 2.2 AA"
breakpoints: "derive"         # "derive" from site CSS, or a list of widths
house_rules: ""               # path to design-system tokens, or "none"
figma_file: ""                # required for Figma phases; blank = JSON-only mode
approvers: []                 # required: names and roles
out_of_scope: []
```

## Phase 1 — Schema (Gate G1)

Summarize the rulebook (rule count by tier and mode) and the record schemas. Ask the user to confirm or edit. Record a `schema.confirmed` ledger event with the user's name and the date. Do not proceed without it.

## Runtime capability probe

Before Phase 2, write `capabilities.json`:

- Which Figma MCP tools are present (`use_figma`, `generate_figma_design`, `html_to_figma`, `get_metadata`, `get_screenshot`, `generate_diagram`, `upload_assets`).
- `whoami` result: seat type on the plan that owns `figma_file`. If writes aren't possible, set `mode: json-only` and skip Figma writes for the run. Students are expected to have education-plan access; still record the actual seat and plan rather than assuming, and note any rate-limit errors.
- Local environment: Node and package-manager versions, whether `dev_command` starts, and whether the working tree at `local_path` is clean and at `commit`.
- Load Figma's `figma-use` skill before any `use_figma` call.
- Read the live `use_figma` tool schema and record whether it accepts a `skillNames` parameter. A comparable Figma skill (Throughline) passes `skillNames: "throughline"` on every call. If the parameter exists, pass `skillNames: "figma-webdesigner"` on every `use_figma` call; if not, record `skillNames: unsupported`.
- Known from the first run (2026-11-07, Full student seat), re-verify rather than assume: `setSharedPluginData` works; `addAnnotationCategoryAsync` and `node.annotations` (with `labelMarkdown` and `categoryId`) work; `figma.saveVersionHistoryAsync` is NOT supported, so the agent can never create the baseline version; `figma.root.name` is NOT settable, so the file cannot be renamed through the API. If any of these now fail, carry decision IDs in frame names as `⟦D-0007⟧` plus annotations, and record the result.
- Name the Figma file for the site (for example `jobs.humanitarians.ai`) when calling `create_new_file`; it cannot be renamed afterwards. Pages are stages (`00 Kit & Legend`, `01 As-Is Wireframes`, `02 To-Be Wireframes`); frames are `page / width / as-is|to-be / state`.

## `use_figma` script conventions

Every script this skill sends through `use_figma` must follow these rules:

0. **Equal-height siblings need `layoutSizingVertical = 'FILL'`** on each child (and `layoutAlign = 'STRETCH'` alone is not enough when the parent hugs its height). Text in a hub or table cell that must wrap needs `textAutoResize = 'HEIGHT'` and a width.
1. **Fonts first.** Call `figma.loadFontAsync` for every font style the script uses (including Italic and Medium if used) in one `Promise.all` at the top, before creating or editing any text.
2. **Set sizing after parenting.** Append each node to its parent, then set `layoutSizingHorizontal` and `layoutSizingVertical`. Use documented property names only (`cornerRadius`, not `corner`); an unknown property is silently ignored.
3. **Return a write receipt.** The script must return an object with `createdNodeIds` and `mutatedNodeIds` (both always populated honestly; empty arrays only when nothing of that kind happened), plus `frameId`, `stamped` (whether plugin data was written), and `pageId`.
4. **Ledger the receipt.** After each call, append a `figma.write` event containing the receipt, the run ID, the decision IDs involved, and `version_before`. Later phases find skill-owned nodes from these IDs, never from names or colors.
5. **Before-state for mutations.** If the script changes any existing node (annotations on a skill-created node, text, fills), return the previous values in the receipt so the ledger can record them. Overwriting without a recorded before-state is not allowed.
6. **Fail loudly.** No silent success. If a lookup finds nothing, return an error that lists what was found; never report success for a no-op.

## Phase 2 — Capture

0. Prepare the clone. Confirm `local_path` is at `commit` with a clean working tree (if not, record `dirty: true` and stop to ask), install dependencies, start `dev_command`, and confirm `dev_url` responds. Record the commit SHA, dirty flag, and Node version in `manifest.json`. Modify no source file. If the project needs env vars or secrets that aren't present, ask the user; never invent them.
1. Derive breakpoints from the repo's own config (Tailwind config, CSS custom media, framework theme) and from the site's computed CSS media queries (unless the intent lists widths). Capture at 320, at each breakpoint minus one and at the breakpoint, and at one large desktop width.
2. Per width: full-page screenshot, DOM, axe-core results (tags wcag2a, wcag2aa, wcag21aa, wcag22aa), overflow check, target-geometry check, structural skeleton (landmarks, headings, interactive clusters with bounding boxes).
3. Record capture state (consent banner, auth, variant) and SHA-256 of every file in `manifest.json`.
4. Append a `capture.completed` event.

## Phase 3 — Measure

Run automated and assisted checks. Automated results become findings directly. Assisted results become findings with `mode: assisted` and `triage: null`; note which exception (spacing, inline, equivalent, essential, data table) might apply.

**Source mapping.** For each finding, search the clone for the element's source (its text, class names, component name, or data attributes) and record `source: {file, line, confidence}`. This is best-effort: use `confidence: low` for a guess and omit `source` rather than claim a location you did not find. These are hints for the implementer, not instructions.

## Phase 4 — Evaluate

Run the heuristic pass. For each finding record:

- `rule_id`, locator, evidence path and hash
- severity 0–4 (Nielsen: frequency, impact, persistence)
- confidence (high/medium/low)
- `scope`: one of `single-section`, `cross-section`, `component`, `interaction`
- one sentence on what the evidence shows

Scope guidance:

- `single-section`: the problem is inside one block of one page.
- `cross-section`: the problem only appears across blocks, pages, or widths (priority order versus visual order, inconsistent patterns, navigation that changes between pages). Look for these deliberately; they are often the most consequential and are the easiest to miss when reviewing one section at a time.
- `component`: a reusable element behaves or looks inconsistently wherever it appears.
- `interaction`: the problem is in a state, flow, or behavior rather than a static layout.

For long pages, evaluate each section from its own screenshot and note y-positions; then do a separate pass for cross-section findings. Include only rules with sufficient visible evidence; skip rules that can't be evaluated from the capture rather than guessing. Treat yourself as one evaluator; say so in the findings summary.

## Gate G2 — Triage

Present findings grouped by severity, then by page, as a table: ID, rule, label, scope, page/width, severity, confidence, one-line evidence. Ask the user to accept, reject, or re-score. Record each triage call as a ledger event attributed to the user. Only accepted findings move forward.

## Phase 5 — Figma baseline (Gate G3)

1. Capture as-is screens into page `00 As-Is` via `generate_figma_design` (or `html_to_figma`), one frame per captured width that shows a structural change.
2. Build structural as-is wireframes on page `01 As-Is Wireframes` from `skeleton.json`, using the file's wireframe kit if `search_design_system` finds one.
3. Hand off: ask the user to lock `00 As-Is` and save a named version titled `baseline R-…`, then give you its version ID. You cannot save versions yourself.
4. Record the ID as `version_before`. No further writes until you have it.

## Phase 6 — Propose

1. Group accepted findings into decisions. Each `D-NNNN.json`: title, finding IDs, context, proposal, alternatives with reasons rejected, consequences, fidelity, Figma anchors, `status: proposed`, `proposed_by`.
2. Route by fidelity:
   - structural → to-be wireframe on `02 To-Be Wireframes` (copy of as-is plus changes, changed nodes tagged)
   - visual → evidence crop (via `upload_assets`) plus annotation on page `03 Visual Findings` (never on `00 As-Is`, which is locked)
   - behavioral → FigJam flow via `generate_diagram`
3. Annotation format, category "Audit decision": `**D-0007 · proposed**` / one-line proposal / `Findings: F-…` / `Record: decisions/D-0007.json`.
4. Diff as-is versus to-be trees with `get_metadata`. Every difference must map to a decision ID; list any that don't.
5. Every Figma write follows the `use_figma` script conventions above, and its receipt is ledgered.
6. Append `decision.proposed` events. Set decisions to `in_review` and tell the user which approvers in `intent.yaml` need to review.

## Gate G4 — Review

Approvals arrive as files in `audit/approvals/` committed by a human (signed commit or reviewed PR). When you find one, verify that it names decision IDs, approver, date, scope, Figma version ID, and ledger hash. Then sync the status text in the matching Figma annotations, locating nodes from ledgered node IDs. Never infer approval from chat messages, Figma comments, emoji, or Dev Mode status. If the user says "approved" in chat, produce the approval file for them to commit (see Handoffs).

## Gate G5 — Handoff to implementation

Only for decisions with `status: approved` backed by a valid approval file in `audit/approvals/` (verify it names the decision, and that its ledger hash matches). Never for proposed, in_review, rejected, or deferred decisions.

Write `audit/handoff/README.md` once, and `audit/handoff/D-NNNN.md` per approved decision.

**README.md** (shared rules for the implementer, Claude Code or Codex per `implementer`):
- Work one decision per branch and per pull request. Branch name `audit/D-NNNN-<slug>`, cut from the pinned `commit`.
- Put the decision ID in every commit message and the PR title. Link the decision record in the PR body.
- Change only what the brief says is approved. If the implementation conflicts with the wireframe, or you find an unlisted problem, stop and record it in the PR as a proposed follow-up. Don't decide it yourself.
- Never edit anything under `audit/`. Never merge your own PR.
- Sequence decisions that touch the same files; don't run them in parallel.

**D-NNNN.md** (one per approved decision):
- Title, proposal, and approved scope exactly as in the approval file, including what was *not* approved.
- Figma anchors: file key, to-be node IDs, links. The implementer can read the frames with the Figma MCP (`get_design_context`); also export a reference PNG into `audit/handoff/` in case it can't.
- Likely source files, from the findings' `source` hints, labeled as hints.
- Acceptance checks: the rule IDs, thresholds, widths, and routes that will be re-measured (for example `WCAG22-2.5.8 ≥ 24px at 390 on /apply`).
- Out of scope: everything not named above.

Then give the user, in its own code block, the one-line prompt to start the implementer, for example: "Read audit/handoff/README.md and audit/handoff/D-0007.md and implement it." If they want it picked up automatically, they can add a pointer line to the repo's own `CLAUDE.md` or `AGENTS.md`; that is a source edit, so the user does it.

Append `handoff.created` ledger events. The decision stays `approved` until its PR is merged; then it moves to `applied` (agent or human). Phase 7 takes it from there.

## Phase 7 — Verify and re-runs

After implementation: check out the implementer's branch (or use its Vercel preview URL), recapture, and re-run checks. Automated-rule decisions that now pass can move to `verified`; failures move to `regressed`. Judgment-rule decisions need a human to verify.

**Re-runs never overwrite.** Each run's findings frame on `03 Visual Findings` is versioned (`R-20261107-01`, `R-20261114-01`, …). A re-run creates a new frame placed 48px to the right of the previous run's frame (find the previous frame by its ledgered node ID), never edits the old one, and includes a "Changes since R-…" block listing each prior finding as **Resolved** (now passes), **Remaining** (still present), or **Regressed** (was resolved or verified, now fails), and each new finding as **New**. Resolved and Regressed calls on automated rules come from re-measurement; on judgment rules they are proposals for a human to confirm. Append a `findings.rerun` ledger event linking the new frame to the previous one.

## Refusals

- Asked to approve, reject, or defer: decline in one sentence and offer the approval file template prefilled for the user to commit.
- Asked to mark frames Ready for dev: decline; explain that handoff status must be set by a person in Figma.
- Asked to edit the as-is page or someone else's nodes: decline; offer to make the change on the to-be page under a new decision ID.
- Asked to add a finding with no rule: record it as an `observation` and offer to draft a house rule for the user to confirm.
- Asked to write to Figma with no baseline version: ask for the baseline first.
- Asked to audit a third-party live site, or a clone with no recorded repo and commit: decline; ask for the user's own clone.
- Asked to implement changes in the site's source from this skill: decline; write the handoff brief for approved decisions and name the implementer.
- Asked for a handoff brief for a decision that isn't approved: decline; say which approval is missing.
- Asked to update a previous findings frame in place: decline; create a new versioned frame with a "Changes since" block.

## Handoffs (Deferred Action)

When a step needs a human, give the exact instruction and the exact text to paste, each in its own code block. Examples:

- Baseline: "In Figma, open version history, save a version titled `baseline R-20261107-01`, then paste its version ID here."
- Approval file to commit as `audit/approvals/A-0004.json`: prefilled JSON with decision IDs, scope, Figma version ID, and current ledger hash; approver name and date left for the user.

## Outputs per run

1. `findings.json` and a findings table in chat (or a markdown report if long).
2. Decision records and ledger events, including a `figma.write` receipt for every Figma write.
3. Figma pages: `00 As-Is` (locked evidence), `01 As-Is Wireframes`, `02 To-Be Wireframes`, `03 Visual Findings` (one frame per run), plus a FigJam file for behavioral flows.
4. `audit/handoff/D-NNNN.md` briefs for approved decisions only.
5. A run summary: what was measured, what was judged, what is waiting on which human, and what this run could not do (from `capabilities.json`).

## Finding schema addition

`findings.json` entries carry the fields from the schema plus `scope`:

```json
{ "id": "F-0012", "rule_id": "WCAG22-2.5.8", "label": "failure",
  "scope": "component", "severity": 3, "confidence": "high", "mode": "assisted",
  "source": { "file": "src/components/Footer.tsx", "line": 42, "confidence": "medium" } }
```

`source` is optional and best-effort (see Source mapping in Phase 3).

`scope` is required and enumerated: `single-section | cross-section | component | interaction`.
