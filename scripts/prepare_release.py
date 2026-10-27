#!/usr/bin/env python3
"""Build a manifest from the actual IPK; reject incomplete or mismatched releases."""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tarfile

REPO = 'K3bOra/UltraAudio'
PACKAGE_NAME = 'enigma2-plugin-extensions-ultraaudio'
BASE = Path(__file__).resolve().parents[1]


def members(payload):
    if payload[:8] != b'!<arch>\n':
        raise ValueError('Not an IPK archive')
    offset = 8
    result = {}
    while offset < len(payload):
        header = payload[offset:offset + 60]
        if len(header) != 60 or header[-2:] != b'`\n':
            raise ValueError('Invalid IPK member')
        size = int(header[48:58].strip())
        if size < 0:
            raise ValueError('Invalid member size')
        name = header[:16].decode('ascii').strip().rstrip('/')
        if name in result:
            raise ValueError('Duplicate IPK member')
        offset += 60
        result[name] = payload[offset:offset + size]
        if len(result[name]) != size:
            raise ValueError('Truncated IPK')
        offset += size + size % 2
    if set(result) != {'debian-binary', 'control.tar.gz', 'data.tar.gz'} or result['debian-binary'] != b'2.0\n':
        raise ValueError('Unexpected archive layout')
    return result


def inspect_package(path):
    payload = path.read_bytes()
    if not 0 < len(payload) <= 32 * 1024 * 1024:
        raise ValueError('Package size outside limits')
    parts = members(payload)
    with tarfile.open(fileobj=io.BytesIO(parts['control.tar.gz']), mode='r:gz') as archive:
        control = archive.extractfile('./control').read().decode('utf-8')
    def field(name):
        return re.search(r'^' + name + r':\s*(\S+)', control, re.M).group(1)
    if field('Package') != PACKAGE_NAME or field('Architecture') != 'all':
        raise ValueError('Wrong plugin or architecture')
    installed_version = field('Version')
    if not re.fullmatch(r'\d+\.\d+\.\d+', installed_version):
        raise ValueError('Expected a stable Final V1 version')
    version = installed_version
    if path.name != 'Ultra_Audio_Final_V' + version.split('.')[0] + '.ipk':
        raise ValueError('Filename does not match package version')
    # Assets intentionally removed in test3 must not make a complete plugin
    # fail a historical file-count threshold. Check the runtime contract.
    prefix = 'usr/lib/enigma2/python/Plugins/Extensions/UltraAudio/'
    required = ('__init__.py', 'assets/checks/audio.aac', 'assets/checks/audio.mp3', 'assets/folders/generic.png', 'assets/folders/quran.png', 'assets/folders/radio.png', 'assets/fonts/Amiri.ttf', 'assets/fonts/Cocon.otf', 'assets/fonts/Osama.otf', 'assets/fonts/Shahid.ttf', 'assets/fonts/XBZar.ttf', 'assets/fonts/YakoutBold.ttf', 'assets/logos/event.png', 'assets/logos/live.png', 'assets/logos/match.png', 'audiohw.py', 'compat.py', 'components.map', 'components.py', 'ctl.py', 'deps.sh', 'diskbackup.py', 'dvbaudio.py', 'engine.py', 'finish_install.sh', 'frontpanel.py', 'gstplay.py', 'guide.py', 'hotkey.py', 'i18n.py', 'iconchoices.py', 'importer.py', 'keymap.xml', 'locale_packs/ar.json', 'logos.py', 'menu.py', 'motion.py', 'pcmplay.py', 'pidguard.py', 'plugin.png', 'plugin.py', 'presets.py', 'quranradio.py', 'receiverguide.py', 'repairui.py', 'screen.py', 'store.py', 'syncguard.py', 'themes.py', 'tvchannel.py', 'uifont.py', 'updater.py', 'updateui.py', 'vdelay.py', 'web/icon-192.png', 'web/icon-512.png', 'web/index.html', 'webui.py')
    required += ('sayedsaeed.py', 'shaarawi.py', 'assets/menu/panel_480x812.png', 'assets/menu/row_420x66.png', 'assets/menu/row_420x66_selected.png', 'assets/menu/set_brand_260x50.png', 'assets/menu/set_sign_250x58.png', 'assets/themes/neon/select.png', 'assets/themes/neon/panel_list.png')
    present = set()
    with tarfile.open(fileobj=io.BytesIO(parts['data.tar.gz']), mode='r:gz') as archive:
        for item in archive:
            if item.name.startswith('/') or '..' in Path(item.name).parts or item.issym() or item.islnk():
                raise ValueError('Unsafe package path')
            if item.isfile():
                normalized = item.name[2:] if item.name.startswith('./') else item.name
                if normalized in present:
                    raise ValueError('Duplicate package path')
                present.add(normalized)
                if item.name.endswith(('.pyc', '.pyo')):
                    raise ValueError('Compiled interpreter-specific files in package')
                if item.name.endswith('.py'):
                    source = archive.extractfile(item).read().decode('utf-8')
                    tree = ast.parse(source, feature_version=(3, 5))
                    if normalized == prefix + '__init__.py':
                        versions = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'PACKAGE_VERSION' for target in node.targets)]
                        if versions != [version]:
                            raise ValueError('Runtime version differs from package version')
    missing = sorted(prefix + name for name in required if prefix + name not in present)
    if missing:
        raise ValueError('Plugin files are incomplete: ' + ', '.join(missing))
    return {'version': version, 'url': 'https://github.com/' + REPO + '/releases/download/v' + version + '/' + path.name,
            'sha256': hashlib.sha256(payload).hexdigest(), 'size': len(payload)}


def prepare():
    if os.environ.get('GITHUB_REPOSITORY', REPO).lower() != REPO.lower():
        raise ValueError('Release workflow is configured only for ' + REPO)
    packages = list((BASE / 'packages').glob('*.ipk'))
    if len(packages) != 1:
        raise ValueError('Keep exactly one current IPK in packages/')
    package = packages[0]
    meta = inspect_package(package)
    notes = json.loads((BASE / 'release-notes.json').read_text(encoding='utf-8'))
    for key in ('notes', 'notes_ar'):
        if not isinstance(notes.get(key), list) or not notes[key] or not all(isinstance(x, str) and x.strip() for x in notes[key]):
            raise ValueError('Missing release notes: ' + key)
        meta[key] = notes[key]
    destination = BASE / 'dist'
    destination.mkdir(exist_ok=True)
    for old in destination.glob('*.ipk'):
        old.unlink()
    shutil.copyfile(str(package), str(destination / package.name))
    (destination / 'update.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    shutil.copyfile(str(BASE / 'install.sh'), str(destination / 'install.sh'))
    installer_hash = hashlib.sha256((destination / 'install.sh').read_bytes()).hexdigest()
    (destination / 'SHA256SUMS').write_text(meta['sha256'] + '  ' + package.name + '\n' + installer_hash + '  install.sh\n', encoding='utf-8')
    (destination / 'release-info.json').write_text(json.dumps({'tag': 'v' + meta['version'], 'version': meta['version'], 'title': 'Ultra Audio Final V' + meta['version'].split('.')[0]}) + '\n')
    (destination / 'notes.md').write_text('Ultra Audio Final V' + meta['version'].split('.')[0] + ' — Python 3 only\n\n' + '\n'.join('- ' + x for x in meta['notes']) + '\n\n' + '\n'.join('- ' + x for x in meta['notes_ar']) + '\n', encoding='utf-8')
    print('Prepared v' + meta['version'] + ': ' + meta['sha256'])


def verify(directory):
    packages = list(directory.glob('*.ipk'))
    if len(packages) != 1:
        raise ValueError('Published release must contain one IPK')
    expected = json.loads((BASE / 'dist/update.json').read_text(encoding='utf-8'))
    actual = json.loads((directory / 'update.json').read_text(encoding='utf-8'))
    if (directory / 'install.sh').read_bytes() != (BASE / 'install.sh').read_bytes():
        raise ValueError('Downloaded installer differs from prepared installer')
    if actual != expected:
        raise ValueError('Downloaded manifest differs from prepared manifest')
    info = inspect_package(packages[0])
    if any(actual.get(key) != value for key, value in info.items()):
        raise ValueError('Downloaded IPK differs from published manifest')
    print('Downloaded release assets verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-published', type=Path)
    args = parser.parse_args()
    verify(args.verify_published) if args.verify_published else prepare()
