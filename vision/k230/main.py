"""CanMV K230 power-on entry; UART commands select the vision task."""
import os
import sys
import time

BOOT_DELAY_SECONDS=5
DISABLE_FLAG='/sdcard/vision_autostart.off'
ERROR_LOG='/sdcard/vision_autostart_error.txt'

def start():
    try:
        os.stat(DISABLE_FLAG)
    except OSError:
        pass
    else:
        print('VISION_AUTOSTART_DISABLED',DISABLE_FLAG)
        return
    try:
        os.exitpoint(os.EXITPOINT_ENABLE)
        print('VISION_AUTOSTART_WAIT',BOOT_DELAY_SECONDS)
        for _ in range(BOOT_DELAY_SECONDS*10):
            os.exitpoint()
            time.sleep_ms(100)
        if '/sdcard' not in sys.path:
            sys.path.insert(0,'/sdcard')
        print('VISION_AUTOSTART_BEGIN','UART2 IO5/IO6 115200')
        import vision_uart_entry
        vision_uart_entry.run()
        print('VISION_AUTOSTART_EXIT')
    except KeyboardInterrupt:
        print('VISION_AUTOSTART_STOPPED')
    except Exception as error:
        if str(error)=='IDE interrupt':
            print('VISION_AUTOSTART_STOPPED')
            return
        print('VISION_AUTOSTART_ERROR',repr(error))
        sys.print_exception(error)
        try:
            with open(ERROR_LOG,'w') as stream:
                sys.print_exception(error,stream)
        except OSError:
            pass
        # Stay at the REPL after an error; do not reboot into a retry loop.

if __name__=='__main__':
    start()
