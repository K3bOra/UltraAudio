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
import subprocess
from release_variants import VARIANTS

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
    if len(result) != 3 or result.get('debian-binary') != b'2.0\n' or len([x for x in result if x in ('control.tar.gz', 'control.tar.xz')]) != 1 or len([x for x in result if x in ('data.tar.gz', 'data.tar.xz')]) != 1:
        raise ValueError('Unexpected archive layout')
    return result


def validate_control(control):
    # Debian control is one RFC822 paragraph. Blank lines start a second entry.
    if re.search(r'\n[ \t]*\n', control.strip('\r\n')):
        raise ValueError('Package control must contain exactly one paragraph')
    for name in ('Package', 'Version', 'Architecture', 'X-UltraAudio-Family'):
        if len(re.findall(r'^' + name + r':', control, re.M)) != 1:
            raise ValueError('Missing or duplicate package control field: ' + name)


def inspect_package(path):
    payload = path.read_bytes()
    if not 0 < len(payload) <= 32 * 1024 * 1024:
        raise ValueError('Package size outside limits')
    parts = members(payload)
    with tarfile.open(fileobj=io.BytesIO(parts[next(x for x in parts if x.startswith('control.tar.'))]), mode='r:*') as archive:
        control = archive.extractfile('./control').read().decode('utf-8')
    validate_control(control)
    # Use the native package parser, not only our own regular expressions.
    native = subprocess.run(['dpkg-deb', '--field', str(path), 'Package', 'Version',
                             'Architecture', 'X-UltraAudio-Family'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if native.returncode:
        raise ValueError('Native package control validation failed: ' + native.stderr.decode('utf-8', 'replace'))
    def field(name):
        return re.search(r'^' + name + r':\s*(\S+)', control, re.M).group(1)
    if field('Package') != PACKAGE_NAME or field('Architecture') != 'all':
        raise ValueError('Wrong plugin or architecture')
    installed_version = field('Version')
    dream = path.suffix == '.deb'
    if not re.fullmatch(r'\d+\.\d+\.\d+-dreamos' if dream else r'\d+\.\d+\.\d+', installed_version):
        raise ValueError('Expected a stable Final V1 version')
    version = installed_version
    variant = next((v for v in VARIANTS if v[2] == path.name), None)
    if not variant or field('X-UltraAudio-Family') != variant[0]:
        raise ValueError('Filename or package family does not match release variant')
    # Assets intentionally removed in test3 must not make a complete plugin
    # fail a historical file-count threshold. Check the runtime contract.
    prefix = 'usr/lib/enigma2/python/Plugins/Extensions/UltraAudio/'
    required = ('__init__.py', 'assets/checks/audio.aac', 'assets/checks/audio.mp3', 'assets/folders/generic.png', 'assets/folders/quran.png', 'assets/folders/radio.png', 'assets/fonts/Amiri.ttf', 'assets/fonts/Cocon.otf', 'assets/fonts/Osama.otf', 'assets/fonts/Shahid.ttf', 'assets/fonts/XBZar.ttf', 'assets/fonts/YakoutBold.ttf', 'assets/logos/event.png', 'assets/logos/live.png', 'assets/logos/match.png', 'audiohw.py', 'compat.py', 'components.map', 'components.py', 'ctl.py', 'deps.sh', 'diskbackup.py', 'dvbaudio.py', 'engine.py', 'finish_install.sh', 'frontpanel.py', 'gstplay.py', 'guide.py', 'hotkey.py', 'i18n.py', 'iconchoices.py', 'importer.py', 'keymap.xml', 'locale_packs/ar.json', 'logos.py', 'menu.py', 'motion.py', 'pcmplay.py', 'pidguard.py', 'plugin.png', 'plugin.py', 'presets.py', 'quranradio.py', 'receiverguide.py', 'repairui.py', 'screen.py', 'store.py', 'syncguard.py', 'themes.py', 'tvchannel.py', 'uifont.py', 'updater.py', 'updateui.py', 'vdelay.py', 'web/icon-192.png', 'web/icon-512.png', 'web/index.html', 'webui.py')
    required += ('sayedsaeed.py', 'shaarawi.py', 'assets/menu/panel_480x812.png', 'assets/menu/row_420x66.png', 'assets/menu/row_420x66_selected.png', 'assets/menu/set_brand_260x50.png', 'assets/menu/set_sign_250x58.png', 'assets/themes/neon/select.png', 'assets/themes/neon/panel_list.png')
    if dream:
        required += ('receivertime.py', 'assets/certs/cacert.pem')
    required += ('receivervolume.py', 'receiverimage.py')
    present = set()
    with tarfile.open(fileobj=io.BytesIO(parts[next(x for x in parts if x.startswith('data.tar.'))]), mode='r:*') as archive:
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
                        expected_updater = (BASE / 'scripts/updater_template.py').read_text(encoding='utf-8').replace("'__CHANNEL__'", repr(variant[1])).replace("'__FAMILY__'", repr(variant[0]))
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
    return {'family': variant[0], 'version': version, 'channel': 'dreamos' if dream else 'ipk', 'format': 'deb' if dream else 'ipk',
            'sha256': hashlib.sha256(payload).hexdigest(), 'size': len(payload)}


def asset_names():
    return [v[2] for v in VARIANTS] + [v[3] for v in VARIANTS] + ['update.json', 'install.sh', 'SHA256SUMS']


def prepare():
    if os.environ.get('GITHUB_REPOSITORY', REPO).lower() != REPO.lower():
        raise ValueError('Release workflow is configured only for ' + REPO)
    from render_installer import render
    if (BASE / 'install.sh').read_text(encoding='utf-8') != render():
        raise ValueError('Installer is stale: run scripts/render_installer.py')
    packages = sorted(p.name for p in (BASE / 'packages').iterdir() if p.suffix in ('.ipk', '.deb'))
    if packages != sorted(v[2] for v in VARIANTS):
        raise ValueError('Expected exactly the four ordinary and Dreambox One/Two packages')
    details = [(v, inspect_package(BASE / 'packages' / v[2])) for v in VARIANTS]
    versions = set(meta['version'].replace('-dreamos', '') for v, meta in details)
    if len(versions) != 1:
        raise ValueError('All four variants must share the same release number')
    version = versions.pop()
    tag = 'v' + version
    destination = BASE / 'dist'
    destination.mkdir(exist_ok=True)
    notes = json.loads((BASE / 'release-notes.json').read_text(encoding='utf-8'))
    all_notes = []
    for variant, meta in details:
        family, channel, package, manifest = variant
        meta['url'] = 'https://github.com/' + REPO + '/releases/download/' + tag + '/' + package
        for key in ('notes', 'notes_ar'):
            value = notes[channel].get(key)
            if not isinstance(value, list) or not value or not all(isinstance(x, str) and x.strip() for x in value):
                raise ValueError('Missing release notes: ' + key)
            meta[key] = value
        shutil.copyfile(str(BASE / 'packages' / package), str(destination / package))
        content = json.dumps(meta, ensure_ascii=False, indent=2) + '\n'
        (destination / manifest).write_text(content, encoding='utf-8')
        if family == 'standard' and channel == 'ipk':
            (destination / 'update.json').write_text(content, encoding='utf-8')
        all_notes += [family + ' / ' + channel + ' / ' + meta['version'], '']
    shutil.copyfile(str(BASE / 'install.sh'), str(destination / 'install.sh'))
    assets = [destination / name for name in asset_names() if name != 'SHA256SUMS']
    (destination / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in sorted(assets)), encoding='utf-8')
    info = {'tag': tag, 'version': version, 'dreamos_version': version + '-dreamos', 'title': 'Ultra Audio ' + version + ' - Enigma2, DreamOS & Dreambox One/Two'}
    (destination / 'release-info.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    (destination / 'notes.md').write_text('Ultra Audio ' + version + '\n\n' + '\n'.join(all_notes) + '\n' + '\n'.join(notes['ipk']['notes_ar'] + notes['ipk']['notes']) + '\n', encoding='utf-8')
    print('Prepared four isolated release variants: ' + tag)


def verify(directory):
    for name in asset_names():
        if (directory / name).read_bytes() != (BASE / 'dist' / name).read_bytes():
            raise ValueError('Downloaded release asset differs: ' + name)
    for family, channel, package, manifest in VARIANTS:
        actual = json.loads((directory / manifest).read_text(encoding='utf-8'))
        info = inspect_package(directory / package)
        if any(actual.get(key) != value for key, value in info.items()):
            raise ValueError('Package differs from its isolated manifest: ' + package)
    print('All four downloaded packages and isolated manifests verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-published', type=Path)
    args = parser.parse_args()
    verify(args.verify_published) if args.verify_published else prepare()
