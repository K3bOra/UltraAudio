"""Offline web badge contracts; isolate the library serializer from receiver IO."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import time

root = Path(os.environ['UA_PLUGIN_ROOT'])
module = ast.parse((root / 'webui.py').read_text())
function = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == 'library')
store = MagicMock()
store._load.return_value = {'folders': [], 'streams': [
    {'id': 'a', 'name': 'A'}, {'id': 'b', 'name': 'B'}, {'id': 'r', 'name': 'Radio'}]}
store.stream_key.side_effect = lambda s: s['id']
store.is_radio_stream.side_effect = lambda s, lib: s['id'] == 'r'
store.stream_display.side_effect = lambda s, lib: (s['name'], '')
store.needs_radio_url.return_value = False
store.stream_icon.return_value = None
guide = MagicMock()
now = time.time()
event = ('Team One vs Team Two', now - 100, now + 100)
guide.view.return_value = ('key', event, False)
scores = MagicMock()
scores.is_live.return_value = True
import re
scope = dict(store=store, guide=guide, i18n=SimpleNamespace(lang=lambda: 'en'),
             receivertime=SimpleNamespace(guide_notice=lambda: ""), T=lambda s: s,
             shared_icon_url=lambda p: None, time=time, to_text=str, LIVE_SCORES=scores,
             LIVE_SPLIT=re.compile(r'\s+vs\s+', re.I), LIVE_BAD_PROGRAM=re.compile('replay', re.I))
exec(compile(ast.Module(body=[function], type_ignores=[]), '<library>', 'exec'), scope)
result = scope['library']()
assert [s['guide']['match_live'] for s in result['streams'][:2]] == [True, True]
assert result['streams'][2]['guide'] is None
scores.ensure.assert_called_once_with(event)
scores.is_live.return_value = False
assert not scope['library']()['streams'][0]['guide']['match_live']
scores.reset_mock()
guide.view.return_value = ('key', ('Replay: Team One vs Team Two', now - 100, now + 100), False)
scope['library']()
scores.ensure.assert_not_called()
assert 'guide' not in store._load.return_value['streams'][0]
print('PASS confirmed-live badges, cache miss, radio exclusion, replay fetch exclusion, one shared request, no stored mutation')
