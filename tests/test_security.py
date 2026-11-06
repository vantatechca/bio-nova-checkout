from itsdangerous import URLSafeTimedSerializer

from app.security import AdminTokens


class TestAdminAuth:
    def test_login_with_correct_password(self, client):
        r = client.post("/api/admin/login", json={"password": "test-admin-pw"})
        assert r.status_code == 200 and r.json()["token"]

    def test_wrong_password(self, client):
        r = client.post("/api/admin/login", json={"password": "nope"})
        assert r.status_code == 401 and r.json() == {"error": "Incorrect password"}

    def test_admin_endpoints_require_a_token(self, client):
        for path in (
            "/api/admin/orders",
            "/api/admin/stats",
            "/api/admin/revenue",
            "/api/admin/visits",
            "/api/admin/email",
            "/api/admin/settings",
        ):
            assert client.get(path).status_code == 401, path
        assert client.get("/api/admin/orders", headers={"Authorization": "Bearer garbage"}).status_code == 401

    def test_store_api_key_does_not_open_the_admin(self, h):
        assert h.client.get("/api/admin/orders", headers=h.store).status_code == 401

    def test_admin_token_does_not_open_the_store_api(self, h):
        assert h.client.get("/api/v1/orders", headers=h.admin).status_code == 401

    def test_tokens_signed_with_another_secret_are_rejected(self, client):
        forged = URLSafeTimedSerializer("not-the-secret", salt=AdminTokens.SALT).dumps({"role": "admin"})
        assert client.get("/api/admin/orders", headers={"Authorization": f"Bearer {forged}"}).status_code == 401

    def test_expired_tokens_are_rejected(self):
        token = AdminTokens.issue("s3cret")
        assert AdminTokens.verify("s3cret", token, max_age_seconds=60)
        assert not AdminTokens.verify("s3cret", token, max_age_seconds=-1)
        assert not AdminTokens.verify("s3cret", "", max_age_seconds=60)

    def test_login_is_throttled_after_ten_failures(self, client):
        for _ in range(10):
            assert client.post("/api/admin/login", json={"password": "bad"}).status_code == 401
        assert client.post("/api/admin/login", json={"password": "bad"}).status_code == 429
        assert (
            client.post("/api/admin/login", json={"password": "test-admin-pw"}).status_code == 429
        )  # even the right one


class TestStoreAuth:
    def test_api_key_via_bearer_or_x_api_key_header(self, h):
        key = h.store["Authorization"].removeprefix("Bearer ")
        assert h.client.get("/api/v1/orders", headers={"X-API-Key": key}).status_code == 200
        assert h.client.get("/api/v1/orders", headers={"Authorization": f"Bearer {key}"}).status_code == 200
        assert h.client.get("/api/v1/orders", headers={"X-API-Key": key + "x"}).status_code == 401
        assert h.client.get("/api/v1/orders").status_code == 401

    def test_rotating_the_key_invalidates_the_old_one(self, h):
        old = dict(h.store)
        new_key = h.client.post("/api/admin/settings/rotate-key", headers=h.admin).json()["apiKey"]
        assert new_key.startswith("sk_")
        assert h.client.get("/api/v1/orders", headers=old).status_code == 401
        assert h.client.get("/api/v1/orders", headers={"Authorization": f"Bearer {new_key}"}).status_code == 200


class TestSettings:
    def test_update_persists_and_validates(self, h):
        assert (
            h.client.put(
                "/api/admin/settings",
                headers=h.admin,
                json={"storeName": "Acme", "currency": "cad", "taxRatePercent": 13, "shippingFlat": 500},
            ).status_code
            == 200
        )
        s = h.client.get("/api/admin/settings", headers=h.admin).json()
        assert (s["storeName"], s["currency"], s["taxRatePercent"], s["shippingFlat"]) == ("Acme", "CAD", 13, 500)
        assert h.client.put("/api/admin/settings", headers=h.admin, json={"currency": "dollars"}).status_code == 400
        assert h.client.put("/api/admin/settings", headers=h.admin, json={"taxRatePercent": 150}).status_code == 400
        assert h.client.put("/api/admin/settings", headers=h.admin, json={"webhookUrl": "ftp://x"}).status_code == 400
        assert (
            h.client.get("/api/admin/settings", headers=h.admin).json()["storeName"] == "Acme"
        )  # failed updates changed nothing

    def test_partial_update_leaves_other_fields_alone(self, h):
        h.configure(storeName="Acme")
        h.configure(shippingFlat=250)
        s = h.client.get("/api/admin/settings", headers=h.admin).json()
        assert s["storeName"] == "Acme" and s["shippingFlat"] == 250 and len(s["paymentMethods"]) == 5

    def test_default_payment_methods_include_zelle_and_interac(self, h):
        methods = h.client.get("/api/admin/settings", headers=h.admin).json()["paymentMethods"]
        assert [m["id"] for m in methods] == ["cod", "bank", "zelle", "interac", "test"]

    def test_new_payment_methods_get_ids_and_labels(self, h):
        h.configure(
            paymentMethods=[
                {"id": "", "label": "", "type": "offline", "instructions": "x", "enabled": True},
                {"id": "My Id!", "label": "Mine", "type": "test", "instructions": "", "enabled": True},
            ]
        )
        methods = h.client.get("/api/admin/settings", headers=h.admin).json()["paymentMethods"]
        assert methods[0]["id"].startswith("pm_") and methods[0]["label"] == methods[0]["id"]
        assert methods[1]["id"] == "MyId"

    def test_unknown_payment_method_type_is_rejected(self, h):
        r = h.client.put(
            "/api/admin/settings", headers=h.admin, json={"paymentMethods": [{"id": "x", "type": "weird"}]}
        )
        assert r.status_code == 400 and "type" in r.json()["error"]

    def test_rotating_the_webhook_secret(self, h):
        before = h.client.get("/api/admin/settings", headers=h.admin).json()["webhookSecret"]
        after = h.client.post("/api/admin/settings/rotate-webhook-secret", headers=h.admin).json()["webhookSecret"]
        assert after != before and after.startswith("whsec_")

    def test_test_session_endpoint_creates_a_usable_checkout(self, h):
        session = h.client.post("/api/admin/test-session", headers=h.admin).json()
        assert session["total"] == 6200 and session["checkout_url"].endswith(session["id"])
        assert h.complete(session["id"], "test").status_code == 200


class TestPlatform:
    def test_health_check(self, client):
        assert client.get("/healthz").json() == {"ok": True}

    def test_pages_and_assets_are_served(self, client):
        assert client.get("/admin").status_code == 200 and client.get("/checkout").status_code == 200
        assert client.get("/admin").headers["x-frame-options"] == "DENY"
        assert client.get("/", follow_redirects=False).headers["location"] == "/admin"
        assert client.get("/static/../app/config.py").status_code == 404

    def test_cors_preflight_is_open_only_for_the_public_api(self, client):
        r = client.options("/api/public/sessions/x/complete")
        assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "*"
        assert "access-control-allow-origin" not in client.get("/api/admin/orders").headers

    def test_unexpected_errors_do_not_leak_details(self, client):
        assert client.get("/api/does-not-exist").status_code == 404
        assert (
            client.post(
                "/api/admin/login", content="not json", headers={"Content-Type": "application/json"}
            ).status_code
            == 400
        )


class TestBranding:
    def test_branding_is_saved_and_exposed_on_the_checkout_page(self, h):
        h.configure(
            logoUrl="https://shop.test/logo.png",
            storeUrl="https://shop.test",
            notice="Please read our policy before ordering.",
            navLinks=[
                {"label": "Home", "url": "https://shop.test/"},
                {"label": "Shop", "url": "https://shop.test/shop"},
            ],
        )
        settings = h.client.get("/api/admin/settings", headers=h.admin).json()
        assert settings["logoUrl"] == "https://shop.test/logo.png" and len(settings["navLinks"]) == 2
        session = h.create_session()
        branding = h.client.get(f"/api/public/sessions/{session['id']}").json()["branding"]
        assert branding == {
            "logo_url": "https://shop.test/logo.png",
            "store_url": "https://shop.test",
            "notice": "Please read our policy before ordering.",
            "nav_links": [
                {"label": "Home", "url": "https://shop.test/"},
                {"label": "Shop", "url": "https://shop.test/shop"},
            ],
        }

    def test_branding_defaults_to_empty(self, h):
        branding = h.client.get(f"/api/public/sessions/{h.create_session()['id']}").json()["branding"]
        assert branding == {"logo_url": "", "store_url": "", "notice": "", "nav_links": []}

    def test_branding_urls_must_be_http_and_links_need_both_fields(self, h):
        put = lambda body: h.client.put("/api/admin/settings", headers=h.admin, json=body)  # noqa: E731
        assert put({"logoUrl": "javascript:alert(1)"}).status_code == 400
        assert put({"storeUrl": "ftp://x"}).status_code == 400
        assert put({"navLinks": [{"label": "", "url": "https://a.test"}]}).status_code == 400
        assert put({"navLinks": [{"label": "Home", "url": ""}]}).status_code == 400
        assert put({"navLinks": [{"label": f"L{i}", "url": "https://a.test"} for i in range(9)]}).status_code == 400
        assert put({"navLinks": [{"label": "Home", "url": "https://a.test"}]}).status_code == 200

    def test_clearing_branding_works(self, h):
        h.configure(navLinks=[{"label": "Home", "url": "https://a.test"}], logoUrl="https://a.test/l.png")
        h.configure(navLinks=[], logoUrl="")
        settings = h.client.get("/api/admin/settings", headers=h.admin).json()
        assert settings["navLinks"] == [] and settings["logoUrl"] == ""
