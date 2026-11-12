import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "sync-grill-flow.sh"


class TestSyncLayout(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SCRIPT.read_text()

    def test_host_list_and_canonical_dedupe(self) -> None:
        for host in (
            '"$HOME/.claude"',
            '"$HOME/.codex"',
            '"$HOME/.config/muse"',
            '"$HOME/.gemini/config"',
            '"$HOME/.pi/agent"',
            '"$HOME/.zcode"',
        ):
            self.assertIn(host, self.text)
        self.assertIn("pwd -P", self.text)
        self.assertIn('grep -qxF "$canon"', self.text)

    def test_chmod_skill_and_local_share(self) -> None:
        self.assertIn("LOCAL_SHARE", self.text)
        self.assertIn('chmod +x "$skill_dst/scripts/grill-flow.py"', self.text)
        self.assertIn('chmod +x "$LOCAL_SHARE/grill-flow.py"', self.text)

    def test_skill_viewer_beside_scripts(self) -> None:
        self.assertIn('"$skill_dst/viewer"', self.text)
        self.assertIn('"$skill_dst/scripts"', self.text)
        self.assertIn("VIEWER_SRC", self.text)
        self.assertIn('cp -R "$VIEWER_SRC" "$skill_dst/viewer"', self.text)

    def test_flat_local_share_viewer(self) -> None:
        self.assertIn('"$LOCAL_SHARE/viewer"', self.text)
        self.assertIn('"$LOCAL_SHARE/grill-flow.py"', self.text)
        self.assertIn('cp -R "$VIEWER_SRC" "$LOCAL_SHARE/viewer"', self.text)

    def test_viewer_tree_includes_model_js(self) -> None:
        viewer = SCRIPT.parent / "viewer"
        self.assertTrue((viewer / "model.js").is_file())
        self.assertTrue((viewer / "app.js").is_file())
        self.assertTrue((viewer / "style.css").is_file())
        skill = SCRIPT.parent / "SKILL.md"
        text = skill.read_text()
        self.assertTrue(text.startswith("---\n"), "SKILL.md must open with YAML frontmatter")
        self.assertIn("name: grill-flow", text.split("---", 2)[1])
        self.assertIn("map browser", text)
        self.assertIn("GET /repo", text)
        self.assertIn("Layout / style locks", text)
        self.assertIn("coalesce adjacent", text)
        css = (viewer / "style.css").read_text()
        self.assertIn("layout / style LOCKS", css)
        self.assertIn(".flow-prose-section", css)
        self.assertIn(".flow-member-run", css)
        self.assertIn("#inspector-panel", css)
        model = (viewer / "model.js").read_text()
        self.assertIn("coalesceMemberRuns", model)
        self.assertIn("flowProseSections", model)

    def test_strip_tests_and_pycache(self) -> None:
        self.assertIn("__pycache__", self.text)
        self.assertIn("test_*.py", self.text)

    def test_cursor_mdc_path(self) -> None:
        self.assertIn("grill-flow.mdc", self.text)
        self.assertIn("$HOME/.cursor/rules", self.text)


if __name__ == "__main__":
    unittest.main()
