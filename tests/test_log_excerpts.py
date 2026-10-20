from datetime import datetime
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def analyzer():
    return runpy.run_path(str(ROOT / 'scripts' / 'analyze_file_transfer.py'))


def test_time_window_selects_four_logs_offsets_and_traceback(tmp_path):
    module = analyzer()
    at = module['excerpt_time']('2026-10-17T10:00:00+03:00')
    (tmp_path / 'serialterminal.log').write_text(
        '2026-10-17T06:59:57+00:00 [RUN] before window\n'
        '2026-10-17T06:59:58+00:00 [ERROR] known failure\n'
        '2026-10-17T07:00:03+00:00 [RUN] after window\n'
    )
    (tmp_path / 'serialterminal.console.log').write_text(
        '2026-10-17T10:00:00+03:00 [s1] [O] observed failure\n'
    )
    (tmp_path / 'serialterminal.fttiming.jsonl').write_text(json.dumps({
        'timestamp': at + 2, 'event': 'failed',
    }) + '\n')
    (tmp_path / 'serialterminal.application.log').write_text(
        '2026-10-17T10:00:01+03:00 [ERROR] known failure\n'
        'Traceback (most recent call last):\n'
        'ValueError: failure details\n'
        '2026-10-17T10:00:03+03:00 [INFO] STOP\n'
    )
    report = module['extract_excerpt'](tmp_path, at=at)
    assert report['matched_lines'] == report['returned_lines'] == 6
    assert report['truncated'] is False
    assert all(not stats['missing'] for stats in report['sources'].values())
    records = report['records']
    assert {row['source'] for row in records} == set(module['EXCERPT_LOGS'].values())
    assert [row['timestamp'] for row in records] == sorted(row['timestamp'] for row in records)
    trace = [row for row in records if row['source'] == 'serialterminal.application.log']
    assert [row['line'] for row in trace] == [1, 2, 3]
    assert all(row['timestamp'] == at + 1 for row in trace)
    assert not any('after window' in row['text'] for row in records)


def test_window_does_not_assume_file_is_chronologically_sorted(tmp_path):
    module = analyzer()
    (tmp_path / 'serialterminal.log').write_text(
        '2026-10-17T07:01:00Z [RUN] future\n'
        '2026-10-17T07:00:00Z [ERROR] delayed log write\n'
    )
    result = module['extract_excerpt'](tmp_path, at=module['excerpt_time']('2026-10-17T07:00:00Z'))
    assert [row['line'] for row in result['records']] == [2]


def test_line_limit_is_global_and_stdout_is_summary_unless_requested(tmp_path, capsys, monkeypatch):
    module = analyzer()
    at = '2026-10-17T07:00:00Z'
    for kind, name in module['EXCERPT_LOGS'].items():
        line = json.dumps({'timestamp': datetime.fromisoformat(at.replace('Z', '+00:00')).timestamp(),
                           'event': 'private-failure-detail'}) if kind == 'timing' else at + ' [ERROR] private-failure-detail'
        (tmp_path / name).write_text((line + '\n') * 10)
    monkeypatch.setitem(module['main'].__globals__, 'analyze', lambda *a, **kw: pytest.fail('full analysis in excerpt mode'))
    args = [str(tmp_path), '--excerpt-at', at, '--max-lines', '3']
    assert module['main'](args) == 0
    output = capsys.readouterr().out
    assert 'private-failure-detail' not in output
    summary = json.loads(output)
    saved = json.loads(Path(summary['excerpt']).read_text())
    assert saved['matched_lines'] == 40
    assert saved['returned_lines'] == 3
    assert saved['truncated'] is True
    assert not (tmp_path / 'analysis.json').exists()
    assert module['main']([*args, '--show-excerpt']) == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(rows) == 4
    assert all('source' in row and 'line' in row and 'text' in row for row in rows[:-1])
    assert len(list(tmp_path.glob('excerpt-*.json'))) == 2


def test_byte_budget_handles_unicode_and_huge_single_lines(tmp_path):
    module = analyzer()
    stamp = '2026-10-17T07:00:00Z'
    (tmp_path / 'serialterminal.log').write_text(stamp + ' [ERROR] ' + 'я' * 100000 + '\n' + stamp + ' [ERROR] next\n')
    report = module['extract_excerpt'](tmp_path, at=module['excerpt_time'](stamp),
                                       kinds=['primary'], max_bytes=700)
    assert report['matched_lines'] == 2
    assert report['sources']['serialterminal.log']['oversized_lines'] == 1
    assert report['record_bytes'] <= 700
    assert report['truncated'] is True
    assert report['records'][0]['text_truncated'] is True
    assert sum(len(module['encoded_excerpt_row'](row).encode('utf-8')) for row in report['records']) <= 700
    numbered = list(module['bounded_source_lines'](tmp_path / 'serialterminal.log'))
    assert [number for number, _, _ in numbered] == [1, 2]


def test_unparseable_timing_does_not_inherit_previous_timestamp_and_sources_unchanged(tmp_path):
    module = analyzer()
    path = tmp_path / 'serialterminal.fttiming.jsonl'
    stamp = module['excerpt_time']('2026-10-17T07:00:00Z')
    data = (json.dumps({'timestamp': stamp}) + '\n{broken\n' + json.dumps({'timestamp': True}) + '\n').encode()
    path.write_bytes(data)
    report = module['extract_excerpt'](tmp_path, at=stamp, kinds=['timing'])
    assert report['returned_lines'] == 1
    assert report['sources'][path.name]['unparsed_timestamps'] == 2
    assert path.read_bytes() == data


@pytest.mark.parametrize('extra', [
    ['--before', '-1'], ['--after', 'nan'], ['--before', 'inf'], ['--after', '301'],
    ['--max-lines', '201'], ['--max-bytes', '32769'], ['--max-lines', '0'],
])
def test_invalid_excerpt_limits_rejected_without_files(tmp_path, extra):
    module = analyzer()
    with pytest.raises(SystemExit) as exc:
        module['main']([str(tmp_path), '--excerpt-at', '2026-10-17T07:00:00Z', *extra])
    assert exc.value.code == 2
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('args', [
    ['--excerpt-at', '2026-10-17T07:00:00'], ['--show-excerpt'], ['--excerpt-log', 'application'],
])
def test_incomplete_excerpt_requests_fail_instead_of_running_full_analysis(tmp_path, args):
    with pytest.raises(SystemExit) as exc:
        analyzer()['main']([str(tmp_path), *args])
    assert exc.value.code == 2
    assert not list(tmp_path.iterdir())


def test_empty_excerpt_summary_has_no_raw_records(tmp_path, capsys):
    assert analyzer()['main']([str(tmp_path), '--excerpt-at', '2026-10-17T07:00:00Z']) == 1
    summary = json.loads(capsys.readouterr().out)
    assert summary['returned_lines'] == 0
    assert all(row['missing'] for row in summary['sources'].values())
    assert 'records' not in summary


def test_normal_analysis_still_prints_one_summary_without_raw_logs(tmp_path, capsys):
    (tmp_path / 'serialterminal.application.log').write_text(
        '2026-10-17T07:00:00Z [ERROR] private-failure-detail\n'
    )
    assert analyzer()['main']([str(tmp_path), '--no-decode']) == 1
    output = capsys.readouterr().out
    assert len(output.splitlines()) == 1
    assert 'private-failure-detail' not in output
    assert set(json.loads(output)) == {'run', 'outcome', 'file_integrity', 'elapsed', 'gaps'}



def test_cli_subprocess_only_exports_the_requested_window(tmp_path):
    source = tmp_path / 'serialterminal.application.log'
    original = (
        '2026-10-17T07:00:00Z [INFO] outside-private-detail\n'
        '2026-10-17T07:00:10Z [ERROR] known-bug-detail\n'
        'Traceback: selected-details\n'
        '2026-10-17T07:00:20Z [INFO] outside-private-detail\n'
    )
    source.write_text(original)
    result = subprocess.run([
        sys.executable, str(ROOT / 'scripts' / 'analyze_file_transfer.py'), str(tmp_path),
        '--excerpt-at', '2026-10-17T07:00:10Z', '--before', '1', '--after', '1',
        '--excerpt-log', 'application', '--show-excerpt', '--max-lines', '2',
    ], text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(lines) == 3
    assert [row['line'] for row in lines[:-1]] == [2, 3]
    assert 'outside-private-detail' not in result.stdout
    assert source.read_text() == original
    assert Path(lines[-1]['excerpt']).is_file()


def test_numeric_timestamp_overflow_is_an_evidence_gap_not_a_crash(tmp_path):
    module = analyzer()
    path = tmp_path / 'serialterminal.fttiming.jsonl'
    path.write_text(json.dumps({'timestamp': 10 ** 400}) + '\n')
    report = module['extract_excerpt'](tmp_path, at=module['excerpt_time']('2026-10-17T07:00:00Z'))
    assert report['returned_lines'] == 0
    assert report['sources'][path.name]['unparsed_timestamps'] == 1
