#!/usr/bin/env python3
"""Run offline receiver-independent checks; optional real-time PCM tests."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

BASE = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--audio', action='store_true', help='also run PCM relay tests; needs ffmpeg and about one minute')
args = parser.parse_args()

subprocess.run([sys.executable, '-B', str(BASE / 'scripts/prepare_release.py')], check=True)
subprocess.run([sys.executable, '-B', str(BASE / 'tests/test_updates.py')], check=True)
subprocess.run([sys.executable, '-B', str(BASE / 'tests/test_e2pc_updates.py')], check=True)
for tree in ('ipk-source', 'deb-source'):
    with tempfile.TemporaryDirectory(prefix='ultraaudio_offline_') as scratch:
        env = dict(os.environ, ULTRAAUDIO_DATA=scratch,
            UA_PLUGIN_ROOT=str(BASE / tree / 'data/usr/lib/enigma2/python/Plugins/Extensions/UltraAudio'))
        names = ['test_timeshift.py', 'test_library.py', 'test_delay_limits.py', 'test_live_rich.py', 'test_scorer_feed.py', 'test_web_test3.py', 'test_playback_bar.py', 'test_turkish.py', 'test_turkish_radio.py']
        if args.audio:
            names.append('test_audio.py')
        for name in names:
            subprocess.run([sys.executable, '-B', str(BASE / 'tests' / name)], env=env, check=True)
subprocess.run([sys.executable, '-B', str(BASE / 'scripts/prepare_release.py'), '--verify-published', str(BASE / 'dist')], check=True)
subprocess.run(['node', str(BASE / 'tests/test_web_guide_clock.cjs')], check=True)
print('PASS all requested offline checks; no external publication or installation')
