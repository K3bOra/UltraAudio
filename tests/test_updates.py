"""Offline integration tests: never invoke a real receiver package manager."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import ssl
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch, Mock, mock_open

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[1]
PLUGIN = 'data/usr/lib/enigma2/python/Plugins/Extensions/UltraAudio'


def load(channel):
    spec = importlib.util.spec_from_file_location('test_updater_' + channel,
        BASE / ('deb-source' if channel == 'dreamos' else 'ipk-source') / PLUGIN / 'updater.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._detect_channel = lambda: channel
    return module


def metadata(channel):
    return json.loads((BASE / 'dist' / ('update-dreamos.json' if channel == 'dreamos' else 'update-ipk.json')).read_text())


def payload(channel):
    name = 'Ultra_Audio_Final_DreamOS.deb' if channel == 'dreamos' else 'Ultra_Audio_Final_V1.ipk'
    return (BASE / 'packages' / name).read_bytes()


def installer():
    text = (BASE / 'install.sh').read_text()
    code = text.split("<<'ULTRAAUDIO_INSTALL_PY'\n", 1)[1].split('\nULTRAAUDIO_INSTALL_PY', 1)[0]
    namespace = {'__name__': 'offline_test', '__file__': str(BASE / 'install.sh')}
    exec(compile(code, 'install.sh:python', 'exec'), namespace)
    return namespace


class PlatformTests(unittest.TestCase):
    def test_platform_detection(self):
        m = load('ipk')
        detect = load('ipk')
        # Reload the original function (load intentionally stubs it elsewhere).
        ns = installer()
        fn = ns['_detect_channel']
        for commands, database, expected in [({'opkg'}, False, 'ipk'), ({'dpkg'}, True, 'dreamos')]:
            with patch.dict(ns, _command_available=lambda name: name in commands, isfile=lambda path: database):
                self.assertEqual(fn(), expected)
        with patch.dict(ns, _command_available=lambda name: True, isfile=lambda path: True, _has_enigma2=lambda path: False):
            with self.assertRaises(RuntimeError): fn()
        with patch.dict(ns, _command_available=lambda name: True, isfile=lambda path: True, _has_enigma2=lambda path: path == '/var/lib/dpkg/status'):
            self.assertEqual(fn(), 'dreamos')
        with patch.dict(ns, _command_available=lambda name: True, isfile=lambda path: True, _has_enigma2=lambda path: 'opkg' in path):
            self.assertEqual(fn(), 'ipk')
        with patch.dict(ns, _command_available=lambda name: False):
            with self.assertRaises(RuntimeError): fn()

    def test_manifest_channel_isolation(self):
        for channel, other in [('ipk', 'dreamos'), ('dreamos', 'ipk')]:
            m = load(channel)
            self.assertEqual(m._verify_meta(m.DEFAULT_REPO, metadata(channel))['channel'], channel)
            with self.assertRaises(ValueError): m._verify_meta(m.DEFAULT_REPO, metadata(other))
            wrong = metadata(channel)
            wrong['url'] = metadata(other)['url']
            with self.assertRaises(ValueError): m._verify_meta(m.DEFAULT_REPO, wrong)

    def test_actual_image_must_match_build(self):
        m = load('dreamos'); m._detect_channel = lambda: 'ipk'
        with self.assertRaises(ValueError): m._verify_meta(m.DEFAULT_REPO, metadata('dreamos'))

    def test_independent_update_checks(self):
        for channel, current in [('ipk', '1.0.12'), ('dreamos', '1.0.12-dreamos')]:
            m = load(channel)
            with patch.object(m, '_current_version', return_value=current), patch.object(m, '_read_https', return_value=json.dumps(metadata(channel)).encode()) as read:
                result = m.check()
                self.assertEqual(result['version'], metadata(channel)['version'])
                self.assertIn('update-' + channel + '.json', read.call_args[0][0])
            with patch.object(m, '_current_version', return_value=metadata(channel)['version']), patch.object(m, '_read_https', return_value=json.dumps(metadata(channel)).encode()):
                self.assertIsNone(m.check())

    def test_legacy_manifest_always_ipk(self):
        self.assertEqual((BASE / 'dist/update.json').read_bytes(), (BASE / 'dist/update-ipk.json').read_bytes())
        self.assertEqual(metadata('ipk')['version'], '1.0.15')
        self.assertEqual(metadata('dreamos')['version'], '1.0.15-dreamos')
        self.assertEqual(json.loads((BASE / 'dist/release-info.json').read_text())['tag'], 'v1.0.15')

    def test_reject_bad_manifests(self):
        m = load('ipk')
        for key, bad in [('size', True), ('size', 0), ('size', None), ('size', 2**30), ('sha256', 'bad'),
                         ('url', 'http://github.com/K3bOra/UltraAudio/a.ipk'), ('url', 'https://github.com/other/repo/releases/download/v1/UltraAudio.ipk'),
                         ('version', '1.0.13-dreamos'), ('channel', 'dreamos'), ('format', 'deb')]:
            meta = metadata('ipk'); meta[key] = bad
            with self.subTest(key=key, value=bad), self.assertRaises(ValueError): m._verify_meta(m.DEFAULT_REPO, meta)

    def test_https_url_restrictions(self):
        m = load('ipk')
        for url in ['http://github.com/a', 'https://github.com.evil.test/a', 'https://user@github.com/a', 'https://github.com:444/a', 'file:///tmp/x']:
            with self.assertRaises(ValueError): m._github_https(url)
        for url in ['https://github.com/a', 'https://release-assets.githubusercontent.com/a']:
            m._github_https(url)


class TLSTests(unittest.TestCase):
    def test_context_requires_valid_chain_and_hostname(self):
        for channel in ('ipk', 'dreamos'):
            context = load(channel)._verified_context()
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)

    def test_certificate_failure_never_disables_verification(self):
        m = load('dreamos')
        contexts = []
        def opener(*handlers):
            contexts.extend(h._context for h in handlers if isinstance(h, m.HTTPSHandler))
            return Mock(open=Mock(side_effect=ssl.SSLError('CERTIFICATE_VERIFY_FAILED')))
        with patch.object(m, 'build_opener', side_effect=opener):
            with self.assertRaises(ssl.SSLError): m._open_verified(m.Request('https://github.com/test'))
        self.assertEqual(len(contexts), 2)
        for context in contexts:
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_missing_verification_runtime_fails_closed(self):
        m = load('dreamos')
        with patch.object(m, 'ssl', object()):
            with self.assertRaises(RuntimeError): m._verified_context()


class InstallTests(unittest.TestCase):
    def test_updater_dispatches_correct_manager(self):
        for channel, current in [('ipk', '1.0.12'), ('dreamos', '1.0.12-dreamos')]:
            m = load(channel)
            meta = metadata(channel); meta['repo'] = m.DEFAULT_REPO
            calls = []
            with patch.object(m, '_current_version', return_value=current), patch.object(m, '_read_https', return_value=payload(channel)), \
                 patch.object(m, '_run_logged', side_effect=lambda args, *a, **k: calls.append(args)), patch.object(m, '_ONLINE_LOG', tempfile.mktemp()):
                self.assertEqual(m.install_verified(meta), meta['version'])
            self.assertEqual(calls[0][:3] if channel == 'dreamos' else calls[0][:2], ['dpkg', '--refuse-downgrade', '-i'] if channel == 'dreamos' else ['opkg', 'install'])
            self.assertTrue(calls[0][-1].endswith('.deb' if channel == 'dreamos' else '.ipk'))
            self.assertFalse(Path(calls[0][-1]).exists())
            self.assertNotIn('--force-downgrade', calls[0])
            self.assertNotIn('--force-overwrite', calls[0])

    def test_refuses_download_for_wrong_platform(self):
        m = load('dreamos'); meta = metadata('ipk'); meta['repo'] = m.DEFAULT_REPO
        with patch.object(m, '_read_https') as read, patch.object(m, '_run_logged') as run:
            with self.assertRaises(ValueError): m.install_verified(meta)
            read.assert_not_called(); run.assert_not_called()

    def test_corruption_never_reaches_package_manager(self):
        for channel in ('ipk', 'dreamos'):
            m = load(channel); meta = metadata(channel); meta['repo'] = m.DEFAULT_REPO
            for data in (payload(channel)[:-1], b'X' + payload(channel)[1:]):
                with patch.object(m, '_read_https', return_value=data), patch.object(m, '_run_logged') as run:
                    with self.assertRaises(ValueError): m.install_verified(meta)
                    run.assert_not_called()

    def test_metadata_mismatch_and_downgrade_refused(self):
        m = load('ipk'); meta = metadata('ipk'); meta['repo'] = m.DEFAULT_REPO
        for control in ['Package: other\nVersion: 1.0.13\nArchitecture: all\n', 'Package: ' + m.PACKAGE_NAME + '\nVersion: 1.0.12\nArchitecture: all\n',
                        'Package: ' + m.PACKAGE_NAME + '\nVersion: 1.0.13\nArchitecture: arm\n']:
            with patch.object(m, '_read_https', return_value=payload('ipk')), patch.object(m, '_ipk_control', return_value=control), patch.object(m, '_run_logged') as run:
                with self.assertRaises(ValueError): m.install_verified(meta)
                run.assert_not_called()
        with patch.object(m, '_read_https', return_value=payload('ipk')), patch.object(m, '_current_version', return_value='1.0.99'), patch.object(m, '_run_logged') as run:
            with self.assertRaises(ValueError): m.install_verified(meta)
            run.assert_not_called()

    def test_package_manager_failure_cleans_temp_and_releases_lock(self):
        m = load('dreamos'); meta = metadata('dreamos'); meta['repo'] = m.DEFAULT_REPO
        paths = []
        def fail(args, *a, **kw):
            paths.append(args[-1]); raise RuntimeError('simulated package manager failure')
        with patch.object(m, '_read_https', return_value=payload('dreamos')), patch.object(m, '_current_version', return_value='1.0.12-dreamos'), patch.object(m, '_run_logged', side_effect=fail), patch.object(m, '_ONLINE_LOG', tempfile.mktemp()):
            with self.assertRaises(RuntimeError): m.install_verified(meta)
        self.assertFalse(Path(paths[0]).exists())
        self.assertTrue(m._INSTALL_LOCK.acquire(False)); m._INSTALL_LOCK.release()

    def test_archive_control_validation(self):
        m = load('ipk')
        for channel in ('ipk', 'dreamos'):
            self.assertIn('Version: ' + metadata(channel)['version'], m._ipk_control(payload(channel)))
        for data in (b'not a package', payload('ipk')[:-1], b'!<arch>\n' + b' ' * 60):
            with self.assertRaises((ValueError, tarfile.TarError)): m._ipk_control(data)

    def test_installer_verify_only_both_channels(self):
        for channel in ('ipk', 'dreamos'):
            ns = installer(); calls = []
            def read(url, limit, progress=None):
                calls.append(url)
                return payload(channel) if progress else json.dumps(metadata(channel)).encode()
            with patch.dict(ns, _read_https=read, _receiver_python_major=lambda: 3), patch('subprocess.call', side_effect=AssertionError('verify-only ran a command')):
                ns['installer_main'](['--verify-only', '--platform=' + channel])
            self.assertEqual(len(calls), 2)
            self.assertIn('update-' + channel + '.json', calls[0])

    def test_installer_platform_override_never_installs(self):
        ns = installer()
        with self.assertRaises(ValueError): ns['installer_main'](['--platform=ipk'])

    def test_python2_opkg_image_rejected_before_download(self):
        ns = installer()
        with patch.dict(ns, _detect_channel=lambda: 'ipk', _receiver_python_major=lambda: 2, _read_https=Mock(side_effect=AssertionError('download attempted'))):
            with self.assertRaises(RuntimeError): ns['installer_main']([])

    def test_installer_full_dispatch_without_real_installation(self):
        for channel in ('ipk', 'dreamos'):
            ns = installer(); calls = []
            def read(url, limit, progress=None):
                return payload(channel) if progress else json.dumps(metadata(channel)).encode()
            def call(args, **kwargs):
                calls.append((args, kwargs)); return 0
            with patch.dict(ns, _detect_channel=lambda: channel, _receiver_python_major=lambda: 3, _read_https=read, _command_available=lambda n: True), \
                 patch('os.geteuid', return_value=0), patch('subprocess.check_output', return_value=b''), patch('subprocess.call', side_effect=call):
                ns['installer_main']([])
            self.assertEqual(calls[0][0], ['apt-get', 'update'] if channel == 'dreamos' else ['opkg', 'update'])
            self.assertEqual(calls[1][0][:3] if channel == 'dreamos' else calls[1][0][:2], ['dpkg', '--refuse-downgrade', '-i'] if channel == 'dreamos' else ['opkg', 'install'])
            self.assertEqual(calls[2][0][0], '/bin/sh')
            self.assertNotIn('ULTRAAUDIO_ONLINE_UPDATE', calls[2][1]['env'])
            self.assertFalse(Path(calls[1][0][-1]).exists())

    def test_known_legacy_dreamos_rebase_only(self):
        ns = installer()
        with patch.dict(ns, _installed_parallel_dreamos=lambda: False):
            for old in ('1.0.23-dreamos', '1.0.24-dreamos'):
                self.assertTrue(ns['_dreamos_numbering_transition']('dreamos', old, '1.0.13-dreamos'))
            for channel, old, new in [('ipk', '1.0.23-dreamos', '1.0.13-dreamos'),
                                      ('dreamos', '1.0.25-dreamos', '1.0.13-dreamos'),
                                      ('dreamos', '1.0.23-dreamos', '1.0.12-dreamos'),
                                      ('dreamos', '1.0.23', '1.0.13-dreamos')]:
                self.assertFalse(ns['_dreamos_numbering_transition'](channel, old, new))
        with patch.dict(ns, _installed_parallel_dreamos=lambda: True):
            self.assertFalse(ns['_dreamos_numbering_transition']('dreamos', '1.0.23-dreamos', '1.0.13-dreamos'))

    def test_installed_scheme_is_read_without_execution(self):
        ns = installer()
        for source, expected in [(b'# -*- coding: utf-8 -*-\nPACKAGE_VERSION="1.0.23-dreamos"\n', False),
                                 (b'# -*- coding: utf-8 -*-\nVERSION_SCHEME="parallel-v1"\nraise RuntimeError("must not execute")\n', True)]:
            with patch('builtins.open', mock_open(read_data=source)):
                self.assertEqual(ns['_installed_parallel_dreamos'](), expected)
        with patch('builtins.open', mock_open(read_data=b'VERSION_SCHEME="unknown"\n')):
            with self.assertRaises(ValueError): ns['_installed_parallel_dreamos']()

    def test_online_updates_keep_normal_version_order(self):
        m = load('dreamos')
        self.assertTrue(m._is_update('1.0.13-dreamos', '1.0.14-dreamos'))
        self.assertFalse(m._is_update('1.0.14-dreamos', '1.0.13-dreamos'))
        self.assertFalse(m._is_update('1.0.23-dreamos', '1.0.13-dreamos'))
        self.assertFalse(m._is_update('1.0.13-dreamos', '1.0.13-dreamos'))

    def test_installer_rebases_only_known_legacy_dreamos(self):
        for old, parallel, permitted in [('1.0.23-dreamos', False, True), ('1.0.24-dreamos', False, True),
                                          ('1.0.23-dreamos', True, False), ('1.0.25-dreamos', False, False)]:
            ns = installer(); calls = []
            def read(url, limit, progress=None):
                return payload('dreamos') if progress else json.dumps(metadata('dreamos')).encode()
            status = ('Package: test\nVersion: %s\nStatus: install ok installed\n' % old).encode()
            with patch.dict(ns, _detect_channel=lambda: 'dreamos', _read_https=read,
                            _command_available=lambda n: True, _installed_parallel_dreamos=lambda: parallel), \
                 patch('os.geteuid', return_value=0), patch('subprocess.check_output', return_value=status), \
                 patch('subprocess.call', side_effect=lambda args, **kw: calls.append(args) or 0):
                if permitted:
                    ns['installer_main']([])
                    self.assertEqual(calls[1][:3], ['dpkg', '--force-downgrade', '-i'])
                    self.assertFalse(Path(calls[1][-1]).exists())
                else:
                    with self.assertRaises(ValueError): ns['installer_main']([])
                    self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
