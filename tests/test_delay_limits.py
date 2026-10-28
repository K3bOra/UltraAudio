"""Exercise the shared 60-second range through playback, persistence and controls."""
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
ROOT = Path(os.environ['UA_PLUGIN_ROOT']).resolve()
sys.path.insert(0, str(ROOT.parent))
_data = tempfile.TemporaryDirectory(prefix='ultraaudio_delay_limits_')
os.environ['ULTRAAUDIO_DATA'] = _data.name
os.environ['ULTRAAUDIO_LOG'] = str(Path(_data.name) / 'engine.log')
from UltraAudio import engine, store


class DelayLimits(unittest.TestCase):
    def test_playback_and_live_adjustment(self):
        player = engine.Engine()
        with patch.object(player, '_stop_locked'), patch('UltraAudio.importer.cancel_link_checks'):
            for ms, expected in [(45000, 45000), (60000, 60000), (65000, 60000), (-500, 0)]:
                player.play({'id': 'test', 'name': 'Test', 'url': 'https://example.com/a.mp3'}, ms, deferred=True)
                self.assertEqual(player.audio_delay_ms, expected)
        player.live_delay = True
        with patch.object(player, 'play') as restart:
            for ms, expected in [(45000, 45000), (60000, 60000), (60500, 60000), (59500, 59500), (0, 0)]:
                player.set_audio_delay(ms)
                self.assertEqual(player.audio_delay_ms, expected)
            restart.assert_not_called()

    def test_saved_channel_survives_reload_above_thirty_seconds(self):
        folder = store.add_folder('Delay regression')
        stream = store.add_stream({'name': 'Recording', 'url': 'https://example.com/a.mp3'}, folder=folder['id'])
        for ms, expected in [(45000, 45000), (60000, 60000), (65000, 60000), (-1, 0)]:
            store.remember_channel('delay-limit-service', stream['id'], 10, ms)
            store._session_memory.clear()
            store._memory_loaded = False
            self.assertEqual(store.recall_channel('delay-limit-service')['audio_ms'], expected)

    def test_backup_accepts_new_range_and_rejects_out_of_range(self):
        stream = store.add_stream({'name': 'Backup delay', 'url': 'https://example.com/b.mp3'})
        store.set_offsets(stream['id'], audio_ms=60000)
        self.assertEqual(store.get_stream(stream['id'])['audio_delay_ms'], 60000)
        backup = store.make_backup()
        store.validate_backup(backup)
        store.restore_backup(backup)
        self.assertEqual(store.get_stream(stream['id'])['audio_delay_ms'], 60000)
        bad = store.make_backup()
        next(s for s in bad['library']['streams'] if s['id'] == stream['id'])['audio_delay_ms'] = 60001
        with self.assertRaises(ValueError): store.validate_backup(bad)

    def test_remote_steps_cross_old_limit_and_stop_at_sixty(self):
        tree = ast.parse((ROOT / 'screen.py').read_text())
        method = next(n for c in tree.body if isinstance(c, ast.ClassDef) for n in c.body
                      if isinstance(n, ast.FunctionDef) and n.name == 'key_audio')
        state = {'state': 'playing', 'audio_delay_supported': True, 'stream_id': 'test',
                 'audio_delay_ms': 30000, 'audio_delay_live': True}
        controller = types.SimpleNamespace(engine=types.SimpleNamespace(status=lambda: state), video=Mock())
        ns = {'ctl': types.SimpleNamespace(get=lambda: controller),
              'store': types.SimpleNamespace(get_settings=lambda: {'step_audio_ms': 500}), 'AUDIO_SETTLE': .25}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'screen:key_audio', 'exec'), ns)
        ui = types.SimpleNamespace(menu=types.SimpleNamespace(is_open=False), _audio_pending=None,
                                  audio_timer=Mock(), refresh=Mock())
        ns['key_audio'](ui, 1)
        self.assertEqual(ui._audio_pending, 30500)
        ui._audio_pending = 59500
        ns['key_audio'](ui, 1); self.assertEqual(ui._audio_pending, 60000)
        ns['key_audio'](ui, 1); self.assertEqual(ui._audio_pending, 60000)
        ns['key_audio'](ui, -1); self.assertEqual(ui._audio_pending, 59500)

    def test_web_controls_cross_old_limit_and_stop_at_sixty(self):
        html = (ROOT / 'web/index.html').read_text()
        function = re.search(r'function audioStep\(dir\) \{.*?\n\}', html, re.S).group(0)
        js = '''const assert = require('assert');
let ST={state:'playing',audio_delay_supported:true,audio_delay_ms:30000,step_audio_ms:500,video:{}};
const ACTIVE=['playing']; let aTarget='same',aPending=null,aTimer=null,aRevision=0,vPending=null;
const audioTarget=()=> 'same',clearAudioPending=()=>{},secs=String,$=()=>({}),paintDials=()=>{},sendAudioPending=()=>{};
const setTimeout=()=>1,clearTimeout=()=>{};
''' + function + '''
audioStep(1); assert.strictEqual(aPending,30500);
aPending=59500;audioStep(1);assert.strictEqual(aPending,60000);
audioStep(1);assert.strictEqual(aPending,60000);
audioStep(-1);assert.strictEqual(aPending,59500);
'''
        subprocess.run(['node', '-e', js], check=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
