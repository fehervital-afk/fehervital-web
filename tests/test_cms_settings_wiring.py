import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_official_domain_and_email_are_centralized():
    data = json.loads(read("assets/content/pages.json"))
    assert data["site"]["domain"] == "fehervital.hu"
    assert data["site"]["contact"]["email"] == "info@fehervital.hu"
    keys = {f["key"] for f in data["pages"]["kapcsolat"]["fields"]}
    assert {"address", "phone", "email"}.isdisjoint(keys)


def test_contact_page_uses_site_contact_hooks():
    html = read("kapcsolat.html")
    assert 'data-cms-contact="address"' in html
    assert 'data-cms-contact="phone"' in html
    assert 'data-cms-contact="email"' in html
    assert "info@fehervital.hu" in html
    assert "fehervital@fehervital.com" not in html


def test_cms_pages_apply_site_settings_and_seo_from_same_data_source():
    js = read("assets/js/app.js")
    assert "fetch(cmsDataUrl()" in js
    assert "cmsApplySiteSettings(data);" in js
    assert "cmsApplySEO(page);" in js
    assert 'data-cms-site="domain"' in js


def test_admin_global_settings_are_wired_to_model():
    html = read("_local_admin/index.html")
    assert 'id="siteDomain"' in html
    assert "function ensureSiteModel()" in html
    assert "function renderGlobalSettings()" in html
    assert "function bindGlobalSettings()" in html
    assert "bind('#contactEmail','input'" in html
    assert "bind('#siteDomain','input'" in html
    assert "bind('#seoTitle','input'" in html
    assert "open('#designBtn','designView')" in html
    assert "open('#contactBtn','contactView')" in html
    assert "open('#seoBtn','seoView')" in html


def test_active_public_sources_no_longer_use_old_email():
    for rel in ["index.html", "kapcsolat.html", "assets/content/pages.json"]:
        text = read(rel)
        assert "fehervital@fehervital.com" not in text
    assert "info@fehervital.hu" in read("index.html")
