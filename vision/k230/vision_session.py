"""Command selection for two vision modes; independent of board transport."""
from material_session import MaterialSession

class VisionSession:
    def __init__(self,diff=None):
        self.control=MaterialSession(diff)
        self.mode='MATERIAL'
        self.position=0
        self.epoch=0

    def apply(self,command,now):
        keys={'seq','enabled','mode','target_color','target_position','roi','lease_ms','pose_id'}
        if not isinstance(command,dict) or set(command)!=keys:raise ValueError('Expected complete vision command')
        seq=command['seq']
        if type(seq) is not int or seq<0:raise ValueError('Invalid seq')
        if seq<=self.control.seq:return False
        mode=command['mode']
        position=command['target_position']
        if mode not in ('MATERIAL','RING'):raise ValueError('Unknown mode')
        if type(position) is not int or not 0<=position<=3:raise ValueError('Invalid position')
        base={k:v for k,v in command.items() if k not in ('mode','target_position')}
        before=self.control.state(now)
        changed=self.control.apply(base,now)
        changed=changed or mode!=self.mode or position!=self.position or before!=self.control.state(now)
        self.mode=mode
        self.position=position
        if changed:self.epoch+=1
        return changed

    def invalidate(self,reason):
        if self.control.fault!=reason:self.epoch+=1
        self.control.invalidate(reason)

    def result(self,colors,rings,ambiguous,now,pending=False,warming=False):
        c=self.control
        state=c.state(now)
        targets=[]
        if state=='ACTIVE':
            if warming:state='WARMING_UP'
            elif self.mode=='MATERIAL':
                material=c.result(colors,ambiguous,now)
                state=material['state']
                if material['observation'] is not None:targets=[material['observation']]
            else:
                chosen=[r for r in rings if self.position==0 or r['position']==self.position]
                ids=[r['position'] for r in chosen]
                if len(ids)!=len(set(ids)):state='TARGET_AMBIGUOUS'
                elif chosen:
                    targets=chosen
                    state='TARGET_FOUND'
                else:state='NUMBER_PENDING' if pending else 'TARGET_NOT_FOUND'
        blockers=['CAMERA_NOT_CONFIRMED_STILL','POSE_UNCALIBRATED']
        if self.mode=='MATERIAL':blockers.insert(0,'COLOR_UNCALIBRATED')
        return {'command_seq':c.seq,'mode':self.mode,'mode_epoch':self.epoch,
                'target_color':c.color if self.mode=='MATERIAL' else None,
                'target_position':self.position if self.mode=='RING' else None,
                'state':state,'observation_valid':bool(targets),'targets':targets,
                'roi':c.roi,'pose_id':c.pose,'command_age_ms':max(0,c.diff(now,c.accepted_ms)),
                'usable_for_alignment':False,'blockers':blockers,'calibrated':False}
