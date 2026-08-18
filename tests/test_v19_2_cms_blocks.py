from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_admin_media_metadata_and_drag_drop():
    admin=(ROOT/'_local_admin/index.html').read_text(encoding='utf-8')
    for text in ('Kép címe','Alt szöveg','Kép leírása','Videó címe','Videó leírása','húzással rendezhető'):
        assert text in admin
    assert "addEventListener('dragstart'" in admin
    assert "addEventListener('drop'" in admin

def test_public_renderer_uses_media_metadata():
    js=(ROOT/'assets/js/app.js').read_text(encoding='utf-8')
    assert "img.title=block.title" in js
    assert "cms-media-title" in js
    assert "cms-media-description" in js

def test_homepage_focus_and_host_protection_untouched():
    home=(ROOT/'preview.html').read_text(encoding='utf-8')
    maintenance=(ROOT/'index.html').read_text(encoding='utf-8')
    assert 'Ingyenes biorezonanciás állapotfelmérés' in home
    assert '<a href="recepcios-ai.html">Recepciós AI</a>' in home
    assert 'Weboldalunk' in maintenance and 'megújul' in maintenance


def test_empty_video_blocks_are_not_rendered():
    js=(ROOT/'assets/js/app.js').read_text(encoding='utf-8')
    assert "const source = String(block.src || '').trim();" in js
    assert "if (!source) return null;" in js
    assert "filter(Boolean)" in js
