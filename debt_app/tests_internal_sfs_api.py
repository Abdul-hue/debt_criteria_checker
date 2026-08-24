"""Smoke tests for the token-free internal SFS guideline API.

Covers the whole CRUD surface with NO auth header at all — a regression here
means the CA backend starts getting 401/404 from a route it depends on.
"""

from django.test import TestCase, override_settings

from debt_app.models import ExpenditureGuideline, GuidelineCategory

BASE = "/api/v1/criteria/internal/sfs"


class InternalSFSGuidelineAPITests(TestCase):
    # The test DB arrives pre-seeded by migrations (~54 guidelines), so every
    # assertion here is scoped to fixtures this class owns — never absolute
    # counts or "first row" indexing.
    def setUp(self):
        self.group = GuidelineCategory.objects.create(name="ZZ Test Group", sort_order=999)
        self.guideline = ExpenditureGuideline.objects.create(
            category="test_housekeeping",
            label="Housekeeping",
            category_group=self.group,
            adult_1="289.75",
            adult_2="372.10",
            aryza_aliases="Groceries",
        )

    # --- guidelines ---------------------------------------------------------

    def test_list_requires_no_token(self):
        res = self.client.get(f"{BASE}/guidelines/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["count"], len(body["results"]))
        mine = [g for g in body["results"] if g["category"] == "test_housekeeping"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["adult_1"], 289.75)

    def test_list_filters(self):
        self.assertEqual(self.client.get(f"{BASE}/guidelines/?category=test_housekeeping").json()["count"], 1)
        self.assertEqual(self.client.get(f"{BASE}/guidelines/?category=nope").json()["count"], 0)
        self.assertEqual(
            self.client.get(f"{BASE}/guidelines/?category_group={self.group.id}").json()["count"], 1
        )

    def test_get_by_id_and_by_category(self):
        by_id = self.client.get(f"{BASE}/guidelines/{self.guideline.id}/")
        by_cat = self.client.get(f"{BASE}/guidelines/by-category/test_housekeeping/")
        self.assertEqual(by_id.status_code, 200)
        self.assertEqual(by_cat.status_code, 200)
        self.assertEqual(by_id.json(), by_cat.json())

    def test_get_unknown_returns_404_payload(self):
        res = self.client.get(f"{BASE}/guidelines/by-category/does-not-exist/")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["code"], "NOT_FOUND")

    def test_create(self):
        res = self.client.post(
            f"{BASE}/guidelines/",
            data={
                "category": "test_mot_spares",
                "label": "MOT and Spares",
                "category_group": self.group.id,
                "min": True,
                "max": True,
                "per_vehicle": 20.00,
                "per_vehicle_max": 33.00,
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual(body["category"], "test_mot_spares")
        self.assertEqual(body["per_vehicle"], 20.0)
        self.assertEqual(body["per_vehicle_max"], 33.0)
        self.assertTrue(body["min"] and body["max"])
        # unspecified amounts default to 0, not null
        self.assertEqual(body["adult_1"], 0.0)

    def test_create_validation(self):
        missing_cat = self.client.post(
            f"{BASE}/guidelines/", data={"label": "x"}, content_type="application/json")
        self.assertEqual(missing_cat.status_code, 400)
        self.assertEqual(missing_cat.json()["code"], "MISSING_CATEGORY")

        missing_label = self.client.post(
            f"{BASE}/guidelines/", data={"category": "x"}, content_type="application/json")
        self.assertEqual(missing_label.json()["code"], "MISSING_LABEL")

        dupe = self.client.post(
            f"{BASE}/guidelines/",
            data={"category": "test_housekeeping", "label": "Dupe"},
            content_type="application/json",
        )
        self.assertEqual(dupe.json()["code"], "DUPLICATE_CATEGORY")

        bad_group = self.client.post(
            f"{BASE}/guidelines/",
            data={"category": "test_new_cat", "label": "New", "category_group": 99999},
            content_type="application/json",
        )
        self.assertEqual(bad_group.json()["code"], "INVALID_CATEGORY_GROUP")

    def test_patch_by_id_and_by_category(self):
        res = self.client.patch(
            f"{BASE}/guidelines/{self.guideline.id}/",
            data={"adult_1": 300.50, "notes": "updated"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["adult_1"], 300.5)
        self.assertEqual(res.json()["notes"], "updated")
        # untouched fields survive a partial update
        self.assertEqual(res.json()["adult_2"], 372.10)

        res2 = self.client.patch(
            f"{BASE}/guidelines/by-category/test_housekeeping/",
            data={"category_group": None},
            content_type="application/json",
        )
        self.assertEqual(res2.status_code, 200)
        self.assertIsNone(res2.json()["category_group"])

    def test_delete(self):
        res = self.client.delete(f"{BASE}/guidelines/{self.guideline.id}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(ExpenditureGuideline.objects.filter(pk=self.guideline.id).exists())

    def test_writes_blocked_from_foreign_ip(self):
        res = self.client.patch(
            f"{BASE}/guidelines/{self.guideline.id}/",
            data={"adult_1": 1},
            content_type="application/json",
            REMOTE_ADDR="10.20.30.40",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["code"], "WRITE_NOT_ALLOWED_FROM_HOST")
        # reads stay open from anywhere
        self.assertEqual(
            self.client.get(f"{BASE}/guidelines/", REMOTE_ADDR="10.20.30.40").status_code, 200
        )

    def test_spoofed_forwarded_header_cannot_pass_the_write_guard(self):
        """X-Forwarded-For is caller-controlled — it must not grant write access."""
        res = self.client.delete(
            f"{BASE}/guidelines/{self.guideline.id}/",
            REMOTE_ADDR="10.20.30.40",
            HTTP_X_FORWARDED_FOR="127.0.0.1",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["code"], "WRITE_NOT_ALLOWED_FROM_HOST")
        self.assertTrue(ExpenditureGuideline.objects.filter(pk=self.guideline.id).exists())

    @override_settings(INTERNAL_API_TRUSTED_PROXIES=["10.0.0.9"])
    def test_forwarded_header_honoured_only_behind_a_trusted_proxy(self):
        # Connection comes from the declared proxy → believe the hop it appended.
        allowed = self.client.patch(
            f"{BASE}/guidelines/{self.guideline.id}/",
            data={"notes": "via proxy"},
            content_type="application/json",
            REMOTE_ADDR="10.0.0.9",
            HTTP_X_FORWARDED_FOR="203.0.113.7, 127.0.0.1",
        )
        self.assertEqual(allowed.status_code, 200)

        # A client prepending a fake hop cannot promote itself: the last entry wins.
        blocked = self.client.patch(
            f"{BASE}/guidelines/{self.guideline.id}/",
            data={"notes": "spoof"},
            content_type="application/json",
            REMOTE_ADDR="10.0.0.9",
            HTTP_X_FORWARDED_FOR="127.0.0.1, 203.0.113.7",
        )
        self.assertEqual(blocked.status_code, 403)

    @override_settings(
        INTERNAL_API_ALLOWED_IPS=["127.0.0.1", "::1", "localhost", "192.168.80.52"]
    )
    def test_ca_backend_can_write_from_the_servers_own_lan_ip(self):
        """
        Production .env config: CA (:2310) reaches this service (:5010) by the
        server's LAN IP, so the connection's source address is that LAN IP —
        NOT 127.0.0.1. Listing it is what makes CA's writes work.
        """
        res = self.client.patch(
            f"{BASE}/guidelines/{self.guideline.id}/",
            data={"adult_1": 310.00},
            content_type="application/json",
            REMOTE_ADDR="192.168.80.52",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["adult_1"], 310.00)
        # Anything not on the list is still refused.
        self.assertEqual(
            self.client.patch(
                f"{BASE}/guidelines/{self.guideline.id}/",
                data={"adult_1": 1},
                content_type="application/json",
                REMOTE_ADDR="192.168.80.99",
            ).status_code,
            403,
        )

    @override_settings(INTERNAL_API_ALLOWED_IPS=["*"])
    def test_wildcard_allows_writes_from_anywhere(self):
        res = self.client.patch(
            f"{BASE}/guidelines/{self.guideline.id}/",
            data={"notes": "open"},
            content_type="application/json",
            REMOTE_ADDR="10.20.30.40",
        )
        self.assertEqual(res.status_code, 200)

    # --- categories ---------------------------------------------------------

    def test_category_crud(self):
        listing = self.client.get(f"{BASE}/categories/")
        self.assertEqual(listing.status_code, 200)
        mine = [c for c in listing.json()["results"] if c["id"] == self.group.id]
        self.assertEqual(len(mine), 1)
        self.assertEqual(
            [g["category"] for g in mine[0]["guidelines"]], ["test_housekeeping"]
        )

        created = self.client.post(
            f"{BASE}/categories/",
            data={"name": "ZZ Travel", "sort_order": 998},
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        new_id = created.json()["id"]

        detail = self.client.get(f"{BASE}/categories/{new_id}/")
        self.assertEqual(detail.status_code, 200)

        patched = self.client.patch(
            f"{BASE}/categories/{new_id}/",
            data={"upper_cap": 1200.00},
            content_type="application/json",
        )
        self.assertEqual(patched.json()["upper_cap"], 1200.00)

        self.assertEqual(self.client.delete(f"{BASE}/categories/{new_id}/").status_code, 204)
        self.assertEqual(self.client.get(f"{BASE}/categories/{new_id}/").status_code, 404)

    def test_deleting_group_keeps_guidelines(self):
        self.assertEqual(self.client.delete(f"{BASE}/categories/{self.group.id}/").status_code, 204)
        self.guideline.refresh_from_db()
        self.assertIsNone(self.guideline.category_group)

    def test_category_validation(self):
        res = self.client.post(f"{BASE}/categories/", data={}, content_type="application/json")
        self.assertEqual(res.json()["code"], "MISSING_NAME")
