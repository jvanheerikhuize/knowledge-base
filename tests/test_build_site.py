"""Tests for scripts/build_site.py — the static overview builder."""
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


if __name__ == "__main__":
    unittest.main()
