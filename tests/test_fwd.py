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


class Palettes(Base):
    def setUp(self):
        super().setUp()
        self.data = fwd.pal.load(fwd.REPO)

    def test_the_four_default_sets_are_there_and_well_formed(self):
        self.assertEqual(fwd.pal.ids(self.data), ["bear-brown", "brutalist", "northeastern", "humanitarians"])
        self.assertEqual(fwd.pal.problems(self.data), [])
        self.assertEqual(self.data["default"], "bear-brown")
        for p in self.data["palettes"]:
            self.assertTrue(p["source"].startswith("https://"))

    def test_contrast_is_the_wcag_formula(self):
        self.assertAlmostEqual(fwd.pal.contrast("#000000", "#FFFFFF"), 21.0, places=2)
        self.assertAlmostEqual(fwd.pal.contrast("#FFFFFF", "#FFFFFF"), 1.0, places=2)
        # Northeastern's Brand Center quotes red on white as 5.9:1
        self.assertAlmostEqual(fwd.pal.contrast("#C8102E", "#FFFFFF"), 5.9, delta=0.05)

    def test_text_is_readable_in_every_set_and_low_pairs_are_written_down(self):
        low = []
        for p in self.data["palettes"]:
            for c in fwd.pal.checks(p):
                if c["pair"] in ("text", "text on cards", "secondary text", "button label"):
                    self.assertTrue(c["passes"], (p["id"], c))
                elif not c["passes"]:
                    low.append((p["id"], c["mode"], c["pair"], c["ratio"]))
                    self.assertTrue(any(f"{c['ratio']:.2f}:1" in n for n in p["notes"]), (p["id"], c))
        # the two known low pairs, so a change to the colors is noticed
        self.assertEqual(sorted(low), [("brutalist", "light", "secondary text on cards", 4.34),
                                       ("humanitarians", "dark", "button against the page", 2.47)])

    def test_bad_file_is_reported(self):
        bad = {"default": "x", "palettes": [{"id": "a", "name": "A", "source": "s", "modes": {"dark": {"ground": "red"}}}]}
        probs = fwd.pal.problems(bad)
        self.assertTrue(any("no light mode" in p for p in probs))
        self.assertTrue(any("not a #RRGGBB" in p for p in probs))
        self.assertTrue(any("default" in p for p in probs))

    def test_init_writes_the_default_and_accepts_a_choice(self):
        audit = self.init()
        self.assertEqual(fwd.read_intent(audit / "intent.yaml")["palette"], "bear-brown")
        self.assertEqual(fwd.palette_check("")["status"], "ok")
        self.assertEqual(fwd.palette_check("northeastern")["status"], "ok")
        self.assertEqual(fwd.palette_check("mauve")["status"], "warn")

    def test_init_refuses_an_unknown_palette_and_creates_nothing(self):
        rc = fwd.cmd_init(argparse.Namespace(site=str(self.site), label=None, palette="mauve"))
        self.assertEqual(rc, 2)
        self.assertFalse((fwd.HOME / "my-site").exists())

    def test_init_with_palette(self):
        self.assertEqual(fwd.cmd_init(argparse.Namespace(site=str(self.site), label=None, palette="humanitarians")), 0)
        self.assertEqual(fwd.read_intent(fwd.audit_dir() / "intent.yaml")["palette"], "humanitarians")

    def test_cli_palettes(self):
        self.assertEqual(fwd.main(["palettes"]), 0)
        self.assertEqual(fwd.main(["palettes", "brutalist"]), 0)
        self.assertEqual(fwd.main(["palettes", "mauve"]), 2)
        self.assertEqual(fwd.main(["palettes", "--json"]), 0)

    def test_figma_script_is_filled_in_from_the_file(self):
        script = fwd.pal.figma_script(fwd.REPO, self.data)
        self.assertNotIn("__MODES__", script)
        modes = fwd.pal.figma_modes(self.data)
        self.assertEqual([m["name"] for m in modes], ["Bear Brown", "Bear Brown dark", "Brutalist", "Brutalist dark",
                                                      "Northeastern", "Humanitarians AI", "Humanitarians AI dark", "Wireframe"])
        for m in modes:
            self.assertIn(m["roles"]["accent"], script)
        one = fwd.pal.figma_modes(self.data, "northeastern")
        self.assertEqual([m["name"] for m in one], ["Northeastern", "Wireframe"])
        self.assertTrue(all(c["passes"] for c in fwd.pal.checks(fwd.pal.wireframe(self.data))))
        self.assertEqual(fwd.main(["palettes", "wireframe"]), 0)
        self.assertEqual(fwd.main(["palettes", "northeastern", "--figma"]), 0)
        self.assertEqual(fwd.main(["palettes", "mauve", "--figma"]), 2)

    def test_figma_script_never_carries_a_typed_color(self):
        template = (fwd.REPO / "figma" / "palette-variables.js").read_text()
        import re
        self.assertEqual(re.findall(r"#[0-9A-Fa-f]{6}\b", template), [])


if __name__ == "__main__":
    unittest.main()
