"""Turkish source-only localization checks; no receiver or package build needed."""
import ast
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys
import tempfile

root = Path(os.environ['UA_PLUGIN_ROOT']).resolve()
sys.path.insert(0, str(root.parent))
sys.dont_write_bytecode = True
with tempfile.TemporaryDirectory() as directory:
    os.environ['ULTRAAUDIO_DATA'] = directory
    from UltraAudio import i18n, store
    ar = json.loads((root / 'locale_packs/ar.json').read_text())['translations']
    pack = json.loads((root / 'locale_packs/tr.json').read_text())
    tr = pack['translations']
    assert ar.keys() <= tr.keys()
    percent = re.compile(r'%(?:\([^)]+\))?[-+#0 ]*\d*(?:\.\d+)?[diouxXeEfFgGcrs%]')
    braces = re.compile(r'\{\d+(?:[^}]*)?\}')
    for source, translation in tr.items():
        assert translation.strip(), source
        assert Counter(percent.findall(source)) == Counter(percent.findall(translation)), source
        assert Counter(braces.findall(source)) == Counter(braces.findall(translation)), source
    assert i18n.available('tr')
    assert ('tr', 'Türkçe') in i18n.LANGUAGES
    for language, direction in [('tr', 'ltr'), ('ar', 'rtl'), ('en', 'ltr'), ('tr', 'ltr')]:
        store.set_settings({'language': language})
        assert i18n.lang() == language
        assert i18n.direction() == direction
    assert i18n.T('Settings') == 'Ayarlar'
    assert i18n.T('%d channels', 12) == '12 kanal'
    assert i18n.T('Could not play the audio: %s', 'test') == 'Ses oynatılamadı: test'
    assert i18n.T('Unknown future label') == 'Unknown future label'
    bundle = i18n.web_bundle()
    assert bundle['lang'] == 'tr' and bundle['dir'] == 'ltr'
    assert bundle['strings']['Save sync'] == 'Eşitlemeyi kaydet'
    assert [v[0] for v in bundle['languages']] == ['en', 'ar', 'tr']
    assert store.display_folder_name({'preset': 'radio_quran', 'name': 'Quran'}, 'tr') == 'Kur’an'
    assert store.display_folder_name({'preset': 'radio_ar', 'name': 'Arabic'}, 'tr') == 'Arapça'
    assert store.display_folder_name({'name': 'My folder'}, 'tr') == 'My folder'
    try:
        store._validated_settings({'language': 'invalid'})
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid language accepted')
for name in ['i18n.py', 'store.py', 'screen.py']:
    ast.parse((root / name).read_text())
print('PASS Turkish pack coverage, formatting placeholders, language persistence, LTR, web bundle and preset labels')
