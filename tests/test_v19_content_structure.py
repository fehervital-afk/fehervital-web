import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    'recepcios_ai': 'recepcios-ai.html',
    'egeszsegpont': 'egeszsegpont.html',
    'termekek': 'termekek.html',
    'biorezonancia': 'biorezonancia.html',
    'harmonyscan': 'harmonyscan.html',
    'oxigenkoncentrator': 'oxigenkoncentrator.html',
    'lagy_lezer': 'lagy-lezer.html',
    'vorosfenyu_hajapolo_sisak': 'vorosfenyu-hajapolo-sisak.html',
    'adatkezeles': 'adatkezeles.html',
    'idopontfoglalas': 'idopontfoglalas.html',
}

def test_v19_pages_exist_and_are_cms_enabled():
    data = json.loads((ROOT / 'assets/content/pages.json').read_text(encoding='utf-8'))
    for slug, filename in PAGES.items():
        assert slug in data['pages'], slug
        html = (ROOT / filename).read_text(encoding='utf-8')
        assert f'data-cms-page="{slug}"' in html, filename


def test_editor_supports_text_image_and_video_on_every_page():
    admin = (ROOT / '_local_admin/index.html').read_text(encoding='utf-8')
    for block_type in ('text', 'image', 'video'):
        assert f'data-add="{block_type}"' in admin
    assert 'uploadToBlock' in admin
    assert 'video/mp4,video/webm,video/ogg' in admin


def test_business_structure_and_homepage_focus_are_preserved():
    home = (ROOT / 'preview.html').read_text(encoding='utf-8')
    products = (ROOT / 'termekek.html').read_text(encoding='utf-8')
    assert '<h1 data-cms-field="hero_title">Ingyenes biorezonanciás állapotfelmérés</h1>' in home
    assert 'Tájékoztató jellegű, wellness célú állapotfelmérés több mint 170 biofizikai paraméter alapján' in home
    assert '<a href="recepcios-ai.html">Recepciós AI</a>' in home
    assert 'Recepciós AI bemutatása' not in home
    assert 'Digitális megoldások és kipróbálható wellness technológiák' not in home
    assert 'recepciosai.hu' in (ROOT / 'recepcios-ai.html').read_text(encoding='utf-8')
    for label in ('Biorezonanciás állapotfelmérő', 'HarmonyScanFlow frekvenciaterápia', 'Oxigénkoncentrátor', 'Lágy Lézer terápia', 'Vörösfényű hajápoló sisak'):
        assert label in products
