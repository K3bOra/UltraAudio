import ast,math,os,time,unittest
from pathlib import Path
from collections import deque
clock=[2.]
class Guard:
 def reset(self,*a,**kw):pass
p=Path(os.environ['UA_PLUGIN_ROOT']) / 'vdelay.py'
ns=dict(math=math,os=os,time=time,deque=deque,isfinite=math.isfinite,monotonic=lambda:clock[0],to_text=str,log=lambda s:None,T=lambda s,*a:s,DelayGuard=Guard)
tree=ast.parse(p.read_text(),feature_version=(3,5));exec(compile(ast.Module(body=[n for n in tree.body if not isinstance(n,(ast.Import,ast.ImportFrom))],type_ignores=[]),str(p),'exec'),ns)
class Seek:
 def __init__(self,ib):self.ib=ib;self.delay=10.;self.fixed_length=None;self.invalid=None
 def getLength(self):return (0,self.invalid if self.invalid is not None else int((self.fixed_length if self.fixed_length is not None else 100+clock[0])*90000))
 def getPlayPosition(self):return (0,int((self.ib.pause_pos if self.ib.pause_pos is not None else 100+clock[0]-self.delay)*90000))
class IB:
 SEEK_STATE_PLAY=(0,0,0,0);SEEK_STATE_PAUSE=(1,0,0,0)
 def __init__(self):self.seekstate=self.SEEK_STATE_PLAY;self.pause_pos=None;self.seek=Seek(self);self.calls=[]
 def getSeek(self):return self.seek
 def timeshiftEnabled(self):return True
 def pauseService(self):self.pause_pos=self.seek.getPlayPosition()[1]/90000.;self.seekstate=self.SEEK_STATE_PAUSE;self.calls.append('pause')
 def unPauseService(self):
  if self.pause_pos is not None:self.seek.delay=100+clock[0]-self.pause_pos
  self.pause_pos=None;self.seekstate=self.SEEK_STATE_PLAY;self.calls.append('resume')
 def doSeekRelative(self,pts):self.seek.delay-=pts/90000.;self.calls.append('seek')

def make():
 clock[0]=2.;v=ns['VideoDelay']();ib=IB();v._ib=ib;v._service='s';v._infobar=lambda:ib;v._service_key=lambda ib:'s';v.state='running';v.target=v.requested=v._actual_delay=10.;v._settle_until=0
 v._quiet=lambda ib:None;v._unquiet=lambda:None;v._ensure_timer=lambda:None
 return v,ib

def ticks(v,n=3):
 for _ in range(n):v._tick();clock[0]+=.25
class Tests(unittest.TestCase):
 def test_small_and_large_shifts(self):
  for value in (0,1,7,25,100):
   with self.subTest(value=value):
    v,ib=make();ib.seek.delay=value;ticks(v);self.assertEqual(v.target,value);self.assertEqual(v.info()['current_s'],value);self.assertEqual(v.requested,10);self.assertEqual(ib.calls,[])
 def test_shift_after_meter_calibration(self):
  v,ib=make();ticks(v);self.assertTrue(v._meter_ok);ib.seek.delay=1;ticks(v);self.assertEqual(v.target,1)
 def test_sequence_of_shifts(self):
  v,ib=make()
  for val in (7,1,25,0,10):ib.seek.delay=val;ticks(v);self.assertEqual(v.target,val)
 def test_duplicate_polling_is_not_confirmation(self):
  v,ib=make();ib.seek.delay=1
  for _ in range(20):v._tick()
  self.assertEqual(v.target,10)
 def test_transient_and_oscillating_samples(self):
  v,ib=make()
  for val in (1,10,7,8,7,8,7,8):ib.seek.delay=val;ticks(v,1)
  self.assertEqual(v.target,10)
 def test_invalid_readings(self):
  for inval in (float('nan'),float('inf'),-1):
   v,ib=make();ib.seek.invalid=inval;ticks(v,8);self.assertEqual(v.target,10)
 def test_no_backward_seek_from_one_bad_sample(self):
  v,ib=make();ticks(v);ib.seek.delay=1;v.start(10);self.assertEqual(v.target,10);self.assertEqual(v.state,'running');self.assertNotIn('seek',ib.calls)
 def test_stopped_index_does_not_create_false_drift(self):
  v,ib=make();ticks(v);ib.seek.fixed_length=100+clock[0];ticks(v,40);self.assertEqual(v.target,10)
 def test_restore_10_from_7(self):
  v,ib=make();ib.seek.delay=7;ticks(v);v.start(10);self.assertEqual(v.state,'filling');self.assertAlmostEqual(v._fill_until-clock[0],3)
  clock[0]=v._fill_until;v._tick();self.assertEqual(v.state,'running');self.assertAlmostEqual(ib.seek.delay,10)
 def test_restore_10_from_1(self):
  v,ib=make();ib.seek.delay=1;ticks(v);v.start(10);self.assertAlmostEqual(v._fill_until-clock[0],9)
 def test_reduce_from_25_to_10(self):
  v,ib=make();ib.seek.delay=25;ticks(v);v.start(10);self.assertEqual(ib.seek.delay,10);clock[0]+=.75;v._tick();self.assertIsNone(v._seek_check);self.assertEqual(v._actual_delay,10)
 def test_user_steps_from_actual_7(self):
  v,ib=make();ib.seek.delay=7;ticks(v);v.adjust(1);self.assertEqual(v.target,8);self.assertAlmostEqual(v._fill_until-clock[0],1)
 def test_settling_and_manual_seek_suppress_sync(self):
  for attr,value in (('_settle_until',100),('_manual_seek',True),('_seek_check',{'t':0})):
   v,ib=make();setattr(v,attr,value)
   for i in range(4):clock[0]=2+i*.25;v._sync_running_delay(ib,clock[0],1)
   self.assertEqual(v.target,10)
 def test_freeze_resume(self):
  v,ib=make();ticks(v);v.toggle_pause();self.assertEqual(v.state,'paused');clock[0]+=2;v.toggle_pause();self.assertEqual(v.state,'running');self.assertEqual(v.target,12)
 def test_channel_change_forgets_measurements(self):
  v,ib=make();ticks(v);v.on_service_changed();self.assertEqual(v.state,'off');self.assertIsNone(v._length_seen);self.assertIsNone(v._drift_cand)
if __name__=='__main__':unittest.main(verbosity=2)
