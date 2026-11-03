# -*- coding: utf-8 -*-
"""Import real plugin/UI and exercise opening, layout, navigation and closing.

Only receiver APIs and the playback controller are replaced. Run with Python
2.7 for DreamOS too; no receiver libraries or network access are required.
"""
from __future__ import print_function
import ast
import os
import shutil
import sys
import tempfile
import types
import xml.etree.ElementTree as ET

root = os.path.abspath(os.environ['UA_PLUGIN_ROOT'])
sys.path.insert(0, os.path.dirname(root))
sys.dont_write_bytecode = True
scratch = tempfile.mkdtemp(prefix='ultraaudio_gui_')
os.environ['ULTRAAUDIO_DATA'] = scratch
dream = os.environ.get('UA_GUI_API', 'dream' if 'deb-source' in root else 'modern') == 'dream'
timer_mode = os.environ.get('UA_TIMER_API', 'signal' if dream else 'callback')

class NS(object):
    def __init__(self, **kwargs): self.__dict__.update(kwargs)

class Signal(object):
    def __init__(self): self.connections = []
    def connect(self, fn):
        connection = NS(callback=fn)
        self.connections.append(connection)
        return connection

class Timer(object):
    def __init__(self):
        self.running = False
        if timer_mode == 'signal': self.timeout = Signal()
        else: self.callback = []
    def start(self, ms, once=False): self.running = True
    def stop(self): self.running = False

class Instance(object):
    def __init__(self): self.selection = 1; self.pixmap = None
    def setPixmap(self, pixmap): self.pixmap = pixmap
    def setPixmapFromFile(self, path): self.pixmap = path
    def setSelectionEnable(self, value): self.selection = value
    def getTopIndex(self): return 0
    def move(self, *args): pass
    def resize(self, *args): pass
    def setFont(self, *args): pass
    def setZPosition(self, value): pass
    def setForegroundColor(self, *args): pass
    def calculateSize(self): return NS(width=lambda: 100, height=lambda: 24)

class Widget(object):
    def __init__(self, text=''):
        self.text, self.visible, self.instance = text, True, Instance()
    def setText(self, text): self.text = text
    def setValue(self, value): self.value = value
    def setRange(self, value): self.range = value
    def show(self): self.visible = True
    def hide(self): self.visible = False

class Content(object):
    TYPE_PIXMAP_ALPHABLEND = 2
    def setFont(self, *args): pass
    def setItemHeight(self, height): self.height = height
    def invalidateEntry(self, i): pass

class MenuList(Widget):
    def __init__(self, values, **kwargs):
        Widget.__init__(self); self.list = values; self.l = Content()
        self.onSelectionChanged = []; self.index = 0
    def setList(self, values): self.list = values
    def getSelectionIndex(self): return self.index
    def moveToIndex(self, i):
        self.index = i
        for fn in self.onSelectionChanged: fn()
    def up(self): self.moveToIndex(max(0, self.index - 1))
    def down(self): self.moveToIndex(min(len(self.list) - 1, self.index + 1))

class ActionMap(dict):
    def __init__(self, contexts, actions, priority): dict.__init__(self, actions)

class Screen(dict):
    def __init__(self, session):
        dict.__init__(self); self.session = session; self.execing = True
        for name in ('onLayoutFinish', 'onExecBegin', 'onExecEnd', 'onHide', 'onClose'):
            setattr(self, name, [])
        if not dream: self.onShow = []
    def setTitle(self, title): self.title = title
    def close(self, *result):
        for fn in self.onExecEnd + self.onHide + self.onClose: fn()
        self.execing = False; self.session.closed = True

class Descriptor(object):
    WHERE_SESSIONSTART=1; WHERE_AUTOSTART=2; WHERE_PLUGINMENU=3; WHERE_EXTENSIONSMENU=4
    def __init__(self, **kwargs): self.__dict__.update(kwargs)

def module(name, **kwargs):
    result = types.ModuleType(name); result.__dict__.update(kwargs)
    sys.modules[name] = result
    return result

for name in ('Plugins', 'Screens', 'Components', 'Tools'): module(name)
module('Plugins.Plugin', PluginDescriptor=Descriptor)
module('Screens.Screen', Screen=Screen)
module('Components.ActionMap', ActionMap=ActionMap)
module('Components.Label', Label=Widget)
module('Components.MenuList', MenuList=MenuList)
module('Components.Pixmap', Pixmap=Widget)
module('Components.ProgressBar', ProgressBar=Widget)
module('Components.ScrollLabel', ScrollLabel=Widget)
module('Components.GUIComponent', GUIComponent=Widget)
module('Tools.LoadPixmap', LoadPixmap=lambda *a, **k: object())
def old_pixmap(pos, size, png): return ('pixmap', pos, size, png)
def new_pixmap(pos, size, png, flags=0): return ('pixmap', pos, size, png, flags)
module('Components.MultiContent', MultiContentEntryPixmapAlphaBlend=old_pixmap if dream else new_pixmap,
       MultiContentEntryText=lambda **kwargs: ('text', kwargs))
enigma = module('enigma')
for filename in os.listdir(root):
    if not filename.endswith('.py'): continue
    with open(os.path.join(root, filename), 'rb') as source:
        tree = ast.parse(source.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'enigma':
            for name in node.names: setattr(enigma, name.name, 0 if name.name.startswith(('RT_', 'BT_')) else NS)
enigma.eTimer = Timer
enigma.eListboxPythonMultiContent = Content
enigma.gFont = lambda face, size: (face, size)
enigma.ePoint = lambda x, y: (x, y)
enigma.eSize = lambda w, h: (w, h)
enigma.addFont = lambda *args: None
width = [1920]
enigma.getDesktop = lambda n: NS(size=lambda: NS(width=lambda: width[0], height=lambda: width[0]*9//16))
module('skin', parseColor=lambda color: color)

from UltraAudio import compat
# Keep all provider/network workers offline, including the real live-match singleton.
compat.start_thread = lambda *args, **kwargs: None
compat._skin_scale_supported = not dream
from UltraAudio import plugin, screen, ctl, store, guide, themes
assert len(plugin.Plugins()) == 4
if os.path.isfile(os.path.join(root, "receivertime.py")):
    from UltraAudio import receivertime
    receivertime.start = lambda session: None
plugin._local_ip = lambda: '127.0.0.1'
status = dict(state='idle', stream_id=None, stream_name='', message='', audio_delay_ms=0,
              audio_delay_supported=True, tv_channel={},
              video=dict(state='off', current_s=0, target_s=0))
engine = NS(status=lambda: dict(status), state='idle', stream=None)
ctl.get = lambda: NS(status=lambda: dict(status), engine=engine)
guide.ensure = lambda *args, **kwargs: None
guide.view = lambda *args, **kwargs: ('channel', (u'مباراة عربية', 10, 10000000000), False)
screen.LIVE_SCORES.is_live = lambda event: bool(event)
folder = store.add_folder(u'مجلد عربي')
stream = store.add_stream(dict(name=u'قناة عربية', url='https://example.invalid/test.mp3', tag=u'عربي'), folder['id'])

class Session(object):
    def __init__(self): self.opened = None; self.closed = False
    def open(self, *args, **kwargs): raise AssertionError('Unexpected repair/fallback screen')
    def openWithCallback(self, callback, cls, *args):
        self.opened = cls(self, *args)
        for fn in self.opened.onLayoutFinish: fn()
        return self.opened

try:
    for pixels in (1280, 1920, 2560, 3840):
        width[0] = pixels
        for theme in store.THEMES:
            for language in ('en', 'ar'):
                store.set_settings(dict(theme=theme, language=language))
                skin = ET.fromstring(screen.build_skin(pixels/1920.0, themes.get()))
                if dream:
                    assert not any('scale' in n.attrib or 'itemHeight' in n.attrib for n in skin.iter())
                session = Session()
                plugin._ui_error = ''
                plugin.main(session)
                assert not plugin._ui_error, plugin._ui_error
                ui = session.opened
                assert isinstance(ui, screen.UltraAudioScreen)
                assert ui.timer.running and len(ui.entries) > 0
                ui.cwd = folder['id']; ui.fill(); ui.refresh()
                assert len(ui.entries) == 1 and ui['list'].list
                status.update(state='playing', stream_id=stream['id'], stream_name=u'قناة عربية')
                engine.state, engine.stream = 'playing', stream
                ui.refresh()
                ui._pic_pending = 1.5
                assert ui._delay_text(status, status['video'])[0]
                ui._pic_pending = None
                status.update(state='idle', stream_id=None)
                engine.state, engine.stream = 'idle', None
                ui.key_vert(1); ui.key_vert(-1)
                ui.menu.toggle(); ui.menu.toggle()
                ui.back(); ui.back()
                assert session.closed and not ui.timer.running
                assert not ui.audio_timer.running and not ui.pic_timer.running
    if dream:
        # A missing PNG/widget must leave native selection available.
        session = Session(); ui = screen.UltraAudioScreen(session)
        original = screen._bundled_pixmap
        screen._bundled_pixmap = lambda path: None
        ui._configure_cursor()
        assert not ui._custom_cursor and ui['list'].instance.selection == 1
        screen._bundled_pixmap = original
        ui.close()
    print('PASS real plugin.main -> constructor -> layout/fill/refresh -> navigation/menu -> EXIT; '
          '3 themes x 2 languages x HD/FHD/WQHD/4K; API=%s timer=%s Python=%s' %
          ('DreamOS' if dream else 'modern', timer_mode, sys.version.split()[0]))
finally:
    shutil.rmtree(scratch)
