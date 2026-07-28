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
            {"context", "search", "get", "triage", "status", "propose_update"},
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
        self.assertLessEqual(result["structuredContent"]["tokens"], 500)
        self.assertNotIn("text", result["structuredContent"])

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

    def test_a_uri_template_is_published(self):
        self.handshake()
        templates = self.result_of(self.send("resources/templates/list"))["resourceTemplates"]
        self.assertEqual(templates[0]["uriTemplate"], "kb://entry/{name}")


if __name__ == "__main__":
    unittest.main()
