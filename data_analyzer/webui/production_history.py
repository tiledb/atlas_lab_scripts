"""Production history milestones and as-of brick-wall / chart snapshots."""

from collections import defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path

from production_summary import (
    COLORS,
    _parse_datetime,
    decode_serial,
)
from plot_cache import cache_banner_html, format_cache_stamp

MAX_BRICK_WALL_BATCH = 13
HISTORY_WALL_POSITIONS = 80  # rows 0 .. 79
HISTORY_WALL_MAX_BATCH = 13  # columns B0 .. B13
HISTORY_CACHE_DIR = Path('/var/www/html/drive/production_plots/history')
HISTORY_INDEX_NAME = 'index.json'
HISTORY_CACHE_VERSION = 13
HISTORY_PNG_WALL_BRICK_H = 2
HISTORY_PNG_WALL_BRICK_W = 14
HISTORY_HTML_WALL_BRICK_H = 8
HISTORY_CHART_Y_MIN = -40
HISTORY_CHART_Y_MAX = 1000


def _fmt(dt):
    if not dt:
        return None
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return str(dt)


def _week_key(dt):
    iso = dt.isocalendar()
    return f'{iso.year}-W{iso.week:02d}'


def _week_label(dt):
    iso = dt.isocalendar()
    # Monday of that ISO week
    monday = dt - timedelta(days=dt.weekday())
    sunday = monday + timedelta(days=6)
    return {
        'week_key': _week_key(dt),
        'year': iso.year,
        'week': iso.week,
        'label': f'Week {iso.week}, {iso.year}',
        'range_label': f'{monday.strftime("%b %d")} – {sunday.strftime("%b %d, %Y")}',
        'week_start': monday.strftime('%Y-%m-%d'),
        'week_end': sunday.strftime('%Y-%m-%d'),
    }


def _board_serials_from_benchtest(bt):
    serials = []
    for slot_num in range(1, 5):
        serial = bt.get(f'db_slot{slot_num}')
        if serial:
            serials.append(serial)
    return serials


def _history_plot_date_bounds():
    """Configured history plot start/end as datetimes (None = unbounded)."""
    try:
        from production_config import load_production_config
        config = load_production_config()
    except Exception:
        config = {}
    start = _config_date_bound(config.get('history_plot_start_date'), end_of_day=False)
    end = _config_date_bound(config.get('history_plot_end_date'), end_of_day=True)
    return start, end


def filter_milestones_by_history_plot_range(milestones):
    """Keep only milestones inside the configured history plot date range."""
    start, end = _history_plot_date_bounds()
    if not start and not end:
        return list(milestones or [])

    filtered = []
    for item in milestones or []:
        dt = item.get('timestamp_dt') or _parse_datetime(item.get('timestamp'))
        if not dt:
            continue
        if start and dt < start:
            continue
        if end and dt > end:
            continue
        filtered.append(item)
    return filtered


def _build_weeks_from_milestones(milestones):
    weeks = []
    week_map = {}
    for item in milestones:
        key = item['week_key']
        if key not in week_map:
            week_map[key] = {
                'week_key': key,
                'label': item['week_label'],
                'range_label': item['week_range_label'],
                'week_start': item['week_start'],
                'week_end': item['week_end'],
                'milestone_indices': [],
                'count': 0,
            }
            weeks.append(week_map[key])
        week_map[key]['milestone_indices'].append(item['index'])
        week_map[key]['count'] += 1
    return weeks


def collect_milestones(db_rows, benchtest_rows):
    """Build chronological procedure milestones from benchtests and burn-in."""
    milestones = []
    seen = set()

    def add_milestone(dt, kind, serials, label, detail=None, ref_id=None):
        if not dt:
            return
        key = (kind, _fmt(dt), tuple(sorted(str(s) for s in serials)), ref_id)
        if key in seen:
            return
        seen.add(key)
        week = _week_label(dt)
        milestones.append({
            'id': f'{kind}-{_fmt(dt)}-{ref_id or "-".join(str(s) for s in serials[:2])}',
            'timestamp': _fmt(dt),
            'timestamp_dt': dt,
            'kind': kind,
            'label': label,
            'detail': detail,
            'serials': [str(s) for s in serials],
            'ref_id': ref_id,
            'week_key': week['week_key'],
            'week_label': week['label'],
            'week_range_label': week['range_label'],
            'week_start': week['week_start'],
            'week_end': week['week_end'],
        })

    for bt in benchtest_rows:
        if bt.get('test_pass') == -1:
            continue
        serials = _board_serials_from_benchtest(bt)
        if not serials:
            continue
        start_dt = _parse_datetime(bt.get('test_start'))
        stop_dt = _parse_datetime(bt.get('test_stop'))
        bt_id = bt.get('id')
        pass_label = {
            1: 'pass',
            0: 'fail',
            None: 'unknown',
        }.get(bt.get('test_pass'), 'unknown')
        if start_dt:
            add_milestone(
                start_dt,
                'benchtest_start',
                serials,
                f'Benchtest {bt_id} started',
                detail=f'{len(serials)} board(s)',
                ref_id=bt_id,
            )
        if stop_dt:
            add_milestone(
                stop_dt,
                'benchtest_stop',
                serials,
                f'Benchtest {bt_id} finished ({pass_label})',
                detail=f'{len(serials)} board(s) · {pass_label}',
                ref_id=bt_id,
            )

    for row in db_rows:
        serial = row.get('serial_no')
        decoded = decode_serial(serial)
        if decoded['tag'] == 90:
            continue
        start_dt = _parse_datetime(row.get('burn_in_start'))
        stop_dt = _parse_datetime(row.get('burn_in_stop'))
        if start_dt:
            add_milestone(
                start_dt,
                'burn_in_start',
                [serial],
                f'Burn-in start · {serial}',
                detail=f'Batch {decoded["batch"]} pos {decoded["position"]}',
                ref_id=str(serial),
            )
        if stop_dt:
            add_milestone(
                stop_dt,
                'burn_in_stop',
                [serial],
                f'Burn-in stop · {serial}',
                detail=f'Batch {decoded["batch"]} pos {decoded["position"]}',
                ref_id=str(serial),
            )

    milestones.sort(key=lambda item: (item['timestamp_dt'], item['kind'], item['id']))
    milestones = filter_milestones_by_history_plot_range(milestones)

    # Stable numeric index for the scrubber (after date-range filtering).
    for index, item in enumerate(milestones):
        item['index'] = index
        item.pop('timestamp_dt', None)

    weeks = _build_weeks_from_milestones(milestones)

    return {
        'success': True,
        'milestones': milestones,
        'weeks': weeks,
        'total': len(milestones),
    }


def _latest_benchtest_for_serial(serial, benchtests_by_serial, as_of_dt):
    latest = None
    latest_dt = None
    for bt in benchtests_by_serial.get(str(serial), []):
        if bt.get('test_pass') == -1:
            continue
        stop_dt = _parse_datetime(bt.get('test_stop'))
        start_dt = _parse_datetime(bt.get('test_start'))
        event_dt = stop_dt or start_dt
        if not event_dt or event_dt > as_of_dt:
            continue
        if latest_dt is None or event_dt > latest_dt:
            latest_dt = event_dt
            latest = bt
    return latest


def _status_as_of(serial, row, benchtests_by_serial, as_of_dt):
    """Approximate db_status/e_test/p_test from procedures known by as_of_dt."""
    latest = _latest_benchtest_for_serial(serial, benchtests_by_serial, as_of_dt)
    if latest is None:
        return None, None, None, False

    test_pass = latest.get('test_pass')
    if test_pass == 1:
        return 1, 1, 1, True
    if test_pass == 0:
        return 0, 0, 0, True
    # Unknown / in progress after a started test: fall back to current flags if present
    return row.get('db_status'), row.get('e_test'), row.get('p_test'), True


def _board_first_seen(serial, row, benchtests_by_serial):
    candidates = []
    for bt in benchtests_by_serial.get(str(serial), []):
        for field in ('test_start', 'test_stop'):
            dt = _parse_datetime(bt.get(field))
            if dt:
                candidates.append(dt)
    for field in ('burn_in_start', 'burn_in_stop'):
        dt = _parse_datetime(row.get(field))
        if dt:
            candidates.append(dt)
    return min(candidates) if candidates else None


def _benchtests_for_board_as_of(serial, benchtests_by_serial, as_of_dt, burn_in_stop_dt):
    result = []
    has_post = False
    for bt in benchtests_by_serial.get(str(serial), []):
        if bt.get('test_pass') == -1:
            continue
        stop_dt = _parse_datetime(bt.get('test_stop'))
        start_dt = _parse_datetime(bt.get('test_start'))
        event_dt = stop_dt or start_dt
        if not event_dt or event_dt > as_of_dt:
            continue

        slot_name = None
        for slot_num in range(1, 5):
            if str(bt.get(f'db_slot{slot_num}') or '') == str(serial):
                slot_name = f'MD{slot_num}'
                break

        result.append({
            'benchtest_id': bt.get('id'),
            'benchtest_slot': slot_name,
            'test_pass': bt.get('test_pass'),
            'test_stop': _fmt(stop_dt),
            'test_op': bt.get('test_op'),
            'failed_tests': None,
            'burned': None,
        })
        if burn_in_stop_dt and stop_dt and stop_dt > burn_in_stop_dt:
            has_post = True
    return result, has_post


def build_history_snapshot(db_rows, benchtest_rows, as_of):
    """Brick wall + cumulative_by_time + burnin_timeline as of a timestamp."""
    as_of_dt = _parse_datetime(as_of)
    if not as_of_dt:
        return {'success': False, 'error': f'Invalid as_of timestamp: {as_of}'}

    benchtests_by_serial = defaultdict(list)
    for bt in benchtest_rows:
        for serial in _board_serials_from_benchtest(bt):
            benchtests_by_serial[str(serial)].append(bt)

    boards_by_batch = {}
    cumulative_points = {'passed': [], 'failed': [], 'no_test': []}
    time_counts = {'passed': 0, 'failed': 0, 'no_test': 0}
    boards_with_time = []
    burnin_boards = []

    for row in db_rows:
        serial = row['serial_no']
        decoded = decode_serial(serial)
        if decoded['tag'] == 90:
            continue
        if decoded['batch'] > HISTORY_WALL_MAX_BATCH:
            continue
        if decoded['position'] < 0 or decoded['position'] >= HISTORY_WALL_POSITIONS:
            continue

        first_seen = _board_first_seen(serial, row, benchtests_by_serial)
        if not first_seen or first_seen > as_of_dt:
            continue

        burn_in_start_dt = _parse_datetime(row.get('burn_in_start'))
        burn_in_stop_dt = _parse_datetime(row.get('burn_in_stop'))
        eff_start = burn_in_start_dt if burn_in_start_dt and burn_in_start_dt <= as_of_dt else None
        eff_stop = burn_in_stop_dt if burn_in_stop_dt and burn_in_stop_dt <= as_of_dt else None

        db_status, e_test, p_test, has_any_test = _status_as_of(
            serial, row, benchtests_by_serial, as_of_dt,
        )
        board_benchtests, has_post = _benchtests_for_board_as_of(
            serial, benchtests_by_serial, as_of_dt, eff_stop,
        )

        # SFP fields: only trust current values once the board has been seen;
        # if no test yet, leave as current physical assignment (lots/SFP).
        board = {
            'serial_no': serial,
            'tag': decoded['tag'],
            'batch': decoded['batch'],
            'position': decoded['position'],
            'db_status': db_status,
            'burn_in': 1 if eff_stop else 0,
            'burn_in_start': _fmt(eff_start),
            'burn_in_stop': _fmt(eff_stop),
            'kin_lot': row.get('kin_lot'),
            'pro_lot': row.get('pro_lot'),
            'gbt_lot': row.get('gbt_lot'),
            'ina_lot': row.get('ina_lot'),
            'ltm_lot': row.get('ltm_lot'),
            'mos_lot': row.get('mos_lot'),
            'op4_lot': row.get('op4_lot'),
            'ok4_lot': row.get('ok4_lot'),
            'ok1_lot': row.get('ok1_lot'),
            'mem_lot': row.get('mem_lot'),
            'sfp_lot': row.get('sfp_lot'),
            'e_test': e_test,
            'p_test': p_test,
            'a0': row.get('a0'),
            'a1': row.get('a1'),
            'b0': row.get('b0'),
            'b1': row.get('b1'),
            'benchtests': board_benchtests,
            'has_benchtest': len(board_benchtests) > 0,
            'has_post_burnin_test': has_post,
            'comments': [],
        }

        batch = decoded['batch']
        boards_by_batch.setdefault(batch, []).append(board)

        # Classification for cumulative chart (mirror summary rules on as-of flags)
        if (db_status == 0 or e_test == 0 or p_test == 0) and board['has_benchtest']:
            classification = 'failed'
        elif db_status is None or e_test is None or p_test is None or not has_any_test:
            classification = 'no_test'
        elif any(board.get(field) is None for field in ('a0', 'a1', 'b0', 'b1')):
            classification = 'no_test'
        elif db_status == 1 and e_test == 1 and p_test == 1:
            classification = 'passed'
        else:
            classification = 'failed'

        latest_bt = _latest_benchtest_for_serial(serial, benchtests_by_serial, as_of_dt)
        test_stop = None
        if latest_bt:
            test_stop = _parse_datetime(latest_bt.get('test_stop')) or _parse_datetime(latest_bt.get('test_start'))
        if test_stop and test_stop <= as_of_dt:
            boards_with_time.append({
                'serial': serial,
                'test_stop': test_stop,
                'classification': classification,
            })

        if eff_start and eff_stop:
            burnin_boards.append({
                'serial': serial,
                'batch': decoded['batch'],
                'burn_in_start': eff_start,
                'burn_in_stop': eff_stop,
            })

    for batch in boards_by_batch:
        boards_by_batch[batch].sort(key=lambda item: item['position'])

    boards_with_time.sort(key=lambda item: item['test_stop'])
    for item in boards_with_time:
        cls = item['classification']
        time_counts[cls] += 1
        cumulative_points[cls].append({
            'x': _fmt(item['test_stop']),
            'y': time_counts[cls],
            'serial': item['serial'],
        })

    burnin_boards.sort(key=lambda item: item['burn_in_start'])
    burnin_timeline = []
    for index, item in enumerate(burnin_boards, start=1):
        start_dt = item['burn_in_start']
        stop_dt = item['burn_in_stop']
        center_dt = start_dt + (stop_dt - start_dt) / 2
        burnin_timeline.append({
            'serial': item['serial'],
            'batch': item['batch'],
            'burn_in_start': _fmt(start_dt),
            'burn_in_stop': _fmt(stop_dt),
            'burn_in_center': _fmt(center_dt),
            'error_minus_ms': (center_dt - start_dt).total_seconds() * 1000,
            'error_plus_ms': (stop_dt - center_dt).total_seconds() * 1000,
            'y_pos': index,
        })

    board_count = sum(len(boards) for boards in boards_by_batch.values())
    pies = _compute_history_pies(boards_by_batch, board_count)
    return {
        'success': True,
        'as_of': _fmt(as_of_dt),
        'board_count': board_count,
        'wall_rows': HISTORY_WALL_POSITIONS,
        'wall_max_batch': HISTORY_WALL_MAX_BATCH,
        'boards_by_batch': boards_by_batch,
        'cumulative_by_time': cumulative_points,
        'burnin_timeline': burnin_timeline,
        'pies': pies,
        'colors': COLORS,
    }


def _expected_total_boards():
    try:
        from production_config import load_production_config
        from production_schedule import build_schedule_projections, load_production_schedule
        from production_summary import SCHEDULE_CSV_PATH
        schedule_entries = load_production_schedule(SCHEDULE_CSV_PATH)
        production_config = load_production_config()
        schedule = build_schedule_projections(
            schedule_entries,
            production_config,
            schedule_csv_path=SCHEDULE_CSV_PATH,
        )
        expected = (schedule.get('expected_by_batch') or {}).get('cumulative') or []
        if expected:
            return int(expected[-1])
    except Exception as exc:
        print(f'History expected-total fallback: {exc}')
    return HISTORY_WALL_POSITIONS * (HISTORY_WALL_MAX_BATCH + 1)


def _compute_history_pies(boards_by_batch, board_count):
    boards = []
    for batch_boards in (boards_by_batch or {}).values():
        boards.extend(batch_boards or [])

    yield_passed = 0
    yield_failed = 0
    burned_in = 0
    for board in boards:
        if board.get('burn_in_stop'):
            burned_in += 1
        if not board.get('has_post_burnin_test'):
            continue
        status = board.get('db_status')
        e_test = board.get('e_test')
        p_test = board.get('p_test')
        if status == 1 and e_test == 1 and p_test == 1:
            yield_passed += 1
        else:
            yield_failed += 1

    not_burned_in = max(board_count - burned_in, 0)
    tested = yield_passed + yield_failed
    no_test_or_untested = max(board_count - yield_passed - yield_failed, 0)
    expected = _expected_total_boards()
    not_yet_produced = max(expected - board_count, 0)
    yield_failure_rate = round((yield_failed / tested * 100) if tested else 0.0, 1)

    return {
        'yield_after_burnin': {'passed': yield_passed, 'failed': yield_failed},
        'yield_failure_rate': yield_failure_rate,
        'burnin_status': {
            'expected': expected,
            'received_burned_in': burned_in,
            'received_not_burned_in': not_burned_in,
            'not_received': not_yet_produced,
            # Compatibility aliases
            'burned_in': burned_in,
            'not_burned_in': not_burned_in,
        },
        'total_produced': {
            'expected': expected,
            'produced': board_count,
            'passed_after_burnin': yield_passed,
            'failed_after_burnin': yield_failed,
            'no_test_or_untested': no_test_or_untested,
            'not_yet_produced': not_yet_produced,
        },
    }


def _collect_time_bounds(snapshot):
    values = []
    for key in ('passed', 'failed', 'no_test'):
        for point in (snapshot.get('cumulative_by_time') or {}).get(key) or []:
            dt = _parse_datetime(point.get('x'))
            if dt:
                values.append(dt)
    for item in snapshot.get('burnin_timeline') or []:
        for field in ('burn_in_start', 'burn_in_stop', 'burn_in_center'):
            dt = _parse_datetime(item.get(field))
            if dt:
                values.append(dt)
    if not values:
        return None, None
    return min(values), max(values)


def _pad_time_axis(start_dt, end_dt, pad=True):
    if not start_dt or not end_dt:
        return None
    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt
    if not pad or start_dt == end_dt:
        # Keep a tiny span so Plotly still draws ticks when only one milestone exists.
        if start_dt == end_dt:
            end_dt = end_dt + timedelta(hours=1)
        return {
            'start': _fmt(start_dt),
            'end': _fmt(end_dt),
        }
    span = (end_dt - start_dt).total_seconds()
    pad_seconds = max(span * 0.02, 24 * 60 * 60)
    delta = timedelta(seconds=pad_seconds)
    return {
        'start': _fmt(start_dt - delta),
        'end': _fmt(end_dt + delta),
    }


def _config_date_bound(date_string, end_of_day=False):
    text = str(date_string or '').strip()
    if not text:
        return None
    part = text.split(' ')[0]
    try:
        dt = datetime.strptime(part, '%Y-%m-%d')
    except ValueError:
        return None
    if end_of_day:
        return dt.replace(hour=23, minute=59, second=59)
    return dt.replace(hour=0, minute=0, second=0)


def apply_history_plot_date_overrides(axis):
    """Override natural axis bounds with configured history plot start/end dates."""
    if not axis:
        return axis
    natural_start = _parse_datetime(axis.get('start'))
    natural_end = _parse_datetime(axis.get('end'))
    cfg_start, cfg_end = _history_plot_date_bounds()
    start_dt = cfg_start or natural_start
    end_dt = cfg_end or natural_end
    return _pad_time_axis(start_dt, end_dt, pad=False) or axis


def compute_milestone_time_axis(milestones):
    """X-axis from first milestone timestamp → last milestone timestamp."""
    values = []
    for item in milestones or []:
        dt = _parse_datetime(item.get('timestamp'))
        if dt:
            values.append(dt)
    if not values:
        return None
    return apply_history_plot_date_overrides(
        _pad_time_axis(min(values), max(values), pad=False)
    )


def compute_source_time_axis(db_rows, benchtest_rows, milestones=None):
    """Prefer first→last milestone; fall back to raw procedure times only if needed."""
    axis = compute_milestone_time_axis(milestones)
    if axis:
        return axis
    values = []
    for bt in benchtest_rows or []:
        if bt.get('test_pass') == -1:
            continue
        for field in ('test_start', 'test_stop'):
            dt = _parse_datetime(bt.get(field))
            if dt:
                values.append(dt)
    for row in db_rows or []:
        decoded = decode_serial(row.get('serial_no'))
        if decoded['tag'] == 90:
            continue
        for field in ('burn_in_start', 'burn_in_stop'):
            dt = _parse_datetime(row.get(field))
            if dt:
                values.append(dt)
    if not values:
        return None
    return apply_history_plot_date_overrides(
        _pad_time_axis(min(values), max(values), pad=False)
    )


def compute_global_time_axis(milestones, snapshots_by_index):
    starts = []
    ends = []
    for milestone in milestones:
        dt = _parse_datetime(milestone.get('timestamp'))
        if dt:
            starts.append(dt)
            ends.append(dt)
    for snapshot in snapshots_by_index.values():
        lo, hi = _collect_time_bounds(snapshot)
        if lo:
            starts.append(lo)
        if hi:
            ends.append(hi)
    if not starts or not ends:
        return None
    return apply_history_plot_date_overrides(
        _pad_time_axis(min(starts), max(ends), pad=False)
    )


def _json_default(value):
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return str(value)


def _snapshot_stem(index, timestamp):
    safe = str(timestamp or 'unknown').replace(' ', 'T').replace(':', '')
    return f'milestone_{int(index):04d}_{safe}'


def snapshot_paths(index, timestamp):
    stem = _snapshot_stem(index, timestamp)
    base = HISTORY_CACHE_DIR / 'snapshots'
    return {
        'stem': stem,
        'json': base / f'{stem}.json',
        'html': base / f'{stem}.html',
        'wall_png': base / f'{stem}_wall.png',
        'cumulative_png': base / f'{stem}_cumulative.png',
        'burnin_png': base / f'{stem}_burnin.png',
        'yield_pie_png': base / f'{stem}_yield_pie.png',
        'burnin_pie_png': base / f'{stem}_burnin_pie.png',
        'produced_pie_png': base / f'{stem}_produced_pie.png',
        'json_name': f'snapshots/{stem}.json',
        'html_name': f'snapshots/{stem}.html',
        'wall_png_name': f'snapshots/{stem}_wall.png',
        'cumulative_png_name': f'snapshots/{stem}_cumulative.png',
        'burnin_png_name': f'snapshots/{stem}_burnin.png',
        'yield_pie_png_name': f'snapshots/{stem}_yield_pie.png',
        'burnin_pie_png_name': f'snapshots/{stem}_burnin_pie.png',
        'produced_pie_png_name': f'snapshots/{stem}_produced_pie.png',
    }


def _board_color(board):
    status = board.get('db_status')
    e_test = board.get('e_test')
    p_test = board.get('p_test')
    has_benchtest = board.get('has_benchtest')
    has_sfp = board.get('a0') and board.get('a1') and board.get('b0') and board.get('b1')
    has_post = board.get('has_post_burnin_test')
    if (status == 0 or e_test == 0 or p_test == 0) and has_benchtest:
        return '#EF553B'
    if status == 0 and not has_benchtest:
        return '#FECB52'
    if status is None or e_test is None or p_test is None:
        return '#FECB52'
    if not has_sfp:
        return '#90EE90'
    if status == 1 and e_test == 1 and p_test == 1 and not has_post:
        return '#FF9800'
    if status == 1 and e_test == 1 and p_test == 1 and has_post:
        return '#00CC96'
    return '#EF553B'


def _hex_to_rgb(color):
    value = (color or '#CCCCCC').lstrip('#')
    if len(value) != 6:
        return (200, 200, 200)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _history_axis_tick_counts():
    try:
        from production_config import load_production_config
        config = load_production_config()
    except Exception:
        config = {}
    try:
        x_ticks = int(config.get('history_plot_x_ticks', 8))
    except (TypeError, ValueError):
        x_ticks = 8
    try:
        y_ticks = int(config.get('history_plot_y_ticks', 6))
    except (TypeError, ValueError):
        y_ticks = 6
    return max(2, min(50, x_ticks)), max(2, min(50, y_ticks))


def _history_y_dtick(y_ticks):
    """Even spacing across 0..HISTORY_CHART_Y_MAX for the configured tick count."""
    ticks = max(2, int(y_ticks or 6))
    return max(1, int(round(HISTORY_CHART_Y_MAX / (ticks - 1))))


def _history_xaxis(title, time_axis):
    x_range = None
    if time_axis and time_axis.get('start') and time_axis.get('end'):
        x_range = [time_axis['start'], time_axis['end']]
    x_ticks, _ = _history_axis_tick_counts()
    return dict(
        title=title,
        type='date',
        range=x_range,
        autorange=not bool(x_range),
        tickformat='%Y-%m-%d',
        tickangle=-30,
        showticklabels=True,
        nticks=x_ticks,
        automargin=True,
    )


def _history_yaxis():
    _, y_ticks = _history_axis_tick_counts()
    return dict(
        title='Cumulative Board Count',
        range=[HISTORY_CHART_Y_MIN, HISTORY_CHART_Y_MAX],
        autorange=False,
        fixedrange=True,
        rangemode='normal',
        tick0=0,
        dtick=_history_y_dtick(y_ticks),
        nticks=y_ticks,
        zeroline=True,
        zerolinewidth=1,
        zerolinecolor='rgba(120,120,120,0.55)',
    )


def _lock_history_chart_y_axis(fig):
    """Force fixed Y for static PNG/HTML export (Kaleido ignores range if autorange is on)."""
    if fig is None:
        return
    _, y_ticks = _history_axis_tick_counts()
    fig.update_yaxes(
        range=[HISTORY_CHART_Y_MIN, HISTORY_CHART_Y_MAX],
        autorange=False,
        fixedrange=True,
        rangemode='normal',
        tick0=0,
        dtick=_history_y_dtick(y_ticks),
        nticks=y_ticks,
        zeroline=True,
        zerolinewidth=1,
        zerolinecolor='rgba(120,120,120,0.55)',
        title_text='Cumulative Board Count',
    )


def _calendar_comment_plot_dt(date_string):
    """Match production-summary calendar label X placement (date at noon)."""
    part = str(date_string or '').split(' ')[0]
    try:
        return datetime.strptime(part, '%Y-%m-%d').replace(hour=12, minute=0, second=0)
    except Exception:
        return None


def _load_history_calendar_comments():
    try:
        from production_schedule import load_schedule_comments
        from production_summary import SCHEDULE_CSV_PATH
        return load_schedule_comments(SCHEDULE_CSV_PATH) or []
    except Exception as exc:
        print(f'History calendar comments unavailable: {exc}')
        return []


def _filter_comments_in_time_axis(comments, time_axis):
    if not comments:
        return []
    start = _parse_datetime((time_axis or {}).get('start')) if time_axis else None
    end = _parse_datetime((time_axis or {}).get('end')) if time_axis else None
    if not start or not end:
        return list(comments)

    start_day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end_day = end.replace(hour=23, minute=59, second=59, microsecond=999999)
    filtered = []
    for item in comments:
        plot_dt = _calendar_comment_plot_dt(item.get('date'))
        if plot_dt and start_day <= plot_dt <= end_day:
            filtered.append(item)
    return filtered


def _build_calendar_label_layout(comments, y_max=HISTORY_CHART_Y_MAX):
    """Vertical dotted lines + angled annotations (same idea as dashboard JS)."""
    if not comments:
        return [], []

    try:
        import plotly.graph_objects as go
    except ImportError:
        return [], []

    top_y = y_max * 0.98
    step = max(y_max * 0.08, 1.0)
    annotations = []
    traces = []
    line_point_count = 25

    for index, item in enumerate(comments):
        plot_dt = _calendar_comment_plot_dt(item.get('date'))
        if not plot_dt:
            continue
        comment = item.get('comment') or ''
        date_label = plot_dt.strftime('%Y-%m-%d')
        annotations.append(dict(
            x=plot_dt,
            y=max(top_y - (index % 5) * step, step * 0.5),
            xref='x',
            yref='y',
            text=comment,
            showarrow=False,
            textangle=-55,
            font=dict(size=9, color='#555'),
            xanchor='left',
        ))
        xs = [plot_dt] * line_point_count
        ys = [(top_y * i) / (line_point_count - 1) for i in range(line_point_count)]
        traces.append(go.Scatter(
            x=xs,
            y=ys,
            mode='lines',
            line=dict(color='rgba(120, 120, 120, 0.45)', width=1, dash='dot'),
            customdata=[[date_label, comment]] * line_point_count,
            hovertemplate='<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>',
            showlegend=False,
            name='Calendar label',
        ))

    return annotations, traces


def _history_chart_figures(snapshot):
    try:
        import plotly.graph_objects as go
    except ImportError as exc:
        print(f'Plotly not available for history charts: {exc}')
        return None, None

    colors = snapshot.get('colors') or {}
    time_axis = snapshot.get('time_axis') or {}
    comments = _filter_comments_in_time_axis(
        _load_history_calendar_comments(),
        time_axis,
    )
    time_annotations, time_label_traces = _build_calendar_label_layout(comments)
    burn_annotations, burn_label_traces = _build_calendar_label_layout(comments)

    by_time = snapshot.get('cumulative_by_time') or {}
    fig_time = go.Figure()
    for key, label, color_key in (
        ('passed', 'Passed', 'passed'),
        ('failed', 'Failed', 'failed'),
        ('no_test', 'No Test', 'no_test'),
    ):
        points = by_time.get(key) or []
        color = colors.get(color_key, '#00CC96')
        if points:
            fig_time.add_trace(go.Scatter(
                x=[point.get('x') for point in points],
                y=[point.get('y') for point in points],
                text=[point.get('serial') for point in points],
                mode='lines+markers',
                name=label,
                line=dict(color=color, width=2),
                marker=dict(size=7, color=color),
                cliponaxis=False,
                showlegend=True,
                hovertemplate='%{x}<br>%{y}<br>Serial: %{text}<extra></extra>',
            ))
        else:
            # Keep legend entry even when this series has no points yet.
            fig_time.add_trace(go.Scatter(
                x=[None],
                y=[None],
                mode='lines+markers',
                name=label,
                line=dict(color=color, width=2),
                marker=dict(size=7, color=color),
                showlegend=True,
                hoverinfo='skip',
            ))
    for trace in time_label_traces:
        fig_time.add_trace(trace)
    fig_time.update_layout(
        title='Cumulative Board Count (by Time)',
        height=560,
        margin=dict(t=50, r=30, b=140, l=60),
        xaxis=_history_xaxis('Test Passed Time', time_axis),
        yaxis=_history_yaxis(),
        showlegend=True,
        legend=dict(
            orientation='h',
            y=-0.28,
            yanchor='top',
            x=0.0,
            xanchor='left',
            bgcolor='rgba(255,255,255,0.85)',
            traceorder='normal',
        ),
        paper_bgcolor='white',
        plot_bgcolor='white',
        autosize=False,
        annotations=time_annotations,
    )

    timeline = snapshot.get('burnin_timeline') or []
    fig_burn = go.Figure()
    burn_color = colors.get('burnin_timeline', '#AB63FA')
    if timeline:
        fig_burn.add_trace(go.Scatter(
            x=[item.get('burn_in_center') for item in timeline],
            y=[item.get('y_pos') for item in timeline],
            mode='markers',
            name='Burned In',
            marker=dict(color=burn_color, size=9),
            cliponaxis=False,
            showlegend=True,
            error_x=dict(
                type='data',
                array=[item.get('error_plus_ms', 0) for item in timeline],
                arrayminus=[item.get('error_minus_ms', 0) for item in timeline],
                symmetric=False,
                color=burn_color,
                thickness=3,
                width=8,
            ),
            text=[
                (
                    f"Serial: {item.get('serial')}<br>Batch: {item.get('batch')}<br>"
                    f"Start: {item.get('burn_in_start')}<br>Stop: {item.get('burn_in_stop')}"
                )
                for item in timeline
            ],
            hovertemplate='%{text}<extra></extra>',
        ))
    else:
        fig_burn.add_trace(go.Scatter(
            x=[None],
            y=[None],
            mode='markers',
            name='Burned In',
            marker=dict(color=burn_color, size=9),
            showlegend=True,
            hoverinfo='skip',
        ))
    for trace in burn_label_traces:
        fig_burn.add_trace(trace)
    fig_burn.update_layout(
        title='Burn-In Timeline',
        height=560,
        margin=dict(t=50, r=30, b=140, l=60),
        xaxis=_history_xaxis('Burn-In Time', time_axis),
        yaxis=_history_yaxis(),
        showlegend=True,
        legend=dict(
            orientation='h',
            y=-0.28,
            yanchor='top',
            x=0.0,
            xanchor='left',
            bgcolor='rgba(255,255,255,0.85)',
            traceorder='normal',
        ),
        paper_bgcolor='white',
        plot_bgcolor='white',
        autosize=False,
        annotations=burn_annotations,
    )
    return fig_time, fig_burn


def _ensure_full_pie_values(labels, values, colors, empty_label='No data yet', empty_color='#B6B6B6'):
    """Always return a drawable full pie (never an empty/blank chart)."""
    cleaned_values = [max(0, float(v or 0)) for v in values]
    if sum(cleaned_values) > 0:
        return labels, cleaned_values, colors
    return [empty_label], [1], [empty_color]


def _history_pie_layout(title):
    return dict(
        title=None,
        height=360,
        width=520,
        margin=dict(t=20, r=20, b=20, l=10),
        showlegend=True,
        legend=dict(
            orientation='v',
            x=0.62,
            y=1.0,
            xanchor='left',
            yanchor='top',
            bgcolor='rgba(0,0,0,0)',
            borderwidth=0,
            font=dict(size=15),
            title=dict(
                text=title,
                font=dict(size=16, color='#333'),
                side='top',
            ),
            traceorder='normal',
            itemsizing='constant',
            itemwidth=40,
        ),
        paper_bgcolor='white',
        plot_bgcolor='white',
        autosize=False,
    )


def _history_pie_trace(labels, values, colors):
    import plotly.graph_objects as go
    return go.Pie(
        labels=labels,
        values=values,
        marker=dict(colors=colors),
        hole=0,
        sort=False,
        textinfo='percent',
        textposition='inside',
        textfont=dict(size=14),
        domain=dict(x=[0.0, 0.58], y=[0.05, 0.95]),
        showlegend=True,
    )


def _history_pie_figures(snapshot):
    try:
        import plotly.graph_objects as go
    except ImportError as exc:
        print(f'Plotly not available for history pies: {exc}')
        return None, None, None

    colors = snapshot.get('colors') or {}
    pies = snapshot.get('pies') or {}
    yield_data = pies.get('yield_after_burnin') or {}
    burnin = pies.get('burnin_status') or {}
    produced = pies.get('total_produced') or {}
    failure_rate = pies.get('yield_failure_rate', 0)

    yield_labels, yield_values, yield_colors = _ensure_full_pie_values(
        ['Passed', 'Failed'],
        [yield_data.get('passed', 0), yield_data.get('failed', 0)],
        [colors.get('passed', '#00CC96'), colors.get('failed', '#EF553B')],
        empty_label='No tested boards yet',
    )
    fig_yield = go.Figure(data=[_history_pie_trace(yield_labels, yield_values, yield_colors)])
    fig_yield.update_layout(
        **_history_pie_layout(f'Yield after Burn-In<br>(Failure Rate: {failure_rate}%)')
    )

    burnin_labels, burnin_values, burnin_colors = _ensure_full_pie_values(
        ['Received Burned In', 'Received Not Burned In', 'Not Received'],
        [
            burnin.get('received_burned_in', burnin.get('burned_in', 0)),
            burnin.get('received_not_burned_in', burnin.get('not_burned_in', 0)),
            burnin.get('not_received', 0),
        ],
        [
            colors.get('burned_in', '#4caf50'),
            colors.get('not_burned_in', '#f44336'),
            colors.get('not_received', colors.get('not_yet_produced', '#B6B6B6')),
        ],
        empty_label='No expected boards yet',
    )
    fig_burnin = go.Figure(data=[_history_pie_trace(burnin_labels, burnin_values, burnin_colors)])
    expected_burnin = burnin.get('expected') or sum(burnin_values)
    fig_burnin.update_layout(
        **_history_pie_layout(f'Burn-In Status<br>(of {expected_burnin} expected)')
    )

    produced_labels, produced_values, produced_colors = _ensure_full_pie_values(
        ['Passed after Burn-In', 'Failed after Burn-In', 'No Test / Untested', 'Not Yet Produced'],
        [
            produced.get('passed_after_burnin', 0),
            produced.get('failed_after_burnin', 0),
            produced.get('no_test_or_untested', 0),
            produced.get('not_yet_produced', 0),
        ],
        [
            colors.get('passed', '#00CC96'),
            colors.get('failed', '#EF553B'),
            colors.get('no_test', '#FECB52'),
            colors.get('not_yet_produced', '#B6B6B6'),
        ],
        empty_label='No boards yet',
    )
    fig_produced = go.Figure(data=[_history_pie_trace(produced_labels, produced_values, produced_colors)])
    fig_produced.update_layout(
        **_history_pie_layout(
            f"Total Produced vs Expected<br>({produced.get('produced', 0)} / {produced.get('expected', 0)})"
        )
    )
    return fig_yield, fig_burnin, fig_produced


def write_history_wall_png(snapshot, path):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        print(f'Pillow not available for history wall PNG: {exc}')
        return False

    boards_by_batch = snapshot.get('boards_by_batch') or {}
    rows = int(snapshot.get('wall_rows') or HISTORY_WALL_POSITIONS)
    max_batch = snapshot.get('wall_max_batch')
    if max_batch is None:
        max_batch = HISTORY_WALL_MAX_BATCH
    max_batch = int(max_batch)
    # Compact crisp wall: no gaps, short bricks.
    brick_h = HISTORY_PNG_WALL_BRICK_H
    brick_w = HISTORY_PNG_WALL_BRICK_W
    gap_x = 0
    gap_y = 0
    label_h = 14
    axis_w = 24
    pad = 4
    legend_h = 28
    scale = 2  # render @2x for sharpness, display at CSS max-width

    width = pad * 2 + axis_w + (max_batch + 1) * (brick_w + gap_x)
    height = pad * 2 + label_h + rows * (brick_h + gap_y) + legend_h
    image = Image.new('RGB', (width * scale, height * scale), (250, 251, 252))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    def sx(value):
        return int(value * scale)

    for batch_num in range(0, max_batch + 1):
        x0 = pad + axis_w + batch_num * (brick_w + gap_x)
        label = f'B{batch_num}'
        if font:
            draw.text((sx(x0), sx(pad)), label, fill=(68, 68, 68), font=font)
        else:
            draw.text((sx(x0), sx(pad)), label, fill=(68, 68, 68))
        boards = boards_by_batch.get(batch_num) or boards_by_batch.get(str(batch_num)) or []
        position_map = {board.get('position'): board for board in boards}
        for pos in range(0, rows):
            y0 = pad + label_h + pos * (brick_h + gap_y)
            board = position_map.get(pos)
            box = [sx(x0), sx(y0), sx(x0 + brick_w - 1), sx(y0 + brick_h - 1)]
            if not board:
                draw.rectangle(box, outline=(229, 229, 229))
                continue
            color = _hex_to_rgb(_board_color(board))
            draw.rectangle(box, fill=color, outline=(210, 210, 210))

    for pos in range(0, rows, 10):
        y0 = pad + label_h + pos * (brick_h + gap_y)
        text = str(pos)
        if font:
            draw.text((sx(4), sx(y0)), text, fill=(102, 102, 102), font=font)
        else:
            draw.text((sx(4), sx(y0)), text, fill=(102, 102, 102))

    # Always-visible color legend under the wall.
    legend_items = [
        ('#00CC96', 'Passed post'),
        ('#FF9800', 'Passed pre'),
        ('#EF553B', 'Failed'),
        ('#FECB52', 'No test'),
        ('#E5E5E5', 'Empty'),
    ]
    legend_y = pad + label_h + rows * (brick_h + gap_y) + 8
    x_cursor = pad + axis_w
    swatch = 8
    for color_hex, label in legend_items:
        rgb = _hex_to_rgb(color_hex)
        box = [sx(x_cursor), sx(legend_y), sx(x_cursor + swatch), sx(legend_y + swatch)]
        if color_hex.upper() == '#E5E5E5':
            draw.rectangle(box, outline=(180, 180, 180), fill=(250, 251, 252))
        else:
            draw.rectangle(box, fill=rgb, outline=(180, 180, 180))
        text_x = x_cursor + swatch + 3
        if font:
            draw.text((sx(text_x), sx(legend_y - 1)), label, fill=(68, 68, 68), font=font)
        else:
            draw.text((sx(text_x), sx(legend_y - 1)), label, fill=(68, 68, 68))
        x_cursor = text_x + max(48, len(label) * 6)

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format='PNG', optimize=True)
    return True


def write_history_chart_pngs(snapshot, cumulative_path, burnin_path):
    fig_time, fig_burn = _history_chart_figures(snapshot)
    if fig_time is None or fig_burn is None:
        return False
    try:
        _lock_history_chart_y_axis(fig_time)
        _lock_history_chart_y_axis(fig_burn)
        cumulative_path.parent.mkdir(parents=True, exist_ok=True)
        fig_time.write_image(str(cumulative_path), format='png', width=1100, height=600, scale=1)
        fig_burn.write_image(str(burnin_path), format='png', width=1100, height=600, scale=1)
        return True
    except Exception as exc:
        print(f'Error writing history chart PNGs: {exc}')
        return False


def write_history_pie_pngs(snapshot, yield_path, burnin_path, produced_path):
    fig_yield, fig_burnin, fig_produced = _history_pie_figures(snapshot)
    if fig_yield is None:
        return False
    try:
        yield_path.parent.mkdir(parents=True, exist_ok=True)
        fig_yield.write_image(str(yield_path), format='png', width=560, height=360, scale=1)
        fig_burnin.write_image(str(burnin_path), format='png', width=560, height=360, scale=1)
        fig_produced.write_image(str(produced_path), format='png', width=560, height=360, scale=1)
        return True
    except Exception as exc:
        print(f'Error writing history pie PNGs: {exc}')
        return False


def build_history_snapshot_html(snapshot, milestone=None, cached_at=None):
    try:
        from plotly.io import to_html
        from brick_wall_cache import build_brick_wall_html
    except ImportError as exc:
        print(f'Deps not available for history HTML export: {exc}')
        return None

    stamp = format_cache_stamp(cached_at or snapshot.get('cached_at'))
    milestone_label = (milestone or {}).get('label') or snapshot.get('as_of') or ''
    rows = snapshot.get('wall_rows') or HISTORY_WALL_POSITIONS
    max_batch = snapshot.get('wall_max_batch')
    if max_batch is None:
        max_batch = HISTORY_WALL_MAX_BATCH

    wall_html = build_brick_wall_html(
        snapshot.get('boards_by_batch') or {},
        cached_at=stamp,
        brick_height=HISTORY_HTML_WALL_BRICK_H,
        max_batch=max_batch,
        fixed_rows=rows,
        title='Production History Brick Wall',
        page_meta=(
            f'{milestone_label} · as of {snapshot.get("as_of") or ""} · '
            f'boards {snapshot.get("board_count", 0)} · wall {rows}×{max_batch + 1}'
        ),
    )

    fig_time, fig_burn = _history_chart_figures(snapshot)
    fig_yield, fig_burnin, fig_produced = _history_pie_figures(snapshot)
    if fig_time is None or fig_burn is None or fig_yield is None:
        return wall_html

    _lock_history_chart_y_axis(fig_time)
    _lock_history_chart_y_axis(fig_burn)

    def _pie_html(fig, div_id, include_js):
        return to_html(
            fig,
            include_plotlyjs='cdn' if include_js else False,
            full_html=False,
            div_id=div_id,
            config={'responsive': True, 'displayModeBar': False},
            default_width='100%',
            default_height=380,
        )

    charts_html = (
        '<div class="history-charts" style="display:flex;flex-direction:column;gap:12px;'
        'padding:0 16px 24px;">'
        '<div class="pies-row" style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));'
        'gap:14px;">'
        '<div class="chart-card" style="background:#fff;border-radius:10px;padding:8px;'
        'box-shadow:0 2px 8px rgba(0,0,0,0.05);min-height:400px;">'
        + _pie_html(fig_yield, 'history-yield-pie', True)
        + '</div><div class="chart-card" style="background:#fff;border-radius:10px;padding:8px;'
        'box-shadow:0 2px 8px rgba(0,0,0,0.05);min-height:400px;">'
        + _pie_html(fig_burnin, 'history-burnin-pie', False)
        + '</div><div class="chart-card" style="background:#fff;border-radius:10px;padding:8px;'
        'box-shadow:0 2px 8px rgba(0,0,0,0.05);min-height:400px;">'
        + _pie_html(fig_produced, 'history-produced-pie', False)
        + '</div></div>'
        '<div class="chart-card" style="background:#fff;border-radius:10px;padding:8px;'
        'box-shadow:0 2px 8px rgba(0,0,0,0.05);">'
        + to_html(fig_time, include_plotlyjs=False, full_html=False, div_id='history-time')
        + '</div><div class="chart-card" style="background:#fff;border-radius:10px;padding:8px;'
        'box-shadow:0 2px 8px rgba(0,0,0,0.05);">'
        + to_html(fig_burn, include_plotlyjs=False, full_html=False, div_id='history-burnin')
        + '</div></div>'
    )
    if '</body>' in wall_html:
        return wall_html.replace('</body>', charts_html + '\n</body>', 1)
    return wall_html + charts_html


def clear_history_cache():
    if not HISTORY_CACHE_DIR.exists():
        return {'removed': 0, 'cache_dir': str(HISTORY_CACHE_DIR)}
    removed = 0
    for path in HISTORY_CACHE_DIR.rglob('*'):
        if path.is_file():
            try:
                path.unlink()
                removed += 1
            except OSError as exc:
                print(f'Error removing history cache {path}: {exc}')
    return {'removed': removed, 'cache_dir': str(HISTORY_CACHE_DIR)}


def load_history_index():
    index_path = HISTORY_CACHE_DIR / HISTORY_INDEX_NAME
    if not index_path.exists():
        return None
    try:
        payload = json.loads(index_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        print(f'Error reading history index: {exc}')
        return None
    if payload.get('version') != HISTORY_CACHE_VERSION:
        return None
    return payload


def _attach_cache_paths(payload, paths, html_ok=True, png_ok=True):
    payload['plot_html'] = paths['html_name'] if html_ok and paths['html'].exists() else None
    payload['plot_wall_png'] = (
        paths['wall_png_name'] if png_ok and paths['wall_png'].exists() else None
    )
    payload['plot_cumulative_png'] = (
        paths['cumulative_png_name'] if png_ok and paths['cumulative_png'].exists() else None
    )
    payload['plot_burnin_png'] = (
        paths['burnin_png_name'] if png_ok and paths['burnin_png'].exists() else None
    )
    payload['plot_yield_pie_png'] = (
        paths['yield_pie_png_name'] if png_ok and paths['yield_pie_png'].exists() else None
    )
    payload['plot_burnin_pie_png'] = (
        paths['burnin_pie_png_name'] if png_ok and paths['burnin_pie_png'].exists() else None
    )
    payload['plot_produced_pie_png'] = (
        paths['produced_pie_png_name'] if png_ok and paths['produced_pie_png'].exists() else None
    )
    return payload


def slim_history_snapshot_for_api(payload):
    """Drop heavy arrays once PNG frames exist — player only needs image URLs."""
    if not payload:
        return payload
    slim = dict(payload)
    has_frames = (
        slim.get('plot_wall_png')
        and slim.get('plot_cumulative_png')
        and slim.get('plot_burnin_png')
        and slim.get('plot_yield_pie_png')
        and slim.get('plot_burnin_pie_png')
        and slim.get('plot_produced_pie_png')
    )
    if has_frames:
        slim.pop('boards_by_batch', None)
        slim.pop('cumulative_by_time', None)
        slim.pop('burnin_timeline', None)
        slim.pop('colors', None)
        slim.pop('pies', None)
    return slim


def load_cached_snapshot(index=None, as_of=None, milestone_id=None, slim=True):
    index_payload = load_history_index() or {}
    milestones = index_payload.get('milestones') or []
    target = None
    if index is not None:
        try:
            target = milestones[int(index)]
        except (IndexError, TypeError, ValueError):
            target = None
    if target is None and milestone_id:
        target = next((item for item in milestones if item.get('id') == milestone_id), None)
    if target is None and as_of:
        target = next((item for item in milestones if item.get('timestamp') == as_of), None)
        if target is None:
            target = next(
                (item for item in milestones if str(item.get('timestamp') or '').startswith(str(as_of))),
                None,
            )

    path = None
    paths = None
    if target and target.get('json'):
        path = HISTORY_CACHE_DIR / target['json']
        paths = snapshot_paths(target.get('index', index or 0), target.get('timestamp') or as_of)
    elif index is not None and as_of:
        paths = snapshot_paths(index, as_of)
        if paths['json'].exists():
            path = paths['json']

    if not path or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        print(f'Error reading history snapshot {path}: {exc}')
        return None

    if paths is None:
        paths = snapshot_paths(
            (target or {}).get('index', index or 0),
            (target or {}).get('timestamp') or payload.get('as_of') or as_of,
        )

    payload['cached'] = True
    _attach_cache_paths(payload, paths)
    # Prefer index-recorded names when present
    if target:
        payload['plot_html'] = target.get('html') or payload.get('plot_html')
        payload['plot_wall_png'] = target.get('wall_png') or payload.get('plot_wall_png')
        payload['plot_cumulative_png'] = (
            target.get('cumulative_png') or payload.get('plot_cumulative_png')
        )
        payload['plot_burnin_png'] = target.get('burnin_png') or payload.get('plot_burnin_png')
        payload['plot_yield_pie_png'] = (
            target.get('yield_pie_png') or payload.get('plot_yield_pie_png')
        )
        payload['plot_burnin_pie_png'] = (
            target.get('burnin_pie_png') or payload.get('plot_burnin_pie_png')
        )
        payload['plot_produced_pie_png'] = (
            target.get('produced_pie_png') or payload.get('plot_produced_pie_png')
        )
    payload['milestone'] = {
        'id': (target or {}).get('id') or payload.get('milestone_id'),
        'index': (target or {}).get('index', index),
        'timestamp': (target or {}).get('timestamp') or payload.get('as_of') or as_of,
        'label': (target or {}).get('label') or payload.get('milestone_label'),
        'detail': (target or {}).get('detail'),
        'kind': (target or {}).get('kind'),
    }
    if slim:
        return slim_history_snapshot_for_api(payload)
    return payload


def _milestone_is_cached(item):
    paths = snapshot_paths(item.get('index', 0), item.get('timestamp'))
    return (
        paths['json'].exists()
        and paths['wall_png'].exists()
        and paths['cumulative_png'].exists()
        and paths['burnin_png'].exists()
        and paths['yield_pie_png'].exists()
        and paths['burnin_pie_png'].exists()
        and paths['produced_pie_png'].exists()
    )


def _time_axis_from_milestones(milestones, extra_snapshots=None, source_axis=None):
    if source_axis and source_axis.get('start') and source_axis.get('end'):
        return apply_history_plot_date_overrides(source_axis)
    axis = compute_milestone_time_axis(milestones)
    if axis:
        return axis
    starts = []
    ends = []
    for snapshot in (extra_snapshots or {}).values():
        lo, hi = _collect_time_bounds(snapshot)
        if lo:
            starts.append(lo)
        if hi:
            ends.append(hi)
    if not starts or not ends:
        return None
    return apply_history_plot_date_overrides(
        _pad_time_axis(min(starts), max(ends), pad=False)
    )


def _write_history_index(milestones, weeks, time_axis, cached_at=None):
    HISTORY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (HISTORY_CACHE_DIR / 'snapshots').mkdir(parents=True, exist_ok=True)
    index_milestones = []
    for item in milestones:
        entry = {key: value for key, value in item.items() if key != 'timestamp_dt'}
        paths = snapshot_paths(entry.get('index', 0), entry.get('timestamp'))
        json_ok = paths['json'].exists()
        wall_ok = paths['wall_png'].exists()
        pies_ok = (
            paths['yield_pie_png'].exists()
            and paths['burnin_pie_png'].exists()
            and paths['produced_pie_png'].exists()
        )
        if json_ok and wall_ok and pies_ok and paths['cumulative_png'].exists() and paths['burnin_png'].exists():
            entry['json'] = paths['json_name']
            entry['html'] = paths['html_name'] if paths['html'].exists() else None
            entry['wall_png'] = paths['wall_png_name']
            entry['cumulative_png'] = paths['cumulative_png_name']
            entry['burnin_png'] = paths['burnin_png_name']
            entry['yield_pie_png'] = paths['yield_pie_png_name']
            entry['burnin_pie_png'] = paths['burnin_pie_png_name']
            entry['produced_pie_png'] = paths['produced_pie_png_name']
            entry['is_cached'] = True
        else:
            entry['json'] = None
            entry['html'] = None
            entry['wall_png'] = None
            entry['cumulative_png'] = None
            entry['burnin_png'] = None
            entry['yield_pie_png'] = None
            entry['burnin_pie_png'] = None
            entry['produced_pie_png'] = None
            entry['is_cached'] = False
        index_milestones.append(entry)

    payload = {
        'success': True,
        'version': HISTORY_CACHE_VERSION,
        'cached_at': cached_at or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'cached': False,
        'total': len(index_milestones),
        'milestones': index_milestones,
        'weeks': weeks or [],
        'time_axis': time_axis,
        'wall_rows': HISTORY_WALL_POSITIONS,
        'wall_max_batch': HISTORY_WALL_MAX_BATCH,
        'cache_dir': str(HISTORY_CACHE_DIR),
        'cached_count': sum(1 for item in index_milestones if item.get('is_cached')),
    }
    (HISTORY_CACHE_DIR / HISTORY_INDEX_NAME).write_text(
        json.dumps(payload, default=_json_default),
        encoding='utf-8',
    )
    return payload


def cache_milestone_snapshot(db_rows, benchtest_rows, milestone, time_axis=None):
    """Build and persist one milestone snapshot; update the history index."""
    HISTORY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (HISTORY_CACHE_DIR / 'snapshots').mkdir(parents=True, exist_ok=True)

    snapshot = build_history_snapshot(db_rows, benchtest_rows, milestone['timestamp'])
    if not snapshot.get('success'):
        return snapshot

    if not time_axis:
        index_payload = load_history_index()
        time_axis = (index_payload or {}).get('time_axis')
        if not time_axis:
            time_axis = compute_milestone_time_axis((index_payload or {}).get('milestones') or [milestone])
        if not time_axis:
            time_axis = compute_source_time_axis(db_rows, benchtest_rows, [milestone])
    snapshot['time_axis'] = time_axis
    cached_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    snapshot['cached_at'] = cached_at
    snapshot['version'] = HISTORY_CACHE_VERSION
    snapshot['milestone_index'] = milestone.get('index')
    snapshot['milestone_id'] = milestone.get('id')
    snapshot['milestone_label'] = milestone.get('label')

    paths = snapshot_paths(milestone.get('index', 0), milestone.get('timestamp'))
    png_keys = (
        'json', 'html', 'wall_png', 'cumulative_png', 'burnin_png',
        'yield_pie_png', 'burnin_pie_png', 'produced_pie_png',
    )
    for key in png_keys:
        try:
            if paths[key].exists():
                paths[key].unlink()
        except OSError:
            pass

    paths['json'].write_text(json.dumps(snapshot, default=_json_default), encoding='utf-8')
    wall_ok = write_history_wall_png(snapshot, paths['wall_png'])
    charts_ok = write_history_chart_pngs(snapshot, paths['cumulative_png'], paths['burnin_png'])
    pies_ok = write_history_pie_pngs(
        snapshot,
        paths['yield_pie_png'],
        paths['burnin_pie_png'],
        paths['produced_pie_png'],
    )
    html = build_history_snapshot_html(snapshot, milestone=milestone, cached_at=cached_at)
    if html:
        paths['html'].write_text(html, encoding='utf-8')

    index_payload = load_history_index()
    milestones = (index_payload or {}).get('milestones') or [milestone]
    weeks = (index_payload or {}).get('weeks') or []
    replaced = False
    updated = []
    cache_fields = {
        'json': paths['json_name'],
        'html': paths['html_name'] if html else None,
        'wall_png': paths['wall_png_name'] if wall_ok else None,
        'cumulative_png': paths['cumulative_png_name'] if charts_ok else None,
        'burnin_png': paths['burnin_png_name'] if charts_ok else None,
        'yield_pie_png': paths['yield_pie_png_name'] if pies_ok else None,
        'burnin_pie_png': paths['burnin_pie_png_name'] if pies_ok else None,
        'produced_pie_png': paths['produced_pie_png_name'] if pies_ok else None,
        'is_cached': bool(wall_ok and charts_ok and pies_ok),
        'board_count': snapshot.get('board_count', 0),
    }
    for item in milestones:
        if item.get('id') == milestone.get('id') or item.get('index') == milestone.get('index'):
            entry = dict(item)
            entry.update(cache_fields)
            updated.append(entry)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        entry = {key: value for key, value in milestone.items() if key != 'timestamp_dt'}
        entry.update(cache_fields)
        updated.append(entry)

    # Keep the shared global axis from first→last milestone.
    resolved_axis = (
        compute_milestone_time_axis(updated)
        or time_axis
        or ((index_payload or {}).get('time_axis') if index_payload else None)
    )
    _write_history_index(updated, weeks, resolved_axis, cached_at=cached_at)

    snapshot['cached'] = True
    snapshot['newly_cached'] = True
    _attach_cache_paths(snapshot, paths, html_ok=bool(html), png_ok=True)
    snapshot['time_axis'] = resolved_axis
    snapshot['milestone'] = {
        'id': milestone.get('id'),
        'index': milestone.get('index'),
        'timestamp': milestone.get('timestamp'),
        'label': milestone.get('label'),
        'detail': milestone.get('detail'),
        'kind': milestone.get('kind'),
    }
    return slim_history_snapshot_for_api(snapshot)


def build_production_history(db_rows, benchtest_rows, force_recompute=False):
    """Return all milestones immediately; cache is filled lazily per milestone."""
    if force_recompute:
        clear_history_cache()

    milestone_payload = collect_milestones(db_rows, benchtest_rows)
    milestones = milestone_payload.get('milestones') or []
    weeks = milestone_payload.get('weeks') or []
    time_axis = compute_milestone_time_axis(milestones)
    return _write_history_index(
        milestones,
        weeks,
        time_axis,
        cached_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )


def build_full_history_cache(db_rows, benchtest_rows, progress_callback=None):
    """Eager rebuild of every milestone snapshot."""
    return rebuild_history_cache(
        db_rows,
        benchtest_rows,
        mode='all',
        progress_callback=progress_callback,
    )


def rebuild_history_cache(db_rows, benchtest_rows, mode='all', progress_callback=None):
    """Rebuild history milestone caches.

    mode:
      - 'all': clear and rebuild every milestone
      - 'missing': only build milestones that are not fully cached
    """
    mode = (mode or 'all').strip().lower()
    if mode not in ('all', 'missing'):
        raise ValueError(f"Invalid history rebuild mode: {mode}")

    force = mode == 'all'
    index_payload = build_production_history(
        db_rows,
        benchtest_rows,
        force_recompute=force,
    )
    milestones = index_payload.get('milestones') or []
    if mode == 'missing':
        targets = [item for item in milestones if not item.get('is_cached')]
    else:
        targets = list(milestones)

    total = len(targets)
    time_axis = index_payload.get('time_axis')
    for offset, item in enumerate(targets, start=1):
        if progress_callback:
            progress_callback(offset, total, item)
        cache_milestone_snapshot(
            db_rows,
            benchtest_rows,
            item,
            time_axis=time_axis,
        )

    final_index = load_history_index() or index_payload
    final_index = dict(final_index)
    final_index['rebuild_mode'] = mode
    final_index['rebuild_built'] = total
    final_index['rebuild_total_milestones'] = len(milestones)
    return final_index


def iter_rebuild_history_cache(db_rows, benchtest_rows, mode='all'):
    """Yield NDJSON-friendly progress events while rebuilding history cache."""
    mode = (mode or 'all').strip().lower()
    if mode not in ('all', 'missing'):
        yield {'event': 'error', 'error': f'Invalid mode: {mode}'}
        return

    force = mode == 'all'
    yield {'event': 'start', 'mode': mode, 'message': 'Collecting milestones...'}
    index_payload = build_production_history(
        db_rows,
        benchtest_rows,
        force_recompute=force,
    )
    milestones = index_payload.get('milestones') or []
    if mode == 'missing':
        targets = [item for item in milestones if not item.get('is_cached')]
    else:
        targets = list(milestones)

    total = len(targets)
    yield {
        'event': 'plan',
        'mode': mode,
        'total': total,
        'milestone_count': len(milestones),
        'message': (
            f'Rebuilding {total} milestone(s)'
            + ('' if mode == 'all' else ' without cache')
        ),
    }
    if total == 0:
        yield {
            'event': 'done',
            'mode': mode,
            'built': 0,
            'total': 0,
            'percent': 100,
            'cached_count': index_payload.get('cached_count', 0),
            'message': 'Nothing to rebuild.',
        }
        return

    time_axis = index_payload.get('time_axis')
    for offset, item in enumerate(targets, start=1):
        cache_milestone_snapshot(
            db_rows,
            benchtest_rows,
            item,
            time_axis=time_axis,
        )
        percent = round(100.0 * offset / total, 1)
        yield {
            'event': 'progress',
            'mode': mode,
            'done': offset,
            'total': total,
            'percent': percent,
            'index': item.get('index'),
            'label': item.get('label'),
            'timestamp': item.get('timestamp'),
            'message': f"Cached {offset}/{total}: {item.get('label') or item.get('timestamp')}",
        }

    final_index = load_history_index() or index_payload
    yield {
        'event': 'done',
        'mode': mode,
        'built': total,
        'total': total,
        'percent': 100,
        'cached_count': final_index.get('cached_count', 0),
        'milestone_count': final_index.get('total', len(milestones)),
        'message': f'Done. Built {total} milestone cache(s).',
    }
