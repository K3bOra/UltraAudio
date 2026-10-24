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
    if not re.fullmatch(r'\d+\.\d+\.\d+-finalv1', installed_version):
        raise ValueError('Expected a stable Final V1 version')
    version = installed_version.split('-')[0]
    if path.name != 'UltraAudio_Final_V1_Python3_v' + version + '.ipk':
        raise ValueError('Filename does not match package version')
    count = 0
    with tarfile.open(fileobj=io.BytesIO(parts['data.tar.gz']), mode='r:gz') as archive:
        for item in archive:
            if item.name.startswith('/') or '..' in Path(item.name).parts or item.issym() or item.islnk():
                raise ValueError('Unsafe package path')
            if item.isfile():
                count += 1
                if item.name.endswith(('.pyc', '.pyo')):
                    raise ValueError('Compiled interpreter-specific files in package')
                if item.name.endswith('.py'):
                    ast.parse(archive.extractfile(item).read().decode('utf-8'), feature_version=(3, 5))
    if count < 900:
        raise ValueError('Plugin files are incomplete')
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
        if not isinstance(notes.get(key), list) or not all(isinstance(x, str) for x in notes[key]):
            raise ValueError('Missing release notes: ' + key)
        meta[key] = notes[key]
    destination = BASE / 'dist'
    destination.mkdir(exist_ok=True)
    for old in destination.glob('*.ipk'):
        old.unlink()
    shutil.copyfile(str(package), str(destination / package.name))
    (destination / 'update.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (destination / 'SHA256SUMS').write_text(meta['sha256'] + '  ' + package.name + '\n', encoding='utf-8')
    (destination / 'release-info.json').write_text(json.dumps({'tag': 'v' + meta['version'], 'version': meta['version']}) + '\n')
    (destination / 'notes.md').write_text('UltraAudio ' + meta['version'] + ' — Python 3 only\n\n' + '\n'.join('- ' + x for x in meta['notes']) + '\n\n' + '\n'.join('- ' + x for x in meta['notes_ar']) + '\n', encoding='utf-8')
    print('Prepared v' + meta['version'] + ': ' + meta['sha256'])


def verify(directory):
    packages = list(directory.glob('*.ipk'))
    if len(packages) != 1:
        raise ValueError('Published release must contain one IPK')
    expected = json.loads((BASE / 'dist/update.json').read_text(encoding='utf-8'))
    actual = json.loads((directory / 'update.json').read_text(encoding='utf-8'))
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
