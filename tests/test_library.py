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
