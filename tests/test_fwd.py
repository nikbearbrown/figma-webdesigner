import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fwd  # noqa: E402


def git(*a, cwd):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        fwd.HOME = self.root / "work"
        fwd.STATE_FILE = fwd.HOME / "state.json"
        self.site = self.root / "my-site"
        self.site.mkdir()
        git("init", "-q", cwd=self.site)
        (self.site / "package.json").write_text(json.dumps({"scripts": {"dev": "next dev"}}))
        git("add", ".", cwd=self.site)
        git("commit", "-q", "-m", "init", cwd=self.site)

    def tearDown(self):
        self.tmp.cleanup()

    def init(self):
        self.assertEqual(fwd.cmd_init(argparse.Namespace(site=str(self.site), label=None)), 0)
        return fwd.audit_dir()

    def add_decision(self, audit, did="D-0001", status="proposed"):
        (audit / "decisions" / f"{did}.json").write_text(json.dumps(
            {"id": did, "title": "Cut the header", "proposal": "Five links down to four.", "finding_ids": ["F-0001"],
             "alternatives": [{"option": "keep", "why_not": "busy"}], "status": status}))


def script(*answers):
    it = iter(answers)
    return lambda prompt="": next(it)


class IntentAndLedger(Base):
    def test_read_intent(self):
        p = self.root / "i.yaml"
        p.write_text('repo: https://x/y   # note\nroutes: []\nownership: ""\nimplementer: codex\napprovers:\n  - Ann\ncommit: "abc # def"\n')
        i = fwd.read_intent(p)
        self.assertEqual(i["repo"], "https://x/y")
        self.assertEqual(i["routes"], "")
        self.assertEqual(i["ownership"], "")
        self.assertEqual(i["implementer"], "codex")
        self.assertEqual(i["approvers"], "(list)")
        self.assertEqual(i["commit"], "abc # def")

    def test_chain_and_tamper(self):
        a = self.root / "audit"
        a.mkdir()
        fwd.ledger_append(a, {"type": "one"})
        fwd.ledger_append(a, {"type": "two"})
        self.assertEqual(fwd.ledger_verify(a), [])
        lines = (a / "ledger.jsonl").read_text().splitlines()
        e = json.loads(lines[0])
        e["type"] = "changed"
        lines[0] = json.dumps(e)
        (a / "ledger.jsonl").write_text("\n".join(lines) + "\n")
        self.assertTrue(fwd.ledger_verify(a))


class Init(Base):
    def test_init_creates_workspace_and_is_idempotent(self):
        audit = self.init()
        for d in ("rulebook", "decisions", "approvals", "handoff", "runs"):
            self.assertTrue((audit / d).is_dir())
        self.assertTrue((audit / "rulebook" / "rules.yaml").exists())
        self.assertEqual(fwd.ledger_verify(audit), [])
        intent = fwd.read_intent(audit / "intent.yaml")
        self.assertEqual(len(intent["commit"]), 40)
        self.assertEqual(intent["dev_command"], "npm run dev")
        self.assertEqual(fwd.missing_intent(audit), ["repo", "ownership", "implementer", "approvers"])
        (audit / "intent.yaml").write_text("repo: kept\n")
        self.init()
        self.assertEqual((audit / "intent.yaml").read_text(), "repo: kept\n")
        self.assertEqual(len(fwd.ledger_events(audit)), 1)

    def test_init_refuses_non_git_folder(self):
        plain = self.root / "plain"
        plain.mkdir()
        self.assertEqual(fwd.cmd_init(argparse.Namespace(site=str(plain), label=None)), 2)
        self.assertFalse(fwd.STATE_FILE.exists())


class Decide(Base):
    def test_approve_writes_file_status_and_ledger(self):
        audit = self.init()
        self.add_decision(audit)
        out = []
        rc = fwd.decide("approve", "D-0001", audit, ask=script("Ann Lee", "", "", "", "D-0001"), say=out.append)
        self.assertEqual(rc, 0)
        a = json.loads((audit / "approvals" / "A-0001.json").read_text())
        self.assertEqual(a["outcome"], "approved")
        self.assertEqual(a["approver"], "Ann Lee")
        self.assertEqual(a["not_approved"], "nothing else")
        d = json.loads((audit / "decisions" / "D-0001.json").read_text())
        self.assertEqual(d["status"], "approved")
        self.assertEqual(d["status_history"][0]["by"], "Ann Lee")
        self.assertEqual(fwd.ledger_events(audit)[-1]["type"], "decision.approved")
        self.assertEqual(fwd.ledger_verify(audit), [])

    def test_wrong_confirmation_writes_nothing(self):
        audit = self.init()
        self.add_decision(audit)
        rc = fwd.decide("approve", "D-0001", audit, ask=script("Ann", "", "", "", "yes"), say=lambda *_: None)
        self.assertEqual(rc, 2)
        self.assertEqual(list((audit / "approvals").iterdir()), [])
        self.assertEqual(json.loads((audit / "decisions" / "D-0001.json").read_text())["status"], "proposed")

    def test_reject_requires_reason_and_name(self):
        audit = self.init()
        self.add_decision(audit)
        self.assertEqual(fwd.decide("reject", "D-0001", audit, ask=script("Ann", ""), say=lambda *_: None), 2)
        self.assertEqual(fwd.decide("reject", "D-0001", audit, ask=script(""), say=lambda *_: None), 2)
        self.assertEqual(fwd.decide("reject", "D-0001", audit, ask=script("Ann", "too busy", "", "D-0001"), say=lambda *_: None), 0)
        self.assertEqual(json.loads((audit / "decisions" / "D-0001.json").read_text())["status"], "rejected")

    def test_decided_needs_reopen(self):
        audit = self.init()
        self.add_decision(audit, status="approved")
        self.assertEqual(fwd.decide("reject", "D-0001", audit, ask=script(), say=lambda *_: None), 2)
        self.assertEqual(fwd.decide("reject", "D-0001", audit, ask=script("Ann", "changed my mind", "", "D-0001"), say=lambda *_: None, reopen=True), 0)

    def test_cli_refuses_without_a_terminal(self):
        audit = self.init()
        self.add_decision(audit)
        rc = fwd.cmd_decide(argparse.Namespace(verb="approve", decision="D-0001", audit=None, reopen=False))
        self.assertEqual(rc, 3)
        self.assertEqual(list((audit / "approvals").iterdir()), [])

    def test_approval_file_edited_after_the_fact_is_caught(self):
        audit = self.init()
        self.add_decision(audit)
        fwd.decide("approve", "D-0001", audit, ask=script("Ann", "", "", "", "D-0001"), say=lambda *_: None)
        f = audit / "approvals" / "A-0001.json"
        a = json.loads(f.read_text())
        a["ledger_hash"] = "0" * 64
        f.write_text(json.dumps(a))
        self.assertTrue(fwd.ledger_verify(audit))


class Tutorial(Base):
    def test_steps_follow_the_files(self):
        audit = self.init()
        st = {s["id"]: s for s in fwd.tutorial_status()}
        self.assertTrue(st[1]["done"])
        self.assertFalse(st[2]["done"])
        (audit / "intent.yaml").write_text("\n".join(f"{k}: x" for k in fwd.REQUIRED_INTENT) + "\n")
        self.assertTrue({s["id"]: s for s in fwd.tutorial_status()}[2]["done"])
        (audit / "runs" / "R-1").mkdir()
        (audit / "runs" / "R-1" / "findings.json").write_text("[]")
        self.add_decision(audit)
        self.assertTrue({s["id"]: s for s in fwd.tutorial_status()}[4]["done"])
        self.assertFalse({s["id"]: s for s in fwd.tutorial_status()}[6]["done"])
        fwd.decide("approve", "D-0001", audit, ask=script("Ann", "", "", "", "D-0001"), say=lambda *_: None)
        s = {s["id"]: s for s in fwd.tutorial_status()}
        self.assertTrue(s[6]["done"])
        self.assertFalse(s[7]["done"])
        (audit / "handoff" / "D-0001.md").write_text("brief")
        self.assertTrue({s["id"]: s for s in fwd.tutorial_status()}[7]["done"])

    def test_manual_step_cannot_skip_ahead_or_mark_derived(self):
        self.init()
        self.assertEqual(fwd.cmd_tutorial(argparse.Namespace(action="done", n="3")), 2)
        self.assertEqual(fwd.cmd_tutorial(argparse.Namespace(action="done", n="2")), 2)


class Checks(Base):
    def test_no_site_blocks_with_a_fix(self):
        items = {i["id"]: i for i in fwd.run_checks(with_mcp=False)}
        self.assertEqual(items["site"]["status"], "missing")
        self.assertTrue(any("git clone" in l for l in items["site"]["fix"]))
        self.assertTrue(fwd.blocking(list(items.values())))

    def test_site_ok_and_installs_missing(self):
        self.init()
        items = {i["id"]: i for i in fwd.run_checks(with_mcp=False)}
        self.assertEqual(items["site"]["status"], "ok")
        self.assertEqual(items["installs"]["status"], "missing")
        self.assertIn("npm install", items["installs"]["fix"][0])

    def test_dirty_site_warns(self):
        self.init()
        (self.site / "new.txt").write_text("x")
        self.assertEqual({i["id"]: i for i in fwd.run_checks(with_mcp=False)}["site"]["status"], "warn")


if __name__ == "__main__":
    unittest.main()
