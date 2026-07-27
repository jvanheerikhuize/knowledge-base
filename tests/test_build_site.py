"""Tests for scripts/build_site.py — the static overview builder."""
import html as html_mod
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import build_site  # noqa: E402


class MarkdownTests(unittest.TestCase):
    known = {"other-entry"}

    def render(self, md):
        return build_site.render_markdown(md, self.known)

    def test_paragraph_and_inline_code(self):
        out = self.render("hello `world`")
        self.assertIn("<p>hello <code>world</code></p>", out)

    def test_headings_are_demoted(self):
        # a level-1 heading in a body must not collide with the page <h1>
        self.assertIn("<h2>Title</h2>", self.render("# Title"))
        self.assertIn("<h3>Sub</h3>", self.render("## Sub"))

    def test_bold_and_italic(self):
        out = self.render("**bold** and *slanted*")
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn("<em>slanted</em>", out)

    def test_resolved_wikilink_becomes_a_link(self):
        out = self.render("see [[other-entry]]")
        self.assertIn('<a class="wl" href="other-entry.html">other-entry</a>', out)

    def test_dangling_wikilink_is_marked_not_linked(self):
        out = self.render("see [[nope]]")
        self.assertIn("missing", out)
        self.assertNotIn('href="nope.html"', out)

    def test_unordered_and_ordered_lists(self):
        self.assertIn("<ul><li>a</li><li>b</li></ul>", self.render("- a\n- b"))
        self.assertIn("<ol><li>a</li><li>b</li></ol>", self.render("1. a\n2. b"))

    def test_table(self):
        out = self.render("| A | B |\n|---|---|\n| 1 | 2 |")
        self.assertIn("<th>A</th>", out)
        self.assertIn("<td>2</td>", out)

    def test_fenced_code_is_escaped_not_interpreted(self):
        out = self.render("```\n<script>x</script>\n```")
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn("<script>", out)

    def test_html_in_prose_is_escaped(self):
        self.assertIn("&lt;b&gt;", self.render("literal <b> tag"))

    def test_markdown_link(self):
        out = self.render("[docs](https://example.com)")
        self.assertIn('<a href="https://example.com">docs</a>', out)


class CollectTests(unittest.TestCase):
    def test_collect_reads_the_real_memory_tree(self):
        entries = build_site.collect()
        self.assertTrue(entries, "expected at least one memory entry")
        for e in entries:
            self.assertIn(e["type"], build_site.TYPES)
            self.assertTrue(e["name"])
            self.assertIsInstance(e["links"], list)

    def test_links_are_resolved_and_backlinks_are_symmetric(self):
        entries = build_site.collect()
        names = {e["name"] for e in entries}
        by_name = {e["name"]: e for e in entries}
        for e in entries:
            for link in e["links"]:
                self.assertIn(link, names)
                self.assertIn(e["name"], by_name[link]["backlinks"])


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name) / "site"
        self.count = build_site.build(self.out)

    def tearDown(self):
        self.tmp.cleanup()

    def test_core_pages_exist(self):
        for name in ("index.html", "types.html", "graph.html", "style.css",
                     "data.json", ".nojekyll"):
            self.assertTrue((self.out / name).exists(), name)

    def test_one_page_per_entry(self):
        pages = list((self.out / "entry").glob("*.html"))
        self.assertEqual(len(pages), self.count)

    def test_data_json_is_valid_and_complete(self):
        data = json.loads((self.out / "data.json").read_text())
        self.assertEqual(data["count"], self.count)
        self.assertEqual(len(data["entries"]), self.count)
        first = data["entries"][0]
        for key in ("name", "type", "description", "confidence", "links",
                    "backlinks", "body", "path"):
            self.assertIn(key, first)

    def test_index_links_to_every_entry_page(self):
        index = (self.out / "index.html").read_text()
        for page in (self.out / "entry").glob("*.html"):
            self.assertIn(f'entry/{page.name}"', index)

    def test_graph_page_contains_mermaid_source(self):
        graph = (self.out / "graph.html").read_text()
        self.assertIn("flowchart LR", graph)
        self.assertIn('class="mermaid"', graph)

    def test_rebuild_is_clean(self):
        # a stale file from a previous build must not survive
        stray = self.out / "entry" / "gone.html"
        stray.write_text("stale")
        build_site.build(self.out)
        self.assertFalse(stray.exists())

    def test_entry_page_shows_frontmatter_and_backlinks(self):
        entries = build_site.collect()
        target = next(e for e in entries if e["backlinks"])
        html = (self.out / "entry" / f"{target['name']}.html").read_text()
        self.assertIn("confidence", html)
        self.assertIn("Linked from", html)
        self.assertIn(target["backlinks"][0], html)


class StatusPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name) / "site"
        self.count = build_site.build(self.out)
        self.html = (self.out / "status.html").read_text()

    def tearDown(self):
        self.tmp.cleanup()

    def test_page_is_built_and_linked_from_the_index(self):
        self.assertIn('href="status.html"', (self.out / "index.html").read_text())

    def test_legend_names_every_status_and_its_remedy(self):
        for status in build_site.STATUS_MODEL:
            self.assertIn(status["label"].lower(), self.html)
            self.assertIn(html_mod.escape(status["meaning"]), self.html)
            self.assertIn(html_mod.escape(status["action"]), self.html)

    def test_every_entry_appears_on_the_board(self):
        for page in (self.out / "entry").glob("*.html"):
            self.assertIn(f'entry/{page.name}"', self.html)

    def test_cards_carry_a_status_for_filtering(self):
        index = (self.out / "index.html").read_text()
        self.assertEqual(index.count("data-status="), self.count)

    def test_entry_page_states_its_status_and_review_date(self):
        entries = build_site.collect()
        page = (self.out / "entry" / f"{entries[0]['name']}.html").read_text()
        self.assertIn("status", page)
        self.assertIn("review by", page)

    def test_data_json_carries_the_status_board_and_model(self):
        data = json.loads((self.out / "data.json").read_text())
        self.assertEqual(len(data["status"]), self.count)
        self.assertEqual(
            [s["key"] for s in data["status_model"]], build_site.STATUS_ORDER
        )
        for record in data["status"]:
            self.assertIn(record["status"], build_site.STATUS_ORDER)


class TriageAndEditingTests(unittest.TestCase):
    """The affordances that let the site be triaged and edited, not just read."""

    slug = "someone/some-repo"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name) / "site"
        build_site.build(self.out, self.slug)
        self.entry = sorted((self.out / "entry").glob("*.html"))[0]

    def tearDown(self):
        self.tmp.cleanup()

    def test_triage_page_and_client_script_are_built(self):
        self.assertTrue((self.out / "triage.html").exists())
        self.assertTrue((self.out / "app.js").exists())

    def test_index_links_to_triage(self):
        self.assertIn('href="triage.html"', (self.out / "index.html").read_text())

    def test_entry_page_links_into_github(self):
        html = self.entry.read_text()
        self.assertIn(f"https://github.com/{self.slug}/edit/", html)
        self.assertIn(f"https://github.com/{self.slug}/issues/new?", html)

    def test_local_editing_controls_ship_hidden(self):
        # the same file is served by Pages (read-only) and serve.py (editable),
        # so the editor must start hidden and be revealed by app.js
        html = self.entry.read_text()
        self.assertIn('id="edit-toggle"', html)
        self.assertIn('class="editor" id="editor" hidden', html)
        self.assertIn('id="entry-data"', html)

    def test_pages_declare_the_api_base_for_the_client(self):
        self.assertIn("window.KB_API", self.entry.read_text())
        self.assertIn("app.js", self.entry.read_text())

    def test_client_stays_read_only_without_an_api(self):
        js = (self.out / "app.js").read_text()
        self.assertIn("capabilities", js)
        self.assertIn("editable", js)

    def test_without_a_repo_slug_no_github_links_are_emitted(self):
        out = pathlib.Path(self.tmp.name) / "anon"
        build_site.build(out, None)
        self.assertNotIn("https://github.com/None", (out / "index.html").read_text())

    def test_data_json_carries_repo_and_triage(self):
        data = json.loads((self.out / "data.json").read_text())
        self.assertEqual(data["repo"], self.slug)
        self.assertIsInstance(data["triage"], list)


class RepoSlugTests(unittest.TestCase):
    def test_explicit_slug_wins_and_is_normalized(self):
        self.assertEqual(build_site.repo_slug("owner/name/"), "owner/name")

    def test_edit_and_issue_urls_are_none_without_a_slug(self):
        self.assertIsNone(build_site.edit_url(None, "memory/semantic/x.md"))
        self.assertIsNone(build_site.issue_url(None, "t", "b"))

    def test_issue_url_escapes_its_query(self):
        url = build_site.issue_url("o/n", "a title", "a body")
        self.assertIn("title=a+title", url)
        self.assertIn("labels=triage", url)


if __name__ == "__main__":
    unittest.main()
