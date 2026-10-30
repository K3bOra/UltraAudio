import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('updater_test', str(Path(__file__).resolve().parents[1]/'ipk-source/data/usr/lib/enigma2/python/Plugins/Extensions/UltraAudio/updater.py'))
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)

class DetectionTests(unittest.TestCase):
    def channel(self, managers=('dpkg','opkg'), deb_pkg=False, ipk_pkg=False, deb_e2=False, ipk_e2=False, pc=False, status=True):
        with patch.object(u,'_command_available',side_effect=lambda name:name in managers), patch.object(u,'isfile',return_value=status), patch.object(u,'_has_package',side_effect=lambda path,name:deb_pkg if 'dpkg' in path else ipk_pkg), patch.object(u,'_has_enigma2',side_effect=lambda path:deb_e2 if 'dpkg' in path else ipk_e2), patch.object(u,'_is_e2pc_opkg',return_value=pc):
            return u._detect_channel()
    def test_confirmed_pc(self):self.assertEqual(self.channel(pc=True),'ipk')
    def test_unknown_dual_manager_is_rejected(self):
        with self.assertRaises(RuntimeError):self.channel()
    def test_receivers(self):
        self.assertEqual(self.channel(managers=('dpkg',)),'dreamos')
        self.assertEqual(self.channel(managers=('opkg',)),'ipk')
        self.assertEqual(self.channel(deb_e2=True),'dreamos')
        self.assertEqual(self.channel(ipk_e2=True),'ipk')
    def test_package_registration_wins(self):
        self.assertEqual(self.channel(deb_pkg=True,ipk_e2=True,pc=True),'dreamos')
        self.assertEqual(self.channel(ipk_pkg=True,deb_e2=True),'ipk')
    def test_conflicting_registrations(self):
        for kwargs in ({'deb_pkg':True,'ipk_pkg':True,'pc':True},{'deb_e2':True,'ipk_e2':True,'pc':True}):
            with self.assertRaises(RuntimeError):self.channel(**kwargs)
    def test_no_managers(self):
        with self.assertRaises(RuntimeError):self.channel(managers=())
    def test_arch_and_path(self):
        expected='/usr/local/e2/lib/enigma2/python/Plugins/Extensions/UltraAudio'
        def run(output, machine='x86_64', canonical=expected, present=True):
            with patch.object(u.sys,'platform','linux'),patch.object(u.os,'uname',return_value=('Linux','','','',machine)),patch.object(u.os.path,'realpath',return_value=canonical),patch.object(u.os.path,'isfile',return_value=present),patch.object(u.subprocess,'check_output',return_value=output):return u._is_e2pc_opkg()
        self.assertTrue(run(b'arch all 1\narch noarch 1\narch x86_64 10\n'))
        for output in (b'',b'arch x86_64 10\n',b'arch all 1\narch armv7 10\n',b'arch all 0\narch x86_64 10\n',b'arch all invalid\narch x86_64 10\n'):
            self.assertFalse(run(output))
        self.assertFalse(run(b'arch all 1\narch x86_64 10\n',machine='aarch64'))
        self.assertFalse(run(b'arch all 1\narch x86_64 10\n',canonical='/usr/lib/enigma2/python/Plugins/Extensions/UltraAudio'))
        self.assertFalse(run(b'arch all 1\narch x86_64 10\n',present=False))
    def test_channel_guard_preserved(self):
        with patch.object(u,'_detect_channel',return_value='dreamos'):
            with self.assertRaises(ValueError):u._channel()
    def test_status_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'status'
            p.write_text('Package: enigma2-plugin-extensions-ultraaudio\nStatus: install ok installed\nVersion: 1.0.14\n\nPackage: unrelated\nStatus: install ok installed\n')
            self.assertTrue(u._has_package(str(p),u.PACKAGE_NAME))
            self.assertFalse(u._has_enigma2(str(p)))
            p.write_text('Package: enigma2-plugin-extensions-ultraaudio\nStatus: deinstall ok config-files\n\nPackage: unrelated\nStatus: install ok installed\n')
            self.assertFalse(u._has_package(str(p),u.PACKAGE_NAME))
    def test_standalone_installer_detects_existing_e2pc(self):
        base=Path(__file__).resolve().parents[1]
        script=(base/'install.sh').read_text()
        code=script.split("<<'ULTRAAUDIO_INSTALL_PY'\n",1)[1].split('\nULTRAAUDIO_INSTALL_PY',1)[0]
        ns={'__name__':'offline_test','__file__':'<stdin>'}
        exec(compile(code,'installer_test','exec'),ns)
        expected='/usr/local/e2/lib/enigma2/python/Plugins/Extensions/UltraAudio'
        with patch.object(u.os.path,'realpath',return_value=expected),patch.object(u.os.path,'isfile',return_value=True),patch.object(u.os,'uname',return_value=('Linux','','','','x86_64')),patch.object(u.subprocess,'check_output',return_value=b'arch all 1\narch noarch 1\narch x86_64 10\n'):
            self.assertIsNone(ns['BUILD_CHANNEL'])
            self.assertTrue(ns['_is_e2pc_opkg']())

if __name__=='__main__':unittest.main(verbosity=2)
