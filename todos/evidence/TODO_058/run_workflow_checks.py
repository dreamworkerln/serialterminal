"""Execute named software checks from the supplied CI workflow, without a second command list."""
from pathlib import Path
import json
import os
import re
import subprocess
import sys
import time
import hashlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
workflow = ROOT / '.github/workflows/ci.yml'
steps = []
current = None
for line in workflow.read_text().splitlines():
    value = line.strip()
    if value.startswith('- name:'):
        current = {'name': value.split(':', 1)[1].strip(), 'blocking': True}
        steps.append(current)
    elif current is not None and value.startswith('continue-on-error:'):
        assert value.split(':', 1)[1].strip() in ('true', 'false')
        current['blocking'] = value.split(':', 1)[1].strip() != 'true'
    elif current is not None and value.startswith('run:'):
        current['command'] = value.split(':', 1)[1].strip()
        assert current['command'] not in ('|', '>'), 'Unsupported multiline command'
assert steps and all('command' in step for step in steps)
qa = Path(sys.argv[1]).resolve()
env = dict(os.environ, PATH=str(qa / 'bin') + os.pathsep + '/usr/bin' + os.pathsep + os.environ['PATH'],
           PYTHONPATH=str(qa) + os.pathsep + os.environ.get('PYTHONPATH', ''))
subprocess.run(['python3', '-c', "import pytest, bleak, dbus_fast, pyte"], env=env, check=True)
results = []
for i, step in enumerate(steps):
    log = HERE / ('workflow-%02d.log' % i)
    start = time.monotonic()
    with log.open('w') as handle:
        run = subprocess.run(['bash', '--noprofile', '--norc', '-eo', 'pipefail', '-c', step['command']],
                             cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, env=env, text=True)
    text = log.read_text()
    result = {**step, 'exit_code': run.returncode, 'seconds': round(time.monotonic() - start, 2),
              'log': str(log.relative_to(ROOT))}
    if step['name'] == 'Tests':
        result['summary'] = text.splitlines()[-1:]
    results.append(result)
    print(json.dumps(result), flush=True)
    if run.returncode and step['blocking']:
        break
report = {'plan_source': str(workflow.relative_to(ROOT)),
          'workflow_sha256': hashlib.sha256(workflow.read_bytes()).hexdigest(),
          'execution': 'local named run steps from existing workflow; setup/install prepared separately',
          'python': subprocess.check_output(['python3', '--version'], env=env, text=True).strip(),
          'checks': results, 'mandatory_dependencies_checked': ['pytest', 'bleak', 'dbus_fast', 'pyte'],
          'status': 'PASS' if len(results) == len(steps) and all(
              row['exit_code'] == 0 or not row['blocking'] for row in results) else 'FAIL',
          'limitations': 'Not a GitHub run; CI infrastructure TODO_051 remains separate'}
(HERE / 'workflow-checks.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'workflow_checks': report['status']}), flush=True)
