#!/usr/bin/env python3
"""Tests for scripts/serve.py — the local read/write server.

Like test_kb.py, each test builds a throwaway KB in a temp directory and runs
the real script against it as a subprocess, so kb.py's module-level ROOT
resolves there instead of into the real repo.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class ServeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        (self.root / "scripts").mkdir()
        for script in ("kb.py", "serve.py", "build_site.py"):
            shutil.copy(REPO_ROOT / "scripts" / script, self.root / "scripts" / script)
        shutil.copytree(REPO_ROOT / ".kb" / "templates", self.root / ".kb" / "templates")
        shutil.copytree(REPO_ROOT / ".kb" / "schema", self.root / ".kb" / "schema")
        self.kb("new", "first-fact", "--type", "semantic")
        self.kb("new", "second-fact", "--type", "semantic")
        self.proc = None

    def tearDown(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=10)
            for pipe in (self.proc.stdout, self.proc.stderr):
                if pipe:
                    pipe.close()
        self.tmpdir.cleanup()

    def kb(self, *args):
        result = subprocess.run(
            [sys.executable, str(self.root / "scripts" / "kb.py"), *args],
            cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def start(self):
        """Launch the server on an ephemeral port and return its base URL."""
        self.proc = subprocess.Popen(
            [sys.executable, str(self.root / "scripts" / "serve.py"),
             "--port", "0", "--no-browser"],
            cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                break
            m = re.search(r"(http://127\.0\.0\.1:\d+/)", line)
            if m:
                return m.group(1)
        self.proc.terminate()
        self.fail(f"server did not start: {self.proc.stderr.read()}")

    def request(self, url, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def entry_text(self, slug, entry_type="semantic"):
        return (self.root / "memory" / entry_type / f"{slug}.md").read_text()


class TestCapabilities(ServeTestCase):
    def test_capabilities_declares_the_site_editable(self):
        base = self.start()
        status, body = self.request(base + "api/capabilities")
        self.assertEqual(status, 200)
        self.assertTrue(body["editable"])
        self.assertIn("verified", body["confidence"])
        self.assertIn("semantic", body["types"])

    def test_site_is_served_alongside_the_api(self):
        base = self.start()
        with urllib.request.urlopen(base + "index.html", timeout=10) as r:
            self.assertEqual(r.status, 200)
            self.assertIn("first-fact", r.read().decode())

    def test_unknown_endpoint_is_a_404(self):
        base = self.start()
        status, body = self.request(base + "api/nonsense")
        self.assertEqual(status, 404)
        self.assertIn("error", body)


class TestEditing(ServeTestCase):
    def test_update_writes_frontmatter_and_body(self):
        base = self.start()
        status, body = self.request(base + "api/entry/first-fact", {
            "description": "edited from the browser",
            "confidence": "high",
            "links": ["second-fact"],
            "body": "New body text.",
        })
        self.assertEqual(status, 200, body)
        text = self.entry_text("first-fact")
        self.assertIn("description: edited from the browser", text)
        self.assertIn("confidence: high", text)
        self.assertIn("links: [second-fact]", text)
        self.assertIn("New body text.", text)

    def test_update_leaves_untouched_fields_alone(self):
        base = self.start()
        before = self.entry_text("first-fact")
        self.request(base + "api/entry/first-fact", {"description": "only this"})
        after = self.entry_text("first-fact")
        self.assertIn("only this", after)
        self.assertIn(re.search(r"^created:.*$", before, re.M).group(0), after)

    def test_dangling_links_are_refused(self):
        base = self.start()
        status, body = self.request(base + "api/entry/first-fact", {"links": ["ghost"]})
        self.assertEqual(status, 400)
        self.assertIn("ghost", body["error"])
        self.assertNotIn("ghost", self.entry_text("first-fact"))

    def test_invalid_confidence_is_refused(self):
        base = self.start()
        status, _ = self.request(base + "api/entry/first-fact", {"confidence": "vibes"})
        self.assertEqual(status, 400)

    def test_empty_description_is_refused(self):
        base = self.start()
        status, _ = self.request(base + "api/entry/first-fact", {"description": "  "})
        self.assertEqual(status, 400)

    def test_unknown_entry_is_a_404(self):
        base = self.start()
        status, _ = self.request(base + "api/entry/missing-thing", {"description": "x"})
        self.assertEqual(status, 404)

    def test_edits_are_recorded_in_the_ingest_log(self):
        base = self.start()
        self.request(base + "api/entry/first-fact", {"description": "logged"})
        self.assertIn("updated `semantic/first-fact.md`", (self.root / ".kb" / "log.md").read_text())


class TestVerifyAndDelete(ServeTestCase):
    def test_verify_stamps_today(self):
        base = self.start()
        status, body = self.request(base + "api/verify/first-fact", {})
        self.assertEqual(status, 200)
        self.assertIn(f"last_verified: {body['last_verified']}", self.entry_text("first-fact"))

    def test_verify_can_also_raise_confidence(self):
        base = self.start()
        self.request(base + "api/verify/first-fact", {"confidence": "verified"})
        self.assertIn("confidence: verified", self.entry_text("first-fact"))

    def test_delete_removes_the_file(self):
        base = self.start()
        status, _ = self.request(base + "api/delete/second-fact", {})
        self.assertEqual(status, 200)
        self.assertFalse((self.root / "memory" / "semantic" / "second-fact.md").exists())

    def test_delete_refuses_while_still_linked(self):
        self.kb("link", "first-fact", "second-fact")
        base = self.start()
        status, body = self.request(base + "api/delete/second-fact", {})
        self.assertEqual(status, 400)
        self.assertIn("first-fact", body["error"])
        self.assertTrue((self.root / "memory" / "semantic" / "second-fact.md").exists())

    def test_forced_delete_strips_inbound_links(self):
        self.kb("link", "first-fact", "second-fact")
        base = self.start()
        status, _ = self.request(base + "api/delete/second-fact", {"force": True})
        self.assertEqual(status, 200)
        self.assertNotIn("second-fact", self.entry_text("first-fact"))

    def test_triage_endpoint_returns_the_same_queue_as_the_cli(self):
        base = self.start()
        status, body = self.request(base + "api/triage")
        self.assertEqual(status, 200)
        self.assertIsInstance(body["triage"], list)


class TestRebuild(ServeTestCase):
    def test_the_site_reflects_an_edit_without_a_restart(self):
        base = self.start()
        self.request(base + "api/entry/first-fact", {"description": "freshly rebuilt copy"})
        with urllib.request.urlopen(base + "entry/first-fact.html", timeout=10) as r:
            self.assertIn("freshly rebuilt copy", r.read().decode())


if __name__ == "__main__":
    unittest.main()
