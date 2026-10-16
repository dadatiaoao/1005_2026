import sys,json
from pathlib import Path
root=Path('outputs/k230_vision')
sys.path.insert(0,str(root.resolve()))
from vision_session import VisionSession

def cmd(seq=1,**changes):
    c=dict(seq=seq,enabled=True,mode='MATERIAL',target_color=3,target_position=0,
           roi=[10,35,620,435],lease_ms=1000,pose_id='bench')
    c.update(changes)
    return c
color=dict(color=3,cx=120,cy=140,rect=(90,110,60,60),pixels=2000)
rings=[dict(position=i,track=i,cx=i*100,cy=240,score=.9,number_age_ms=20) for i in (1,2,3)]
tests=[]
s=VisionSession()
assert s.apply(cmd(),0)
r=s.result([color],rings,[],1)
assert r['targets']==[color] and r['target_position'] is None and r['mode_epoch']==1
assert s.apply(cmd(2,mode='RING'),100)
assert s.result([color],rings,[],101,warming=True)['targets']==[]
r=s.result([color],rings,[],102)
assert r['targets']==rings and r['target_color'] is None and r['mode_epoch']==2
assert s.apply(cmd(3,mode='RING',target_position=2),200)
r=s.result([color],rings,[],201)
assert [t['position'] for t in r['targets']]==[2]
assert all('color' not in t for t in r['targets'])
assert s.apply(cmd(4),300)
assert s.result([color],rings,[],301,warming=True)['targets']==[]
assert s.result([],rings,[],302)['targets']==[]
tests.append('mode_change_warmup_and_distinct_target_schemas')

assert not s.apply(cmd(3,mode='RING'),400)
assert s.mode=='MATERIAL' and s.control.accepted_ms==300
assert not s.apply(cmd(5),500)
assert s.epoch==4 and s.control.accepted_ms==500
assert s.result([color],rings,[],1500)['targets']==[]
assert s.apply(cmd(6),1501) # expired restart resets confirmation
assert s.epoch==5
tests.append('replay_heartbeat_and_expired_restart')

s.apply(cmd(7,mode='RING',target_position=2),1600)
assert s.result([],rings+[rings[1]],[],1601)['state']=='TARGET_AMBIGUOUS'
assert s.result([],[],[],1601,pending=True)['state']=='NUMBER_PENDING'
assert s.result([],[],[],1601)['state']=='TARGET_NOT_FOUND'
for reason in ('COMMAND_FILE_MISSING','INVALID_COMMAND'):
    s.invalidate(reason)
    r=s.result([color],rings,[],1602)
    assert r['state']==reason and r['targets']==[] and not r['observation_valid']
assert s.apply(cmd(8,enabled=False,mode='RING'),1700)
assert s.result([color],rings,[],1701)['state']=='STOPPED'
assert s.result([color],rings,[],1701)['targets']==[]
tests.append('duplicate_pending_loss_stop_and_fault_clear_coordinates')

for changes in ({'mode':'STACK'},{'target_position':4},{'target_position':True},{'roi':[0,0,640,481]}):
    try:s.apply(cmd(9,**changes),1800)
    except ValueError:pass
    else:raise AssertionError(changes)
assert s.control.seq==8 and s.mode=='RING'
for mode in ('MATERIAL','RING'):
    s.apply(cmd(s.control.seq+1,mode=mode),1900)
    r=s.result([color],rings,[],1901)
    assert not r['usable_for_alignment'] and not r['calibrated']
tests.append('invalid_commands_atomic_and_demo_alignment_blocked')
for file in ('vision_session.py','vision_unified.py'):
    compile((root/file).read_text(encoding='utf-8'),file,'exec')
(root/'vision_session_tests.json').write_text(json.dumps({'passed':tests,'scope':'Host command routing/invalidation behavior; board tests separate'},indent=2),encoding='utf-8')
print('PASSED',len(tests),'unified vision behavior groups')
