# -*- coding: utf-8 -*-
"""UltraAudio manual GitHub update: manifest -> hash verified package -> user-confirmed dpkg/opkg.

Supports both DEB (DreamOS / dpkg) and IPK (opkg) receivers on Python 2.7 and Python 3.x.
"""
from __future__ import print_function, division

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

try:
    from urllib.request import Request, HTTPRedirectHandler, build_opener
    from urllib.error import HTTPError
    from urllib.parse import urlsplit
    _string_types = (str,)
    _int_types = (int,)
except ImportError:
    from urllib2 import Request, HTTPRedirectHandler, build_opener, HTTPError
    from urlparse import urlsplit
    _string_types = (str, unicode)
    _int_types = (int, long)

# Updates always use private, verified SSL contexts. Playback TLS settings
# and its compatibility cache must never affect executable package downloads.
import ssl
from os.path import isfile
try:
    from urllib.request import HTTPSHandler
except ImportError:
    from urllib2 import HTTPSHandler

BUILD_CHANNEL = '__CHANNEL__'
_VERIFY_CHANNEL = None
PACKAGE_NAME = 'enigma2-plugin-extensions-ultraaudio'


def _command_available(name):
    return any(os.path.isfile(os.path.join(p, name)) and os.access(os.path.join(p, name), os.X_OK)
               for p in os.environ.get('PATH', '/usr/sbin:/usr/bin:/sbin:/bin').split(os.pathsep))


def _has_enigma2(path):
    try:
        with open(path, 'rb') as handle:
            data = handle.read().decode('utf-8', 'replace')
        return any(re.search(r'^Package:\s*enigma2\s*$', block, re.M)
                   and re.search(r'^Status:.* installed\s*$', block, re.M)
                   for block in data.split('\n\n'))
    except EnvironmentError:
        return False


def _has_package(path, name):
    try:
        with open(path, 'rb') as handle:
            data = handle.read().decode('utf-8', 'replace')
        return any(re.search(r'^Package:\s*' + re.escape(name) + r'\s*$', block, re.M)
                   and re.search(r'^Status:.* installed\s*$', block, re.M)
                   for block in data.split('\n\n'))
    except EnvironmentError:
        return False


def _is_e2pc_opkg():
    # Narrow fallback for the confirmed x86-64 OpenPLi-PC layout. Never use
    # the distro name, BUILD_CHANNEL or the presence of opkg alone as proof.
    if sys.platform != 'linux' or os.uname()[4].lower() not in ('x86_64', 'amd64'):
        return False
    expected = '/usr/local/e2/lib/enigma2/python/Plugins/Extensions/UltraAudio'
    alias = '/usr/lib/enigma2/python/Plugins/Extensions/UltraAudio'
    current = (os.path.realpath(alias) if BUILD_CHANNEL is None else
               os.path.realpath(os.path.dirname(os.path.abspath(__file__))))
    if (current != expected or os.path.realpath(alias) != expected
            or not os.path.isfile(os.path.join(expected, 'plugin.py'))):
        return False
    try:
        output = subprocess.check_output(['opkg', 'print-architecture'],
                                         stderr=subprocess.STDOUT).decode('utf-8', 'replace')
        arches = set()
        for line in output.splitlines():
            fields = line.split()
            if len(fields) == 3 and fields[0] == 'arch':
                try:
                    if int(fields[2]) > 0:
                        arches.add(fields[1])
                except ValueError:
                    pass
        # Online UltraAudio packages are Architecture: all.
        return 'all' in arches and 'x86_64' in arches
    except (EnvironmentError, subprocess.CalledProcessError):
        return False


def _detect_channel():
    deb = _command_available('dpkg') and isfile('/var/lib/dpkg/status')
    ipk = _command_available('opkg')
    if deb and ipk:
        ipk_paths = ('/var/lib/opkg/status', '/usr/lib/opkg/status',
                     '/usr/local/var/lib/opkg/status', '/usr/local/lib/opkg/status')
        deb_plugin = _has_package('/var/lib/dpkg/status', PACKAGE_NAME)
        ipk_plugin = any(_has_package(p, PACKAGE_NAME) for p in ipk_paths)
        if deb_plugin and ipk_plugin:
            raise RuntimeError('UltraAudio is registered in both DEB and IPK; resolve the duplicate registration')
        if deb_plugin != ipk_plugin:
            return 'dreamos' if deb_plugin else 'ipk'
        deb_e2 = _has_enigma2('/var/lib/dpkg/status')
        ipk_e2 = any(_has_enigma2(p) for p in ipk_paths)
        if deb_e2 != ipk_e2:
            return 'dreamos' if deb_e2 else 'ipk'
        if not deb_e2 and not ipk_e2 and _is_e2pc_opkg():
            return 'ipk'
        raise RuntimeError('Ambiguous package managers; cannot safely choose DEB or IPK')
    if deb:
        return 'dreamos'
    if ipk:
        return 'ipk'
    raise RuntimeError('No supported receiver package manager (dpkg/opkg) found')

def _channel():
    detected = _VERIFY_CHANNEL or _detect_channel()
    if BUILD_CHANNEL is not None and detected != BUILD_CHANNEL:
        raise ValueError('Installed plugin channel does not match this image; run the unified installer')
    return detected


def _certificate_error(exc):
    reason = getattr(exc, 'reason', exc)
    return (isinstance(reason, ssl.SSLError) and
            ('CERTIFICATE_VERIFY_FAILED' in str(reason).upper() or
             'CERTIFICATE VERIFY FAILED' in str(reason).upper()))


def _verified_context(cafile=None):
    if not hasattr(ssl, 'create_default_context'):
        raise RuntimeError('Verified HTTPS needs Python 2.7.9+ or Python 3.5+ and working SSL')
    context = ssl.create_default_context(cafile=cafile)
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    return context


def _open_verified(request):
    # Do not import compat.https_handlers: playback may opt out of validation.
    try:
        return build_opener(_GitHubRedirect(), HTTPSHandler(context=_verified_context())).open(request, timeout=20)
    except Exception as error:
        if not _certificate_error(error):
            raise
        bundle = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'certs', 'cacert.pem')
        if not isfile(bundle):
            # Standalone installer can reuse the CA bundle of an existing install.
            bundle = '/usr/lib/enigma2/python/Plugins/Extensions/UltraAudio/assets/certs/cacert.pem'
        if not isfile(bundle):
            raise RuntimeError('HTTPS certificate verification failed; correct the receiver clock/CA certificates and retry')
        return build_opener(_GitHubRedirect(), HTTPSHandler(context=_verified_context(bundle))).open(request, timeout=20)


_monotonic = getattr(time, 'monotonic', time.time)
try:
    _DEVNULL = subprocess.DEVNULL
except AttributeError:
    _DEVNULL = open(os.devnull, 'r+b')

_REPO = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9_.-]{1,100}$')
_SHA = re.compile(r'^[0-9a-fA-F]{64}$')
_MAX_MANIFEST = 64 * 1024
_MAX_PACKAGE = 32 * 1024 * 1024
DEFAULT_REPO = 'K3bOra/UltraAudio'
_INSTALL_LOCK = threading.Lock()
_ONLINE_LOG = '/tmp/ultraaudio-online-update.log'


def _fullmatch(pat, val, flags=0):
    if hasattr(re, 'fullmatch'):
        if hasattr(pat, 'fullmatch'):
            return pat.fullmatch(val)
        return re.fullmatch(pat, val, flags)
    if hasattr(pat, 'match'):
        m = pat.match(val)
        return m if (m is not None and m.end() == len(val)) else None
    return re.match(r'(?:' + pat + r')\Z', val, flags)


def _github_https(url):
    parts = urlsplit(url)
    host = parts.hostname or ''
    if (parts.scheme != 'https' or parts.username or parts.password or parts.port
            or not (host == 'github.com' or host.endswith('.githubusercontent.com'))):
        raise ValueError('Download must use GitHub HTTPS')


class _GitHubRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _github_https(newurl)
        return HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)


def normalize_repo(value):
    value = (value or '').strip()
    if value.startswith('https://github.com/'):
        value = value[len('https://github.com/'):].rstrip('/')
    if value.endswith('.git'):
        value = value[:-4]
    if not _fullmatch(_REPO, value) or '..' in value or value.startswith('.'):
        raise ValueError('GitHub repository must be owner/repo')
    return str(value)


def _read_https(url, limit, progress=None):
    _github_https(url)
    request = Request(url, headers={'User-Agent': 'UltraAudio-Updater', 'Cache-Control': 'no-cache'})
    response = _open_verified(request)
    try:
        _github_https(response.geturl())
        if progress is None:
            data = response.read(limit + 1)
        else:
            data = bytearray()
            reader = getattr(response, 'read1', response.read)
            started, reported = _monotonic(), 0.0
            while True:
                if _monotonic() - started > 300:
                    raise RuntimeError('Package download exceeded five minutes')
                chunk = reader(min(16384, limit + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError('Download exceeds size limit')
                now = _monotonic()
                if now - reported >= 0.5:
                    progress(len(data))
                    reported = now
            progress(len(data))
            data = bytes(data)
    finally:
        response.close()
    if len(data) > limit:
        raise ValueError('Download exceeds size limit')
    return data


def _current_version():
    channel = _channel()
    commands = (['dpkg', '-s', PACKAGE_NAME],) if channel == 'dreamos' else (['opkg', 'status', PACKAGE_NAME],)
    for cmd in commands:
        try:
            data = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8', 'replace')
            x = re.search(r'^Version:\s*(\S+)', data, re.M)
            if x:
                return x.group(1)
        except Exception:
            pass
    try:
        from . import PACKAGE_VERSION
        return PACKAGE_VERSION
    except Exception:
        return "1.0.6"


def _version_tuple(v):
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:[-+.]|$)', v)
    return tuple(int(x) for x in match.groups()) if match else (0, 0, 0)


def _legacy_transition(installed, target):
    return (_fullmatch(r'1\.\d+\.\d+', target) is not None
            and _fullmatch(r'2\.0\.(?:[0-9]|1[0-3])-finalv1', installed) is not None)


def _version_revision(v):
    m = _fullmatch(r'(\d+\.\d+\.\d+)(?:-radio(\d+))?', v)
    if m:
        return (_version_tuple(m.group(1)), int(m.group(2) or 0))
    return (_version_tuple(v), 0)


def _is_update(installed, target):
    return _legacy_transition(installed, target) or _version_revision(target) > _version_revision(installed)


def _verify_meta(repo, meta):
    if not isinstance(meta, dict):
        raise ValueError('Invalid update.json')
    channel = _channel()
    expected_format = 'deb' if channel == 'dreamos' else 'ipk'
    if meta.get('channel') != channel or meta.get('format') != expected_format:
        raise ValueError('Update channel/package format does not match this receiver')
    version = meta.get('version')
    url = meta.get('url')
    sha = meta.get('sha256')
    if not isinstance(version, _string_types) or not _fullmatch((r'\d+\.\d+\.\d+-dreamos' if channel == 'dreamos' else r'\d+\.\d+\.\d+'), version):
        raise ValueError('Invalid release version')
    if not isinstance(url, _string_types) or not isinstance(sha, _string_types) or not _fullmatch(_SHA, sha):
        raise ValueError('Manifest lacks verified package URL and SHA256')
    pr = urlsplit(url)
    path = pr.path
    prefix = '/%s/releases/download/' % repo
    if pr.scheme != 'https' or pr.hostname != 'github.com' or pr.username or pr.password or pr.port or pr.query or pr.fragment or not path.startswith(prefix):
        raise ValueError('Release must be hosted in configured GitHub repository')
    fname = path.rsplit('/', 1)[-1]
    relative = path[len(prefix):].split('/')
    if len(relative) != 2 or not _fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', relative[0]) or '..' in relative[0]:
        raise ValueError('Invalid release tag')
    if not _fullmatch(r'Ultra_?Audio[-_A-Za-z0-9.]*\.' + expected_format, fname, re.I):
        raise ValueError('Unexpected update package name')
    if not isinstance(meta.get('size'), _int_types) or isinstance(meta.get('size'), bool) or not 0 < meta['size'] <= _MAX_PACKAGE:
        raise ValueError('Invalid package size')

    def notes(key):
        value = meta.get(key, '')
        if isinstance(value, list) and all(isinstance(line, _string_types) for line in value):
            value = '\n'.join(value)
        if not isinstance(value, _string_types):
            raise ValueError('Invalid release notes')
        return value.replace('\r\n', '\n').replace('\r', '\n')

    return {'channel': channel, 'format': expected_format, 'version': str(version), 'url': str(url), 'sha256': str(sha).lower(), 'size': meta.get('size'), 'repo': repo,
            'notes': notes('notes'), 'notes_ar': notes('notes_ar')}


def check(repo=DEFAULT_REPO):
    repo = normalize_repo(repo)
    filename = 'update-dreamos.json' if _channel() == 'dreamos' else 'update-ipk.json'
    manifest = 'https://github.com/%s/releases/latest/download/%s' % (repo, filename)
    try:
        data = _read_https(manifest, _MAX_MANIFEST)
    except HTTPError as error:
        if error.code != 404:
            raise
        data = _read_https('https://raw.githubusercontent.com/%s/main/%s' % (repo, filename), _MAX_MANIFEST)
    meta = _verify_meta(repo, json.loads(data.decode('utf-8')))
    if not _is_update(_current_version(), meta['version']):
        return None
    return meta


_XZ_MAGIC = b'\xfd7zXZ\x00'


def _unxz(body):
    """Python 2.7's tarfile cannot open .xz members; use lzma if present, else an image tool (xz/xzcat/busybox)."""
    try:
        import lzma
        return lzma.decompress(body)
    except ImportError:
        pass
    for cmd in (['xz', '-dc'], ['xzcat'], ['unxz', '-c'], ['busybox', 'xzcat']):
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out = proc.communicate(body)[0]
        except (EnvironmentError, ValueError):
            continue
        if proc.returncode == 0 and out:
            return out
    raise ValueError('xz-compressed package cannot be read on this image (no xz/lzma support)')


def _ipk_control(payload):
    if payload[:8] != b'!<arch>\n':
        raise ValueError('Downloaded file is not a valid DEB/IPK archive')
    offset, members = 8, {}
    while offset < len(payload):
        header = payload[offset:offset + 60]
        if len(header) != 60 or header[-2:] != b'`\n':
            raise ValueError('Malformed archive header')
        size = int(header[48:58].strip())
        name = header[:16].decode('ascii').strip().rstrip('/')
        if size < 0 or name in members:
            raise ValueError('Malformed or duplicate archive member')
        offset += 60
        body = payload[offset:offset + size]
        if len(body) != size:
            raise ValueError('Truncated archive')
        members[name] = body
        offset += size + size % 2
    if offset != len(payload) or members.get('debian-binary') != b'2.0\n':
        raise ValueError('Invalid package format marker')
    controls = [name for name in members if name in ('control.tar.gz', 'control.tar.xz', 'control.tar')]
    if len(controls) != 1 or not any(name in members for name in ('data.tar.gz', 'data.tar.xz', 'data.tar')):
        raise ValueError('Archive control/data member is missing or ambiguous')
    body = members[controls[0]]
    if body[:6] == _XZ_MAGIC and sys.version_info[0] < 3:
        body = _unxz(body)
    with tarfile.open(fileobj=io.BytesIO(body), mode='r:*') as archive:
        matches = [item for item in archive if item.name in ('control', './control')]
        if len(matches) != 1 or not matches[0].isfile() or matches[0].size > 16384:
            raise ValueError('Archive lacks valid control file')
        return archive.extractfile(matches[0]).read().decode('utf-8')


def _emit(progress, percent, stage):
    if progress is not None:
        progress(percent, stage)


def _log_tail(path):
    try:
        with open(path, 'rb') as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - 16384))
            return handle.read().decode('utf-8', 'replace')
    except EnvironmentError:  # IOError on Python 2
        return ''


def _run_logged(args, env, timeout, progress, finishing=False):
    percent = 90 if finishing else 80
    stage = 'Checking required components...' if finishing else 'Installing package...'
    with open(_ONLINE_LOG, 'ab', buffering=0) as output:
        process = subprocess.Popen(args, stdin=_DEVNULL, stdout=output,
                                   stderr=subprocess.STDOUT, env=env, close_fds=True)
        started, reported = _monotonic(), 0.0
        while process.poll() is None:
            now = _monotonic()
            if now - started > timeout:
                process.terminate()
                deadline = _monotonic() + 5.0
                while process.poll() is None and _monotonic() < deadline:
                    time.sleep(0.1)
                if process.poll() is None:
                    process.kill()
                    process.wait()
                raise RuntimeError('Installation timed out. Log: ' + _ONLINE_LOG)
            if now - reported >= 1:
                tail = _log_tail(_ONLINE_LOG)
                if finishing and 'Required components verified.' in tail:
                    percent, stage = 98, 'Finishing update...'
                elif not finishing and ('Configuring enigma2-plugin-extensions-ultraaudio' in tail or 'Setting up enigma2-plugin-extensions-ultraaudio' in tail):
                    percent, stage = 85, 'Configuring plugin...'
                elif not finishing and ('Upgrading enigma2-plugin-extensions-ultraaudio' in tail or 'Unpacking enigma2-plugin-extensions-ultraaudio' in tail):
                    stage = 'Replacing installed plugin...'
                _emit(progress, percent, stage)
                reported = now
            time.sleep(0.2)
        if process.returncode:
            raise RuntimeError('Installation failed. Log: %s\n%s' % (_ONLINE_LOG, _log_tail(_ONLINE_LOG)[-600:]))
        if not finishing:
            _emit(progress, 85, 'Plugin installed successfully.')


def install_verified(meta, progress=None):
    if not _INSTALL_LOCK.acquire(False):
        raise RuntimeError('Another UltraAudio update is already running')
    try:
        return _install_verified(meta, progress)
    finally:
        _INSTALL_LOCK.release()


def _install_verified(meta, progress):
    meta = _verify_meta(normalize_repo(meta['repo']), meta)
    _emit(progress, 1, 'Downloading update...')

    def downloaded(size):
        percent = max(1, min(100, int(100 * size / meta['size']))) if meta.get('size') else 1
        _emit(progress, percent, 'Downloading update...')
    payload = _read_https(meta['url'], _MAX_PACKAGE, downloaded)
    _emit(progress, 100, 'Download complete.')
    _emit(progress, 75, 'Verifying package...')
    if meta.get('size') and len(payload) != meta['size']:
        raise ValueError('Package size mismatch')
    if hashlib.sha256(payload).hexdigest() != meta['sha256']:
        raise ValueError('SHA256 verification failed')
    control = _ipk_control(payload)
    pkg = re.search(r'^Package:\s*(\S+)', control, re.M)
    version = re.search(r'^Version:\s*(\S+)', control, re.M)
    if not pkg or pkg.group(1) != 'enigma2-plugin-extensions-ultraaudio':
        raise ValueError('Wrong package in update')
    if not version or version.group(1) != meta['version']:
        raise ValueError('Version mismatch between package and manifest')
    architecture = re.search(r'^Architecture:\s*(\S+)', control, re.M)
    if not architecture or architecture.group(1) != 'all':
        raise ValueError('Wrong package architecture')
    installed = _current_version()
    if not _is_update(installed, meta['version']):
        raise ValueError('Update is not newer than the installed version')
    use_dpkg = _channel() == 'dreamos'
    suffix = '.deb' if use_dpkg else '.ipk'
    fd, path = tempfile.mkstemp(prefix='ultraaudio_verified_', suffix=suffix, dir='/tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(payload)
        if use_dpkg:
            args = ['dpkg', '--refuse-downgrade', '-i', path]
        else:
            args = ['opkg', 'install']
            if _legacy_transition(installed, meta['version']):
                args.append('--force-downgrade')
            args.append(path)
        env = dict(os.environ, ULTRAAUDIO_ONLINE_UPDATE='1', DEBIAN_FRONTEND='noninteractive')
        with open(_ONLINE_LOG, 'wb'):
            pass
        _emit(progress, 80, 'Installing package...')
        _run_logged(args, env, 600, progress)
        stat = os.stat(path)
        signature = '%d:%d:%d:%d' % (stat.st_dev, stat.st_ino, stat.st_size, int(stat.st_mtime))
        finish = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'finish_install.sh')
        _emit(progress, 90, 'Checking required components...')
        _run_logged(['/bin/sh', finish, path, signature], env, 1260, progress, finishing=True)
        _emit(progress, 100, 'Update complete. Restarting the interface...')
        return meta['version']
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--control':
        sys.exit(64)
    try:
        with open(sys.argv[2], 'rb') as handle:
            payload = handle.read(_MAX_PACKAGE + 1)
        if len(payload) > _MAX_PACKAGE:
            raise ValueError('Package exceeds size limit')
        sys.stdout.write(_ipk_control(payload))
    except Exception as error:
        print('UltraAudio package metadata: %s' % error, file=sys.stderr)
        sys.exit(1)
