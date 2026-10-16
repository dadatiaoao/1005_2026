"""Injected UART transport. Importing this file never configures any pins."""
import struct
from vision_wire import Parser,packet,OPEN,COMMAND,RECEIPT,ACK,RESULT,decode_command,encode_result
from vision_session import VisionSession

class VisionUART:
    def __init__(self,uart,diff=None):
        self.uart=uart
        self.parser=Parser(diff)
        self.session=VisionSession(diff)
        self.session.invalidate('LINK_RESET')
        self.session_id=0
        self.reset_pending=True
        self.tx=bytearray()
        self.rx_bytes=0
        self.tx_bytes=0

    def _queue(self,data):
        if len(self.tx)+len(data)>512:
            self.session.invalidate('LINK_RESET')
            self.reset_pending=True
            return False
        self.tx.extend(data)
        return True

    def _flush(self):
        if self.tx:
            n=self.uart.write(self.tx)
            if n:
                if not 0<n<=len(self.tx):raise OSError('Invalid UART write count')
                self.tx_bytes+=n
                self.tx=self.tx[n:]

    def poll(self,now):
        self._flush()
        # K230 any() reports readability, not necessarily buffered byte count.
        data=self.uart.read(256) if self.uart.any() else b''
        self.rx_bytes+=len(data or b'')
        reset=self.reset_pending
        self.reset_pending=False
        for kind,sid,seq,payload in self.parser.feed(data or b'',now):
            code=0
            changed=False
            if kind==OPEN and seq==0 and not payload:
                self.session_id=sid
                self.session=VisionSession(self.parser.diff)
                self.session.invalidate('LINK_RESET')
                changed=True
                print('VISION_UART_OPEN',sid)
            elif kind==RECEIPT:
                if sid==self.session_id and seq==self.session.control.seq and len(payload)==10:
                    frame,valid,target,cx10,cy10=struct.unpack('<IBBHH',payload)
                    print('VISION_MCU_RECEIPT',{'seq':seq,'frame':frame,'valid':valid,'id':target,'cx10':cx10,'cy10':cy10})
                continue
            elif kind!=COMMAND:
                continue
            elif sid!=self.session_id:code=2
            elif seq<=self.session.control.seq or seq==0:code=3
            else:
                try:
                    command=decode_command(payload,seq)
                    changed=self.session.apply(command,now)
                    if changed:print('VISION_UART_COMMAND',{'seq':seq,'mode':self.session.mode,'color':self.session.control.color,'position':self.session.position})
                except (ValueError,TypeError):
                    code=1
                    self.session.invalidate('INVALID_COMMAND')
                    changed=True
            reset=reset or changed
            self._queue(packet(ACK,sid,seq,struct.pack('<BBI',code,int(changed),self.session.epoch)))
        self._flush()
        return reset or self.reset_pending

    def publish(self,result,frame,captured_ms,algorithm_ms,now):
        self._flush()
        # Do not queue more camera results behind a slow transmitter.
        if self.session_id and self.session.control.seq>=1 and not self.tx:
            payload=encode_result(result,frame,captured_ms,algorithm_ms)
            self._queue(packet(RESULT,self.session_id,self.session.control.seq,payload))
            self._flush()

    def close(self):
        self.uart.deinit()

    def on_io_error(self):
        self.session.invalidate('LINK_RESET')
        self.session_id=0
        self.tx=bytearray()
        self.parser.buf=bytearray()
        self.reset_pending=True
