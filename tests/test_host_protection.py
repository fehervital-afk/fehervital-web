import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTECTED_HOSTS = {"fehervital.hu", "www.fehervital.hu"}


def normalized_host(host_header):
    host = host_header.strip().lower()
    if host.startswith("["):
        return host[1 : host.find("]")]
    return host.split(":", 1)[0].rstrip(".")


def public_result(host_header, path):
    host = normalized_host(host_header)
    maintenance_path = path in {"/", "/index.html"}
    if host in PROTECTED_HOSTS:
        return "maintenance" if maintenance_path else "redirect-maintenance"
    return "full-site" if path != "/" else "redirect-full-site"


def test_required_host_matrix_and_ports():
    assert public_result("www.fehervital.hu", "/") == "maintenance"
    assert public_result("fehervital.hu:443", "/biorezonancia.html") == "redirect-maintenance"
    assert public_result("fehervital-web.onrender.com", "/") == "redirect-full-site"
    assert public_result("localhost:8000", "/") == "redirect-full-site"
    assert public_result("127.0.0.1:8000", "/") == "redirect-full-site"


def test_guard_uses_exact_normalized_hostname_matching():
    app = (ROOT / "assets/js/app.js").read_text(encoding="utf-8")
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    for source in (app, index):
        assert '"fehervital.hu", "www.fehervital.hu"' in source
        assert "window.location.hostname.toLowerCase().replace(/\\.$/, \"\")" in source
    assert "sessionStorage" not in app


def test_maintenance_is_noindex_nofollow_and_self_contained():
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<meta name="robots" content="[^"]*noindex[^"]*nofollow', index)
    assert "info@fehervital.hu" in index
    assert "assets/" not in index


def test_redirects_cannot_loop():
    assert public_result("fehervital.hu", "/preview.html") == "redirect-maintenance"
    assert public_result("fehervital.hu", "/") == "maintenance"
    assert public_result("localhost", "/") == "redirect-full-site"
    assert public_result("localhost", "/preview.html") == "full-site"
