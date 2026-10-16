"""Host-only checks; existing fixtures run in a disposable directory."""
from pathlib import Path
import ast, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
modules = sorted(ROOT.glob('*.py'))
for module in modules:
    ast.parse(module.read_text(encoding='utf-8'), filename=module.name)
with tempfile.TemporaryDirectory(prefix='k230_vision_checks_', dir=ROOT/'tests') as temp:
    temp = Path(temp).resolve()
    assert temp.is_relative_to(ROOT.resolve())
    (temp/'work').mkdir()
    sources = temp/'outputs/k230_vision'
    sources.mkdir(parents=True)
    for module in modules:
        shutil.copy2(module, sources/module.name)
    reports = []
    for fixture in ['vision_wire_selftest.py','test_vision_session.py','test_vision_startup.py']:
        target = sources/fixture
        shutil.copy2(ROOT/'tests'/fixture, target)
        result = subprocess.run([sys.executable,str(target)], cwd=temp,
                                env={**os.environ,'TMP':str(temp),'TEMP':str(temp)},
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(fixture+' failed:\n'+result.stdout+result.stderr)
        reports.append({'test':fixture,'passed':True,'summary':result.stdout.strip().splitlines()[-1]})
print(json.dumps({'python_syntax_files':len(modules),'hardware_accessed':False,
                  'passed':reports},ensure_ascii=False,indent=2))
