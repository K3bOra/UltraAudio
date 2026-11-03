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
 def _sample(self, state='in', seen=1000):
  m=match();m.update(state=state,_observed_at=seen);return m
 def _view(self,m,event=EVENT,language='en'):
  c=f.Scores();c._matches=[m]
  with patch.object(f,'_wall_now',return_value=NOW),patch.object(f,'monotonic',return_value=1000),patch.object(f,'interface_language',return_value=language),patch.object(c,'_get_cached_logo',side_effect=lambda t:'/logo/'+t),patch.object(c,'_spawn_logo_downloads',side_effect=AssertionError('No network')):
   return c.is_live(event),c.view(event)
 def test_live_freshness_and_provider_states(self):
  for state,seen,expected in [('in',1000,True),('in',1,False),('pre',1000,False),('post',1000,False)]:
   live,result=self._view(self._sample(state,seen));self.assertEqual(live,expected);self.assertEqual(result is not None,expected)
 def test_replays_and_outside_program_window_are_hidden(self):
  for event in [('Sevilla vs Osasuna - Replay',NOW-3600,NOW+3600),('ملخص Sevilla vs Osasuna',NOW-3600,NOW+3600),('Sevilla vs Osasuna',NOW+1,NOW+3600),('Sevilla vs Osasuna',NOW-3600,NOW)]:
   self.assertEqual(self._view(self._sample(),event),(False,None))
 def test_bilingual_names_crests_and_score_orientation(self):
  for code,expected,score in [('en',('Sevilla','Osasuna'),'3 - 0'),('ar',('أوساسونا','إشبيلية'),'0 - 3')]:
   live,result=self._view(self._sample(),language=code);self.assertTrue(live)
   self.assertEqual((result[4]['left_name'],result[4]['right_name']),expected);self.assertEqual(result[1],score)
   self.assertEqual(result[3],('/logo/home123','/logo/away123') if code=='en' else ('/logo/away123','/logo/home123'))
class MatchCard(unittest.TestCase):
 def test_fixed_card_geometry_all_resolutions(self):
  import xml.etree.ElementTree as ET
  from types import SimpleNamespace as NS
  scope=dict(os=os,store=NS(ASSETS=str(ROOT/'assets')),themes=NS(face=lambda n:'Regular'),ui_pixmap_path=lambda p,w,h:p,skin_scale_attr=lambda:' scale="1"')
  tree=ast.parse((ROOT/'footballcard.py').read_text());tree.body=[n for n in tree.body if not isinstance(n,(ast.Import,ast.ImportFrom))]
  exec(compile(tree,'footballcard','exec'),scope)
  for k in (2./3,1.,4./3,2.):
   xml=ET.fromstring('<screen>'+scope['skin_parts'](k,{})+'</screen>');widgets={n.get('name'):n for n in xml}
   p=widgets['football_panel'];x,y=map(int,p.get('position').split(','));w,h=map(int,p.get('size').split(','))
   self.assertLessEqual(abs(x+w/2.-1260*k),1);self.assertEqual(y,round(74*k))
   self.assertEqual(widgets['football_live'].get('foregroundColor'),'#FF0000')
   for n in xml:
    nx,ny=map(int,n.get('position').split(','));nw,nh=map(int,n.get('size').split(','))
    self.assertGreaterEqual(nx,x);self.assertGreaterEqual(ny,y);self.assertLessEqual(nx+nw,x+w+1);self.assertLessEqual(ny+nh,y+h+1)
 def test_live_only_visibility_gate(self):
  tree=ast.parse((ROOT/'footballcard.py').read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef));method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_refresh_card')
  scope=dict(monotonic=lambda:100,lang=lambda:'en',SCORES=types.SimpleNamespace(_rev=1,is_live=lambda e:bool(e and e[0]=='live'),is_candidate=lambda e:False,view=lambda e:('id','1 - 0','46',('',''))),log=lambda s:None)
  exec(compile(ast.Module(body=[method],type_ignores=[]),'card','exec'),scope)
  for event in (None,('recorded',0,100),('live',0,100)):
   calls=[];screen=types.SimpleNamespace(_index=lambda:0,entries=[dict(event=event,payload=('stream','x'))],cwd='',_shown=None)
   card=types.SimpleNamespace(screen=screen,_badges=None,_last_ensure_key=None,_last_ensure_at=0,_hide_widgets=lambda:calls.append('hide'),_render=lambda *a:calls.append('show'))
   scope['_refresh_card'](card);self.assertEqual(calls,['show' if event and event[0]=='live' else 'hide'])
if __name__=='__main__':unittest.main()
