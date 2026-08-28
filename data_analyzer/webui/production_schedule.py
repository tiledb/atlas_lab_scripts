"""Parse the Swedish production schedule calendar CSV."""

import calendar
import re
from datetime import datetime, timedelta
from pathlib import Path

SWEDISH_MONTHS = {
    'januari': 1,
    'februari': 2,
    'mars': 3,
    'april': 4,
    'maj': 5,
    'juni': 6,
    'juli': 7,
    'augusti': 8,
    'september': 9,
    'oktober': 10,
    'november': 11,
    'december': 12,
}

MONTH_NAMES_SV = {
    1: 'Januari',
    2: 'Februari',
    3: 'Mars',
    4: 'April',
    5: 'Maj',
    6: 'Juni',
    7: 'Juli',
    8: 'Augusti',
    9: 'September',
    10: 'Oktober',
    11: 'November',
    12: 'December',
}

WEEKDAY_LETTERS = ['M', 'T', 'O', 'T', 'F', 'L', 'S']

BATCH_PATTERN = re.compile(
    r'batch\s*#\s*(\d+)\s*(?:\((\d+)\)|(\d+)\s+prototypes)',
    re.IGNORECASE,
)


def _parse_batch_entry(text):
    match = BATCH_PATTERN.search(text)
    if not match:
        return None

    if re.search(r'\(backup\)', text, re.IGNORECASE):
        return None

    batch_number = int(match.group(1))
    if match.group(2):
        board_count = int(match.group(2))
    elif match.group(3):
        board_count = int(match.group(3))
    else:
        return None

    return {
        'batch': batch_number,
        'board_count': board_count,
        'label': match.group(0).strip(),
    }


def _format_day_cell(year, month, day):
    dt = datetime(year, month, day)
    letter = WEEKDAY_LETTERS[dt.weekday()]
    return f'{letter}  {day}' if day < 10 else f'{letter} {day}'


def load_calendar_grid(csv_path):
    """Load the full production schedule calendar for editing."""
    path = Path(csv_path)
    if not path.exists():
        return _default_calendar_grid(2026)

    lines = path.read_text(encoding='utf-8').splitlines()
    if not lines:
        return _default_calendar_grid(2026)

    header_columns = lines[0].split(';')
    months = _parse_month_headers(lines[0])
    month_headers = []
    for month_info in months:
        label = header_columns[month_info['column']].strip()
        if not label:
            label = f"{MONTH_NAMES_SV[month_info['month']]} {month_info['year']}"
        month_headers.append({
            'label': label,
            'month': month_info['month'],
            'year': month_info['year'],
        })

    rows = []
    for day in range(1, 32):
        data_line = lines[day] if day < len(lines) else ''
        columns = data_line.split(';')
        cells = []

        for month_info in months:
            year = month_info['year']
            month = month_info['month']
            if day > calendar.monthrange(year, month)[1]:
                cells.append({'valid': False, 'day_label': '', 'event': '', 'week': ''})
                continue

            base = month_info['column']
            day_label = columns[base].strip() if base < len(columns) else ''
            event = columns[base + 1].strip() if base + 1 < len(columns) else ''
            week = columns[base + 2].strip() if base + 2 < len(columns) else ''
            if not day_label:
                day_label = _format_day_cell(year, month, day)

            cells.append({
                'valid': True,
                'day_label': day_label,
                'event': event,
                'week': week,
            })

        rows.append({'day': day, 'cells': cells})

    return {'months': month_headers, 'rows': rows}


def _default_calendar_grid(year):
    months = []
    for month_number in range(1, 13):
        months.append({
            'label': f'{MONTH_NAMES_SV[month_number]} {year}',
            'month': month_number,
            'year': year,
        })

    rows = []
    for day in range(1, 32):
        cells = []
        for month_info in months:
            if day > calendar.monthrange(month_info['year'], month_info['month'])[1]:
                cells.append({'valid': False, 'day_label': '', 'event': '', 'week': ''})
            else:
                cells.append({
                    'valid': True,
                    'day_label': _format_day_cell(month_info['year'], month_info['month'], day),
                    'event': '',
                    'week': '',
                })
        rows.append({'day': day, 'cells': cells})

    return {'months': months, 'rows': rows}


def calendar_grid_to_csv(grid):
    """Serialize an editable calendar grid back to CSV text."""
    months = grid.get('months', [])
    rows = grid.get('rows', [])

    header_parts = []
    for month_info in months:
        header_parts.extend([month_info.get('label', ''), '', ''])
    header_line = ';'.join(header_parts)

    body_lines = []
    for row in rows:
        day = row.get('day')
        columns = []
        for month_index, month_info in enumerate(months):
            cells = row.get('cells', [])
            cell = cells[month_index] if month_index < len(cells) else {}
            if not cell.get('valid', True):
                columns.extend(['', '', ''])
                continue

            year = month_info['year']
            month = month_info['month']
            day_label = _format_day_cell(year, month, day)
            event = str(cell.get('event', '') or '').strip()
            week = str(cell.get('week', '') or '').strip()
            if not week:
                week = str(datetime(year, month, day).isocalendar()[1])
            columns.extend([day_label, event, week])

        body_lines.append(';'.join(columns))

    return '\n'.join([header_line] + body_lines) + '\n'


def save_calendar_grid(grid, csv_path):
    """Save calendar grid to CSV with backup of the previous file."""
    from production_config import save_schedule_text

    csv_text = calendar_grid_to_csv(grid)
    save_schedule_text(csv_text, Path(csv_path))
    return csv_text


def _parse_month_headers(header_line):
    columns = header_line.strip().split(';')
    months = []

    for index in range(0, len(columns), 3):
        header = columns[index].strip()
        if not header:
            continue

        parts = header.split()
        if len(parts) < 2:
            continue

        month_name = parts[0].lower()
        if month_name not in SWEDISH_MONTHS:
            continue

        try:
            year = int(parts[1])
        except ValueError:
            continue

        months.append({
            'month': SWEDISH_MONTHS[month_name],
            'year': year,
            'column': index,
        })

    return months


def _is_schedule_comment(text):
    text = text.strip()
    if not text:
        return False
    if BATCH_PATTERN.search(text):
        return False
    if re.search(r'\(backup\)', text, re.IGNORECASE):
        return False
    if text.lower() == 'veckonr.se':
        return False
    if re.fullmatch(r'\d+\s*', text):
        return False
    if not re.search(r'[A-Za-zÅÄÖåäö]', text):
        return False
    return True


def _iter_calendar_event_cells(csv_path):
    path = Path(csv_path)
    if not path.exists():
        return

    lines = path.read_text(encoding='utf-8').splitlines()
    if not lines:
        return

    months = _parse_month_headers(lines[0])
    for row_index, line in enumerate(lines[1:], start=1):
        day = row_index
        columns = line.split(';')

        for month_info in months:
            base = month_info['column']
            if base >= len(columns):
                continue

            day_cell = columns[base].strip()
            if not day_cell:
                continue

            month = month_info['month']
            year = month_info['year']
            if day > calendar.monthrange(year, month)[1]:
                continue

            event_cell = columns[base + 1].strip() if base + 1 < len(columns) else ''
            planned_date = datetime(year, month, day).strftime('%Y-%m-%d %H:%M:%S')
            yield planned_date, event_cell


def load_schedule_comments(csv_path):
    """Load non-batch calendar comments from the schedule CSV."""
    comments = []
    for planned_date, event_cell in _iter_calendar_event_cells(csv_path):
        if _is_schedule_comment(event_cell):
            comments.append({
                'date': planned_date,
                'comment': event_cell.strip(),
            })

    comments.sort(key=lambda item: item['date'])
    return comments


def load_production_schedule(csv_path):
    """Load planned batch production dates from the calendar CSV."""
    entries = []

    for planned_date, event_cell in _iter_calendar_event_cells(csv_path):
        if 'batch #' not in event_cell.lower():
            continue

        batch_info = _parse_batch_entry(event_cell)
        if not batch_info:
            continue

        entries.append({
            'batch': batch_info['batch'],
            'board_count': batch_info['board_count'],
            'label': batch_info['label'],
            'planned_date': planned_date,
        })

    entries.sort(key=lambda entry: (entry['planned_date'], entry['batch']))
    return entries


def _apply_day_offset(date_string, days):
    planned = datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S')
    shifted = planned + timedelta(days=days)
    return shifted.strftime('%Y-%m-%d %H:%M:%S')


def build_schedule_projections(entries, config=None, schedule_csv_path=None):
    """Build cumulative expected production traces for charts."""
    config = config or {}
    pretest_offset = int(config.get('pretest_offset_days', 0))
    post_test_offset = int(config.get('post_test_offset_days', 0))
    burnin_offset = int(config.get('burnin_offset_days', 0))
    comments = load_schedule_comments(schedule_csv_path) if schedule_csv_path else []

    if not entries:
        return {
            'expected_by_batch': {'batches': [], 'cumulative': []},
            'expected_by_time': [],
            'expected_tested_by_time': [],
            'expected_burnin_timeline': [],
            'comments': comments,
            'offsets': {
                'pretest_offset_days': pretest_offset,
                'post_test_offset_days': post_test_offset,
                'burnin_offset_days': burnin_offset,
            },
        }

    by_batch = sorted(entries, key=lambda entry: entry['batch'])
    cumulative = 0
    expected_by_batch = {'batches': [], 'cumulative': []}
    for entry in by_batch:
        cumulative += entry['board_count']
        expected_by_batch['batches'].append(entry['batch'])
        expected_by_batch['cumulative'].append(cumulative)

    by_time = sorted(entries, key=lambda entry: entry['planned_date'])
    cumulative = 0
    expected_by_time = []
    expected_tested_by_time = []
    expected_burnin_timeline = []

    for entry in by_time:
        cumulative += entry['board_count']
        produced_date = _apply_day_offset(entry['planned_date'], burnin_offset)
        tested_date = _apply_day_offset(
            entry['planned_date'],
            burnin_offset + pretest_offset + post_test_offset,
        )

        expected_by_time.append({
            'x': produced_date,
            'y': cumulative,
            'batch': entry['batch'],
            'board_count': entry['board_count'],
            'label': entry['label'],
        })
        expected_tested_by_time.append({
            'x': tested_date,
            'y': cumulative,
            'batch': entry['batch'],
            'board_count': entry['board_count'],
            'label': entry['label'],
        })

        burnin_start = datetime.strptime(tested_date, '%Y-%m-%d %H:%M:%S')
        burnin_duration = max(burnin_offset, 1)
        burnin_stop = burnin_start + timedelta(days=burnin_duration)
        center_dt = burnin_start + (burnin_stop - burnin_start) / 2
        error_minus_ms = (center_dt - burnin_start).total_seconds() * 1000
        error_plus_ms = (burnin_stop - center_dt).total_seconds() * 1000

        expected_burnin_timeline.append({
            'batch': entry['batch'],
            'board_count': entry['board_count'],
            'label': entry['label'],
            'burn_in_start': burnin_start.strftime('%Y-%m-%d %H:%M:%S'),
            'burn_in_stop': burnin_stop.strftime('%Y-%m-%d %H:%M:%S'),
            'burn_in_center': center_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'error_minus_ms': error_minus_ms,
            'error_plus_ms': error_plus_ms,
            'y_pos': cumulative,
        })

    return {
        'expected_by_batch': expected_by_batch,
        'expected_by_time': expected_by_time,
        'expected_tested_by_time': expected_tested_by_time,
        'expected_burnin_timeline': expected_burnin_timeline,
        'comments': comments,
        'offsets': {
            'pretest_offset_days': pretest_offset,
            'post_test_offset_days': post_test_offset,
            'burnin_offset_days': burnin_offset,
        },
    }
