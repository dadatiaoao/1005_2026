"""One number read per frame; fresh geometry with bounded-age identity.
No coordinates are cached here. Missing/unknown/changed IDs require reconfirmation.
"""
CONFIRM_READS=3
REFRESH_MS=350
MAX_NUMBER_AGE_MS=900

class NumberSchedule:
    def __init__(self,diff=None):
        if diff is None:
            import time
            diff=getattr(time,'ticks_diff',lambda a,b:a-b)
        self.diff=diff
        self.states={}

    def sync(self,observed,now):
        retained={}
        for track in observed:
            track_id=track['id']
            state=self.states.get(track_id)
            if state is None:
                state={'digit':0,'count':0,'attempt':None,'read':None,'score':0.0}
            if state['read'] is not None and self.diff(now,state['read'])>MAX_NUMBER_AGE_MS:
                state['digit']=0
                state['count']=0
                state['read']=None
            retained[track_id]=state
        self.states=retained

    def select(self,observed,now):
        best=None
        oldest=-1
        for track in observed:
            state=self.states[track['id']]
            age=1000000 if state['attempt'] is None else self.diff(now,state['attempt'])
            confirmed=state['digit'] and state['count']>=CONFIRM_READS
            if confirmed and state['read'] is not None and self.diff(now,state['read'])<REFRESH_MS:
                continue
            if age>oldest:
                oldest=age
                best=track
        return best

    def record(self,track_id,reading,captured_ms):
        state=self.states[track_id]
        digit=reading['digit']
        count=state['count']+1 if digit and digit==state['digit'] else (1 if digit else 0)
        state.update({'digit':digit,'count':count,'attempt':captured_ms,
                      'read':captured_ms if digit else None,'score':reading['score']})

    def positions(self,observed,now):
        current=[s['digit'] for s in self.states.values() if s['digit']]
        duplicates={d for d in current if current.count(d)>1}
        positions={}
        for track in observed:
            state=self.states[track['id']]
            digit=state['digit']
            if digit and digit not in duplicates and state['count']>=CONFIRM_READS and state['read'] is not None:
                age=self.diff(now,state['read'])
                if 0<=age<=MAX_NUMBER_AGE_MS:
                    positions[track['id']]={'position':digit,'score':state['score'],'number_age_ms':age}
        return positions
