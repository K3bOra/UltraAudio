"""Regression checks for the control paragraph rejected by receiver dpkg."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'scripts'))
from prepare_release import validate_control
from release_variants import VARIANTS


class ControlMetadata(unittest.TestCase):
    def test_rejects_the_reported_two_paragraph_control(self):
        control = ('Package: enigma2-plugin-extensions-ultraaudio\nVersion: 1.0.28-dreamos\n'
                   'Architecture: all\n\nX-UltraAudio-Family: standard\n')
        with self.assertRaisesRegex(ValueError, 'exactly one paragraph'):
            validate_control(control)
        validate_control(control.replace('\n\n', '\n'))

    def test_native_parser_accepts_every_shipped_package(self):
        for family, channel, filename, manifest in VARIANTS:
            with self.subTest(filename=filename):
                output = subprocess.check_output(['dpkg-deb', '--field', str(BASE / 'packages' / filename),
                                                  'Package', 'Version', 'Architecture', 'X-UltraAudio-Family'])
                self.assertIn(('X-UltraAudio-Family: ' + family).encode(), output)

    def test_dpkg_dry_run_accepts_both_deb_packages(self):
        # --no-act never runs maintainer scripts or installs files; the DB/root/log are isolated.
        for family, channel, filename, manifest in VARIANTS:
            if channel != 'dreamos':
                continue
            with self.subTest(filename=filename), tempfile.TemporaryDirectory(prefix='ua_dpkg_validation_') as d:
                root = Path(d)
                (root / 'updates').mkdir()
                (root / 'status').touch()
                result = subprocess.run(['dpkg', '--admindir=' + d, '--instdir=' + d,
                                         '--log=' + str(root / 'dpkg.log'), '--force-not-root',
                                         '--no-act', '--unpack', str(BASE / 'packages' / filename)],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
