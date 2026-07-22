#!/usr/bin/env python3
"""Stdlib unittest suite for scripts/visualize.py, run against a temp KB."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class VisualizeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        (self.root / "scripts").mkdir()
        (self.root / "memory" / "templates").mkdir(parents=True)
        (self.root / "memory" / "schema").mkdir(parents=True)
        shutil.copy(REPO_ROOT / "scripts" / "kb.py", self.root / "scripts" / "kb.py")
        shutil.copy(REPO_ROOT / "scripts" / "visualize.py", self.root / "scripts" / "visualize.py")
        shutil.copy(
            REPO_ROOT / "memory" / "templates" / "entry.template.md",
            self.root / "memory" / "templates" / "entry.template.md",
        )
        shutil.copy(
            REPO_ROOT / "memory" / "schema" / "entry.schema.json",
            self.root / "memory" / "schema" / "entry.schema.json",
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def run_kb(self, *args):
        return subprocess.run(
            [sys.executable, str(self.root / "scripts" / "kb.py"), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
        )

    def run_visualize(self):
        return subprocess.run(
            [sys.executable, str(self.root / "scripts" / "visualize.py")],
            cwd=self.root,
            capture_output=True,
            text=True,
        )

    def edit_frontmatter(self, entry_type, slug, **fields):
        import re

        path = self.root / "memory" / entry_type / f"{slug}.md"
        text = path.read_text()
        for key, value in fields.items():
            if key == "links":
                rendered = "[" + ", ".join(value) + "]"
                text = text.replace("links: []", f"links: {rendered}")
            else:
                text = re.sub(rf"^{key}:.*$", f"{key}: {value}", text, flags=re.MULTILINE)
        path.write_text(text)

    def test_empty_kb_produces_placeholder_node(self):
        result = self.run_visualize()
        self.assertEqual(result.returncode, 0, result.stderr)
        mmd = (self.root / "memory" / "_generated" / "graph.mmd").read_text()
        self.assertIn("no entries yet", mmd)
        md = (self.root / "memory" / "_generated" / "graph.md").read_text()
        self.assertIn("```mermaid", md)

    def test_entries_become_nodes_with_type_class(self):
        self.run_kb("new", "graph-entry", "--type", "procedural")
        result = self.run_visualize()
        self.assertEqual(result.returncode, 0, result.stderr)
        mmd = (self.root / "memory" / "_generated" / "graph.mmd").read_text()
        self.assertIn("n_graph_entry", mmd)
        self.assertIn(":::procedural", mmd)

    def test_links_become_edges(self):
        self.run_kb("new", "source-entry", "--type", "semantic")
        self.run_kb("new", "target-entry", "--type", "semantic")
        self.edit_frontmatter("semantic", "source-entry", links=["target-entry"])
        result = self.run_visualize()
        self.assertEqual(result.returncode, 0, result.stderr)
        mmd = (self.root / "memory" / "_generated" / "graph.mmd").read_text()
        self.assertIn("n_source_entry --> n_target_entry", mmd)

    def test_dangling_link_produces_no_edge(self):
        self.run_kb("new", "lonely-entry", "--type", "semantic")
        self.edit_frontmatter("semantic", "lonely-entry", links=["nonexistent-target"])
        result = self.run_visualize()
        self.assertEqual(result.returncode, 0, result.stderr)
        mmd = (self.root / "memory" / "_generated" / "graph.mmd").read_text()
        self.assertNotIn("-->", mmd)

    def test_index_groups_entries_by_type(self):
        self.run_kb("new", "semantic-entry", "--type", "semantic")
        self.run_kb("new", "procedural-entry", "--type", "procedural")
        result = self.run_visualize()
        self.assertEqual(result.returncode, 0, result.stderr)
        index = (self.root / "memory" / "_generated" / "index.md").read_text()
        self.assertIn("# Memory index", index)
        self.assertIn("## semantic", index)
        self.assertIn("`semantic-entry`", index)
        self.assertIn("## procedural", index)
        self.assertIn("`procedural-entry`", index)
        semantic_pos = index.index("## semantic")
        procedural_pos = index.index("## procedural")
        semantic_entry_pos = index.index("`semantic-entry`")
        self.assertTrue(semantic_pos < semantic_entry_pos < procedural_pos)

    def test_index_empty_kb_has_no_type_sections(self):
        result = self.run_visualize()
        self.assertEqual(result.returncode, 0, result.stderr)
        index = (self.root / "memory" / "_generated" / "index.md").read_text()
        self.assertIn("# Memory index", index)
        self.assertNotIn("## semantic", index)


if __name__ == "__main__":
    unittest.main()
