"""Vision wire draft v1. Same code on CPython and K230 MicroPython."""
import struct

MAGIC=b'\xa5\x5a'
VERSION=1
OPEN=1
COMMAND=2
RECEIPT=3
ACK=0x81
RESULT=0x82
MAX_PAYLOAD=96
HEADER=14
FRAME_TIMEOUT_MS=250
STATES=('STOPPED','WARMING_UP','TARGET_FOUND','TARGET_NOT_FOUND','TARGET_AMBIGUOUS',
        'NUMBER_PENDING','COMMAND_EXPIRED','INVALID_COMMAND','COMMAND_FILE_MISSING','LINK_RESET')

def crc16(data):
    crc=0xffff
    for value in data:
        crc^=value<<8
        for _ in range(8):crc=((crc<<1)^0x1021)&0xffff if crc&0x8000 else (crc<<1)&0xffff
    return crc

def packet(kind,session,seq,payload=b''):
    if not 0<session<=0xffffffff or not 0<=seq<=0xffffffff:raise ValueError('Invalid wire identifier')
    if len(payload)>MAX_PAYLOAD:raise ValueError('Payload too large')
    body=struct.pack('<BBHII',VERSION,kind,len(payload),session,seq)+payload
    return MAGIC+body+struct.pack('<H',crc16(body))

class Parser:
    def __init__(self,diff=None):
        if diff is None:
            import time
            diff=getattr(time,'ticks_diff',lambda a,b:a-b)
        self.diff=diff
        self.buf=bytearray()
        self.last_ms=None
        self.bad_crc=0
        self.bad_header=0

    def feed(self,data,now):
        if self.buf and self.last_ms is not None and self.diff(now,self.last_ms)>FRAME_TIMEOUT_MS:self.buf=bytearray()
        if data:self.last_ms=now
        frames=[]
        for value in data:
            self.buf.append(value)
            while len(self.buf)>=2:
                if self.buf[0]!=0xa5 or self.buf[1]!=0x5a:
                    self.buf=self.buf[1:]
                    continue
                if len(self.buf)<HEADER:break
                version,kind,size,session,seq=struct.unpack('<BBHII',self.buf[2:HEADER])
                if version!=VERSION or size>MAX_PAYLOAD or session==0:
                    self.bad_header+=1
                    self.buf=self.buf[1:]
                    continue
                total=HEADER+size+2
                if len(self.buf)<total:break
                expected=struct.unpack('<H',self.buf[total-2:total])[0]
                if crc16(self.buf[2:total-2])!=expected:
                    self.bad_crc+=1
                    self.buf=self.buf[1:]
                    continue
                frames.append((kind,session,seq,bytes(self.buf[HEADER:total-2])))
                self.buf=self.buf[total:]
        return frames

def encode_command(c):
    if c['mode'] not in ('MATERIAL','RING'):raise ValueError('Invalid mode')
    if type(c['enabled']) is not bool:raise ValueError('Invalid enable')
    if not c['pose_id'].startswith('P') or not c['pose_id'][1:].isdigit():raise ValueError('Wire pose_id is P0..P65535')
    pose=int(c['pose_id'][1:])
    return struct.pack('<BBBBHHHHIH',int(c['enabled']),1 if c['mode']=='MATERIAL' else 2,
                       c['target_color'],c['target_position'],*c['roi'],c['lease_ms'],pose)

def decode_command(payload,seq):
    if len(payload)!=18:raise ValueError('Invalid command length')
    enabled,mode,color,position,x,y,w,h,lease,pose=struct.unpack('<BBBBHHHHIH',payload)
    if enabled not in (0,1) or mode not in (1,2):raise ValueError('Invalid command mode/enable')
    return {'seq':seq,'enabled':bool(enabled),'mode':'MATERIAL' if mode==1 else 'RING',
            'target_color':color,'target_position':position,'roi':[x,y,w,h],
            'lease_ms':lease,'pose_id':'P%d'%pose}

def encode_result(result,frame,captured_ms,algorithm_ms):
    state=STATES.index(result['state'])
    mode=1 if result['mode']=='MATERIAL' else 2
    targets=result['targets']
    if len(targets)>3:raise ValueError('Too many targets')
    flags=int(result['observation_valid'])|int(result['usable_for_alignment'])<<1|int(result['calibrated'])<<2
    payload=struct.pack('<BBHIIIIHH',state,mode,flags,result['mode_epoch']&0xffffffff,
                        frame&0xffffffff,captured_ms&0xffffffff,min(0xffffffff,result['command_age_ms']),
                        min(65535,max(0,int(round(algorithm_ms*10)))),len(targets))
    for item in targets:
        target_id=item['color'] if mode==1 else item['position']
        w,h=item['rect'][2:] if mode==1 else (0,0)
        age=item.get('number_age_ms',0)
        score=int(round(item.get('score',0)*1000))
        payload+=struct.pack('<BBHHHHHH',target_id,0,int(round(item['cx']*10)),int(round(item['cy']*10)),w,h,age,score)
    return payload

def decode_result(payload):
    if len(payload)<24:raise ValueError('Short result')
    state,mode,flags,epoch,frame,captured,age,algorithm,count=struct.unpack('<BBHIIIIHH',payload[:24])
    if state>=len(STATES) or mode not in (1,2) or flags&~7 or count>3 or len(payload)!=24+count*14:raise ValueError('Invalid result header')
    if (state==2)!=(count>0) or bool(flags&1)!=(count>0) or (flags&2 and (flags&5)!=5):raise ValueError('Inconsistent result validity')
    if mode==1 and count>1:raise ValueError('Multiple selected material targets')
    targets=[]
    ids=[]
    for i in range(count):
        target_id,reserved,cx,cy,w,h,number_age,score=struct.unpack('<BBHHHHHH',payload[24+i*14:38+i*14])
        if reserved or not 1<=target_id<=(6 if mode==1 else 3) or target_id in ids or cx>=6400 or cy>=4800 or score>1000:raise ValueError('Invalid target')
        if mode==1 and (not 1<=w<=640 or not 1<=h<=480 or number_age or score):raise ValueError('Invalid material fields')
        if mode==2 and (w or h or number_age>900):raise ValueError('Invalid ring fields')
        ids.append(target_id)
        targets.append({'id':target_id,'cx10':cx,'cy10':cy,'width':w,'height':h,'number_age_ms':number_age,'score1000':score})
    return {'state':STATES[state],'mode':mode,'flags':flags,'epoch':epoch,'frame':frame,
            'captured_ms':captured,'command_age_ms':age,'algorithm_ms10':algorithm,'targets':targets}
