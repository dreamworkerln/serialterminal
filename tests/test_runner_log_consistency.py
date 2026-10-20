import json
from pathlib import Path
import runpy

import pytest


ROOT = Path(__file__).resolve().parents[1]


def analyzer():
    return runpy.run_path(str(ROOT / 'scripts' / 'analyze_file_transfer.py'))


def fixture(tmp_path):
    result = {'outcome': 'PASS', 'transfer_id': 'root',
              'sender_open': {'session': 's1'}, 'receiver_open': {'session': 's2'}}
    api, rows = [], []
    for index, (tx_done, rx_done, state) in enumerate(((500, 300, 'sending'), (1000, 1000, 'completed'))):
        snapshots = {}
        for role, session, done in (('TX', 's1', tx_done), ('RX', 's2', rx_done)):
            snapshot = {'direction': role, 'transfer_id': 'root', 'state': state, 'wire_bytes': 1000,
                        'bytes_completed': done, 'chunks_total': 100, 'chunks_completed': done // 10, 'elapsed': index + 1}
            snapshots[role] = snapshot
            request_id = len(api)
            api.extend([
                {'direction': 'request', 'timestamp': 1, 'message': {
                    'id': request_id, 'op': 'file_transfer_observe', 'session': session}},
                {'direction': 'response', 'timestamp': 1, 'message': {
                    'id': request_id, 'ok': True, 'result': {'progress': snapshot}}},
            ])
        rows.append({'timestamp': '2026-10-17T00:00:00+00:00', 'elapsed': index + 1,
                     'transfer_id': 'root', **snapshots,
                     'delta': {'bytes': tx_done - rx_done, 'percentage_points': (tx_done - rx_done) / 10},
                     'verified': state == 'completed'})
    save(tmp_path / 'agent.jsonl', api)
    save(tmp_path / 'progress.jsonl', rows)
    return result, api, rows


def save(path, rows):
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


def test_pair_progress_is_proved_by_preceding_st_responses(tmp_path):
    result, _, _ = fixture(tmp_path)
    gaps = []
    report = analyzer()['runner_progress_stats'](tmp_path, result, gaps)
    assert gaps == []
    assert report['consistency'] == 'PASS'
    assert report['api_matched_snapshots'] == 4
    assert report['intermediate_snapshots'] == {'TX': 1, 'RX': 1}
    assert report['max_absolute_difference_pp'] == 20


@pytest.mark.parametrize('fault, expected', [
    ('invented_rx', 'snapshot absent'), ('delta', 'incorrect TX-RX'),
    ('early_verified', 'verified before'), ('role', 'wrong snapshot role'),
    ('elapsed', 'elapsed is not monotonic'), ('future', 'snapshot absent'),
    ('missing_api', 'missing agent.jsonl'), ('empty', 'no verified observation'),
    ('wrong_root', 'wrong ROOT transfer_id'),
])
def test_progress_anomalies_cannot_receive_consistency_pass(tmp_path, fault, expected):
    result, api, rows = fixture(tmp_path)
    if fault == 'invented_rx':
        rows[0]['RX'] = {**rows[0]['RX'], 'bytes_completed': 400}
    elif fault == 'delta':
        rows[0]['delta']['bytes'] = 0
    elif fault == 'early_verified':
        rows[0]['verified'] = True
    elif fault == 'role':
        rows[0]['RX'] = {**rows[0]['RX'], 'direction': 'TX'}
    elif fault == 'elapsed':
        rows[1]['elapsed'] = 0
    elif fault == 'future':
        for row in api:
            row['timestamp'] = 9999999999
    elif fault == 'empty':
        rows = []
    elif fault == 'wrong_root':
        rows[0]['transfer_id'] = 'another-root'
    save(tmp_path / 'agent.jsonl', api)
    save(tmp_path / 'progress.jsonl', rows)
    if fault == 'missing_api':
        (tmp_path / 'agent.jsonl').unlink()
    gaps = []
    report = analyzer()['runner_progress_stats'](tmp_path, result, gaps)
    assert report['consistency'] == 'INCONCLUSIVE'
    assert any(expected in gap for gap in gaps)


def test_progress_omission_only_allowed_for_unstarted_transfer(tmp_path):
    gaps = []
    assert analyzer()['runner_progress_stats'](tmp_path, {}, gaps) == {'available': False}
    assert not gaps
    analyzer()['runner_progress_stats'](tmp_path, {'transfer_id': 'root'}, gaps)
    assert gaps == ['missing progress.jsonl for started transfer']


def test_st_ft1_events_must_agree_between_primary_and_timing_logs(tmp_path):
    (tmp_path / 'serialterminal.log').write_text(
        '[time] [FT1] ' + json.dumps({'session': 's1', 'transfer_id': 'root', 'kind': 'progress'}) + '\n')
    save(tmp_path / 'serialterminal.fttiming.jsonl', [{'segment_id': 'x', 'seq': 1, 'event': 'run_stop'}])
    report = analyzer()['analyze'](tmp_path, decode=False)
    assert 'FT1 event counts differ between primary and timing logs' in report['evidence_gaps']
