import sys,os,tempfile,importlib,ast,json,re,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
r=Path(os.environ['UA_PLUGIN_ROOT']).resolve();sys.path.insert(0,str(r.parent));sys.dont_write_bytecode=True
with tempfile.TemporaryDirectory() as tmp:
 os.environ['ULTRAAUDIO_DATA']=tmp
 from UltraAudio import store,presets,updater,importer,iconchoices,shaarawi,sayedsaeed,webui
 for p in r.rglob('*.json'):json.loads(p.read_text())
 ET.parse(r/'keymap.xml')
 for k,file in webui._STATIC.items():assert (r/'web'/file).is_file(),file
 for data in iconchoices.catalog():
  if isinstance(data,dict) and data.get('key'):assert iconchoices.resolve(data['key']),data
 print('PASS XML, JSON packs, web static assets and icon catalog')
 funcs=[presets.install_foxfm,presets.install_radio,presets.install_quran_direct,presets.install_radio_expansion,presets.install_radio_link_repairs,presets.install_radio_107,presets.install_radio_complete,presets.install_sayed_saeed,presets.install_shaarawi]
 for f in funcs:f()
 first=store._load();ids=[x['id'] for x in first['folders']+first['streams']];assert len(ids)==len(set(ids))
 for f in funcs:f()
 second=store._load();assert len(first['streams'])==len(second['streams'])
 assert len(first['folders'])==len(second['folders'])
 print('PASS bundled libraries installed twice without duplicate IDs/stations:',len(second['streams']),'streams')
 entries=importer.parse_m3u('#EXTM3U\n#EXTINF:-1,Test\nhttps://example.com/a.mp3\n');assert entries
 backup=store.make_backup();store.validate_backup(backup)
 prior=Path(store.LIBRARY_FILE).read_bytes()
 try:store.restore_backup({'app':'Bad'})
 except ValueError:pass
 else:raise AssertionError('invalid backup accepted')
 assert Path(store.LIBRARY_FILE).read_bytes()==prior
 print('PASS M3U import and invalid-backup rejection without touching library')

# Exercise actual Guide.view: Arabic must not refer to comprehension e.
import types,threading
cls=next(n for n in ast.parse((r/'guide.py').read_text()).body if isinstance(n,ast.ClassDef) and n.name=='Guide')
method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='view')
ns={'stream_channel_key':lambda s:'bein1','to_text':str,'_provider':lambda *a:'bein','monotonic':lambda:100,'MAX_AGE':3600}
exec(compile(ast.Module(body=[method],type_ignores=[]),'guide.py','exec'),ns)
for arabic in ('عنوان عربي',''):
 obj=types.SimpleNamespace(_lock=threading.RLock(),_states={'bein':{'updated':100,'events':{'bein1':(('English title',arabic,900,1100,'description'),)},'busy':False}},_receiver={})
 for language in ('en','ar'):
  result=ns['view'](obj,{'name':'beIN SPORTS 1'},language,now=1000)
  assert result[1][0] == (arabic if language=='ar' and arabic else 'English title'),result
print('PASS Arabic and English guide titles, including missing Arabic fallback')

# Reproduce Python 2's missing functools.lru_cache on the real UI import.
if 'deb-source' in r.parts:
 import functools
 from UltraAudio import compat
 source=ast.parse((r/'screen.py').read_text())
 imports=[n for n in source.body if isinstance(n,ast.ImportFrom) and any(a.name=='lru_cache' for a in n.names)]
 assert imports,'screen cache import missing'
 original=functools.lru_cache
 try:
  del functools.lru_cache
  scope={'__package__':'UltraAudio'}
  exec(compile(ast.Module(body=imports,type_ignores=[]),'screen.py','exec'),scope)
  calls=[]
  @scope['lru_cache'](maxsize=2)
  def cached(value):
   calls.append(value);return value
  assert cached('a')=='a';cached('a');assert calls==['a']
  cached('b');cached('a');cached('c');cached('b');assert calls==['a','b','c','b'],calls
  cached.cache_clear();cached('b');assert calls[-2:]==['b','b']
  for file in r.glob('*.py'):
   for node in ast.walk(ast.parse(file.read_text())):
    assert not (isinstance(node,ast.ImportFrom) and node.module=='functools' and any(a.name=='lru_cache' for a in node.names)),file
 finally:
  functools.lru_cache=original
 print('PASS DreamOS actual UI cache import without functools.lru_cache, hits, eviction, clear')
