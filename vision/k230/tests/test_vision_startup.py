"""No board access: startup escape/failure behaviour only."""
import importlib.util,sys,types,tempfile,traceback,json
from pathlib import Path

path=Path('outputs/k230_vision/main.py')
spec=importlib.util.spec_from_file_location('vision_power_entry',path)
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
passed=[]

class Clock:
    def __init__(self):self.ms=0
    def sleep_ms(self,value):self.ms+=value
class OS:
    EXITPOINT_ENABLE=1
    def __init__(self,disabled=False):self.disabled=disabled;self.polls=0
    def stat(self,path):
        if not self.disabled:raise OSError(2,'missing')
        return ()
    def exitpoint(self,*args):self.polls+=1

def scenario(disabled=False,error=None):
    clock=Clock();calls=[];fake=types.ModuleType('vision_uart_entry')
    def run():
        assert clock.ms==5000
        calls.append(clock.ms)
        if error:raise error
    fake.run=run
    entry.os=OS(disabled);entry.time=clock
    entry.sys=types.SimpleNamespace(path=[],print_exception=lambda exc,stream=sys.stdout:traceback.print_exception(type(exc),exc,exc.__traceback__,file=stream))
    old=sys.modules.get('vision_uart_entry');sys.modules['vision_uart_entry']=fake
    try:entry.start()
    finally:
        if old is None:sys.modules.pop('vision_uart_entry',None)
        else:sys.modules['vision_uart_entry']=old
    return calls,clock.ms

workspace_temp=Path('work').resolve()
with tempfile.TemporaryDirectory(dir=workspace_temp) as folder:
    assert Path(folder).resolve().is_relative_to(workspace_temp)
    entry.ERROR_LOG=str(Path(folder)/'error.txt')
    assert scenario(disabled=True)==([],0)
    passed.append('disable_flag_prevents_hardware_import_and_delay')
    assert scenario()==([5000],5000)
    passed.append('escape_window_before_single_UART_entry_call')
    assert scenario(error=ValueError('camera failure'))==([5000],5000)
    assert 'camera failure' in Path(entry.ERROR_LOG).read_text()
    passed.append('fatal_error_records_traceback_and_returns_without_restart')
    Path(entry.ERROR_LOG).unlink()
    assert scenario(error=KeyboardInterrupt())==([5000],5000)
    assert not Path(entry.ERROR_LOG).exists()
    passed.append('operator_interrupt_returns_without_crash_log')
Path('outputs/k230_vision/startup_host_tests.json').write_text(json.dumps({'passed':passed,'scope':'fake OS/clock/vision entry only; no power-on validation'},indent=2),encoding='utf-8')
print('STARTUP_GUARDS_PASS',len(passed))
