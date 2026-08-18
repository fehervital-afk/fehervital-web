import json
import shutil
import unittest
from pathlib import Path

from scripts.build_public import DIST, ROOT, build


class PublicBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build()

    @classmethod
    def tearDownClass(cls):
        if DIST.exists():
            shutil.rmtree(DIST)

    def test_required_public_pages_are_published(self):
        required = {
            "index.html",
            "preview.html",
            "biorezonancia.html",
            "harmonyscan.html",
            "ai.html",
            "kapcsolat.html",
            "adatkezeles.html",
            "idopontfoglalas.html",
            "assets/css/style.css",
            "assets/js/app.js",
            "assets/content/pages.json",
        }
        for relative in required:
            self.assertTrue((DIST / relative).is_file(), relative)

    def test_private_admin_and_automation_files_are_not_published(self):
        forbidden = {
            "_local_admin",
            "local_admin_server.py",
            "scripts",
            ".github",
            ".git",
            ".local_backups",
            "assets/content/agents.json",
            "assets/content/ai_audit.json",
            "assets/content/ai_log.json",
            "assets/content/ai_tasks.json",
            "assets/content/automation.json",
            "assets/content/autopilot.json",
            "assets/content/business_intelligence.json",
            "assets/content/business_memory.json",
            "assets/content/business_os.json",
            "assets/content/ceo.json",
            "assets/content/content_generator.json",
            "assets/content/execution_queue.json",
            "assets/content/marketing.json",
            "assets/content/strategic_goals.json",
            "assets/content/weekly_report.json",
        }
        for relative in forbidden:
            self.assertFalse((DIST / relative).exists(), relative)

    def test_only_pages_json_is_exposed_from_content_directory(self):
        content_dir = DIST / "assets/content"
        published = {p.name for p in content_dir.iterdir() if p.is_file()}
        self.assertEqual(published, {"pages.json"})

    def test_pages_json_is_valid_json(self):
        data = json.loads((DIST / "assets/content/pages.json").read_text(encoding="utf-8"))
        self.assertIn("site", data)
        self.assertIn("pages", data)

    def test_build_does_not_modify_source_pages(self):
        self.assertTrue((ROOT / "_local_admin/index.html").is_file())
        self.assertTrue((ROOT / "assets/content/ai_tasks.json").is_file())


if __name__ == "__main__":
    unittest.main()
