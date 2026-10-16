"""01Studio CanMV K230: IO5=TX, IO6=RX (40-pin header pins 11/12)."""
from machine import UART,FPIOA
from vision_uart import VisionUART
from vision_unified import main

def run(diagnostics=False):
    fpioa=FPIOA()
    fpioa.set_function(5,FPIOA.UART2_TXD)
    fpioa.set_function(6,FPIOA.UART2_RXD)
    uart=UART(UART.UART2,baudrate=115200,bits=UART.EIGHTBITS,
              parity=UART.PARITY_NONE,stop=UART.STOPBITS_ONE,timeout=0)
    main(VisionUART(uart),diagnostics=diagnostics)

if __name__=='__main__':run()
