from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

here = Path(__file__).resolve().parent
meta = json.loads((here / 'case.json').read_text())
work = Path(sys.argv[1]).resolve()
evidence = Path(sys.argv[2]).resolve()
evidence.mkdir(parents=True, exist_ok=True)
python = sys.executable
runner = here / 'pytest_runner.py'
source = work / meta['source']
fixed = source.read_bytes()
summary = {}
is_perch = meta['repo'].endswith('/perch')


def run(label, args, expected=0, cwd=work, timeout=300):
    with (evidence / (label + '.log')).open('w') as log:
        proc = subprocess.run(args, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                              check=False, timeout=timeout)
    output = (evidence / (label + '.log')).read_text(errors='replace')
    print(label, proc.returncode, output[-450:], flush=True)
    assert proc.returncode == expected, (label, output[-7500:])


def test(label, files, expected=0, coverage=False, cwd=work):
    args = [python, str(runner), *files, '-q', '--tb=short',
            '--junitxml=' + str(evidence / (label + '.xml'))]
    if coverage:
        args += ['--cov=' + ('chirp' if is_perch else 't5'), '--cov-branch',
                 '--cov-report=json:' + str(evidence / 'coverage.json')]
    run(label, args, expected=expected, cwd=cwd)
    root = ET.parse(evidence / (label + '.xml')).getroot()
    counts = [sum(int(s.attrib.get(k, 0)) for s in root.iter('testsuite'))
              for k in ['tests', 'failures', 'errors', 'skipped']]
    failed = sorted(t.attrib.get('classname', '') + '::' + t.attrib['name']
                    for t in root.iter('testcase')
                    if t.find('failure') is not None or t.find('error') is not None)
    summary[label] = dict(counts=counts, failed_nodes=failed)
    print(label, counts, flush=True)
    return counts


assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=work,
                               text=True).strip() == meta['head']
print('EXACT SOURCE', meta['head'], flush=True)
run('dependencies', [python, '-m', 'pip', 'freeze'])
run('dependency-check', [python, '-m', 'pip', 'check'])
original = subprocess.check_output(['git', 'show', meta['base'] + ':' + meta['source']], cwd=work)
new_count, original_failures = (19, 7) if is_perch else (15, 9)
full_count = 29 if is_perch else 35
try:
    assert test('fixed-focused', [meta['test']]) == [new_count, 0, 0, 0]
    assert test('fixed-suite', meta['suite_files'], coverage=True) == [full_count, 0, 0, 0]
    source.write_bytes(original)
    assert test('original-focused', [meta['test']], expected=1) == [new_count, original_failures, 0, 0]
    existing = [f for f in meta['suite_files'] if f != meta['test']]
    assert test('baseline-suite', existing) == [full_count - new_count, 0, 0, 0]
finally:
    source.write_bytes(fixed)
assert source.read_bytes() == fixed
assert test('restored-focused', [meta['test']]) == [new_count, 0, 0, 0]
run('source-restored', ['git', 'diff', '--exit-code'])
run('lint', [python, '-m', 'ruff', 'check', '--isolated', '--select', 'E9,F', meta['source'], meta['test']])
run('new-test-format', [python, '-m', 'pyink', '--check', '--pyink-indentation', '2',
                        '--pyink-use-majority-quotes', meta['test']])
run('compilation', [python, '-m', 'py_compile', meta['source'], meta['test']])
run('patch-check', ['git', 'diff', '--check', meta['base']])
# Validate a pristine source export, including real package __init__ imports.
with tempfile.TemporaryDirectory() as directory:
    exported = Path(directory)
    archive = evidence / 'submitted-source.tar'
    run('source-export', ['git', 'archive', '--format=tar', '--output=' + str(archive), 'HEAD'])
    import tarfile
    with tarfile.open(archive) as tar:
        # All archive entries are tracked files from this verified repository.
        for item in tar.getmembers():
            assert not Path(item.name).is_absolute() and '..' not in Path(item.name).parts
        tar.extractall(exported, filter='data')
    module = 'chirp' if is_perch else 't5'
    code = (f'import {module}; from pathlib import Path; p=Path({module}.__file__).resolve(); '
            f'print(p); assert p.is_relative_to(Path({str(exported)!r}))')
    run('exported-import', [python, '-c', code], cwd=exported)
    assert test('exported-suite', meta['suite_files'], cwd=exported) == [full_count, 0, 0, 0]
(evidence / 'summary.json').write_text(json.dumps(summary, indent=2))
print('VALIDATED', meta['head'], flush=True)
