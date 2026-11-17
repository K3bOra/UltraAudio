#!/usr/bin/env python3
"""Offline routing, family isolation and verification of the four shipped packages."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'scripts'))
from release_variants import VARIANTS
from prepare_release import inspect_package

TEMPLATE = (BASE / 'scripts/updater_template.py').read_text()


def updater(family, channel):
    namespace = {'__name__': 'release_updater', '__file__': '/test/updater.py'}
    code = TEMPLATE.replace("'__CHANNEL__'", repr(channel)).replace("'__FAMILY__'", repr(family))
    exec(compile(code, '<updater>', 'exec'), namespace)
    return namespace


class ReleaseFamilies(unittest.TestCase):
    def test_four_packages_and_versions(self):
        for family, channel, package, manifest in VARIANTS:
            with self.subTest(package=package):
                meta = inspect_package(BASE / 'packages' / package)
                self.assertEqual(meta['family'], family)
                self.assertEqual(meta['version'], '1.0.28-dreamos' if channel == 'dreamos' else '1.0.28')

    def test_matrix_rejects_other_three_variants(self):
        for family, channel, package, manifest in VARIANTS:
            ns = updater(family, channel)
            ns['_detect_family'] = lambda: family
            ns['_detect_channel'] = lambda: channel
            self.assertEqual(ns['_manifest_name'](), manifest)
            for other_family, other_channel, other_package, other_manifest in VARIANTS:
                meta = json.loads((BASE / 'dist' / other_manifest).read_text())
                if (other_family, other_channel) == (family, channel):
                    verified = ns['_verify_meta']('K3bOra/UltraAudio', meta)
                    self.assertEqual(verified['family'], family)
                    self.assertIn(package, verified['url'])
                    control = ns['_ipk_control']((BASE / 'packages' / package).read_bytes())
                    ns['_verify_package_family'](control)
                else:
                    with self.assertRaises(ValueError):
                        ns['_verify_meta']('K3bOra/UltraAudio', meta)
                    if other_family != family:
                        with self.assertRaises(ValueError):
                            ns['_verify_package_family']('X-UltraAudio-Family: ' + other_family)
            good = json.loads((BASE / 'dist' / manifest).read_text())
            for wrong in ('', 'unknown', 'standard' if family != 'standard' else 'dreambox-one-two'):
                bad = dict(good, family=wrong)
                with self.assertRaises(ValueError):
                    ns['_verify_meta']('K3bOra/UltraAudio', bad)
            bad = dict(good, url=good['url'].rsplit('/', 1)[0] + '/Ultra_Audio_Wrong.' + good['format'])
            with self.assertRaises(ValueError):
                ns['_verify_meta']('K3bOra/UltraAudio', bad)

    def test_hardware_models_and_pinned_family(self):
        ns = updater(None, None)
        for model in ('one', 'two', 'dreamone', 'dreamtwo', 'dreamboxone', 'dreamboxtwo', 'dreamboxoneuhd', 'dreamboxtwouhd'):
            ns['_model_values'] = lambda: [model]
            self.assertEqual(ns['_family'](), 'dreambox-one-two')
        for model in ('dm900', 'dm920', 'dm8000', 'vuduo4k', 'zgemmah7'):
            ns['_model_values'] = lambda: [model]
            self.assertEqual(ns['_family'](), 'standard')
        for family in ('standard', 'dreambox-one-two'):
            ns = updater(family, 'ipk')
            ns['_model_values'] = lambda: []
            self.assertEqual(ns['_family'](), family)
            ns['_detect_family'] = lambda: 'standard' if family != 'standard' else 'dreambox-one-two'
            with self.assertRaises(ValueError):
                ns['_family']()

    def test_model_normalization(self):
        ns = updater(None, None)
        def model_open(path, mode):
            if path == '/proc/stb/info/model':
                return io.BytesIO(b'Dreambox Two UHD\x00\n')
            raise OSError('absent')
        ns['open'] = model_open
        self.assertEqual(ns['_family'](), 'dreambox-one-two')
        ns['_model_values'] = lambda: []
        with patch('os.uname', return_value=('Linux', '', '', '', 'aarch64')):
            with self.assertRaises(RuntimeError):
                ns['_family']()

    def test_no_cross_family_fallback(self):
        for family, channel, package, manifest in VARIANTS:
            ns = updater(family, channel)
            ns['_detect_family'] = lambda: family
            ns['_detect_channel'] = lambda: channel
            ns['_current_version'] = lambda: '1.0.27'
            urls = []
            def read(url, limit):
                urls.append(url)
                if len(urls) == 1:
                    raise ns['HTTPError'](url, 404, 'missing', {}, None)
                return (BASE / 'dist' / manifest).read_bytes()
            ns['_read_https'] = read
            self.assertIsNotNone(ns['check']())
            self.assertEqual(len(urls), 2)
            self.assertTrue(all(url.endswith('/' + manifest) for url in urls))
            def missing(url, limit):
                raise ns['HTTPError'](url, 404, 'missing', {}, None)
            ns['_read_https'] = missing
            with self.assertRaises(ns['HTTPError']):
                ns['check']()

    def test_unified_installer_all_four_routes(self):
        # Run the exact embedded code with network and installation stubbed out.
        script = (BASE / 'install.sh').read_text().split("<<'ULTRAAUDIO_INSTALL_PY'\n", 1)[1].rsplit('\nULTRAAUDIO_INSTALL_PY', 1)[0]
        for family, channel, package, manifest in VARIANTS:
            ns = {'__name__': 'offline_installer', '__file__': '/test/install.py'}
            exec(compile(script, '<installer>', 'exec'), ns)
            urls = []
            def read(url, limit, *args):
                urls.append(url)
                return (BASE / 'dist' / url.rsplit('/', 1)[1]).read_bytes()
            ns['_read_https'] = read
            ns['_receiver_python_major'] = lambda: 3
            with contextlib.redirect_stdout(io.StringIO()):
                ns['installer_main'](['--verify-only', '--platform=' + channel, '--family=' + family])
            self.assertEqual([url.rsplit('/', 1)[1] for url in urls], [manifest, package])


if __name__ == '__main__':
    unittest.main(verbosity=2)
