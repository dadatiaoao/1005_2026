"""Pure protocol checks: runnable on K230 without UART pin changes."""
import struct
from vision_wire import Parser,packet,crc16,OPEN,COMMAND,ACK,RESULT,encode_command,decode_command,encode_result,decode_result
from vision_uart import VisionUART

def command(seq=1,**changes):
    c={'seq':seq,'enabled':True,'mode':'MATERIAL','target_color':3,'target_position':0,
       'roi':[10,35,620,435],'lease_ms':2000,'pose_id':'P7'}
    c.update(changes)
    return c

def result(mode='MATERIAL',state='TARGET_FOUND',targets=None):
    if targets is None:
        targets=[{'color':3,'cx':482,'cy':221,'rect':(448,176,70,91),'pixels':5000}] if mode=='MATERIAL' else [{'position':2,'cx':254.8,'cy':308.1,'number_age_ms':100,'score':.91}]
    return {'mode':mode,'state':state,'targets':targets,'mode_epoch':2,'command_age_ms':100,
            'observation_valid':bool(targets),'usable_for_alignment':False,'calibrated':False}

class MemoryUART:
    def __init__(self):self.rx=bytearray();self.tx=bytearray();self.closed=False;self.limit=7
    def any(self):return int(bool(self.rx))
    def read(self,n):
        part=bytes(self.rx[:n]);self.rx=self.rx[n:];return part
    def write(self,data):
        n=min(len(data),self.limit);self.tx.extend(data[:n]);return n
    def deinit(self):self.closed=True

def run():
    passed=[]
    assert crc16(b'123456789')==0x29b1
    c=command()
    raw=packet(COMMAND,123,1,encode_command(c))
    assert len(raw)==34 and decode_command(raw[14:-2],1)==c
    parser=Parser()
    frames=[]
    for value in raw:frames.extend(parser.feed(bytes([value]),10))
    assert frames==[(COMMAND,123,1,encode_command(c))]
    assert len(parser.buf)<=112
    passed.append('crc_reference_and_single_byte_fragmentation')

    broken=bytearray(raw);broken[-1]^=1
    malformed=b'\xa5\x5a\x01\x02\xff\xff'+b'\x00'*8
    frames=parser.feed(b'noise'+bytes(broken)+malformed+raw+raw,20)
    assert len(frames)==2 and parser.bad_crc and parser.bad_header
    partial=Parser();assert partial.feed(raw[:9],0)==[]
    assert partial.feed(raw[9:],251)==[]
    assert partial.feed(raw,252)==[(COMMAND,123,1,encode_command(c))]
    passed.append('noise_crc_bad_length_glued_packets_and_partial_timeout')

    for mode in ('MATERIAL','RING'):
        payload=encode_result(result(mode),10,100,95.4)
        decoded=decode_result(payload)
        assert decoded['mode']==(1 if mode=='MATERIAL' else 2) and decoded['frame']==10
        assert decoded['flags']==1 and len(decoded['targets'])==1
    empty=encode_result(result(state='STOPPED',targets=[]),11,101,0)
    assert decode_result(empty)['targets']==[]
    bad=bytearray(empty);bad[0]=2
    try:decode_result(bad)
    except ValueError:pass
    else:raise AssertionError('empty TARGET_FOUND accepted')
    passed.append('material_ring_empty_and_inconsistent_result_validation')

    uart=MemoryUART();endpoint=VisionUART(uart)
    uart.rx.extend(packet(OPEN,123,0))
    assert endpoint.poll(0)
    uart.rx.extend(raw)
    assert endpoint.poll(10) and endpoint.session.control.seq==1
    accepted_ms=endpoint.session.control.accepted_ms
    uart.rx.extend(raw+packet(COMMAND,456,2,encode_command(command(2))))
    assert not endpoint.poll(20)
    assert endpoint.session_id==123 and endpoint.session.control.accepted_ms==accepted_ms
    uart.rx.extend(packet(COMMAND,123,2,encode_command(command(2,mode='RING',target_position=2))))
    assert endpoint.poll(30) and endpoint.session.mode=='RING'
    for now in range(40,160):endpoint.poll(now)
    assert not endpoint.tx
    reply=Parser().feed(bytes(uart.tx),160)
    assert [struct.unpack('<BBI',f[3])[0] for f in reply]==[0,0,3,2,0]
    endpoint.publish(result('RING'),12,160,95.4,160)
    for now in range(161,200):endpoint.poll(now)
    reply=Parser().feed(bytes(uart.tx),200)
    assert reply[-1][:3]==(RESULT,123,2)
    assert decode_result(reply[-1][3])['targets'][0]['id']==2
    assert endpoint.session.result([],[],[],2030)['state']=='COMMAND_EXPIRED'
    endpoint.on_io_error()
    assert endpoint.session_id==0 and endpoint.session.result([],[],[],2031)['targets']==[]
    endpoint.close();assert uart.closed
    passed.append('endpoint_session_sequence_partial_tx_mode_change_expiry_and_io_loss')
    print('WIRE_SELFTEST_PASS',len(passed),passed)
    return passed

if __name__=='__main__':run()
