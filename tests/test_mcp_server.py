#!/usr/bin/env python3
"""Tests for scripts/mcp_server.py — the MCP stdio server.

Like the other suites, each test builds a throwaway KB in a temp directory and
drives the real script as a subprocess over stdin/stdout, so kb.py's
module-level ROOT resolves there instead of into the real repo — and so the
stdio framing itself is under test rather than mocked away.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = "2025-11-25"


class McpTestCase(unittest.TestCase):
    read_only = False

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        (self.root / "scripts").mkdir()
        for script in ("kb.py", "mcp_server.py"):
            shutil.copy(REPO_ROOT / "scripts" / script, self.root / "scripts" / script)
        shutil.copytree(REPO_ROOT / ".kb" / "templates", self.root / ".kb" / "templates")
        shutil.copytree(REPO_ROOT / ".kb" / "schema", self.root / ".kb" / "schema")
        self.kb("new", "first-fact", "--type", "semantic")
        self.kb("new", "second-fact", "--type", "semantic")
        (self.root / "memory" / "AGENT.md").write_text("# Agent Memory — Entry Point\n")
        self.proc = None
        self.next_id = 0

    def tearDown(self):
        if self.proc:
            self.proc.stdin.close()
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

    def start(self, *extra):
        args = [sys.executable, str(self.root / "scripts" / "mcp_server.py"), *extra]
        if self.read_only and "--read-only" not in extra:
            args.append("--read-only")
        self.proc = subprocess.Popen(
            args, cwd=self.root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        return self.proc

    def send(self, method, params=None, notification=False):
        """Write one JSON-RPC message; return the parsed response, or None."""
        if self.proc is None:
            self.start()
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if not notification:
            self.next_id += 1
            message["id"] = self.next_id
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        if notification:
            return None
        line = self.proc.stdout.readline()
        self.assertTrue(line.strip(), "server closed stdout without responding")
        return json.loads(line)

    def send_raw(self, raw):
        if self.proc is None:
            self.start()
        self.proc.stdin.write(raw + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def handshake(self, version=PROTOCOL):
        response = self.send("initialize", {
            "protocolVersion": version,
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "0"},
        })
        self.send("notifications/initialized", notification=True)
        return response

    def call(self, tool, arguments=None):
        return self.send("tools/call", {"name": tool, "arguments": arguments or {}})

    def result_of(self, response):
        self.assertNotIn("error", response, response)
        return response["result"]

    def entry_text(self, slug, entry_type="semantic"):
        return (self.root / "memory" / entry_type / f"{slug}.md").read_text()


class TestLifecycle(McpTestCase):
    def test_initialize_reports_server_info_and_capabilities(self):
        result = self.result_of(self.handshake())
        self.assertEqual(result["protocolVersion"], PROTOCOL)
        self.assertEqual(result["serverInfo"]["name"], "knowledge-base")
        self.assertIn("tools", result["capabilities"])
        self.assertIn("resources", result["capabilities"])
        self.assertIn("context", result["instructions"])

    def test_a_known_older_protocol_version_is_echoed_back(self):
        result = self.result_of(self.handshake(version="2025-06-18"))
        self.assertEqual(result["protocolVersion"], "2025-06-18")

    def test_an_unknown_protocol_version_falls_back_to_the_latest_supported(self):
        result = self.result_of(self.handshake(version="1999-01-01"))
        self.assertEqual(result["protocolVersion"], PROTOCOL)

    def test_ping_is_answered(self):
        self.handshake()
        self.assertEqual(self.result_of(self.send("ping")), {})

    def test_notifications_get_no_response(self):
        self.handshake()
        # If the notification had produced a response, this reply would be its
        # line rather than the ping's.
        self.send("notifications/cancelled", {"requestId": 1}, notification=True)
        self.assertEqual(self.result_of(self.send("ping")), {})

    def test_unknown_method_is_a_method_not_found_error(self):
        self.handshake()
        response = self.send("kb/nonsense")
        self.assertEqual(response["error"]["code"], -32601)

    def test_malformed_json_does_not_kill_the_connection(self):
        self.handshake()
        response = self.send_raw("{not json")
        self.assertEqual(response["error"]["code"], -32700)
        self.assertEqual(self.result_of(self.send("ping")), {})

    def test_batch_requests_are_refused(self):
        self.handshake()
        response = self.send_raw(json.dumps([{"jsonrpc": "2.0", "id": 99, "method": "ping"}]))
        self.assertEqual(response["error"]["code"], -32600)

    def test_non_object_params_is_a_tool_error_not_a_crash(self):
        # 2026-07-29 and 2026-07-30 each wrote this test independently; the
        # later one is kept because it also proves the server keeps serving
        # after the bad request, which is what "not a crash" actually means.
        self.handshake()
        response = self.send_raw(json.dumps(
            {"jsonrpc": "2.0", "id": 98, "method": "ping", "params": "not-an-object"}))
        self.assertEqual(response["error"]["code"], -32602)
        self.assertEqual(self.result_of(self.send("ping")), {})

    def test_missing_method_is_an_invalid_request_error(self):
        self.handshake()
        response = self.send_raw(json.dumps({"jsonrpc": "2.0", "id": 97}))
        self.assertEqual(response["error"]["code"], -32600)

    def test_every_response_is_exactly_one_line(self):
        self.handshake()
        self.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "id": 50, "method": "tools/call",
             "params": {"name": "get", "arguments": {"name": "first-fact"}}}) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        payload = json.loads(line)  # would fail if the multi-line body leaked out
        self.assertIn("\n", payload["result"]["content"][0]["text"])


class TestToolListing(McpTestCase):
    def test_tools_are_listed_with_schemas(self):
        self.handshake()
        tools = {t["name"]: t for t in self.result_of(self.send("tools/list"))["tools"]}
        self.assertEqual(
            set(tools),
            {"context", "search", "get", "triage", "due", "status", "dupes",
             "duplicate_candidates", "consolidate", "history", "judge",
             "propose_update", "capture"},
        )
        for tool in tools.values():
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertNotIn("handler", tool)
        self.assertTrue(tools["search"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["propose_update"]["annotations"]["readOnlyHint"])
        self.assertEqual(tools["context"]["inputSchema"]["required"], ["query"])

    def test_unknown_tool_is_an_invalid_params_error(self):
        self.handshake()
        response = self.call("teleport")
        self.assertEqual(response["error"]["code"], -32602)


class TestReadTools(McpTestCase):
    def test_search_ranks_and_returns_structured_hits(self):
        self.kb("set", "first-fact", "description", "how retrieval ranking works")
        self.handshake()
        result = self.result_of(self.call("search", {"query": "retrieval ranking"}))
        self.assertFalse(result["isError"])
        names = [h["name"] for h in result["structuredContent"]["hits"]]
        self.assertEqual(names[0], "first-fact")
        self.assertIn("first-fact", result["content"][0]["text"])

    def test_search_without_a_query_is_a_tool_error_not_a_protocol_error(self):
        self.handshake()
        result = self.result_of(self.call("search", {}))
        self.assertTrue(result["isError"])
        self.assertIn("query is required", result["content"][0]["text"])

    def test_search_can_be_limited_and_filtered_by_type(self):
        self.handshake()
        result = self.result_of(self.call(
            "search", {"query": "fact", "limit": 1, "type": "semantic"}))
        self.assertEqual(len(result["structuredContent"]["hits"]), 1)

    def test_search_rejects_an_unknown_type(self):
        self.handshake()
        result = self.result_of(self.call("search", {"query": "fact", "type": "vibes"}))
        self.assertTrue(result["isError"])

    def test_get_returns_the_whole_entry_and_its_frontmatter(self):
        self.handshake()
        result = self.result_of(self.call("get", {"name": "first-fact"}))
        self.assertIn("name: first-fact", result["content"][0]["text"])
        self.assertEqual(result["structuredContent"]["type"], "semantic")
        self.assertEqual(result["structuredContent"]["frontmatter"]["name"], "first-fact")

    def test_get_on_a_missing_entry_is_a_tool_error(self):
        self.handshake()
        result = self.result_of(self.call("get", {"name": "ghost"}))
        self.assertTrue(result["isError"])
        self.assertIn("ghost", result["content"][0]["text"])

    def test_context_returns_a_budgeted_pack_with_provenance(self):
        self.kb("set", "first-fact", "description", "how retrieval ranking works")
        self.handshake()
        result = self.result_of(self.call(
            "context", {"query": "retrieval ranking", "budget": 500}))
        text = result["content"][0]["text"]
        self.assertIn("# Context for: retrieval ranking", text)
        self.assertIn("confidence:", text)
        self.assertEqual(result["structuredContent"]["budget"], 500)
        self.assertNotIn("text", result["structuredContent"])

    def test_context_tells_an_agent_whether_the_budget_truncated_the_pack(self):
        """An agent reading a short pack has to know which question to ask:
        'is that all there is' or 'should I raise the budget'."""
        for i in range(4):
            self.kb("new", f"bulky-{i}", "--type", "semantic")
            self.kb("set", f"bulky-{i}", "description",
                    "retrieval ranking " + ("filler words " * 200))
        self.handshake()
        result = self.result_of(self.call(
            "context", {"query": "retrieval ranking", "budget": 300}))
        structured = result["structuredContent"]
        self.assertTrue(structured["budget_bound"])
        self.assertIsNotNone(structured["next_omitted"])
        self.assertIn("Stopped on budget, not on matches",
                      result["content"][0]["text"])

    def test_triage_reports_the_same_queue_the_cli_does(self):
        self.handshake()
        result = self.result_of(self.call("triage"))
        cli = json.loads(self.kb("triage", "--json").stdout)
        self.assertEqual(result["structuredContent"]["triage"], cli)

    def test_triage_can_be_filtered_by_reason(self):
        self.handshake()
        result = self.result_of(self.call("triage", {"reason": "orphan"}))
        for row in result["structuredContent"]["triage"]:
            self.assertTrue(any(x["code"] == "orphan" for x in row["reasons"]))

    def test_due_reports_the_same_queue_the_cli_does(self):
        self.kb("new", "due-soon", "--type", "prospective", "--due", "2030-01-01")
        self.handshake()
        result = self.result_of(self.call("due"))
        cli = json.loads(self.kb("due", "--json").stdout)
        self.assertEqual(result["structuredContent"]["due"], cli)

    def test_due_can_be_filtered_by_within(self):
        self.kb("new", "far-off", "--type", "prospective", "--due", "2099-01-01")
        self.handshake()
        result = self.result_of(self.call("due", {"within": 7}))
        self.assertEqual(result["structuredContent"]["due"], [])

    def test_due_rejects_a_negative_within(self):
        self.handshake()
        result = self.result_of(self.call("due", {"within": -1}))
        self.assertTrue(result["isError"])

    def test_status_accounts_for_every_entry(self):
        self.handshake()
        result = self.result_of(self.call("status"))
        names = {r["name"] for r in result["structuredContent"]["entries"]}
        self.assertEqual(names, {"first-fact", "second-fact"})
        self.assertEqual(sum(result["structuredContent"]["counts"].values()), 2)

    def test_status_rejects_an_unknown_status(self):
        self.handshake()
        result = self.result_of(self.call("status", {"status": "haunted"}))
        self.assertTrue(result["isError"])


class TestProposeUpdate(McpTestCase):
    def test_it_stages_frontmatter_and_body_without_committing(self):
        self.handshake()
        result = self.result_of(self.call("propose_update", {
            "name": "first-fact",
            "description": "edited over MCP",
            "confidence": "high",
            "links": ["second-fact"],
            "body": "New body text.",
        }))
        self.assertFalse(result["isError"])
        text = self.entry_text("first-fact")
        self.assertIn("description: edited over MCP", text)
        self.assertIn("confidence: high", text)
        self.assertIn("links: [second-fact]", text)
        self.assertIn("New body text.", text)
        self.assertFalse(result["structuredContent"]["committed"])
        self.assertIn("git diff", result["content"][0]["text"])

    def test_verify_stamps_a_last_verified_date(self):
        self.kb("set", "first-fact", "last_verified", "2000-01-01")
        self.handshake()
        self.result_of(self.call("propose_update", {"name": "first-fact", "verify": True}))
        self.assertNotIn("last_verified: 2000-01-01", self.entry_text("first-fact"))

    def test_a_verification_over_mcp_lands_in_the_same_review_trail(self):
        # The CLI and this server are two write surfaces onto one store, so a
        # review done here has to be as findable as one done there —
        # otherwise `kb.py log --action verified` silently describes a subset.
        self.handshake()
        self.result_of(self.call("propose_update", {
            "name": "first-fact", "verify": True,
            "verify_note": "re-ran the build against the claim",
        }))
        log = (self.root / ".kb" / "log.md").read_text()
        self.assertIn("verified `semantic/first-fact.md`", log)
        self.assertIn("checked: re-ran the build against the claim", log)

    def test_a_verify_note_without_a_verify_is_refused(self):
        # Silently dropping it would let a caller believe the evidence was
        # recorded when only the edit was.
        self.handshake()
        result = self.result_of(self.call("propose_update", {
            "name": "first-fact", "description": "no verification here",
            "verify_note": "evidence with nothing to attach to",
        }))
        self.assertTrue(result["isError"])
        self.assertNotIn("evidence with nothing to attach to",
                         (self.root / ".kb" / "log.md").read_text())

    def test_dangling_links_are_refused(self):
        self.handshake()
        result = self.result_of(self.call(
            "propose_update", {"name": "first-fact", "links": ["ghost"]}))
        self.assertTrue(result["isError"])
        self.assertNotIn("ghost", self.entry_text("first-fact"))

    def test_self_links_are_refused(self):
        self.handshake()
        result = self.result_of(self.call(
            "propose_update", {"name": "first-fact", "links": ["first-fact"]}))
        self.assertTrue(result["isError"])

    def test_invalid_confidence_is_refused(self):
        self.handshake()
        result = self.result_of(self.call(
            "propose_update", {"name": "first-fact", "confidence": "vibes"}))
        self.assertTrue(result["isError"])
        self.assertIn("confidence: unverified", self.entry_text("first-fact"))

    def test_an_empty_change_set_is_refused(self):
        self.handshake()
        result = self.result_of(self.call("propose_update", {"name": "first-fact"}))
        self.assertTrue(result["isError"])
        self.assertIn("nothing to change", result["content"][0]["text"])

    def test_a_missing_entry_is_a_tool_error_not_a_crash(self):
        self.handshake()
        result = self.result_of(self.call(
            "propose_update", {"name": "ghost", "description": "whatever"}))
        self.assertTrue(result["isError"])
        self.assertIn("ghost", result["content"][0]["text"])

    def test_the_body_cannot_be_emptied(self):
        self.handshake()
        result = self.result_of(self.call(
            "propose_update", {"name": "first-fact", "body": "   "}))
        self.assertTrue(result["isError"])

    def test_edits_are_recorded_in_the_ingest_log(self):
        self.handshake()
        self.call("propose_update", {"name": "first-fact", "description": "logged"})
        self.assertIn("updated `semantic/first-fact.md`",
                      (self.root / ".kb" / "log.md").read_text())

    def test_the_staged_entry_still_passes_lint(self):
        self.handshake()
        self.call("propose_update", {"name": "first-fact",
                                     "description": "still valid", "links": ["second-fact"]})
        result = subprocess.run(
            [sys.executable, str(self.root / "scripts" / "kb.py"), "lint"],
            cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TestDupesOverMcp(McpTestCase):
    PROSE = (
        "The knowledge base stores every memory as a markdown file with a "
        "small block of YAML frontmatter at the top. There is no database and "
        "no vector store anywhere in the design, and git is the only durable "
        "write path that the system relies on for its history."
    )

    def set_body(self, slug, prose):
        self.handshake()
        self.call("propose_update", {"name": slug, "body": prose})

    OTHER = (
        "Each note here lives on disk as ordinary text, carrying a short "
        "header of structured fields. Nothing relational is involved, no "
        "embedding index exists, and version control alone provides the "
        "lasting record of how things changed over time."
    )

    def test_a_clean_store_reports_none_and_still_names_the_limit(self):
        self.handshake()
        self.call("propose_update", {"name": "first-fact", "body": self.PROSE})
        self.call("propose_update", {"name": "second-fact", "body": self.OTHER})
        result = self.result_of(self.call("dupes"))
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["pairs"], [])
        self.assertIn("not the same claim written twice", result["content"][0]["text"])

    def test_copied_text_is_reported(self):
        self.handshake()
        for slug in ("first-fact", "second-fact"):
            self.call("propose_update", {"name": slug, "body": self.PROSE})
        result = self.result_of(self.call("dupes"))
        pairs = result["structuredContent"]["pairs"]
        self.assertEqual(len(pairs), 1)
        self.assertEqual({pairs[0]["a"], pairs[0]["b"]}, {"first-fact", "second-fact"})

    def test_entries_still_holding_the_template_are_flagged(self):
        """Two scaffolded-but-unfilled entries are verbatim duplicates of each
        other. Surfacing that is the point, not a false positive."""
        self.handshake()
        result = self.result_of(self.call("dupes"))
        pairs = result["structuredContent"]["pairs"]
        self.assertEqual({pairs[0]["a"], pairs[0]["b"]}, {"first-fact", "second-fact"})
        self.assertEqual(pairs[0]["jaccard"], 1.0)

    def test_a_non_numeric_threshold_is_a_tool_error(self):
        self.handshake()
        result = self.result_of(self.call("dupes", {"threshold": "loose"}))
        self.assertTrue(result["isError"])
        self.assertIn("must be a number", result["content"][0]["text"])

    def test_dupes_is_read_only(self):
        self.handshake()
        tools = {t["name"]: t for t in self.result_of(self.send("tools/list"))["tools"]}
        self.assertTrue(tools["dupes"]["annotations"]["readOnlyHint"])


class TestCandidatesOverMcp(McpTestCase):
    """The blocker and the verdict ledger, driven the way an agent would."""

    CLAIM = ("Every memory here is a markdown file with a small block of YAML "
             "frontmatter at the top. There is no database and no vector store "
             "anywhere in the design, and git is the only durable write path "
             "the system relies on for its history.")
    RESTATEMENT = ("Each note lives on disk as ordinary text carrying a short "
                   "header of structured fields. Nothing relational is "
                   "involved, no embedding index exists, and version control "
                   "alone provides the lasting record of how things changed.")

    def setUp(self):
        super().setUp()
        for slug, prose in (("first-fact", self.CLAIM),
                            ("second-fact", self.RESTATEMENT)):
            path = self.root / "memory" / "semantic" / f"{slug}.md"
            head, _, _ = path.read_text().partition("---\n")[2].partition("\n---\n")
            path.write_text(f"---\n{head}\n---\n\n{prose}\n")

    def candidates(self, args=None):
        return self.result_of(self.call("duplicate_candidates", args or {}))

    def test_it_surfaces_the_pair_dupes_is_built_to_miss(self):
        self.handshake()
        result = self.candidates()
        self.assertFalse(result["isError"])
        pairs = result["structuredContent"]["pairs"]
        self.assertIn({"first-fact", "second-fact"},
                      [{p["a"], p["b"]} for p in pairs])
        self.assertIn("candidates, not duplicates", result["content"][0]["text"])

    def test_a_recorded_verdict_takes_the_pair_out_of_the_queue(self):
        self.handshake()
        verdict = self.result_of(self.call("judge", {
            "a": "first-fact", "b": "second-fact", "verdict": "distinct",
            "agreement": "agree",
            "note": "different claims, shared vocabulary"}))
        self.assertFalse(verdict["isError"])
        self.assertFalse(verdict["structuredContent"]["committed"])
        pairs = self.candidates()["structuredContent"]["pairs"]
        self.assertNotIn({"first-fact", "second-fact"},
                         [{p["a"], p["b"]} for p in pairs])

    def test_the_verdict_is_staged_in_the_working_tree(self):
        self.handshake()
        self.call("judge", {"a": "first-fact", "b": "second-fact",
                            "verdict": "overlap"})
        ledger = json.loads((self.root / ".kb" / "verdicts.json").read_text())
        self.assertEqual(ledger["verdicts"][0]["verdict"], "overlap")

    def test_a_verdict_without_an_agreement_leaves_the_pair_in_the_queue(self):
        """The tool must not let an agent half-judge a pair and look done."""
        self.handshake()
        result = self.result_of(self.call("judge", {
            "a": "first-fact", "b": "second-fact", "verdict": "distinct"}))
        self.assertIsNone(result["structuredContent"]["agreement"])
        self.assertIn("half-judged", result["content"][0]["text"])
        pairs = self.candidates()["structuredContent"]["pairs"]
        self.assertIn({"first-fact", "second-fact"},
                      [{p["a"], p["b"]} for p in pairs])

    def test_a_contradiction_is_recorded_and_stays_outstanding(self):
        self.handshake()
        result = self.result_of(self.call("judge", {
            "a": "first-fact", "b": "second-fact", "verdict": "overlap",
            "agreement": "contradict"}))
        self.assertEqual(result["structuredContent"]["agreement"], "contradict")
        self.assertIn("contradicted", result["content"][0]["text"])
        pairs = self.candidates()["structuredContent"]["pairs"]
        pair = next(p for p in pairs if {p["a"], p["b"]} == {"first-fact", "second-fact"})
        self.assertEqual(pair["agreement"], "contradict")

    def test_a_contradiction_reaches_the_triage_tool(self):
        self.handshake()
        self.call("judge", {"a": "first-fact", "b": "second-fact",
                            "verdict": "overlap", "agreement": "contradict"})
        report = self.result_of(self.call("triage", {}))["structuredContent"]
        flagged = {r["name"]: [x["code"] for x in r["reasons"]]
                   for r in report["triage"]}
        self.assertIn("contradiction", flagged.get("first-fact", []))
        self.assertIn("contradiction", flagged.get("second-fact", []))

    def test_an_unknown_agreement_is_a_tool_error(self):
        self.handshake()
        result = self.result_of(self.call("judge", {
            "a": "first-fact", "b": "second-fact", "verdict": "distinct",
            "agreement": "sort of"}))
        self.assertTrue(result["isError"])
        self.assertIn("agreement must be one of", result["content"][0]["text"])

    def test_the_judge_schema_offers_both_axes(self):
        self.handshake()
        tools = {t["name"]: t for t in self.result_of(self.send("tools/list"))["tools"]}
        props = tools["judge"]["inputSchema"]["properties"]
        self.assertEqual(props["agreement"]["enum"], ["agree", "contradict"])
        self.assertNotIn("agreement", tools["judge"]["inputSchema"]["required"])
    def test_judging_a_missing_entry_is_a_tool_error_not_a_crash(self):
        self.handshake()
        result = self.result_of(self.call(
            "judge", {"a": "first-fact", "b": "ghost", "verdict": "distinct"}))
        self.assertTrue(result["isError"])
        self.assertIn("ghost", result["content"][0]["text"])

    def test_an_unknown_verdict_is_a_tool_error(self):
        self.handshake()
        result = self.result_of(self.call("judge", {
            "a": "first-fact", "b": "second-fact", "verdict": "maybe"}))
        self.assertTrue(result["isError"])
        self.assertIn("verdict must be one of", result["content"][0]["text"])

    def test_an_entry_cannot_be_judged_against_itself(self):
        self.handshake()
        result = self.result_of(self.call("judge", {
            "a": "first-fact", "b": "first-fact", "verdict": "duplicate"}))
        self.assertTrue(result["isError"])

    def test_a_non_numeric_neighbour_count_is_a_tool_error(self):
        self.handshake()
        result = self.candidates({"neighbours": "lots"})
        self.assertTrue(result["isError"])
        self.assertIn("must be an integer", result["content"][0]["text"])

    def test_candidates_is_read_only_and_judge_is_not(self):
        self.handshake()
        tools = {t["name"]: t for t in self.result_of(self.send("tools/list"))["tools"]}
        self.assertTrue(tools["duplicate_candidates"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["consolidate"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["judge"]["annotations"]["readOnlyHint"])

    def test_consolidate_reports_what_a_verdict_left_undone(self):
        self.handshake()
        self.assertFalse(self.result_of(self.call("judge", {
            "a": "first-fact", "b": "second-fact", "verdict": "overlap",
            "agreement": "agree"}))["isError"])
        result = self.result_of(self.call("consolidate", {}))
        self.assertFalse(result["isError"])
        edges = result["structuredContent"]["missing_edges"]
        self.assertIn({"first-fact", "second-fact"},
                      [{p["a"], p["b"]} for p in edges])
        self.assertIn("Proposals, not decisions", result["content"][0]["text"])

    def test_consolidate_clears_once_the_link_exists(self):
        self.handshake()
        self.call("judge", {"a": "first-fact", "b": "second-fact",
                            "verdict": "overlap", "agreement": "agree"})
        self.assertFalse(self.result_of(self.call("propose_update", {
            "name": "first-fact", "links": ["second-fact"]}))["isError"])
        edges = self.result_of(self.call(
            "consolidate", {}))["structuredContent"]["missing_edges"]
        self.assertNotIn({"first-fact", "second-fact"},
                         [{p["a"], p["b"]} for p in edges])

    def test_a_non_numeric_margin_is_a_tool_error(self):
        self.handshake()
        result = self.result_of(self.call("consolidate", {"margin": "wide"}))
        self.assertTrue(result["isError"])
        self.assertIn("must be a number", result["content"][0]["text"])


class TestHistoryOverMcp(McpTestCase):
    def git(self, *args):
        result = subprocess.run(
            ["git", "-c", "user.email=t@example.com", "-c", "user.name=Test", *args],
            cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_history_is_a_read_tool_and_labels_each_revision(self):
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "the store as first written")
        self.kb("set", "first-fact", "description", "a corrected claim")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "correct first-fact")

        self.handshake()
        tools = {t["name"]: t for t in self.result_of(self.send("tools/list"))["tools"]}
        self.assertTrue(tools["history"]["annotations"]["readOnlyHint"])

        result = self.result_of(self.call("history", {"name": "first-fact"}))
        self.assertFalse(result["isError"])
        changes = [r["change"] for r in result["structuredContent"]["revisions"]]
        self.assertEqual(changes, ["created", "claim"])
        self.assertIn("claim changed", result["content"][0]["text"])

    def test_without_a_repository_it_is_an_error_not_an_empty_history(self):
        self.handshake()
        result = self.result_of(self.call("history", {"name": "first-fact"}))
        self.assertTrue(result["isError"])
        self.assertIn("git", result["content"][0]["text"])

    def test_history_of_a_missing_entry_is_an_error(self):
        self.git("init", "-q", "-b", "main")
        self.handshake()
        result = self.result_of(self.call("history", {"name": "no-such-entry"}))
        self.assertTrue(result["isError"])


class TestJudgeIsAWriteTool(McpTestCase):
    read_only = True

    def test_judging_is_gone_in_read_only_mode_but_candidates_remain(self):
        self.handshake()
        names = {t["name"] for t in self.result_of(self.send("tools/list"))["tools"]}
        self.assertNotIn("judge", names)
        self.assertIn("duplicate_candidates", names)
        self.assertIn("consolidate", names)


class TestArchiveOverMcp(McpTestCase):
    def test_archiving_is_staged_like_any_other_proposal(self):
        self.handshake()
        result = self.result_of(self.call(
            "propose_update", {"name": "second-fact", "archive": True}))
        self.assertFalse(result["isError"])
        self.assertIn("archived", result["structuredContent"]["changed"])
        self.assertFalse(result["structuredContent"]["committed"])
        self.assertRegex(self.entry_text("second-fact"), r"archived: \d{4}-\d{2}-\d{2}")

    def test_an_archived_entry_drops_out_of_search(self):
        self.kb("set", "first-fact", "description", "shared subject matter")
        self.kb("set", "second-fact", "description", "shared subject matter")
        self.handshake()
        self.call("propose_update", {"name": "second-fact", "archive": True})
        result = self.result_of(self.call("search", {"query": "shared subject"}))
        names = [h["name"] for h in result["structuredContent"]["hits"]]
        self.assertIn("first-fact", names)
        self.assertNotIn("second-fact", names)

    def test_archived_entries_can_be_searched_on_request(self):
        self.kb("set", "second-fact", "description", "shared subject matter")
        self.handshake()
        self.call("propose_update", {"name": "second-fact", "archive": True})
        result = self.result_of(self.call(
            "search", {"query": "shared subject", "include_archived": True}))
        names = [h["name"] for h in result["structuredContent"]["hits"]]
        self.assertIn("second-fact", names)

    def test_unarchiving_puts_it_back(self):
        self.handshake()
        self.call("propose_update", {"name": "second-fact", "archive": True})
        result = self.result_of(self.call(
            "propose_update", {"name": "second-fact", "archive": False}))
        self.assertFalse(result["isError"])
        self.assertNotIn("archived:", self.entry_text("second-fact"))

    def test_archiving_twice_is_a_tool_error(self):
        self.handshake()
        self.call("propose_update", {"name": "second-fact", "archive": True})
        result = self.result_of(self.call(
            "propose_update", {"name": "second-fact", "archive": True}))
        self.assertTrue(result["isError"])
        self.assertIn("already archived", result["content"][0]["text"])

    def test_unarchiving_a_live_entry_is_a_tool_error(self):
        self.handshake()
        result = self.result_of(self.call(
            "propose_update", {"name": "first-fact", "archive": False}))
        self.assertTrue(result["isError"])
        self.assertIn("not archived", result["content"][0]["text"])

    def test_the_archived_status_is_offered_by_the_status_tool(self):
        self.handshake()
        tools = {t["name"]: t for t in self.result_of(self.send("tools/list"))["tools"]}
        self.assertIn("archived", tools["status"]["inputSchema"]["properties"]["status"]["enum"])
        self.call("propose_update", {"name": "second-fact", "archive": True})
        result = self.result_of(self.call("status", {"status": "archived"}))
        names = [r["name"] for r in result["structuredContent"]["entries"]]
        self.assertEqual(names, ["second-fact"])


class TestReadOnlyMode(McpTestCase):
    read_only = True

    def test_the_write_tool_is_not_advertised(self):
        self.handshake()
        names = {t["name"] for t in self.result_of(self.send("tools/list"))["tools"]}
        self.assertNotIn("propose_update", names)
        self.assertIn("context", names)

    def test_calling_the_write_tool_explains_why_it_is_gone(self):
        self.handshake()
        response = self.call("propose_update", {"name": "first-fact", "verify": True})
        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("read-only", response["error"]["message"])

    def test_reads_still_work(self):
        self.handshake()
        result = self.result_of(self.call("get", {"name": "first-fact"}))
        self.assertFalse(result["isError"])


class TestResources(McpTestCase):
    def test_every_entry_is_listed_as_a_resource(self):
        self.handshake()
        resources = self.result_of(self.send("resources/list"))["resources"]
        uris = {r["uri"] for r in resources}
        self.assertIn("kb://entry/first-fact", uris)
        self.assertIn("kb://entry/second-fact", uris)
        self.assertIn("kb://agent", uris)
        for r in resources:
            self.assertEqual(r["mimeType"], "text/markdown")

    def test_an_archived_entry_is_listed_but_labelled(self):
        # Every other retrieval surface on this server drops archived entries.
        # A resource listing cannot: a client needs to find the entry it wants
        # to un-archive. So it stays listed and carries the label instead --
        # the same "appears, classified" policy `status` uses.
        self.call("propose_update", {"name": "second-fact", "archive": True})
        resources = self.result_of(self.send("resources/list"))["resources"]
        by_uri = {r["uri"]: r for r in resources}
        self.assertIn("kb://entry/second-fact", by_uri)
        retired = by_uri["kb://entry/second-fact"]
        self.assertIn("archived", retired["title"])
        self.assertTrue(retired["description"].startswith("[archived] "))

    def test_a_live_entry_carries_no_archived_label(self):
        self.handshake()
        resources = self.result_of(self.send("resources/list"))["resources"]
        live = {r["uri"]: r for r in resources}["kb://entry/first-fact"]
        self.assertNotIn("archived", live["title"])
        self.assertNotIn("[archived]", live["description"])

    def test_an_archived_entry_resource_still_reads_back_in_full(self):
        self.call("propose_update", {"name": "second-fact", "archive": True})
        result = self.result_of(self.send("resources/read", {"uri": "kb://entry/second-fact"}))
        self.assertEqual(result["contents"][0]["text"], self.entry_text("second-fact"))

    def test_an_entry_resource_reads_back_the_file(self):
        self.handshake()
        result = self.result_of(self.send("resources/read", {"uri": "kb://entry/first-fact"}))
        self.assertEqual(result["contents"][0]["text"], self.entry_text("first-fact"))

    def test_the_agent_resource_reads_the_entry_point_doc(self):
        self.handshake()
        result = self.result_of(self.send("resources/read", {"uri": "kb://agent"}))
        self.assertIn("Entry Point", result["contents"][0]["text"])

    def test_an_unknown_resource_is_a_resource_not_found_error(self):
        self.handshake()
        for uri in ("kb://entry/ghost", "kb://nonsense", "file:///etc/passwd"):
            response = self.send("resources/read", {"uri": uri})
            self.assertEqual(response["error"]["code"], -32002, uri)

    def test_resources_read_without_a_uri_is_an_invalid_params_error(self):
        self.handshake()
        response = self.send("resources/read", {})
        self.assertEqual(response["error"]["code"], -32602)

    def test_resource_listing_omits_the_agent_entry_when_agent_md_is_absent(self):
        (self.root / "memory" / "AGENT.md").unlink()
        self.handshake()
        resources = self.result_of(self.send("resources/list"))["resources"]
        self.assertNotIn("kb://agent", {r["uri"] for r in resources})

    def test_a_uri_template_is_published(self):
        self.handshake()
        templates = self.result_of(self.send("resources/templates/list"))["resourceTemplates"]
        self.assertEqual(templates[0]["uriTemplate"], "kb://entry/{name}")


class TestCaptureOverMcp(McpTestCase):
    PROSE = ("A boat sails against the wind by tacking across it, because the "
             "sail works as a wing generating lift sideways rather than simply "
             "catching the air and being pushed along by it.")

    def test_passage_alone_reports_neighbours_and_writes_nothing(self):
        self.handshake()
        result = self.result_of(self.call("capture", {"passage": self.PROSE}))
        self.assertFalse(result["isError"])
        self.assertFalse(result["structuredContent"]["written"])
        self.assertIn("Nothing written", result["content"][0]["text"])
        self.assertFalse((self.root / "memory" / "semantic" / "sailing.md").exists())

    def test_type_and_name_stage_an_unverified_entry(self):
        self.handshake()
        result = self.result_of(self.call("capture", {
            "passage": self.PROSE, "type": "semantic", "name": "sailing"}))
        self.assertFalse(result["isError"])
        text = self.entry_text("sailing")
        self.assertIn("confidence: unverified", text)
        self.assertIn("tacking across it", text)
        self.assertFalse(result["structuredContent"]["committed"])
        self.assertIn("git diff", result["content"][0]["text"])

    def test_extend_appends_to_an_entry_instead_of_writing_a_twin(self):
        self.handshake()
        before = sorted(p.name for p in (self.root / "memory" / "semantic").iterdir())
        result = self.result_of(self.call("capture", {
            "passage": "Restated once more.", "extend": "first-fact"}))
        self.assertFalse(result["isError"])
        self.assertIn("Restated once more.", self.entry_text("first-fact"))
        self.assertEqual(
            before, sorted(p.name for p in (self.root / "memory" / "semantic").iterdir()))

    def test_extend_and_a_new_name_together_are_refused(self):
        self.handshake()
        result = self.result_of(self.call("capture", {
            "passage": self.PROSE, "extend": "first-fact",
            "type": "semantic", "name": "sailing"}))
        self.assertTrue(result["isError"])
        self.assertFalse((self.root / "memory" / "semantic" / "sailing.md").exists())

    def test_an_empty_passage_is_a_tool_error(self):
        self.handshake()
        self.assertTrue(self.result_of(self.call("capture", {"passage": "  "}))["isError"])

    def test_a_colliding_slug_is_a_tool_error_not_a_dead_server(self):
        self.handshake()
        result = self.result_of(self.call("capture", {
            "passage": self.PROSE, "type": "semantic", "name": "first-fact"}))
        self.assertTrue(result["isError"])
        self.assertIn("already exists", result["content"][0]["text"])
        # the server must still answer afterwards — scaffold_entry used to exit
        self.assertFalse(self.result_of(self.call("search", {"query": "fact"}))["isError"])

    def test_a_prospective_capture_without_a_due_date_is_a_tool_error(self):
        self.handshake()
        result = self.result_of(self.call("capture", {
            "passage": self.PROSE, "type": "prospective", "name": "check-sails"}))
        self.assertTrue(result["isError"])
        self.assertIn("due", result["content"][0]["text"])


class TestCaptureIsAWriteTool(McpTestCase):
    read_only = True

    def test_it_is_gone_in_read_only_mode(self):
        self.handshake()
        names = {t["name"] for t in self.result_of(self.send("tools/list"))["tools"]}
        self.assertNotIn("capture", names)
        response = self.call("capture", {"passage": "anything"})
        self.assertEqual(response["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
