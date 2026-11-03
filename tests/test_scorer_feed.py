"""Real public scoreboard fixture; no network used by offline tests."""
import copy,importlib,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(os.environ['UA_PLUGIN_ROOT']).resolve();sys.path.insert(0,str(ROOT.parent));sys.dont_write_bytecode=True
f=importlib.import_module('UltraAudio.livefootball')
s=importlib.import_module('UltraAudio.scorerfeed')
FIXTURE=json.loads((Path(__file__).parent/'fixtures/everton_newcastle_20261029_espn.json').read_text())
KICKOFF=1793303100

def match():
 return {'id':'45lqtyvrk8dkh4j3pa69jiiok','teams':('home123','away123'),'names':({'everton'},{'newcastle','newcastle united'}),'kickoff':KICKOFF,'goals':(2,0),'clock':"66'",'minute':66,'ht_goals':(2,0),'competition':'Carabao Cup','lang_data':{'en':{'home_name':'Everton','away_name':'Newcastle','competition':'Carabao Cup','stage':'Round of 16'},'ar':{'home_name':'إيفرتون','away_name':'نيوكاسل','competition':'كأس الرابطة','stage':'دور الـ 16'}}}

def game(data):return data['events'][0]['competitions'][0]
class Feed(unittest.TestCase):
 def test_real_fixture_and_compact_snapshot(self):
  with patch.object(s,'monotonic',return_value=1000):
   compact=s.compact_snapshot(FIXTURE);matches=s.extract_live_matches(compact,f.team_name,f.team_aliases)
  self.assertEqual(len(matches),1);m=matches[0]
  self.assertEqual(m['goals'],(2,0));self.assertEqual(m['state'],'in');self.assertEqual(m['clock'],"66'")
  self.assertEqual(m['lang_data']['en']['home_name'],'Everton')
  self.assertNotIn('details',compact['events'][0]['competitions'][0])
 def test_identity_state_and_freshness_guards(self):
  for change in ('missing-team','duplicate-side','wrong-time','invalid-state','stale'):
   data=copy.deepcopy(FIXTURE);g=game(data)
   if change=='missing-team':g['competitors'].pop()
   if change=='duplicate-side':g['competitors'][0]['homeAway']='away'
   if change=='wrong-time':g['date']='bad';data['events'][0]['date']='bad'
   if change=='invalid-state':g['status']['type']['state']='cancelled'
   if change=='stale':g['_observed_at']=1
   with patch.object(s,'monotonic',return_value=1000):self.assertEqual(s.extract_live_matches(data,f.team_name),[],change)
 def test_cache_and_failure_backoff(self):
  calls=[]
  def read(url,limit):calls.append(url);return json.dumps(FIXTURE).encode()
  feed=s.ScoreboardScorers(read)
  with patch.object(s,'monotonic',return_value=100):
   self.assertIsNotNone(feed.refresh_day('20261029'));self.assertIsNotNone(feed.refresh_day('20261029'))
  self.assertEqual(len(calls),1)
  def failed(url,limit):calls.append(url);raise IOError('offline')
  feed.read=failed
  with patch.object(s,'monotonic',return_value=161):self.assertIsNotNone(feed.refresh_day('20261029'))
  count=len(calls)
  with patch.object(s,'monotonic',return_value=162):self.assertIsNotNone(feed.refresh_day('20261029'))
  self.assertEqual(len(calls),count)
  with patch.object(s,'monotonic',return_value=1000):self.assertEqual(s.extract_live_matches(feed.cache['20261029'][1],f.team_name),[])
 def test_current_card_uses_live_result_in_both_directions(self):
  for language,score,left in [('en','2 - 0','Everton'),('ar','0 - 2','نيوكاسل')]:
   c=f.Scores();m=match();m.update(state='in',_observed_at=1000);c._matches=[m]
   with patch.object(f,'interface_language',return_value=language),patch.object(f,'_wall_now',return_value=KICKOFF+3600),patch.object(f,'monotonic',return_value=1000),patch.object(c,'_get_cached_logo',side_effect=lambda t:'/logo/'+t),patch.object(c,'_spawn_logo_downloads',side_effect=AssertionError('No network')):
    result=c.view(('Everton vs Newcastle United',KICKOFF-900,KICKOFF+10000))
   self.assertEqual(result[1],score);self.assertEqual(result[4]['left_name'],left)
if __name__=='__main__':unittest.main()
