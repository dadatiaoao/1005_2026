"""Transport-independent material selection. No hardware actuation.
Observation validity is separate from calibration and camera-motion prerequisites.
"""
class MaterialSession:
    def __init__(self,diff=None):
        if diff is None:
            import time
            diff=getattr(time,'ticks_diff',lambda a,b:a-b)
        self.diff=diff
        self.seq=-1
        self.enabled=False
        self.color=1
        self.roi=(10,35,620,435)
        self.pose='bench'
        self.lease_ms=60000
        self.accepted_ms=0
        self.fault=None

    def invalidate(self,reason):
        self.enabled=False
        self.fault=reason

    def apply(self,command,now):
        allowed={'seq','enabled','target_color','roi','lease_ms','pose_id'}
        if not isinstance(command,dict) or set(command)!=allowed:
            raise ValueError('Expected complete command fields')
        seq=command['seq']
        if type(seq) is not int or seq<0:raise ValueError('Invalid seq')
        if seq<=self.seq:return False
        enabled=command['enabled']
        color=command['target_color']
        roi=command['roi']
        lease=command['lease_ms']
        pose=command['pose_id']
        if type(enabled) is not bool:raise ValueError('enabled must be boolean')
        if type(color) is not int or not 1<=color<=6:raise ValueError('Invalid color')
        if not isinstance(roi,(tuple,list)) or len(roi)!=4 or any(type(v) is not int for v in roi):raise ValueError('Invalid ROI')
        x,y,w,h=roi
        if x<0 or y<0 or w<40 or h<40 or x+w>640 or y+h>480:raise ValueError('ROI outside image or too small')
        if type(lease) is not int or not 500<=lease<=120000:raise ValueError('lease_ms outside 500..120000')
        if not isinstance(pose,str) or not pose or len(pose)>32:raise ValueError('Invalid pose_id')
        changed=(enabled,color,tuple(roi),pose)!=(self.enabled,self.color,self.roi,self.pose) or self.fault is not None
        self.seq=seq
        self.enabled=enabled
        self.color=color
        self.roi=tuple(roi)
        self.pose=pose
        self.lease_ms=lease
        self.accepted_ms=now
        self.fault=None
        return changed

    def state(self,now):
        if self.fault:return self.fault
        if not self.enabled:return 'STOPPED'
        if self.diff(now,self.accepted_ms)>=self.lease_ms:return 'COMMAND_EXPIRED'
        return 'ACTIVE'

    def result(self,stable,ambiguous,now,calibrated=False,camera_stationary=None,pose_calibrated=False):
        state=self.state(now)
        matches=[item for item in stable if item['color']==self.color]
        observation=None
        if state=='ACTIVE':
            if self.color in ambiguous:state='TARGET_AMBIGUOUS'
            elif len(matches)==1:
                observation=matches[0]
                state='TARGET_FOUND'
            else:state='TARGET_NOT_FOUND'
        blockers=[]
        if not calibrated:blockers.append('COLOR_UNCALIBRATED')
        if camera_stationary is not True:blockers.append('CAMERA_NOT_CONFIRMED_STILL')
        if not pose_calibrated:blockers.append('POSE_UNCALIBRATED')
        return {'command_seq':self.seq,'state':state,'target_color':self.color,
                'observation_valid':observation is not None,'observation':observation,
                'usable_for_alignment':observation is not None and not blockers,
                'blockers':blockers,'roi':self.roi,'pose_id':self.pose,
                'command_age_ms':max(0,self.diff(now,self.accepted_ms))}
