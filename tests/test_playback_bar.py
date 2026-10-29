"""Exercise the real overlay source against a receiver-independent GUI harness."""
import ast
import copy
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from PIL import Image

root = Path(os.environ['UA_PLUGIN_ROOT']).resolve()


class Timer:
    def __init__(self):
        self.callback, self.running = [], False
    def start(self, ms, once=False):
        self.ms, self.running = ms, True
    def stop(self):
        self.running = False


class Widget:
    def __init__(self, text=''):
        self.text, self.visible = text, True
        self.instance = NS(setPixmap=lambda p: None, resize=MagicMock(), move=MagicMock())
    def setText(self, text):
        self.text = text
    def show(self):
        self.visible = True
    def hide(self):
        self.visible = False


class Screen(dict):
    def __init__(self, session):
        self.session = session
        self.onLayoutFinish, self.onExecBegin, self.onExecEnd = [], [], []
        self.onHide, self.onClose = [], []
    def close(self):
        for callback in self.onClose:
            callback()


class ActionMap(dict):
    """Receiver ActionMap calls bound callbacks without positional arguments."""
    def __init__(self, contexts, actions, priority):
        super().__init__(actions)
    def action(self, context, action):
        response = self[action]()
        return 1 if response is None else response


class NumberActionMap(ActionMap):
    def action(self, context, action):
        if action.isdigit():
            response = self[action](int(action))
            return 1 if response is None else response
        return super().action(context, action)


class Marker:
    def __init__(self, *args):
        self.running = False
    def update(self, *args, **kwargs):
        self.running = True
    def stop(self):
        self.running = False
    close = stop


state = dict(state='playing', stream_id='station', generation=7, tv_service='tv',
             audio_delay_supported=True, audio_delay_live=True, audio_delay_ms=0,
             video=dict(state='running', current_s=7.0, target_s=10.0))
controller = MagicMock()
controller.status.side_effect = lambda: copy.deepcopy(state)
controller.engine = NS(lock=threading.Lock(), state='playing', stream={'id': 'station'})
store = MagicMock(ASSETS=str(root / 'assets'))
store.get_settings.return_value = dict(step_video_s=1.0, step_audio_ms=500)
store.get_stream.return_value = dict(id='station', name='Audio')
store.stream_display.return_value = ('Audio', '')
store.stream_icon.return_value = str(root / 'assets/folders/radio.png')
store.is_radio_stream.return_value = True
store.recall_channel.return_value = None
theme = dict(pal=dict(accent='#00DA7F', text='#FFFFFF', muted='#D1DDD7', live='#FF5E66'))
themes = NS(get=lambda: theme, face=lambda n: 'Regular',
            pic=lambda th, n: str(root / 'assets/ui' / n))
guide = MagicMock()
scope = dict(os=os, time=time, escape=escape, Screen=Screen,
             ActionMap=ActionMap, NumberActionMap=NumberActionMap,
             Label=Widget, Pixmap=Widget, LoadPixmap=lambda p: NS(size=lambda: NS(width=lambda: 320, height=lambda: 176)),
             eSize=lambda w,h: (w,h), ePoint=lambda x,y: (x,y),
             eTimer=Timer, getDesktop=lambda n: NS(size=lambda: NS(width=lambda: 1920, height=lambda: 1080)),
             ctl=NS(get=lambda: controller), guide=guide, store=store, themes=themes,
             native=lambda v: v, log=lambda message: None, T=lambda text, *args: text % args if args else text,
             lang=lambda: 'en', PlaybackMarker=Marker)
tree = ast.parse((root / 'playbackbar.py').read_text())
tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
exec(compile(tree, '<playbackbar>', 'exec'), scope)
for width, height in [(1280, 720), (1920, 1080), (3840, 2160)]:
    x, y, w, h, scale = scope['geometry'](width, height)
    assert abs(x + w / 2.0 - width / 2.0) <= 0.5
    assert height - (y + h) == 2
    xml = ET.fromstring(scope['build_skin'](width, height, theme))
    assert tuple(map(int, xml.get('position').split(','))) == (x, y)
    for widget in xml:
        px, py = map(int, widget.get('position').split(','))
        pw, ph = map(int, widget.get('size').split(','))
        assert 0 <= px and 0 <= py and px + pw <= w and py + ph <= h
    assert xml.find('ePixmap').get('pixmap').endswith('/football_panel.png')
    # Native skin creates static ePixmaps separately from GUI components.
    # Explicit layers prevent the panel painting over every dynamic widget.
    background = xml.find('ePixmap')
    for widget in list(xml)[1:]:
        assert int(widget.get('zPosition')) > int(background.get('zPosition'))
        if widget.tag == 'widget':
            assert widget.get('transparent') == '1'
        elif widget.tag == 'ePixmap':
            with Image.open(widget.get('pixmap')) as image:
                assert image.size == tuple(map(int, widget.get('size').split(',')))
                assert image.mode == 'RGBA'
                assert any(0 < alpha < 255 for alpha in image.getchannel('A').tobytes())
            assert widget.get('scale') is None  # no 192px -> tiny circle receiver scaling
    for index in range(8):
        with Image.open(scope['sized_asset']('eq_%d' % index, int(66 * scale), int(28 * scale))) as image:
            assert image.size == (int(66 * scale), int(28 * scale))
    picon = next(w for w in xml if w.get('name') == 'picon')
    name = next(w for w in xml if w.get('name') == 'name')
    assert int(picon.get('position').split(',')[0]) < int(name.get('position').split(',')[0])
    assert name.get('halign') == 'center'
    guide_widget = next(w for w in xml if w.get('name') == 'guide')
    assert guide_widget.get('foregroundColor') == theme['pal']['live']
    time_widget = next(w for w in xml if w.get('name') == 'time')
    tx = int(time_widget.get('position').split(',')[0])
    tw = int(time_widget.get('size').split(',')[0])
    assert time_widget.get('position').split(',')[0] == name.get('position').split(',')[0]
    assert time_widget.get('size').split(',')[0] == name.get('size').split(',')[0]
    assert time_widget.get('halign') == name.get('halign') == 'center'
    marker = next(node for node in xml if node.get('name') == 'marker')
    mx = int(marker.get('position').split(',')[0])
    mw = int(marker.get('size').split(',')[0])
    assert abs(mx + mw / 2.0 - w / 2.0) <= 1
    for number in [node for node in xml.findall('ePixmap') if '/num_' in node.get('pixmap','')]:
        nx = int(number.get('position').split(',')[0])
        nw = int(number.get('size').split(',')[0])
        assert nx + nw <= mx or nx >= mx + mw
for source_w, source_h in [(320,176),(176,320),(100,100),(640,352)]:
    pw, ph = scope['fit_picon'](source_w,source_h,144,84)
    assert pw <= 144 and ph <= 84
    assert abs(pw/ph - source_w/source_h) < 0.025
Bar = scope['PlaybackBar']
bar = Bar(NS())
bar._layout_ready()
assert bar['picture_value'].text == '7.0 s'  # measured delay, not the 10-second target
bar['picon'].instance.resize.assert_called_with((144, 79))
assert bar['name'].text == 'Audio'
assert bar['picture_caption'].text == 'Picture'
assert bar['audio_caption'].text == 'Audio'
assert bar['audio_value'].text == '0.0 s'
assert bar['guide'].text == ''
guide.ensure.assert_not_called()  # radios never request a TV guide
bar.adjust('picture', 1)
bar.adjust('picture', 1)
assert bar._pending['picture'] == 12.0 and bar._picture_timer.ms == 850
bar.apply('picture')
controller.set_video_delay.assert_called_once_with(12.0, 'station', 7)
bar.adjust('audio', 1)
bar.adjust('audio', 1)
bar.apply('audio')
controller.set_audio_delay.assert_called_once_with(1000, 'station', 7)
state['audio_delay_supported'] = False
bar.adjust('audio', 1)
assert bar._pending['audio'] is None
state['audio_delay_supported'] = True
bar.adjust('picture', 1)
state['tv_service'] = 'different-channel'
bar.apply('picture')
assert controller.set_video_delay.call_count == 1
bar.refresh()
assert bar._closed and not bar._refresh_timer.running and not bar._marker.running
state['tv_service'] = 'tv'
bar = Bar(NS())
bar._layout_ready()
bar.adjust('audio', 1)
bar._suspend()
bar.apply('audio')
assert controller.set_audio_delay.call_count == 1
assert not bar._audio_timer.running and not bar._marker.running
bar._resume()
bar['actions']['0']()
assert bar._closed
session = MagicMock()
state['state'] = 'idle'
assert scope['open_bar'](session) == 0
session.openWithCallback.assert_not_called()
state['state'] = 'playing'
assert scope['open_bar'](session) == 1
session.openWithCallback.assert_called_once()
assert session.openWithCallback.call_args.args[1] is Bar
print('PASS centered overlay/2px at HD-FHD-4K, original theme asset, picon left, measured delay, batched controls, stale-target guard, hidden timers, 0 toggle and idle fallback')

# A commentary channel actually receives the guide and start/end times.
state['state'] = 'playing'
store.is_radio_stream.return_value = False
guide.view.return_value = (None, ('Live match guide', 1000, 4600))
bar = Bar(NS())
bar._layout_ready()
assert bar['guide'].text == 'Live match guide' and bar['time'].text
assert bar['name'].text == 'Audio' and bar._marker.running
bar._cleanup()
print('PASS explicit native layers, sized antialiased circles/marker, name/guide/control content')

# Use the receiver's native summary stack, identical to the main plugin screen.
main_tree = ast.parse((root / 'screen.py').read_text())
def summary_method(tree, classname):
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == classname)
    return next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'createSummary')
assert ast.dump(summary_method(tree, 'PlaybackBar')) == ast.dump(summary_method(main_tree, 'UltraAudioScreen'))
print('PASS guide uses live red and front display reuses the main plugin summary')

# Reproduce the Test5 crash at the actual key-dispatch boundary, before any
# delay/controller work. A direct bar.adjust() test could never catch this.
legacy = NumberActionMap(['NumberActions'], {'6': lambda: None}, -2)
try:
    legacy.action('NumberActions', '6')
except TypeError:
    pass
else:
    raise AssertionError('Legacy numeric callback must reproduce the extra-argument crash')
state['audio_delay_supported'] = True
state['video'] = dict(state='running', current_s=7.0, target_s=10.0)
controller.set_audio_delay.reset_mock()
controller.set_video_delay.reset_mock()
bar = Bar(NS())
bar._layout_ready()
assert type(bar['actions']) is ActionMap
for key, kind, expected in [('6','audio',500), ('4','audio',0), ('3','picture',11.0), ('1','picture',9.0)]:
    assert bar['actions'].action('NumberActions', key) == 1
    assert bar._pending[kind] == expected
    bar.apply(kind)
assert controller.set_audio_delay.call_args_list[0].args == (500,'station',7)
assert controller.set_audio_delay.call_args_list[1].args == (0,'station',7)
assert controller.set_video_delay.call_count == 2
bar['actions'].action('NumberActions', '0')
assert bar._closed
bar = Bar(NS())
bar._layout_ready()
bar['actions'].action('OkCancelActions', 'cancel')
assert bar._closed
print('PASS reproduced legacy numeric TypeError; actual 1/3/4/6/0/EXIT dispatch works')

# Color keys use the existing exact reset entry points, cancel pending same-kind
# steps and cannot revive them on a late timer callback.
controller.set_audio_delay.reset_mock()
controller.set_video_delay.reset_mock()
controller.reset_picture.reset_mock()
bar = Bar(NS())
bar._layout_ready()
bar['actions'].action('NumberActions', '3')
bar['actions'].action('NumberActions', '6')
bar['actions'].action('ColorActions', 'yellow')
controller.reset_picture.assert_called_once_with('station', 7)
assert bar._pending['picture'] is None and not bar._picture_timer.running
assert bar._pending['audio'] == 500
bar.apply('picture')
controller.set_video_delay.assert_not_called()
bar['actions'].action('ColorActions', 'blue')
controller.set_audio_delay.assert_called_once_with(0, 'station', 7)
assert bar._pending['audio'] is None and not bar._audio_timer.running
bar.apply('audio')
assert controller.set_audio_delay.call_count == 1
state['audio_delay_supported'] = False
bar['actions'].action('ColorActions', 'blue')
assert controller.set_audio_delay.call_count == 1
state['audio_delay_supported'] = True
state['tv_service'] = 'changed-service'
bar['actions'].action('ColorActions', 'yellow')
assert controller.reset_picture.call_count == 1
state['tv_service'] = 'tv'
bar._cleanup()
xml = ET.fromstring(scope['build_skin'](1920, 1080, theme))
for color, caption in [('yellow','picture_caption'),('blue','audio_caption')]:
    dash = next(node for node in xml if ('key_' + color + '_') in node.get('pixmap',''))
    label = next(node for node in xml if node.get('name') == caption)
    dx,dy = map(int,dash.get('position').split(','));dw,dh = map(int,dash.get('size').split(','))
    lx,ly = map(int,label.get('position').split(','));lw,lh = map(int,label.get('size').split(','))
    assert dx + dw/2 == lx + lw/2
    assert ly + lh <= dy and dy + dh <= 119
print('PASS original dashes centered below captions; color reset, pending cancellation and stale/unsupported guards')

# Green matches the main screen toggle and quiet-time guard; paused picture
# stepping starts from the measured paused position, exactly like key_pic.
controller.toggle_pause.reset_mock()
bar = Bar(NS())
bar._layout_ready()
with patch.object(time, 'time', return_value=100):
    bar['actions'].action('ColorActions','green')
    bar['actions'].action('ColorActions','green')
assert controller.toggle_pause.call_count == 1
with patch.object(time, 'time', return_value=101):
    bar['actions'].action('ColorActions','green')
assert controller.toggle_pause.call_count == 2
state['video']['state']='paused'
bar.refresh()
assert bar['freeze_caption'].text == 'Resume'
bar['actions'].action('NumberActions','3')
assert bar._pending['picture'] == 8.0
bar._cleanup()
state['video']['state']='running'
xml=ET.fromstring(scope['build_skin'](1920,1080,theme))
green=next(node for node in xml if 'key_green_' in node.get('pixmap',''))
freeze=next(node for node in xml if node.get('name')=='freeze_caption')
marker=next(node for node in xml if node.get('name')=='marker')
assert green.get('position') == '221,115'
assert freeze.get('position').split(',')[1] == '98'
assert int(marker.get('position').split(',')[1]) >= 119
bar=Bar(NS());bar._layout_ready();bar['actions'].action('ColorActions','red')
controller.stop.assert_called_once_with()
assert bar._closed
print('PASS green freeze/resume + held-key guard, paused picture stepping and red stop')
