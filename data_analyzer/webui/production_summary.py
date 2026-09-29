"""Production summary statistics for the web UI dashboard."""

from datetime import datetime
from pathlib import Path

from benchtest_results import get_failed_tests_for_serial
from production_config import load_production_config
from production_schedule import build_schedule_projections, load_production_schedule

SCHEDULE_CSV_PATH = Path(__file__).parent / 'production_schedule.csv'


COLORS = {
    'passed': '#00CC96',
    'failed': '#EF553B',
    'no_test': '#FECB52',
    'burned_in': '#4caf50',
    'not_burned_in': '#f44336',
    'not_received': '#B6B6B6',
    'burnin_timeline': '#AB63FA',
    'expected_produced': '#636EFA',
    'expected_tested': '#00B5D8',
    'expected_burnin': '#FF6692',
    'not_yet_produced': '#B6B6B6',
    'other_produced': '#9D7BD8',
    'passed_before_not_after': '#EF553B',
    'passed_before_last_after_failed': '#EF553B',
    'passed_after_burnin': '#00CC96',
    'other_burned_in': '#B6B6B6',
}


def _parse_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def decode_serial(serial):
    serial = str(serial).zfill(7)
    return {
        'tag': int(serial[:2]),
        'batch': int(serial[2:4]),
        'position': int(serial[4:7]),
    }


def _has_benchtest(serial, serial_to_benchtests):
    return serial in serial_to_benchtests and len(serial_to_benchtests[serial]) > 0


def _classify_board(row, serial_to_benchtests):
    status = row.get('db_status')
    e_test = row.get('e_test')
    p_test = row.get('p_test')
    serial = row['serial_no']

    has_benchtest = _has_benchtest(serial, serial_to_benchtests)

    if (status == 0 or e_test == 0 or p_test == 0) and has_benchtest:
        return 'failed'
    if status == 0 and not has_benchtest:
        return 'no_test'
    if status is None or e_test is None or p_test is None:
        return 'no_test'
    if any(row.get(field) is None for field in ('a0', 'a1', 'b0', 'b1')):
        return 'no_test'
    if status == 1 and e_test == 1 and p_test == 1:
        return 'passed'
    return 'failed'


def _has_post_burnin_test(row, serial_to_benchtest_stops):
    burn_in_stop = _parse_datetime(row.get('burn_in_stop'))
    if not burn_in_stop:
        return False

    serial = row['serial_no']
    for test_stop in serial_to_benchtest_stops.get(serial, []):
        test_stop_dt = _parse_datetime(test_stop)
        if test_stop_dt and test_stop_dt > burn_in_stop:
            return True
    return False


def _build_benchtest_maps(benchtest_rows):
    serial_to_benchtests = {}
    serial_to_benchtest_stops = {}
    serial_to_latest_test_stop = {}

    for bt in benchtest_rows:
        if bt.get('test_pass') == -1:
            continue

        test_stop = bt.get('test_stop')
        for slot_num in range(1, 5):
            serial = bt.get(f'db_slot{slot_num}')
            if not serial:
                continue

            serial_to_benchtests.setdefault(serial, []).append(bt['id'])
            if test_stop:
                serial_to_benchtest_stops.setdefault(serial, []).append(test_stop)
                current_latest = serial_to_latest_test_stop.get(serial)
                if current_latest is None or str(test_stop) > str(current_latest):
                    serial_to_latest_test_stop[serial] = test_stop

    return serial_to_benchtests, serial_to_benchtest_stops, serial_to_latest_test_stop


def _serial_benchtest_results(benchtest_rows):
    mapping = {}
    pass_cache = {}
    for benchtest in benchtest_rows:
        if benchtest.get('test_pass') == -1:
            continue
        benchtest_id = benchtest.get('id')
        for slot_num in range(1, 5):
            serial = benchtest.get(f'db_slot{slot_num}')
            if not serial:
                continue
            serial_key = _format_board_serial(serial)
            cache_key = (serial_key, benchtest_id)
            if cache_key not in pass_cache:
                _failed_tests, board_pass_fail = get_failed_tests_for_serial(
                    serial_key,
                    benchtest_id,
                )
                if board_pass_fail is not None:
                    try:
                        pass_cache[cache_key] = int(board_pass_fail)
                    except (TypeError, ValueError):
                        pass_cache[cache_key] = benchtest.get('test_pass')
                else:
                    pass_cache[cache_key] = benchtest.get('test_pass')
            mapping.setdefault(serial_key, []).append({
                'id': benchtest_id,
                'test_stop': benchtest.get('test_stop'),
                'test_pass': pass_cache[cache_key],
            })
    return mapping


def _format_board_serial(serial):
    return str(serial).zfill(7)


def _is_passed_test(test_pass):
    if test_pass is None:
        return False
    try:
        return int(test_pass) == 1
    except (TypeError, ValueError):
        return False


def _is_failed_test(test_pass):
    if test_pass is None:
        return False
    try:
        return int(test_pass) == 0
    except (TypeError, ValueError):
        return False


def _classify_burnin_tests(row, tests):
    burn_in_stop = _parse_datetime(row.get('burn_in_stop'))
    passed_before = False
    passed_after = False
    after_tests = []
    for test in tests or []:
        test_stop = _parse_datetime(test.get('test_stop'))
        is_after = bool(burn_in_stop and test_stop and test_stop > burn_in_stop)
        if is_after:
            after_tests.append((test_stop, test.get('id') or 0, test))
        if not _is_passed_test(test.get('test_pass')):
            continue
        if is_after:
            passed_after = True
        else:
            passed_before = True

    last_after_failed = False
    if after_tests:
        after_tests.sort(key=lambda item: (item[0], item[1]))
        last_after_failed = _is_failed_test(after_tests[-1][2].get('test_pass'))
    return passed_before, passed_after, last_after_failed


def _has_passed_before_burnin(row, serial_to_tests):
    tests = (serial_to_tests or {}).get(_format_board_serial(row['serial_no']))
    passed_before, _, _ = _classify_burnin_tests(row, tests)
    return passed_before


def _counts_as_failed_after_burnin(
    row,
    classification,
    serial_to_tests,
    serial_to_benchtest_stops,
):
    tests = (serial_to_tests or {}).get(_format_board_serial(row['serial_no']))
    passed_before, passed_after, last_after_failed = _classify_burnin_tests(row, tests)
    if passed_after:
        return False
    if classification == 'failed' or last_after_failed:
        return True
    # Only failed before burn-in (never passed before) and never passed after.
    if not passed_before:
        return True
    return False


def _burnin_pass_groups(boards, serial_to_tests):
    passed_before_last_after_failed = []
    passed_after = []
    burned_in = 0
    for board in boards:
        if not board.get('burn_in_stop'):
            continue
        burned_in += 1
        passed_before, passed_after_flag, last_after_failed = _classify_burnin_tests(
            board,
            serial_to_tests.get(_format_board_serial(board['serial_no'])),
        )
        entry = {
            'serial': _format_board_serial(board['serial_no']),
            'batch': board.get('decoded_batch'),
        }
        if passed_before and last_after_failed:
            passed_before_last_after_failed.append(entry)
        if passed_after_flag:
            passed_after.append(entry)

    passed_before_last_after_failed.sort(key=lambda item: item['serial'])
    passed_after.sort(key=lambda item: item['serial'])

    def _payload(items):
        return {
            'count': len(items),
            'boards': items,
            'other_count': max(burned_in - len(items), 0),
            'burned_in': burned_in,
        }

    return _payload(passed_before_last_after_failed), _payload(passed_after)


def build_production_summary(db_rows, benchtest_rows, schedule_csv_path=None):
    serial_to_benchtests, serial_to_benchtest_stops, serial_to_latest_test_stop = _build_benchtest_maps(
        benchtest_rows
    )
    serial_to_tests = _serial_benchtest_results(benchtest_rows)

    boards = []
    for row in db_rows:
        decoded = decode_serial(row['serial_no'])
        if decoded['tag'] == 90:
            continue

        board = dict(row)
        board['decoded_batch'] = decoded['batch']
        board['position'] = decoded['position']
        board['classification'] = _classify_board(row, serial_to_benchtests)
        board['has_post_burnin_test'] = _has_post_burnin_test(row, serial_to_benchtest_stops)
        board['test_stop'] = serial_to_latest_test_stop.get(row['serial_no'])
        boards.append(board)

    total_boards = len(boards)

    yield_passed = 0
    yield_failed = 0
    for board in boards:
        if _counts_as_failed_after_burnin(
            board,
            board['classification'],
            serial_to_tests,
            serial_to_benchtest_stops,
        ):
            yield_failed += 1
        elif board['has_post_burnin_test'] and board['classification'] == 'passed':
            yield_passed += 1

    burned_in = sum(1 for board in boards if board.get('burn_in_stop'))
    received_not_burned_in = max(total_boards - burned_in, 0)

    batch_stats = {}
    for board in boards:
        batch = board['decoded_batch']
        if batch not in batch_stats:
            batch_stats[batch] = {'passed': 0, 'failed': 0, 'no_test': 0}
        batch_stats[batch][board['classification']] += 1

    sorted_batches = sorted(batch_stats.keys())
    cumulative_by_batch = {
        'batches': sorted_batches,
        'passed': [],
        'failed': [],
        'no_test': [],
    }
    cumulative_passed = cumulative_failed = cumulative_no_test = 0
    for batch in sorted_batches:
        stats = batch_stats[batch]
        cumulative_passed += stats['passed']
        cumulative_failed += stats['failed']
        cumulative_no_test += stats['no_test']
        cumulative_by_batch['passed'].append(cumulative_passed)
        cumulative_by_batch['failed'].append(cumulative_failed)
        cumulative_by_batch['no_test'].append(cumulative_no_test)

    boards_with_time = [board for board in boards if board.get('test_stop')]
    boards_with_time.sort(key=lambda board: str(board['test_stop']))

    cumulative_by_time = {
        'passed': [],
        'failed': [],
        'no_test': [],
    }
    time_passed = time_failed = time_no_test = 0
    for board in boards_with_time:
        if board['classification'] == 'passed':
            time_passed += 1
            cumulative_by_time['passed'].append({
                'x': str(board['test_stop']),
                'y': time_passed,
                'serial': board['serial_no'],
            })
        elif board['classification'] == 'failed':
            time_failed += 1
            cumulative_by_time['failed'].append({
                'x': str(board['test_stop']),
                'y': time_failed,
                'serial': board['serial_no'],
            })
        else:
            time_no_test += 1
            cumulative_by_time['no_test'].append({
                'x': str(board['test_stop']),
                'y': time_no_test,
                'serial': board['serial_no'],
            })

    burnin_timeline = []
    burnin_boards = [
        board for board in boards
        if board.get('burn_in_start') and board.get('burn_in_stop')
    ]
    burnin_boards.sort(key=lambda board: str(board['burn_in_start']))

    for index, board in enumerate(burnin_boards, start=1):
        start_dt = _parse_datetime(board['burn_in_start'])
        stop_dt = _parse_datetime(board['burn_in_stop'])
        if not start_dt or not stop_dt:
            continue

        center_dt = start_dt + (stop_dt - start_dt) / 2
        error_minus_ms = (center_dt - start_dt).total_seconds() * 1000
        error_plus_ms = (stop_dt - center_dt).total_seconds() * 1000

        burnin_timeline.append({
            'serial': board['serial_no'],
            'batch': board['decoded_batch'],
            'burn_in_start': start_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'burn_in_stop': stop_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'burn_in_center': center_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'error_minus_ms': error_minus_ms,
            'error_plus_ms': error_plus_ms,
            'y_pos': index,
        })

    tested_after_burnin = yield_passed + yield_failed
    yield_failure_rate = (yield_failed / tested_after_burnin * 100) if tested_after_burnin > 0 else 0
    post_burnin_pass_rate = (yield_passed / tested_after_burnin * 100) if tested_after_burnin > 0 else 0

    passed_after_burnin = yield_passed
    failed_after_burnin = yield_failed
    no_test_count = sum(1 for board in boards if board['classification'] == 'no_test')
    no_test_or_untested = max(total_boards - passed_after_burnin - failed_after_burnin, 0)

    schedule_entries = load_production_schedule(schedule_csv_path or SCHEDULE_CSV_PATH)
    production_config = load_production_config()
    schedule_path = schedule_csv_path or SCHEDULE_CSV_PATH
    schedule = build_schedule_projections(
        schedule_entries,
        production_config,
        schedule_csv_path=schedule_path,
    )

    expected_total = 0
    expected_batches = schedule.get('expected_by_batch', {})
    if expected_batches.get('cumulative'):
        expected_total = expected_batches['cumulative'][-1]

    # Burn-in status is always relative to the expected production total.
    burnin_expected = int(expected_total) if expected_total else 0
    if burnin_expected <= 0:
        burnin_expected = max(total_boards, 0)
    not_yet_produced = max(burnin_expected - total_boards, 0) if burnin_expected else 0
    not_received = not_yet_produced
    passed_before_last_after_failed, passed_after_burnin_pie = _burnin_pass_groups(boards, serial_to_tests)

    return {
        'success': True,
        'timestamp': datetime.utcnow().strftime('%Y-%m-%d - %H:%M:%S'),
        'total_boards': total_boards,
        'post_burnin_pass_rate': round(post_burnin_pass_rate, 1),
        'yield_failure_rate': round(yield_failure_rate, 1),
        'yield_after_burnin': {
            'passed': yield_passed,
            'failed': yield_failed,
        },
        'burnin_status': {
            'expected': burnin_expected,
            'received_burned_in': burned_in,
            'received_not_burned_in': received_not_burned_in,
            'not_received': not_received,
            # Compatibility aliases
            'burned_in': burned_in,
            'not_burned_in': received_not_burned_in,
        },
        'total_produced': {
            'expected': burnin_expected,
            'produced': total_boards,
            'passed_after_burnin': passed_after_burnin,
            'failed_after_burnin': failed_after_burnin,
            'no_test': no_test_count,
            'no_test_or_untested': no_test_or_untested,
            'not_yet_produced': not_yet_produced,
        },
        'cumulative_by_batch': cumulative_by_batch,
        'cumulative_by_time': cumulative_by_time,
        'burnin_timeline': burnin_timeline,
        'schedule': schedule,
        'production_config': production_config,
        'colors': COLORS,
        'passed_before_not_after': passed_before_last_after_failed,
        'passed_before_last_after_failed': passed_before_last_after_failed,
        'passed_after_burnin': passed_after_burnin_pie,
    }
