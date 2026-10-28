import os,sys,tempfile,subprocess,time,concurrent.futures,types
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(os.environ['UA_PLUGIN_ROOT']).parent.resolve()))
os.environ['ULTRAAUDIO_LOG']=str(Path(os.environ['ULTRAAUDIO_DATA']) / 'audio-test.log')
from UltraAudio import engine,updater
sink='''import sys,time
with open(sys.argv[1],"wb",buffering=0) as f:
 while True:
  b=sys.stdin.buffer.read(9600)
  if not b:break
  f.write(b)
  time.sleep(len(b)/192000.)
'''
def case(seconds,delay=0,live=False):
 with tempfile.TemporaryDirectory() as tmp:
  p=Path(tmp);mp3=p/'tone.mp3';out=p/'out.pcm'
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration='+str(seconds),'-c:a','libmp3lame',str(mp3)],check=True)
  cmd=['ffmpeg','-v','error']+(['-re'] if live else [])+['-i',str(mp3),'-ar','48000','-ac','2','-f','s16le','-']
  expected=subprocess.check_output([x for x in cmd if x!='-re'])
  procs=engine._spawn_relay(cmd,[sys.executable,'-c',sink,str(out)],[],lambda:delay)
  started=time.monotonic();eof_draining=False
  try:
   while engine.relay_alive(procs,time.monotonic(),500):
    state=procs[0].relay_state;now=time.monotonic()
    if procs[0].poll() is not None and procs[-1].poll() is None:eof_draining=True
    assert not engine.relay_output_stalled(state,now,500),'writer stalled'
    assert not (not state.get('input_backpressure') and not state.get('input_eof') and now-state.get('last_read_t',started)>12),'false reconnect'
    assert now-started<seconds+delay/1000.+10,'drain timeout'
    time.sleep(.05)
   assert procs[0].wait(timeout=2)==0
   assert procs[-1].wait(timeout=2)==0
   got=out.read_bytes()
   if delay:
    assert got.endswith(expected),'recording tail or frames missing'
    prefix=got[:-len(expected)];assert not prefix.strip(b'\0'),'unexpected leading sound'
    assert len(prefix)>192000*(delay/1000.-1),'initial delay cancelled by EOF'
   else:assert got==expected,(len(got),len(expected))
   assert eof_draining,'did not exercise decoder EOF while writer active'
   print('PASS',{'seconds':seconds,'delay_ms':delay,'live':live,'complete_pcm_bytes':len(expected),'elapsed':round(time.monotonic()-started,2)},flush=True)
  finally:engine._kill(procs)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
 fs=[ex.submit(case,6),ex.submit(case,3,15000),ex.submit(case,25)]
 if os.environ.get('UA_TEST_MAX_DELAY') == '1':
  fs.append(ex.submit(case,2,60000))
 for f in fs:f.result()
case(3,live=True)
# Supervision edge cases with deterministic clocks.
class Proc:
 def __init__(self,rc=None):self.rc=rc
 def poll(self):return self.rc
dec,out=Proc(0),Proc();dec.relay_state={'relay_done_t':10}
assert engine.relay_alive([dec,out],14.9,500)
assert not engine.relay_alive([dec,out],15,500)
dec.relay_state={'writer_broke':True};assert not engine.relay_alive([dec,out],1)
out.rc=1;assert not engine.relay_alive([dec,out],1)
assert engine.relay_output_stalled({'write_started_t':1},7)
assert updater._is_update('1.0.11-test1','1.0.12')
assert updater._is_update('1.0.10','1.0.12')
print('PASS bounded writer drain, writer failure, stalled-output watchdog, upgrades from test1 and 1.0.10',flush=True)
# Manual Stop must remain prompt even with EOF buffered during a long delay.
with tempfile.TemporaryDirectory() as tmp:
 f=Path(tmp)/'pcm';cmd=[sys.executable,'-c','import sys;sys.stdout.buffer.write(bytes(192000*2));sys.stdout.flush()']
 ps=engine._spawn_relay(cmd,[sys.executable,'-c',sink,str(f)],[],lambda:30000)
 time.sleep(.4);start=time.monotonic();engine._kill(ps)
 deadline=time.monotonic()+2
 while 'relay_done_t' not in ps[0].relay_state and time.monotonic()<deadline:time.sleep(.02)
 assert 'relay_done_t' in ps[0].relay_state,'relay thread hung after Stop'
 print('PASS Stop during delayed EOF drain:',round(time.monotonic()-start,2),'seconds',flush=True)
