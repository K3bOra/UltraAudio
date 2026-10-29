"""Regression checks for bilingual details and the clipped two-row ticker."""
import ast,importlib,os,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(os.environ['UA_PLUGIN_ROOT']).resolve();sys.path.insert(0,str(ROOT.parent));sys.dont_write_bytecode=True
f=importlib.import_module('UltraAudio.livefootball')
NOW=1793275200
EVENT=('Sevilla vs Osasuna',NOW-3600,NOW+3600)
def match():
 return {'id':'match123','teams':('home123','away123'),'names':({'sevilla'},{'osasuna'}),'competition':'League','kickoff':NOW-3600,'goals':(3,0),'clock':"70'",'minute':70,'lang_data':{'en':{'home_name':'Sevilla','away_name':'Osasuna'},'ar':{'home_name':'إشبيلية','away_name':'أوساسونا'}}}
class Details(unittest.TestCase):
 def test_half_time_orientation(self):
  for code,expected in [('en',(1,0)),('ar',(0,1))]:self.assertEqual(f._parse_match_html('<div>(HT 1 - 0)</div><div>Overview</div>',match(),code)['ht_goals'],expected)
 def test_cancelled_commentary_does_not_create_scorer(self):
  m=match();m['goals']=(0,0)
  d=f._parse_match_html("<div>28'</div><div>Goal! Sevilla 1, Osasuna 0. Player (Sevilla) header.</div><div>VAR Decision: No Goal Sevilla.</div>",m,'en')
  self.assertEqual(d['scorers'],('',''))
 def test_all_scorers_retained_and_minutes_grouped(self):
  html=''.join("<div>%d'</div><div>Goal! Sevilla 3, Osasuna 0. %s (Sevilla) header.</div>"%(i,n) for i,n in [(30,'C'),(20,'B'),(10,'A')])
  self.assertEqual(len(f._parse_match_html(html,match(),'en')['scorers'][0].splitlines()),3)
  m=match();m['goals']=(2,0)
  html="<div>20'</div><div>Goal! Sevilla 2, Osasuna 0. Player (Sevilla) header.</div><div>10'</div><div>Goal! Sevilla 1, Osasuna 0. Player (Sevilla) header.</div>"
  s=f._parse_match_html(html,m,'en')['scorers'][0];self.assertEqual(len(s.splitlines()),1);self.assertIn("10'",s);self.assertIn("20'",s)
 def test_language_mapping_and_fresh_half_time(self):
  c=f.Scores();m=match();m['ht_goals']=(2,0);c._matches=[m];c._updated=999
  c._details[m['id']]={'updated':999,'goals':(3,0),'ht_goals':(0,1),'cards':((2,1),(1,0)),'lang_details':{'en':{'scorers':('Home','')},'ar':{'scorers':('مضيف','')}}}
  with tempfile.TemporaryDirectory() as directory:
   paths=[str(Path(directory)/x) for x in ('home','away')]
   for p in paths:Path(p).write_bytes(b'fixture')
   c._logos=dict(zip(m['teams'],paths))
   for code in ('en','ar'):
    with patch.object(f.time,'time',return_value=NOW),patch.object(f,'monotonic',return_value=1000),patch.object(f,'interface_language',return_value=code):
     r=c.view(EVENT);e=r[4]
     if code=='en':self.assertEqual(r[3],tuple(paths));self.assertEqual(e['ht_text'],'(HT 2 - 0)');self.assertEqual(e['left_yc'],2)
     else:self.assertEqual(r[3],tuple(reversed(paths)));self.assertEqual(e['ht_text'],'(ش1 0 - 2)');self.assertEqual(e['right_yc'],2)
   c._details[m['id']]['updated']=1
   with patch.object(f.time,'time',return_value=NOW),patch.object(f,'monotonic',return_value=1000):self.assertEqual(c.view(EVENT)[4]['left_scorers'],'')
 def test_failed_logo_backoff(self):
  c=f.Scores();c._updated=999;c._last_attempt=990;c._matches=[match()];c._logo_attempts={('home123','away123'):990}
  with patch.object(f.time,'time',return_value=NOW),patch.object(f,'monotonic',return_value=1000),patch.object(f,'start_thread') as thread:c.ensure(EVENT);thread.assert_not_called()
class Ticker(unittest.TestCase):
 def test_native_tick_wrap_pause_and_hidden_stop(self):
  tree=ast.parse((ROOT/'scorerticker.py').read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef));tick=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='tick')
  ns={'monotonic':lambda:100,'ePoint':lambda x,y:(x,y)};exec(compile(ast.Module(body=[tick],type_ignores=[]),'ticker','exec'),ns)
  obj=types.SimpleNamespace(active=True,body=types.SimpleNamespace(move=lambda point:positions.append(point)),timer=types.SimpleNamespace(stop=lambda:stops.append(True)),pause_until=0,offset=53,count=3,line_h=18)
  positions=[];stops=[];ns['tick'](obj);self.assertEqual(obj.offset,0);self.assertEqual(positions[-1],(0,0));self.assertEqual(obj.pause_until,102)
  ns['tick'](obj);self.assertEqual(len(positions),1)
  obj.active=False;ns['tick'](obj);self.assertTrue(stops)
 def test_two_rows_only_and_column_gaps(self):
  # Actual skin generated with Enigma imports stubbed; verifies both resolutions.
  mods={n:types.ModuleType(n) for n in ['Components','Components.Label','Components.Pixmap','Tools','Tools.LoadPixmap','enigma','UltraAudio.scorerticker']}
  mods['Components.Label'].Label=object;mods['Components.Pixmap'].Pixmap=object;mods['Tools.LoadPixmap'].LoadPixmap=lambda p:None;mods['enigma'].ePoint=lambda x,y:(x,y);mods['UltraAudio.scorerticker'].ScorerTicker=object
  with patch.dict(sys.modules,mods):card=importlib.import_module('UltraAudio.footballcard')
  import xml.etree.ElementTree as ET
  for k in (1.,2./3):
   with patch.object(card.themes,'pic',return_value='/panel.png'),patch.object(card.themes,'face',return_value='Regular'):
    root=ET.fromstring('<screen>'+card.skin_parts(k,{})+'</screen>');widgets={w.get('name'):w for w in root}
    def bounds(n):w=widgets[n];x,y=map(int,w.get('position').split(','));a,b=map(int,w.get('size').split(','));return x,y,x+a,y+b
    l=bounds('football_left_scorers');r=bounds('football_right_scorers');c=bounds('football_comp');p=bounds('football_panel')
    self.assertLess(l[2],c[0]);self.assertLess(c[2],r[0]);self.assertLessEqual(l[3],p[3]);self.assertLessEqual(r[3],p[3]);self.assertEqual(l[3]-l[1],round(36*k))
if __name__=='__main__':unittest.main()
