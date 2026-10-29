import json
import os
from pathlib import Path
import sys
import tempfile

root = Path(os.environ['UA_PLUGIN_ROOT']).resolve()
sys.path.insert(0, str(root.parent))
sys.dont_write_bytecode = True
with tempfile.TemporaryDirectory() as directory:
    os.environ['ULTRAAUDIO_DATA'] = directory
    from UltraAudio import store, presets, turkishradio
    catalog = json.loads(Path(turkishradio.CATALOG).read_text())['stations']
    # Do not create an unrelated root if the main radio migration has not run.
    assert turkishradio.install()['skipped']
    presets.install_radio()
    before = store._load()
    prior = json.loads(json.dumps(before))
    result = presets.install_turkish_radio()
    assert result['added'] == len(catalog)
    library = store._load()
    folder = next(f for f in library['folders'] if f.get('preset') == 'radio_turkish')
    radio = next(f for f in library['folders'] if f.get('preset') == 'radio_root')
    assert folder['parent'] == radio['id']
    assert all(f in library['folders'] for f in prior['folders'])
    assert all(s in library['streams'] for s in prior['streams'])
    streams = [s for s in library['streams'] if s['folder'] == folder['id']]
    assert len(streams) == len(catalog)
    assert {(s['name'], s['url']) for s in streams} == {(s['name'], s['url']) for s in catalog}
    assert all(store.is_radio_stream(s, library) for s in streams)
    assert all(store.stream_icon(s, lib=library).endswith('/folders/radio.png') for s in streams)
    for scale, suffix in [(1, ''), (2, '@2x'), (3, '@4x')]:
        icon = store.folder_icon(folder, scale=scale, lib=library)
        assert icon.endswith('/folders/turkish' + suffix + '.png') and Path(icon).is_file()
    for language, name in [('ar', 'تركي'), ('en', 'Turkish'), ('tr', 'Türkçe')]:
        assert store.display_folder_name(folder, language) == name
    assert presets.install_turkish_radio()['skipped']
    # Respect a deleted station, edited station and renamed folder on later boots.
    removed = streams[0]['id']
    edited = streams[1]['id']
    library['streams'] = [s for s in library['streams'] if s['id'] != removed]
    next(s for s in library['streams'] if s['id'] == edited)['name'] = 'My station'
    next(f for f in library['folders'] if f['id'] == folder['id'])['name'] = 'My Turkish'
    store._save(library)
    assert presets.install_turkish_radio()['skipped']
    assert store._load() == library
    assert store.display_folder_name(next(f for f in library['folders'] if f['id'] == folder['id']), 'ar') == 'My Turkish'
    backup = store.make_backup()
    store.validate_backup(backup)
    store.restore_backup(backup)
    assert presets.install_turkish_radio()['skipped']
    assert not any(s['id'] == removed for s in store._load()['streams'])
print('PASS %d Turkish radios nested under Radio, exact catalog, separate folder/stream icons, no reseed or lost edits, backup round-trip' % len(catalog))
