#!/usr/bin/env python3
"""Prepare a paired release with independent, strictly separated IPK/DEB channels."""
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
    dream = path.suffix == '.deb'
    if not re.fullmatch(r'\d+\.\d+\.\d+-dreamos' if dream else r'\d+\.\d+\.\d+', installed_version):
        raise ValueError('Expected a stable Final V1 version')
    version = installed_version
    expected_name = 'Ultra_Audio_Final_DreamOS.deb' if dream else 'Ultra_Audio_Final_V1.ipk'
    if path.name != expected_name:
        raise ValueError('Filename does not match package version')
    # Assets intentionally removed in test3 must not make a complete plugin
    # fail a historical file-count threshold. Check the runtime contract.
    prefix = 'usr/lib/enigma2/python/Plugins/Extensions/UltraAudio/'
    required = ('__init__.py', 'assets/checks/audio.aac', 'assets/checks/audio.mp3', 'assets/folders/generic.png', 'assets/folders/quran.png', 'assets/folders/radio.png', 'assets/fonts/Amiri.ttf', 'assets/fonts/Cocon.otf', 'assets/fonts/Osama.otf', 'assets/fonts/Shahid.ttf', 'assets/fonts/XBZar.ttf', 'assets/fonts/YakoutBold.ttf', 'assets/logos/event.png', 'assets/logos/live.png', 'assets/logos/match.png', 'audiohw.py', 'compat.py', 'components.map', 'components.py', 'ctl.py', 'deps.sh', 'diskbackup.py', 'dvbaudio.py', 'engine.py', 'finish_install.sh', 'frontpanel.py', 'gstplay.py', 'guide.py', 'hotkey.py', 'i18n.py', 'iconchoices.py', 'importer.py', 'keymap.xml', 'locale_packs/ar.json', 'logos.py', 'menu.py', 'motion.py', 'pcmplay.py', 'pidguard.py', 'plugin.png', 'plugin.py', 'presets.py', 'quranradio.py', 'receiverguide.py', 'repairui.py', 'screen.py', 'store.py', 'syncguard.py', 'themes.py', 'tvchannel.py', 'uifont.py', 'updater.py', 'updateui.py', 'vdelay.py', 'web/icon-192.png', 'web/icon-512.png', 'web/index.html', 'webui.py')
    required += ('sayedsaeed.py', 'shaarawi.py', 'assets/menu/panel_480x812.png', 'assets/menu/row_420x66.png', 'assets/menu/row_420x66_selected.png', 'assets/menu/set_brand_260x50.png', 'assets/menu/set_sign_250x58.png', 'assets/themes/neon/select.png', 'assets/themes/neon/panel_list.png')
    if dream:
        required += ('receivertime.py', 'assets/certs/cacert.pem')
    required += ('receivervolume.py',)
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
                if item.name.endswith(('.pyc', '.pyo', '.bak', '.tmp')) or '__pycache__' in Path(item.name).parts:
                    raise ValueError('Compiled interpreter-specific files in package')
                if item.name.endswith('.py'):
                    source = archive.extractfile(item).read().decode('utf-8')
                    tree = ast.parse(source, feature_version=(3, 5))
                    if normalized == prefix + 'updater.py':
                        expected_updater = (BASE / 'scripts/updater_template.py').read_text(encoding='utf-8').replace("'__CHANNEL__'", repr('dreamos' if dream else 'ipk'))
                        if source != expected_updater:
                            raise ValueError('Packaged updater differs from the tested channel template')
                    if normalized == prefix + '__init__.py':
                        versions = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'PACKAGE_VERSION' for target in node.targets)]
                        if versions != [version]:
                            raise ValueError('Runtime version differs from package version')
                        if dream:
                            schemes = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'VERSION_SCHEME' for target in node.targets)]
                            if schemes != ['parallel-v1']:
                                raise ValueError('DreamOS parallel numbering marker is missing')
    missing = sorted(prefix + name for name in required if prefix + name not in present)
    if missing:
        raise ValueError('Plugin files are incomplete: ' + ', '.join(missing))
    return {'version': version, 'channel': 'dreamos' if dream else 'ipk', 'format': 'deb' if dream else 'ipk',
            'sha256': hashlib.sha256(payload).hexdigest(), 'size': len(payload)}


def prepare():
    if os.environ.get('GITHUB_REPOSITORY', REPO).lower() != REPO.lower():
        raise ValueError('Release workflow is configured only for ' + REPO)
    from render_installer import render
    if (BASE / 'install.sh').read_text(encoding='utf-8') != render():
        raise ValueError('Installer is stale: run scripts/render_installer.py')
    packages = sorted(p for p in (BASE / 'packages').iterdir() if p.suffix in ('.ipk', '.deb'))
    if sorted(p.name for p in packages) != ['Ultra_Audio_Final_DreamOS.deb', 'Ultra_Audio_Final_V1.ipk']:
        raise ValueError('Keep exactly the current IPK and DreamOS DEB in packages/')
    details = {p.suffix[1:]: (p, inspect_package(p)) for p in packages}
    # Both package versions advance together; their update channels stay separate.
    ipk_version = details['ipk'][1]['version']
    dream_version = details['deb'][1]['version'].replace('-dreamos', '')
    if dream_version != ipk_version:
        raise ValueError('IPK and DreamOS must use the same parallel release number')
    tag = 'v' + ipk_version
    destination = BASE / 'dist'
    destination.mkdir(exist_ok=True)
    expected = {'Ultra_Audio_Final_V1.ipk', 'Ultra_Audio_Final_DreamOS.deb', 'update-ipk.json', 'update-dreamos.json', 'update.json', 'install.sh', 'SHA256SUMS', 'release-info.json', 'notes.md'}
    for old in destination.iterdir():
        if old.is_file() and old.name in expected:
            old.unlink()
    notes = json.loads((BASE / 'release-notes.json').read_text(encoding='utf-8'))
    all_notes = []
    for kind in ('ipk', 'deb'):
        package, meta = details[kind]
        meta['url'] = 'https://github.com/' + REPO + '/releases/download/' + tag + '/' + package.name
        for key in ('notes', 'notes_ar'):
            value = notes[meta['channel']].get(key)
            if not isinstance(value, list) or not value or not all(isinstance(x, str) and x.strip() for x in value):
                raise ValueError('Missing release notes: ' + key)
            meta[key] = value
        shutil.copyfile(str(package), str(destination / package.name))
        manifest = 'update-dreamos.json' if kind == 'deb' else 'update-ipk.json'
        content = json.dumps(meta, ensure_ascii=False, indent=2) + '\n'
        (destination / manifest).write_text(content, encoding='utf-8')
        if kind == 'ipk':
            # Old Python3 installations still read update.json. Never point
            # this legacy endpoint at a DreamOS package.
            (destination / 'update.json').write_text(content, encoding='utf-8')
        all_notes += [meta['channel'] + ' ' + meta['version'], ''] + ['- ' + x for x in meta['notes'] + meta['notes_ar']] + ['']
    shutil.copyfile(str(BASE / 'install.sh'), str(destination / 'install.sh'))
    assets = sorted(destination / name for name in expected if name not in ('SHA256SUMS', 'release-info.json', 'notes.md'))
    sums = ''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in assets)
    (destination / 'SHA256SUMS').write_text(sums, encoding='utf-8')
    info = {'tag': tag, 'version': ipk_version, 'dreamos_version': details['deb'][1]['version'], 'title': 'Ultra Audio Final V1 - Enigma2 & DreamOS'}
    (destination / 'release-info.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    (destination / 'notes.md').write_text('Ultra Audio Final V1\n\n' + '\n'.join(all_notes), encoding='utf-8')
    print('Prepared paired release ' + tag)


def verify(directory):
    for name in ('Ultra_Audio_Final_V1.ipk', 'Ultra_Audio_Final_DreamOS.deb', 'update-ipk.json', 'update-dreamos.json', 'update.json', 'install.sh', 'SHA256SUMS'):
        if (directory / name).read_bytes() != (BASE / 'dist' / name).read_bytes():
            raise ValueError('Downloaded release asset differs: ' + name)
    for kind, package, manifest in [('ipk', 'Ultra_Audio_Final_V1.ipk', 'update-ipk.json'), ('deb', 'Ultra_Audio_Final_DreamOS.deb', 'update-dreamos.json')]:
        actual = json.loads((directory / manifest).read_text(encoding='utf-8'))
        info = inspect_package(directory / package)
        if any(actual.get(key) != value for key, value in info.items()):
            raise ValueError('Package differs from platform manifest: ' + kind)
    print('Both downloaded platform packages and manifests verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-published', type=Path)
    args = parser.parse_args()
    verify(args.verify_published) if args.verify_published else prepare()
