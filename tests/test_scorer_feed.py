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
 def test_real_fixture_and_repeated_player(self):
  d=s.parse_scorers(FIXTURE,match(),f.team_name)
  self.assertEqual(d['scorers_neutral'],("J. Garner  34'\nH. Hackney  45'",''))
  self.assertEqual(d['cards'],((1,0),(0,0)))
  data=copy.deepcopy(FIXTURE);game(data)['details'][1]['athletesInvolved'][0]['shortName']='J. Garner'
  self.assertEqual(s.parse_scorers(data,match(),f.team_name)['scorers_neutral'][0],"J. Garner  34', 45'")
 def test_identity_score_and_completeness_guards(self):
  for change in ('wrong-team','wrong-side','wrong-time','wrong-score','partial','shootout','own-goal','cancelled','ambiguous'):
   data=copy.deepcopy(FIXTURE);g=game(data)
   if change=='wrong-team':g['competitors'][0]['team']={'name':'Liverpool'}
   if change=='wrong-side':g['competitors'][0]['homeAway']='away'
   if change=='wrong-time':g['date']='2026-10-28T19:45Z'
   if change=='wrong-score':g['competitors'][0]['score']='3'
   if change=='partial':g['details'].pop(0)
   if change=='shootout':g['details'][0]['shootout']=True
   if change=='own-goal':g['details'][0]['ownGoal']=True
   if change=='cancelled':g['details'][0]['cancelled']=True
   if change=='ambiguous':data['events'].append(copy.deepcopy(data['events'][0]))
   self.assertIsNone(s.parse_scorers(data,match(),f.team_name),change)
 def test_cache_failure_backoff_and_expiry(self):
  calls=[]
  def read(url,limit):calls.append(url);return json.dumps(FIXTURE).encode()
  feed=s.ScoreboardScorers(read)
  with patch.object(s,'monotonic',return_value=100):
   self.assertIsNotNone(feed.get(match(),f.team_name));self.assertIsNotNone(feed.get(match(),f.team_name))
  self.assertEqual(len(calls),1)
  self.assertEqual(s.parse_scorers(s.compact_snapshot(FIXTURE),match(),f.team_name)['scorers_neutral'],("J. Garner  34'\nH. Hackney  45'",''))
  def failed(url,limit):calls.append(url);raise IOError('offline')
  feed.read=failed
  with patch.object(s,'monotonic',return_value=161):self.assertIsNotNone(feed.get(match(),f.team_name))
  with patch.object(s,'monotonic',return_value=222):self.assertIsNone(feed.get(match(),f.team_name))
  with patch.object(s,'monotonic',return_value=223):self.assertIsNone(feed.get(match(),f.team_name))
  self.assertEqual(len(calls),3)
 def test_worker_to_card_both_interface_directions(self):
  c=f.Scores();m=match();c._matches=[m];c._updated=999
  c._scorer_feed=s.ScoreboardScorers(lambda url,limit:json.dumps(FIXTURE).encode())
  with patch.object(s,'monotonic',return_value=1000),patch.object(f,'monotonic',return_value=1000):
   with patch.object(f,'_read',side_effect=AssertionError('No HTML requests needed')):c._fetch_details(m)
  with tempfile.TemporaryDirectory() as folder:
   paths=[str(Path(folder)/name) for name in ('home','away')]
   for p in paths:Path(p).write_bytes(b'logo')
   c._logos=dict(zip(m['teams'],paths))
   for language,key,other in [('en','left_scorers','right_scorers'),('ar','right_scorers','left_scorers')]:
    with patch.object(f,'interface_language',return_value=language),patch.object(f.time,'time',return_value=KICKOFF+3600),patch.object(f,'monotonic',return_value=1000):
     extra=c.view(('Everton vs Newcastle United',KICKOFF-900,KICKOFF+10000))[4]
     self.assertIn('J. Garner',extra[key]);self.assertIn('H. Hackney',extra[key]);self.assertEqual(extra[other],'')
  # A new score immediately invalidates old scorer details.
  m['goals']=(3,0)
  self.assertNotEqual(c._details[m['id']]['goals'],m['goals'])
if __name__=='__main__':unittest.main()
