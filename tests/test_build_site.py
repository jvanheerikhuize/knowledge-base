"""Tests for scripts/build_site.py — the static overview builder."""
import html as html_mod
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import build_site  # noqa: E402
import kb  # noqa: E402


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

    def test_a_code_span_is_inert(self):
        # An entry documenting the syntax means the literal text. Rendering it
        # as a wikilink styled it as a dangling link to an entry nobody meant.
        out = self.render("resolved `[[wikilinks]]`, links out and backlinks")
        self.assertIn("<code>[[wikilinks]]</code>", out)
        self.assertNotIn("missing", out)

    def test_a_resolvable_wikilink_inside_a_code_span_is_still_inert(self):
        out = self.render("write `[[other-entry]]` to link it")
        self.assertIn("<code>[[other-entry]]</code>", out)
        self.assertNotIn('href="other-entry.html"', out)

    def test_emphasis_markers_inside_a_code_span_are_left_alone(self):
        out = self.render("the glob `**/*.py` matches")
        self.assertIn("<code>**/*.py</code>", out)
        self.assertNotIn("<strong>", out)

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

    def test_data_json_carries_the_aggregate_stats(self):
        stats = json.loads((self.out / "data.json").read_text())["stats"]
        self.assertEqual(stats["entries"], self.count)
        for key in ("by_type", "by_confidence", "links", "age_days",
                    "created_by_month"):
            self.assertIn(key, stats)

    def test_index_reports_link_density_and_median_age(self):
        index = (self.out / "index.html").read_text()
        stats = json.loads((self.out / "data.json").read_text())["stats"]
        self.assertIn(f"<b>{stats['links']['per_entry']}</b> per entry", index)
        self.assertIn(f"<b>{stats['age_days']['median']}d</b> median since verified",
                      index)

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


class EmptyStoreTests(unittest.TestCase):
    """The page-rendering functions are pure over `entries`, so the empty-KB
    branches can be exercised directly without standing up a whole empty
    store on disk."""

    def test_mermaid_source_falls_back_to_a_placeholder_node(self):
        self.assertIn('empty["(no entries yet)"]', build_site.mermaid_source([]))

    def test_index_page_falls_back_to_a_placeholder_message(self):
        self.assertIn('<p class="empty">No entries yet.</p>', build_site.build_index([]))

    def test_index_page_stats_are_zero(self):
        index = build_site.build_index([])
        self.assertIn("<b>0</b> entries", index)
        self.assertIn("<b>—</b> newest", index)

    def test_index_page_without_a_stats_block_reads_the_store_anyway_not(self):
        # build_index is pure over its arguments: omitting stats must render
        # placeholders, not silently measure the real repo.
        index = build_site.build_index([])
        self.assertIn("<b>0.0</b> per entry", index)
        self.assertIn("<b>—d</b> median since verified", index)


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


class ChangesPageTests(unittest.TestCase):
    """`build_changes` — the reviewable view of `.kb/log.md` (ROADMAP Phase 10)."""

    entries = [{"name": "known-entry", "type": "semantic"}]

    def test_empty_log_shows_the_placeholder(self):
        out = build_site.build_changes([], self.entries)
        self.assertIn('<p class="empty">No mutations recorded yet.</p>', out)

    def test_a_record_renders_date_action_type_and_link(self):
        records = [{
            "date": "2026-08-02", "action": "created",
            "type": "semantic", "name": "known-entry", "detail": "",
        }]
        out = build_site.build_changes(records, self.entries)
        self.assertIn("2026-08-02", out)
        self.assertIn("created", out)
        self.assertIn('href="entry/known-entry.html"', out)

    def test_detail_is_shown_and_escaped(self):
        records = [{
            "date": "2026-08-02", "action": "linked",
            "type": "semantic", "name": "known-entry", "detail": "-> <script>x</script>",
        }]
        out = build_site.build_changes(records, self.entries)
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn("<script>x</script>", out)

    def test_a_deleted_entry_is_not_linked(self):
        records = [{
            "date": "2026-08-02", "action": "deleted",
            "type": "semantic", "name": "gone-entry", "detail": "",
        }]
        out = build_site.build_changes(records, self.entries)
        self.assertNotIn('href="entry/gone-entry.html"', out)
        self.assertIn("gone-entry", out)
        self.assertIn("(deleted)", out)


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

    def test_index_links_to_changes(self):
        self.assertIn('href="changes.html"', (self.out / "index.html").read_text())

    def test_changes_page_is_built_and_lists_real_log_mutations(self):
        # The real .kb/log.md always has at least one "created" entry — the
        # store did not spring into existence with zero mutations.
        html = (self.out / "changes.html").read_text()
        self.assertTrue((self.out / "changes.html").exists())
        self.assertIn("created", html)

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


class RgbaTests(unittest.TestCase):
    def test_hex_is_split_into_channels_with_alpha(self):
        self.assertEqual(build_site._rgba("#ff0000", 0.5), "rgba(255,0,0,0.50)")

    def test_alpha_is_formatted_to_two_places(self):
        self.assertEqual(build_site._rgba("#000000", 1), "rgba(0,0,0,1.00)")


class TimelinePageTests(unittest.TestCase):
    """`build_timeline` — ROADMAP Phase 8: growth by month, a type × status
    heat map, and every created/verified event, newest first."""

    def entries(self):
        return [
            {"name": "old-fact", "type": "semantic", "created": "2026-01-05",
             "last_verified": "2026-01-05", "status": "current"},
            {"name": "new-fact", "type": "semantic", "created": "2026-07-20",
             "last_verified": "2026-08-01", "status": "ageing"},
            {"name": "a-log", "type": "episodic", "created": "2026-07-20",
             "last_verified": "", "status": "stale"},
        ]

    def test_empty_store_falls_back_to_placeholders(self):
        out = build_site.build_timeline([])
        self.assertIn('<p class="empty">No dated entries yet.</p>', out)
        self.assertIn('<p class="empty">Nothing to plot yet.</p>', out)

    def test_bars_group_by_creation_month(self):
        out = build_site.build_timeline(self.entries())
        self.assertIn("2026-01", out)
        self.assertIn("2026-07", out)
        # two entries created in 2026-07, one in 2026-01
        self.assertIn('<span class="bar-count">2</span>', out)
        self.assertIn('<span class="bar-count">1</span>', out)

    def test_heatmap_cell_carries_type_and_status(self):
        out = build_site.build_timeline(self.entries())
        self.assertIn('title="1 semantic × current"', out)
        self.assertIn('title="1 semantic × ageing"', out)
        self.assertIn('title="1 episodic × stale"', out)

    def test_events_include_both_created_and_verified_and_link_to_the_entry(self):
        out = build_site.build_timeline(self.entries())
        self.assertIn('href="entry/old-fact.html"', out)
        self.assertIn("created", out)
        self.assertIn("verified", out)
        # created == last_verified must not double up as two identical events
        self.assertEqual(out.count(">old-fact<"), 1)

    def test_events_are_sorted_newest_first(self):
        out = build_site.build_timeline(self.entries())
        self.assertLess(out.index("2026-08-01"), out.index("2026-01-05"))

    def test_page_is_built_and_linked_from_the_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "site"
            build_site.build(out)
            self.assertTrue((out / "timeline.html").exists())
            self.assertIn('href="timeline.html"', (out / "index.html").read_text())


class SavedSearchTests(unittest.TestCase):
    """Saved searches as shareable URLs (ROADMAP Phase 8): the index page's
    client script must read `?q=`/`?type=` on load and keep the URL in sync,
    since the actual filtering only runs in a browser."""

    def test_index_reads_and_writes_query_params(self):
        index = build_site.build_index([])
        self.assertIn("URLSearchParams(location.search)", index)
        self.assertIn("history.replaceState", index)

    def test_copy_link_button_is_present(self):
        index = build_site.build_index([])
        self.assertIn('id="copy-link"', index)
        self.assertIn("navigator.clipboard.writeText(location.href)", index)


class StatusForecastTests(unittest.TestCase):
    """The status board is a snapshot, and a store that is about to go stale
    all at once has a perfectly clean snapshot. The forecast is the only thing
    on the page about a date other than today, so it has to survive there."""

    FORECAST = {
        "today": "2026-08-05", "cycle_days": 90, "dated": 6, "undated": 0,
        "first": "2026-10-25", "last": "2026-10-27", "span_days": 2,
        "busiest": "2026-10-25", "already_due": 0, "is_cohort": True,
        "by_date": [["2026-10-25", 4], ["2026-10-26", 1], ["2026-10-27", 1]],
    }

    def test_the_window_and_the_busiest_day_are_rendered(self):
        page = build_site.build_status([], [], None, self.FORECAST)
        self.assertIn("2026-10-25", page)
        self.assertIn("2026-10-27", page)
        self.assertIn("2d wide", page)
        self.assertIn("busiest 2026-10-25 (4)", page)

    def test_a_cohort_is_named_as_one(self):
        page = build_site.build_status([], [], None, self.FORECAST)
        self.assertIn("one cohort", page)
        spread = dict(self.FORECAST, is_cohort=False, span_days=70)
        self.assertNotIn("one cohort",
                         build_site.build_status([], [], None, spread))

    def test_the_page_builds_without_a_forecast(self):
        page = build_site.build_status([], [])
        self.assertNotIn("Coming due", page)


class BundleContractTests(unittest.TestCase):
    """`site/data.json` is the published bundle — the only way to read this
    store without importing the tooling. Its shape is therefore a contract,
    not an implementation detail: these tests pin the exact key sets so a
    field cannot be added, dropped, or renamed without someone deciding to
    bump `BUNDLE_SCHEMA_VERSION` in the same commit."""

    BUNDLE_KEYS = {
        "schema_version", "generated", "count", "repo", "confidence_levels",
        "stale_days", "triage", "stats", "status_model", "status", "entries",
    }
    ENTRY_KEYS = {
        "name", "type", "description", "confidence", "effective_confidence",
        "decayed_by", "authority", "created", "last_verified", "source", "due",
        "links", "body", "path", "backlinks", "status", "action", "review_by",
    }
    # `stats` is published inside the bundle, so its shape is part of the
    # contract too. Pinning only the top-level keys let the whole aggregate
    # block change silently, which is the gap this class exists to close.
    STATS_KEYS = {
        "entries", "archived", "by_type", "by_confidence",
        "by_effective_confidence", "decayed", "links", "age_days",
        "body_words", "created_by_month", "review_forecast",
    }
    FORECAST_KEYS = {
        "today", "cycle_days", "dated", "undated", "first", "last",
        "span_days", "busiest", "already_due", "is_cohort", "by_date",
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name) / "site"
        build_site.build(self.out)
        self.data = json.loads((self.out / "data.json").read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def test_bundle_keys_are_exactly_the_published_set(self):
        self.assertEqual(set(self.data), self.BUNDLE_KEYS)

    def test_entry_keys_are_exactly_the_published_set(self):
        for entry in self.data["entries"]:
            self.assertEqual(set(entry), self.ENTRY_KEYS, entry["name"])

    def test_stats_keys_are_exactly_the_published_set(self):
        self.assertEqual(set(self.data["stats"]), self.STATS_KEYS)

    def test_review_forecast_ships_so_a_consumer_can_see_the_coming_load(self):
        # The bundle already carried every *current* status. What it could not
        # express is that a store written in one burst comes due in one burst,
        # which is a property of the dates in aggregate, not of any entry.
        forecast = self.data["stats"]["review_forecast"]
        self.assertEqual(set(forecast), self.FORECAST_KEYS)
        self.assertEqual(forecast["cycle_days"], kb.STALE_DAYS)

    def test_schema_version_is_declared(self):
        self.assertIsInstance(self.data["schema_version"], int)
        self.assertEqual(self.data["schema_version"], build_site.BUNDLE_SCHEMA_VERSION)

    def test_decay_rules_ship_so_a_consumer_can_recompute_them(self):
        # A bundle is read long after it is built, so the derived values in it
        # age. Exporting the rules as well as the results is what makes the
        # staleness recomputable by a reader that has no access to kb.py.
        self.assertEqual(self.data["stale_days"], kb.STALE_DAYS)
        self.assertEqual(self.data["confidence_levels"], kb.CONFIDENCE_LEVELS)

    def test_entries_carry_the_as_read_confidence_not_only_the_as_written_one(self):
        by_name = {s["name"]: s for s in self.data["status"]}
        for entry in self.data["entries"]:
            status = by_name[entry["name"]]
            self.assertEqual(entry["effective_confidence"],
                             status["effective_confidence"], entry["name"])
            self.assertEqual(entry["decayed_by"], status["decayed_by"], entry["name"])

    def test_effective_confidence_is_derived_not_copied_from_frontmatter(self):
        # Today every entry is fresh, so as-written and as-read agree and this
        # field could be a copy of `confidence` without any test noticing.
        # Substituting the decay function proves collect() actually calls it.
        real = build_site.collect()
        original = build_site.effective_confidence
        build_site.effective_confidence = lambda fm, today=None: ("sentinel", 3)
        try:
            entries = build_site.collect()
        finally:
            build_site.effective_confidence = original
        self.assertTrue(entries)
        for entry, before in zip(entries, real):
            self.assertEqual(entry["effective_confidence"], "sentinel")
            self.assertEqual(entry["decayed_by"], 3)
            # the recorded claim is untouched — decay is a read-time view
            self.assertEqual(entry["confidence"], before["confidence"])


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
