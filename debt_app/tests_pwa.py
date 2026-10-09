"""
Lead Gen PWA: manifest, icons and the /sw.js service-worker route.
"""

import json
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from PIL import Image

PUBLIC = Path(settings.BASE_DIR) / "frontend" / "public"


class ServiceWorkerRouteTests(SimpleTestCase):

    def _built(self, body=b"self.addEventListener('fetch', () => {})"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dist = Path(tmp.name) / "frontend" / "dist"
        dist.mkdir(parents=True)
        (dist / "sw.js").write_bytes(body)
        return Path(tmp.name)

    def test_served_from_site_root_as_javascript_and_never_cached(self):
        with override_settings(BASE_DIR=self._built(b"// sw")):
            resp = self.client.get("/sw.js")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/javascript")
        self.assertEqual(resp.content, b"// sw")
        self.assertIn("no-cache", resp["Cache-Control"])
        self.assertIn("no-store", resp["Cache-Control"])

    def test_missing_build_is_404_not_the_spa_page(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=Path(tmp)):
            self.assertEqual(self.client.get("/sw.js").status_code, 404)


class ServiceWorkerSafetyTests(SimpleTestCase):
    """The worker must never persist case data: no Cache Storage, no IndexedDB."""

    def setUp(self):
        self.src = (PUBLIC / "sw.js").read_text(encoding="utf-8")

    def test_uses_no_persistent_storage(self):
        for forbidden in ("caches.", "indexedDB", "localStorage", "cache.put", "cache.add"):
            self.assertNotIn(forbidden, self.src, forbidden)

    def test_handles_page_navigations_only(self):
        self.assertIn("request.mode !== 'navigate'", self.src)
        for quoted in ("'/api", '"/api', "`/api"):  # no code path special-cases the API
            self.assertNotIn(quoted, self.src)

    def test_no_django_template_syntax(self):
        for token in ("{{", "{%", "{#"):
            self.assertNotIn(token, self.src)


class ManifestTests(SimpleTestCase):

    def setUp(self):
        self.manifest = json.loads((PUBLIC / "lead-gen.webmanifest").read_text(encoding="utf-8"))

    def test_launches_standalone_into_lead_gen(self):
        m = self.manifest
        self.assertEqual(m["display"], "standalone")
        self.assertEqual(m["start_url"], "/lead-gen")
        self.assertEqual(m["id"], "/lead-gen")
        self.assertEqual(m["scope"], "/")  # /login stays inside the app window
        for key in ("name", "short_name", "theme_color", "background_color"):
            self.assertTrue(m[key], key)

    def test_icons_exist_at_declared_sizes(self):
        purposes = set()
        for icon in self.manifest["icons"]:
            path = PUBLIC / icon["src"]
            self.assertTrue(path.exists(), icon["src"])
            w, h = (int(n) for n in icon["sizes"].split("x"))
            with Image.open(path) as im:
                self.assertEqual(im.size, (w, h), icon["src"])
                self.assertEqual(im.format, "PNG")
            purposes.add(icon["purpose"])
        sizes = {i["sizes"] for i in self.manifest["icons"] if i["purpose"] == "any"}
        self.assertTrue({"192x192", "512x512"} <= sizes)
        self.assertIn("maskable", purposes)
