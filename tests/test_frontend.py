"""The HTML pages must only reference files that the app actually serves."""

import re

import pytest

PAGES = ["/admin", "/checkout", "/static/demo/thank-you.html"]


@pytest.mark.parametrize("page", PAGES)
def test_every_referenced_asset_is_served(client, page):
    html = client.get(page).text
    assets = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
    for asset in assets:
        assert client.get(asset).status_code == 200, f"{page} references missing {asset}"
    if page != "/static/demo/thank-you.html":
        assert assets, f"{page} should load its CSS/JS from /static"


def test_admin_modules_are_served_as_javascript(client):
    response = client.get("/static/admin/js/main.js")
    assert response.status_code == 200 and "javascript" in response.headers["content-type"]
    # every relative import inside the admin modules resolves to a real file
    for module in ["main", "api", "views/orders", "views/settings", "views/email"]:
        source = client.get(f"/static/admin/js/{module}.js").text
        base = module.rsplit("/", 1)[0] + "/" if "/" in module else ""
        for target in re.findall(r"from '(\./[^']+|\.\./[^']+)'", source):
            path = (
                (base + target).replace("views/../", "").replace("./", "", 1)
                if target.startswith("../")
                else base + target[2:]
            )
            assert client.get(f"/static/admin/js/{path}").status_code == 200, f"{module} imports missing {target}"


def test_absolute_static_imports_resolve(client):
    """Modules import each other (and the shared icons / card providers) via absolute /static paths."""
    modules = [
        "/static/admin/js/util.js",
        "/static/admin/js/components.js",
        "/static/checkout/checkout.js",
        "/static/checkout/card/index.js",
    ]
    for path in modules:
        source = client.get(path).text
        targets = re.findall(r"from '(/static/[^']+)'", source) + re.findall(r"import\('(/static/[^']+)'\)", source)
        for target in targets:
            assert client.get(target).status_code == 200, f"{path} imports missing {target}"
