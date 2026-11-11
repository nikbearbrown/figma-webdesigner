#!/usr/bin/env python3
"""figma-webdesigner command line: help, check, init, tutorial, palettes, approve/reject/defer, ledger, install.

Standard library only. Run it through ./fwd.

Design rules (see SKILL.md):
  * Only a person may approve, reject or defer a change. approve/reject/defer refuse to run
    unless stdin and stdout are a terminal. That stops accidents; it is not a lock. The real
    control is that the person commits the approval file and a reviewer sees it.
  * The ledger is append-only and hash-chained. This tool only appends.
  * Nothing here edits the student's site.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # ./fwd runs python -I, which drops the script folder
import palettes as pal  # noqa: E402

VERSION = "0.4.0"
REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("FWD_HOME", str(Path.home() / "figma-webdesigner-work")))
STATE_FILE = HOME / "state.json"
SKILL_LINK = Path.home() / ".claude" / "skills" / "figma-webdesigner"

REQUIRED_INTENT = ["repo", "local_path", "commit", "dev_command", "routes", "ownership", "implementer", "approvers"]
DECIDED = {"approved", "rejected", "deferred"}


# ───────────────────────── small helpers ─────────────────────────

def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run(cmd: list[str], cwd: str | None = None, timeout: int = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, "not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def audit_dir(override: str | None = None) -> Path | None:
    if override:
        return Path(override).expanduser().resolve()
    ws = load_state().get("workspace")
    return Path(ws) / "audit" if ws else None


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "site"


# ───────────────────────── intent.yaml (tiny reader) ─────────────────────────

def read_intent(path: Path) -> dict[str, str]:
    """Top-level `key: value` pairs only. A key with no value but indented `- ` lines counts as filled."""
    out: dict[str, str] = {}
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return out
    for i, line in enumerate(lines):
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val and val[0] in "\"'":
            q = val[0]
            end = val.find(q, 1)
            val = val[1:end] if end > 0 else val[1:]
        else:
            val = re.split(r"\s+#", val, maxsplit=1)[0].strip()
        if val == "":
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if re.match(r"^\s+-\s+\S", nxt):
                val = "(list)"
        if val in ("[]", "{}"):
            val = ""
        out[key] = val
    return out


def missing_intent(audit: Path) -> list[str]:
    intent = read_intent(audit / "intent.yaml")
    return [k for k in REQUIRED_INTENT if not intent.get(k, "").strip()]


# ───────────────────────── ledger ─────────────────────────

def _hash_event(body: dict) -> str:
    # Same rule as the first run's ledger: sha256 of the event without "hash", default json.dumps.
    return hashlib.sha256(json.dumps(body, ensure_ascii=False).encode()).hexdigest()


def ledger_events(audit: Path) -> list[dict]:
    p = audit / "ledger.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def ledger_head(audit: Path) -> str:
    ev = ledger_events(audit)
    return ev[-1]["hash"] if ev else "GENESIS"


def ledger_append(audit: Path, event: dict) -> dict:
    body = dict(event)
    body["at"] = now()
    body["prev"] = ledger_head(audit)
    body["hash"] = _hash_event(body)
    with (audit / "ledger.jsonl").open("a") as f:
        f.write(json.dumps(body, ensure_ascii=False) + "\n")
    return body


def ledger_verify(audit: Path) -> list[str]:
    """Return a list of problems; empty means the chain and the approval files check out."""
    problems: list[str] = []
    prev = "GENESIS"
    events = ledger_events(audit)
    for n, e in enumerate(events, 1):
        body = {k: v for k, v in e.items() if k != "hash"}
        if e.get("prev") != prev:
            problems.append(f"event {n} ({e.get('type')}): prev does not match the event before it")
        if _hash_event(body) != e.get("hash"):
            problems.append(f"event {n} ({e.get('type')}): hash does not match its contents")
        prev = e.get("hash", "")
    by_file = {e.get("approval_file"): e for e in events if e.get("approval_file")}
    for f in sorted((audit / "approvals").glob("A-*.json")) if (audit / "approvals").exists() else []:
        rel = f"audit/approvals/{f.name}"
        ev = by_file.get(rel)
        try:
            a = json.loads(f.read_text())
        except ValueError:
            problems.append(f"{f.name}: not valid JSON")
            continue
        if ev is None:
            problems.append(f"{f.name}: no ledger event points at this approval file")
        elif a.get("ledger_hash") != ev.get("prev"):
            problems.append(f"{f.name}: ledger_hash does not match the ledger at the time it was written")
    return problems


# ───────────────────────── checks ─────────────────────────

def _ver(cmd: list[str]) -> str:
    code, out = run(cmd)
    return out.splitlines()[0] if code == 0 and out else ""


def check_item(id_, label, status, detail, fix=None, required=True):
    return {"id": id_, "label": label, "status": status, "detail": detail, "fix": fix or [], "required": required}


def site_facts(path: Path) -> dict:
    f: dict = {"exists": path.is_dir()}
    if not f["exists"]:
        return f
    code, top = run(["git", "-C", str(path), "rev-parse", "--show-toplevel"])
    f["git"] = code == 0
    if f["git"]:
        f["remote"] = run(["git", "-C", str(path), "remote", "get-url", "origin"])[1] if run(["git", "-C", str(path), "remote"])[1] else ""
        f["commit"] = run(["git", "-C", str(path), "rev-parse", "HEAD"])[1]
        f["dirty"] = bool(run(["git", "-C", str(path), "status", "--porcelain"])[1])
    pkg = path / "package.json"
    f["package_json"] = pkg.exists()
    f["node_modules"] = (path / "node_modules").is_dir()
    f["dev_script"] = False
    if pkg.exists():
        try:
            f["dev_script"] = "dev" in json.loads(pkg.read_text()).get("scripts", {})
        except ValueError:
            pass
    return f


def run_checks(site_override: str | None = None, with_mcp: bool = True) -> list[dict]:
    state = load_state()
    items: list[dict] = []

    pv = sys.version_info
    items.append(check_item("python", "python3", "ok" if pv >= (3, 9) else "missing", f"{pv.major}.{pv.minor}.{pv.micro}",
                            [] if pv >= (3, 9) else ["Install Python 3.9 or newer from python.org."]))

    git = shutil.which("git")
    items.append(check_item("git", "git", "ok" if git else "missing", _ver(["git", "--version"]) if git else "not installed",
                            [] if git else ["macOS: xcode-select --install", "Other: https://git-scm.com/downloads"]))

    node = shutil.which("node")
    nver = _ver(["node", "--version"]) if node else ""
    nmajor = int(re.sub(r"\D.*", "", nver.lstrip("v")) or 0) if nver else 0
    items.append(check_item("node", "node", "ok" if nmajor >= 18 else "missing",
                            nver if node else "not installed",
                            [] if nmajor >= 18 else ["Install Node 18 or newer from https://nodejs.org (needed to run a copy of your site)."]))

    pm = next((p for p in ("npm", "pnpm", "yarn") if shutil.which(p)), None)
    items.append(check_item("pm", "package manager", "ok" if pm else "warn", pm or "none of npm, pnpm, yarn found",
                            [] if pm else ["npm comes with Node. Reinstall Node from https://nodejs.org."], required=False))

    claude = shutil.which("claude")
    items.append(check_item("claude", "Claude Code", "ok" if claude else "warn",
                            _ver(["claude", "--version"]) if claude else "not on PATH",
                            [] if claude else ["Install Claude Code: https://claude.com/claude-code", "The tutorial is run by Claude, so you need it."], required=False))

    # Figma MCP
    if not with_mcp:
        items.append(check_item("figma", "Figma connection", "unknown", "skipped (--no-mcp)", required=False))
    elif not claude:
        items.append(check_item("figma", "Figma connection", "unknown", "cannot check without the claude command", required=True))
    else:
        code, out = run(["claude", "mcp", "list"], timeout=45)
        line = next((l for l in out.splitlines() if "mcp.figma.com" in l or re.search(r"\bfigma\b", l, re.I)), "")
        if code == 124:
            items.append(check_item("figma", "Figma connection", "unknown", "claude mcp list timed out", ["Run `claude mcp list` yourself and look for figma."]))
        elif not line:
            items.append(check_item("figma", "Figma connection", "missing", "no Figma server is configured in Claude Code",
                                    ["claude mcp add --transport http figma https://mcp.figma.com/mcp",
                                     "Then in Claude Code type /mcp and sign in to figma with your school Figma account."]))
        elif "Connected" in line:
            items.append(check_item("figma", "Figma connection", "ok",
                                    "connected. Claude checks your seat (whoami) in tutorial step 1; a view-only seat cannot write."))
        else:
            items.append(check_item("figma", "Figma connection", "missing", "configured but not signed in",
                                    ["In Claude Code type /mcp, choose figma, and sign in with your school Figma account."]))

    # site clone
    site = site_override or state.get("site_path")
    if not site:
        items.append(check_item("site", "your site (local copy)", "missing", "none set yet",
                                ["git clone <your-repo-url> ~/my-site", "./fwd init ~/my-site",
                                 "Not sure of the repo? In Vercel open the project, then Settings > Git: it names the repo."]))
    else:
        p = Path(site).expanduser()
        f = site_facts(p)
        if not f["exists"]:
            items.append(check_item("site", "your site (local copy)", "missing", f"{p} does not exist", ["./fwd init <path to your clone>"]))
        elif not f.get("git"):
            items.append(check_item("site", "your site (local copy)", "missing", f"{p} is not a git repository",
                                    ["Clone your repo with git so the audit can pin a commit: git clone <your-repo-url> ~/my-site"]))
        else:
            dirty = " (has uncommitted changes: commit or stash first)" if f["dirty"] else ""
            items.append(check_item("site", "your site (local copy)", "warn" if f["dirty"] else "ok",
                                    f"{p} at {f['commit'][:7]}{dirty}", ["cd " + str(p) + " && git status"] if f["dirty"] else []))
            items.append(check_item("remote", "site belongs to you", "todo", f"remote is {f['remote'] or 'none'}. Only you can confirm you own it or have permission; you say so in tutorial step 2.", required=False))
            if f["package_json"]:
                if f["node_modules"]:
                    items.append(check_item("installs", "site installs", "ok", "node_modules present", required=False))
                else:
                    items.append(check_item("installs", "site installs", "missing", "node_modules not found",
                                            [f"cd {p} && npm install"], required=False))
                items.append(check_item("dev", "site can run locally", "ok" if f["dev_script"] else "warn",
                                        "has a dev script (npm run dev)" if f["dev_script"] else "no dev script in package.json: the audit can use your deployed site or a Vercel preview URL instead", required=False))
            else:
                items.append(check_item("installs", "site installs", "todo", "no package.json: static site or another stack; Claude will ask how you run it", required=False))

    # workspace + intent
    audit = audit_dir()
    if audit and audit.exists():
        miss = missing_intent(audit)
        items.append(check_item("intent", "audit intent (intent.yaml)", "ok" if not miss else "todo",
                                "complete" if not miss else "still to fill in: " + ", ".join(miss) + " (Claude asks in step 2)", required=False))
        items.append(palette_check(read_intent(audit / "intent.yaml").get("palette", "")))
    else:
        items.append(check_item("intent", "audit workspace", "todo", "not created yet (./fwd init creates it)", required=False))

    linked = SKILL_LINK.exists()
    items.append(check_item("install", "installed as a Claude skill", "ok" if linked else "warn",
                            str(SKILL_LINK) if linked else "not installed: Claude only sees it when opened in this folder",
                            [] if linked else ["./fwd install"], required=False))
    return items


def palette_check(chosen: str) -> dict:
    """Which of the default color sets the wireframes use. Never blocks: an unknown name falls back, out loud."""
    data = pal.load(REPO)
    known = pal.ids(data)
    if not chosen:
        return check_item("palette", "colors", "ok", f"{data['default']} (the default; ./fwd palettes lists all {len(known)})", required=False)
    if chosen in known:
        return check_item("palette", "colors", "ok", f"{chosen} ({pal.find(data, chosen)['name']})", required=False)
    return check_item("palette", "colors", "warn", f"'{chosen}' is not one of: {', '.join(known)}. {data['default']} will be used",
                      ["Set palette: in audit/intent.yaml to one of those, or run ./fwd palettes"], required=False)


MARK = {"ok": "[ok]     ", "missing": "[missing]", "warn": "[check]  ", "unknown": "[?]      ", "todo": "[todo]   "}


def blocking(items: list[dict]) -> list[dict]:
    return [i for i in items if i["required"] and i["status"] in ("missing",)]


def next_step(items: list[dict]) -> tuple[str, list[str]]:
    miss = blocking(items)
    if miss:
        i = miss[0]
        return f"Fix: {i['label']}. {i['detail']}.", i["fix"]
    unk = [i for i in items if i["required"] and i["status"] == "unknown"]
    if unk:
        return f"Check by hand: {unk[0]['label']}. {unk[0]['detail']}.", unk[0]["fix"]
    for i in items:
        if i["status"] in ("missing", "warn") and not i["required"] and i["id"] in ("installs", "site"):
            return f"Optional but wise: {i['label']}. {i['detail']}.", i["fix"]
    step = tutorial_status()
    cur = next((s for s in step if not s["done"]), None)
    if cur:
        return f"Start the tutorial: step {cur['id']}, {cur['title']}.", ["./fwd tutorial"]
    return "You have finished the tutorial.", []


def print_checks(items: list[dict]) -> None:
    w = max(len(i["label"]) for i in items)
    for i in items:
        print(f"{MARK[i['status']]} {i['label']:<{w}}  {i['detail']}")
        if i["status"] in ("missing", "warn", "unknown") and i["fix"]:
            for line in i["fix"]:
                print(f"{'':<{len(MARK['ok']) + 1}}{'':<{w}}    {line}")


# ───────────────────────── tutorial ─────────────────────────

def tutorial_steps() -> dict:
    return json.loads((REPO / "tutorial" / "steps.json").read_text())


def tutorial_status() -> list[dict]:
    spec = tutorial_steps()["steps"]
    state = load_state()
    manual_done = set(state.get("tutorial_done", []))
    audit = audit_dir()
    has_audit = bool(audit and audit.exists())
    items = run_checks(with_mcp=False)
    req_ok = not blocking(items)
    decisions = []
    if has_audit:
        for f in sorted((audit / "decisions").glob("D-*.json")):
            try:
                decisions.append(json.loads(f.read_text()))
            except ValueError:
                pass
    findings = bool(has_audit and list((audit / "runs").glob("*/findings.json")))
    derived = {
        1: req_ok and bool(state.get("site_path")),
        2: has_audit and not missing_intent(audit),
        4: findings and bool(decisions),
        6: bool(decisions) and all(d.get("status") in DECIDED for d in decisions),
        7: bool(decisions) and all(
            (audit / "handoff" / f"{d['id']}.md").exists() for d in decisions if d.get("status") == "approved"
        ) and all(d.get("status") in DECIDED for d in decisions),
    }
    out = []
    prev_done = True
    for s in spec:
        done = derived[s["id"]] if s["mode"] == "derived" else s["id"] in manual_done
        out.append({**s, "done": bool(done), "blocked": not prev_done})
        prev_done = prev_done and bool(done)
    return out


def cmd_tutorial(args) -> int:
    spec = tutorial_steps()
    st = tutorial_status()
    if args.action == "done":
        n = int(args.n)
        step = next((s for s in st if s["id"] == n), None)
        if not step:
            print(f"There is no step {n}.")
            return 2
        if step["mode"] == "derived":
            print(f"Step {n} is marked done by what is on disk, not by hand: {step['done_when']}")
            return 2
        if step["blocked"]:
            print(f"Finish the steps before step {n} first.")
            return 2
        state = load_state()
        state["tutorial_done"] = sorted(set(state.get("tutorial_done", [])) | {n})
        save_state(state)
        print(f"Step {n} marked done: {step['title']}.")
        return 0
    if args.action == "reset":
        state = load_state()
        state["tutorial_done"] = []
        save_state(state)
        print("Hand-marked steps cleared. Steps decided by files on disk stay as they are.")
        return 0
    print(f"Tutorial: {spec['title']}\n{spec['intro']}\n")
    cur = next((s for s in st if not s["done"]), None)
    for s in st:
        mark = "[x]" if s["done"] else ("[>]" if cur and s["id"] == cur["id"] else "[ ]")
        print(f"{mark} {s['id']}. {s['title']}")
    if cur:
        print(f"\nNOW: step {cur['id']}, {cur['title']}\n  You:    {cur['you']}\n  Claude: {cur['claude']}\n  Done when: {cur['done_when']}")
        if cur["mode"] == "manual":
            print(f"  (Claude runs ./fwd tutorial done {cur['id']} when this is true.)")
    else:
        print("\nAll seven steps are done. Run it again on another page: edit routes in audit/intent.yaml.")
    return 0


# ───────────────────────── init ─────────────────────────

INTENT_TEMPLATE = """# audit/intent.yaml. Claude fills the blank fields by asking you; nothing is captured until every required one is filled.
site_label: {label}
repo: {repo}                  # required: GitHub URL of the site
local_path: {path}            # required: your local copy
commit: {commit}              # required: the commit this audit is pinned to
dev_command: {dev}            # required: how you run it locally, e.g. "npm run dev" (or "none: deployed site")
dev_url: http://localhost:3000
routes: ["/"]                 # required: pages to audit. The tutorial uses the home page.
ownership: ""                 # required: "own repo", or who gave you permission, and when
implementer: ""               # required: "claude-code" or "codex"
conformance_target: "WCAG 2.2 AA"
breakpoints: [1440, 390]
house_rules: none
palette: {palette}           # colors for the wireframes: {palette_ids} (./fwd palettes)
figma_file: ""                # blank until Claude creates the Figma file for this site
approvers: []                 # required: your name and role
out_of_scope: []
"""


def cmd_init(args) -> int:
    site = Path(args.site).expanduser().resolve()
    if not site.is_dir():
        print(f"{site} is not a folder. Clone your site first:\n  git clone <your-repo-url> {site}")
        return 2
    f = site_facts(site)
    if not f.get("git"):
        print(f"{site} is not a git repository. The audit pins a commit, so it needs one.\n  git clone <your-repo-url> <folder>")
        return 2
    if getattr(args, "palette", None) and args.palette not in pal.ids(pal.load(REPO)):
        print(f"'{args.palette}' is not one of the color sets: {', '.join(pal.ids(pal.load(REPO)))}. Nothing was created.")
        return 2
    label = args.label or slug(site.name)
    ws = HOME / label
    audit = ws / "audit"
    created = not audit.exists()
    for d in ("rulebook", "decisions", "approvals", "handoff", "runs", "schema"):
        (audit / d).mkdir(parents=True, exist_ok=True)
    if not (audit / "intent.yaml").exists():
        dev = '"npm run dev"' if f.get("dev_script") else '""'
        pdata = pal.load(REPO)
        chosen = getattr(args, "palette", None) or pdata["default"]
        (audit / "intent.yaml").write_text(INTENT_TEMPLATE.format(label=label, repo=f.get("remote") or '""', path=str(site), commit=f.get("commit", ""), dev=dev,
                                                                  palette=chosen, palette_ids=", ".join(pal.ids(pdata))))
    if not (audit / "rulebook" / "rules.yaml").exists():
        shutil.copy(REPO / "starter" / "rules.yaml", audit / "rulebook" / "rules.yaml")
    if created:
        ledger_append(audit, {"type": "workspace.initialized", "by": "fwd init", "site_path": str(site), "commit": f.get("commit"), "tool_version": VERSION})
    state = load_state()
    state.update({"site_path": str(site), "label": label, "workspace": str(ws)})
    save_state(state)
    print(f"{'Created' if created else 'Found'} your audit folder: {audit}")
    print(f"Site: {site} at {f.get('commit', '')[:7]}{' (uncommitted changes: commit or stash first)' if f.get('dirty') else ''}")
    print("\nNext: in Claude Code, type: tutorial   (open it in the figma-webdesigner folder, or anywhere after ./fwd install)")
    return 0


# ───────────────────────── approve / reject / defer ─────────────────────────

OUTCOME = {"approve": "approved", "reject": "rejected", "defer": "deferred"}


def next_approval_id(audit: Path) -> str:
    nums = [int(m.group(1)) for f in (audit / "approvals").glob("A-*.json") if (m := re.match(r"A-(\d+)\.json", f.name))]
    return f"A-{(max(nums) + 1) if nums else 1:04d}"


def decide(verb: str, decision_id: str, audit: Path, ask=input, say=print, reopen: bool = False) -> int:
    """The person decides. All input comes through `ask`; the caller guarantees a terminal."""
    outcome = OUTCOME[verb]
    dfile = audit / "decisions" / f"{decision_id}.json"
    if not dfile.exists():
        say(f"No decision {decision_id} in {audit / 'decisions'}.")
        return 2
    d = json.loads(dfile.read_text())
    cur = d.get("status")
    if cur in ("approved", "rejected") and not reopen:
        say(f"{decision_id} is already {cur}. Changing it reopens it, which is a deliberate act: add --reopen.")
        return 2
    if cur in ("applied", "verified", "regressed"):
        say(f"{decision_id} is {cur}; it has been built. Open a new decision instead.")
        return 2

    say(f"\n{decision_id}: {d.get('title', '')}")
    say(f"Proposal: {d.get('proposal', '')}")
    for a in d.get("alternatives", []):
        say(f"  Passed over: {a.get('option')} ({a.get('why_not')})")
    if d.get("consequences"):
        say(f"Consequences: {d['consequences']}")
    say(f"Findings: {', '.join(d.get('finding_ids', []))}\n")

    name = ask("Your name (this goes in the record): ").strip()
    if not name:
        say("A name is required. Nothing was written.")
        return 2
    scope = ""
    not_approved = ""
    reason = ""
    if verb == "approve":
        scope = ask("What exactly are you approving? (Enter = as written above): ").strip() or "as written in the decision record"
        not_approved = ask("What is NOT approved? (Enter = nothing else): ").strip() or "nothing else"
    else:
        reason = ask(f"Why are you {'rejecting' if verb == 'reject' else 'deferring'} it? ").strip()
        if not reason:
            say("A reason is required. Nothing was written.")
            return 2
    figma_version = ask("Figma version ID of your saved baseline (Enter = none): ").strip() or None
    confirm = ask(f"Type {decision_id} to {verb} it: ").strip()
    if confirm != decision_id:
        say("Not confirmed. Nothing was written.")
        return 2

    aid = next_approval_id(audit)
    approval = {
        "id": aid, "decisions": [decision_id], "outcome": outcome, "approver": name, "at": now(),
        "scope": scope or None, "not_approved": not_approved or None, "reason": reason or None,
        "figma_version_id": figma_version, "ledger_hash": ledger_head(audit),
        "supersedes_status": cur if reopen else None,
        "written_by": f"fwd {verb}, run by the approver in a terminal",
    }
    (audit / "approvals" / f"{aid}.json").write_text(json.dumps(approval, indent=2) + "\n")
    d.setdefault("status_history", []).append({"status": outcome, "by": name, "at": approval["at"], "approval_file": f"audit/approvals/{aid}.json", "from": cur})
    d["status"] = outcome
    dfile.write_text(json.dumps(d, indent=2) + "\n")
    ledger_append(audit, {"type": f"decision.{outcome}", "decision_id": decision_id, "approval_file": f"audit/approvals/{aid}.json", "by": name})
    say(f"\n{decision_id} is now {outcome}. Wrote audit/approvals/{aid}.json and a ledger event.")
    say("Commit that file yourself: the commit is what makes it yours.")
    return 0


def cmd_decide(args) -> int:
    audit = audit_dir(args.audit)
    if not audit or not audit.exists():
        print("No audit folder yet. Run ./fwd init <your site> first.")
        return 2
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(f"Only a person can {args.verb} a change, and this is not a terminal a person is typing in.\n"
              f"Open your own terminal and run:\n  ./fwd {args.verb} {args.decision}\n"
              "(Chat messages and agent-run commands do not count as approval.)")
        return 3
    return decide(args.verb, args.decision, audit, reopen=args.reopen)


# ───────────────────────── palettes ─────────────────────────

def cmd_palettes(args) -> int:
    data = pal.load(REPO)
    bad = pal.problems(data)
    if bad:
        print("palettes/palettes.json has problems:")
        for b in bad:
            print("  - " + b)
        return 1
    if args.figma:
        if args.name and not pal.find(data, args.name):
            print(f"There is no color set called '{args.name}'. The sets are: {', '.join(pal.ids(data))}.")
            return 2
        print(pal.figma_script(REPO, data, args.name))
        return 0
    if args.json:
        one = pal.find(data, args.name) if args.name else None
        if args.name and not one:
            print(json.dumps({"error": f"no palette {args.name}", "known": pal.ids(data)}))
            return 2
        chosen = [one] if one else data["palettes"]
        print(json.dumps({"checked": data["checked"], "default": data["default"], "roles": data["roles"],
                          "palettes": [{**p, "contrast": pal.checks(p)} for p in chosen]}, indent=2))
        return 0
    if not args.name:
        pal.print_list(data)
        print("\nSee one in full, with its contrast worked out:  ./fwd palettes <id>")
        return 0
    one = pal.find(data, args.name) or (pal.wireframe(data) if args.name == "wireframe" else None)
    if not one:
        print(f"There is no color set called '{args.name}'. The sets are: {', '.join(pal.ids(data))}.")
        return 2
    pal.print_one(one)
    return 0


# ───────────────────────── templates ─────────────────────────

USABLE_ORDER = ["copy with credit", "copyleft: share alike"]


def load_templates(folder: Path) -> dict:
    """The catalog of open website templates, tolerant of a missing or broken file."""
    out = {"sites": [], "checked": "", "problems": []}
    p = folder / "site-templates.json"
    if not p.exists():
        out["problems"].append("site-templates.json is not here yet")
        return out
    try:
        data = json.loads(p.read_text())
    except ValueError:
        out["problems"].append("site-templates.json is not valid JSON")
        return out
    out["sites"] = [e for e in data.get("entries", []) if isinstance(e, dict) and e.get("url")]
    out["checked"] = data.get("checked", "")
    return out


def template_label(e: dict) -> str:
    return e.get("name", "") + (f" / {e['path']}" if e.get("path") else "")


def template_matches(entry: dict, word: str) -> bool:
    hay = " ".join(str(entry.get(k, "")) for k in ("kind", "name", "path", "what", "stack")).lower()
    return word.lower() in hay


def credits_markdown(cat: dict) -> str:
    """templates/CREDITS.md, made from the catalog so it cannot drift from it."""
    lines = ["# Credits", "",
             "Every website template this tool points to, with the licence it is offered under and who made it.",
             "This tool links to these works; it does not contain copies of them. If you build on one, this is the credit to give,",
             "and its licence file is the thing to read first.", "",
             f"Made by `./fwd templates --credits` from the catalog in this folder ({len(cat['sites'])} templates). Do not edit by hand.", ""]
    by_lic: dict[str, list[dict]] = {}
    for e in cat["sites"]:
        by_lic.setdefault(str(e.get("license")), []).append(e)
    for lic in sorted(by_lic, key=lambda k: (-len(by_lic[k]), k)):
        lines += [f"## {lic} ({len(by_lic[lic])})", ""]
        for e in sorted(by_lic[lic], key=lambda e: template_label(e).lower()):
            who = e.get("by") or e.get("name", "").split("/")[0] + " and contributors"
            lines.append(f"- [{template_label(e)}]({e['url']}), by {who}")
        lines.append("")
    return "\n".join(lines)


def cmd_templates(args) -> int:
    cat = load_templates(REPO / "templates")
    if not cat["sites"]:
        print("No template catalog yet: " + "; ".join(cat["problems"]) + ".")
        return 2
    if args.credits:
        print(credits_markdown(cat), end="")
        return 0
    if args.json:
        pick = (lambda e: template_matches(e, args.kind)) if args.kind else (lambda e: True)
        print(json.dumps({"checked": cat["checked"], "sites": [e for e in cat["sites"] if pick(e)]}, indent=2))
        return 0
    if not args.kind:
        print(f"Open-licensed website templates: {len(cat['sites'])}, gathered {cat['checked']}.\n")
        for field, title in (("kind", "By kind of site"), ("stack", "By what they are built with")):
            counts: dict[str, int] = {}
            for e in cat["sites"]:
                k = str(e.get(field) or "other").lower()
                counts[k] = counts.get(k, 0) + 1
            print(f"{title}\n  " + ", ".join(f"{k} {n}" for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))) + "\n")
        print('See one kind:  ./fwd templates portfolio      (any word: "blog", "astro", "documentation")')
        print("Each has a licence that allows reuse and a credit to give. Open the licence before you build on one.")
        return 0
    hits = [e for e in cat["sites"] if template_matches(e, args.kind)]
    if not hits:
        print(f"Nothing in the catalog matches '{args.kind}'. Run ./fwd templates to see the kinds.")
        return 2
    hits.sort(key=lambda e: (USABLE_ORDER.index(e["usable"]) if e.get("usable") in USABLE_ORDER else 9, -(e.get("stars") or 0)))
    print(f"{len(hits)} matching '{args.kind}'")
    for e in hits:
        flags = "".join(f" [{f}]" for f in ("official", "archived", "stale") if e.get(f))
        print(f"  {template_label(e)}  ({e.get('stack', '?')}, {e.get('license')}: {e.get('usable')}){flags}")
        print(f"      {e.get('what', '')}")
        if e.get("limits"):
            print(f"      Limits: {e['limits']}")
        if e.get("demo"):
            print(f"      See it: {e['demo']}")
        print(f"      {e['url']}")
    print("\ncopy with credit = you may build from it and must keep its licence notice. copyleft = your site's code must be shared under the same terms.")
    print("Gathered by search and checked against GitHub's licence data, not audited. Open the licence before you build on one.")
    return 0


# ───────────────────────── ledger / install / help ─────────────────────────

def cmd_ledger(args) -> int:
    audit = audit_dir(args.audit)
    if not audit or not (audit / "ledger.jsonl").exists():
        print("No ledger found. Run ./fwd init <your site> first, or pass --audit <path to audit folder>.")
        return 2
    problems = ledger_verify(audit)
    n = len(ledger_events(audit))
    if problems:
        print(f"Ledger has {len(problems)} problem(s) in {n} events:")
        for p in problems:
            print("  - " + p)
        return 1
    print(f"Ledger is valid: {n} events, chain intact, every approval file matches.")
    return 0


def cmd_install(_args) -> int:
    if SKILL_LINK.exists() or SKILL_LINK.is_symlink():
        if SKILL_LINK.resolve() == REPO:
            print(f"Already installed: {SKILL_LINK}")
            return 0
        print(f"{SKILL_LINK} already exists and is not this folder. Move it aside first; nothing was changed.")
        return 2
    SKILL_LINK.parent.mkdir(parents=True, exist_ok=True)
    SKILL_LINK.symlink_to(REPO)
    print(f"Installed: {SKILL_LINK} -> {REPO}\nOpen Claude Code in any folder and ask it to use figma-webdesigner.")
    return 0


HELP_HEAD = f"""figma-webdesigner {VERSION}
Redesign your own site with Claude and Figma, with a paper trail.

You point it at a copy of your site. It draws your page as a wireframe in Figma,
suggests changes with reasons, draws the rewritten page, and you accept or reject
each change. Approved changes go to Claude Code or Codex. Nothing here edits your site.
"""

HELP_COMMANDS = """COMMANDS
  ./fwd help                   this screen: checks your setup, names the next step
  ./fwd check [--json]         the checks alone (--no-mcp skips the slow Figma check)
  ./fwd init <site folder>     set up an audit folder for your site's local copy
  ./fwd tutorial               the first tutorial: redesign your home page
  ./fwd palettes [id]          the default colors: bear-brown, brutalist, northeastern, humanitarians
  ./fwd templates [kind]       open-licensed website templates (portfolio, blog, docs, ...), with credits
  ./fwd approve <D-id>         YOU accept a change (also: reject, defer). Your terminal only.
  ./fwd ledger verify          check the record has not been altered
  ./fwd install                make this a Claude skill available in every folder
"""


def cmd_help(args) -> int:
    print(HELP_HEAD)
    print("YOUR SETUP")
    items = run_checks(with_mcp=not args.no_mcp)
    print_checks(items)
    msg, fix = next_step(items)
    print(f"\nNEXT STEP\n  {msg}")
    for line in fix:
        print(f"    {line}")
    print("\n" + HELP_COMMANDS)
    return 0


def cmd_check(args) -> int:
    items = run_checks(args.site, with_mcp=not args.no_mcp)
    if args.json:
        print(json.dumps({"version": VERSION, "ready": not blocking(items), "checks": items}, indent=2))
    else:
        print_checks(items)
        msg, fix = next_step(items)
        print(f"\nNext: {msg}")
        for line in fix:
            print(f"  {line}")
    return 1 if blocking(items) else 0


class QuietParser(argparse.ArgumentParser):
    def error(self, message):  # our own short message replaces argparse's usage dump
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    p = QuietParser(prog="fwd", add_help=False)
    sub = p.add_subparsers(dest="cmd")
    h = sub.add_parser("help", add_help=False)
    h.add_argument("--no-mcp", action="store_true")
    c = sub.add_parser("check", add_help=False)
    c.add_argument("--json", action="store_true")
    c.add_argument("--no-mcp", action="store_true")
    c.add_argument("--site")
    i = sub.add_parser("init", add_help=False)
    i.add_argument("site")
    i.add_argument("--label")
    i.add_argument("--palette")
    pp = sub.add_parser("palettes", add_help=False)
    pp.add_argument("name", nargs="?")
    pp.add_argument("--json", action="store_true")
    pp.add_argument("--figma", action="store_true")
    t = sub.add_parser("tutorial", add_help=False)
    t.add_argument("action", nargs="?", default="show", choices=["show", "done", "reset"])
    t.add_argument("n", nargs="?")
    tp = sub.add_parser("templates", add_help=False)
    tp.add_argument("kind", nargs="?")
    tp.add_argument("--json", action="store_true")
    tp.add_argument("--credits", action="store_true")
    for verb in OUTCOME:
        d = sub.add_parser(verb, add_help=False)
        d.set_defaults(verb=verb)
        d.add_argument("decision")
        d.add_argument("--audit")
        d.add_argument("--reopen", action="store_true")
    l = sub.add_parser("ledger", add_help=False)
    l.add_argument("action", choices=["verify"])
    l.add_argument("--audit")
    sub.add_parser("install", add_help=False)
    sub.add_parser("version", add_help=False)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        argv = ["help"] + argv[1:]
    p = build_parser()
    try:
        args = p.parse_args(argv)
    except SystemExit:
        print("That command was not understood.\n")
        print(HELP_COMMANDS)
        return 2
    if args.cmd == "help":
        return cmd_help(args)
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "tutorial":
        return cmd_tutorial(args)
    if args.cmd == "palettes":
        return cmd_palettes(args)
    if args.cmd == "templates":
        return cmd_templates(args)
    if args.cmd in OUTCOME:
        return cmd_decide(args)
    if args.cmd == "ledger":
        return cmd_ledger(args)
    if args.cmd == "install":
        return cmd_install(args)
    if args.cmd == "version":
        print(VERSION)
        return 0
    print(HELP_COMMANDS)
    return 2


if __name__ == "__main__":
    sys.exit(main())
