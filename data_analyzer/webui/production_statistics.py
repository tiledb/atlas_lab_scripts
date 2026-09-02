"""Failure mode statistics for the web UI dashboard."""

from collections import defaultdict
from datetime import datetime

from benchtest_results import get_failed_tests_for_serial
from production_summary import _build_benchtest_maps, _classify_board, decode_serial

BENCHTEST_DRIVE_BASE = 'https://piro-atlas-lab.fysik.su.se/drive/benchtests'

FAILURE_MODE_COLORS = {
    'E-Test': '#FF6692',
    'P-Test': '#AB63FA',
    'Other Failure': '#FFA15A',
}

BENCHTEST_COLOR_PALETTE = [
    '#636EFA',
    '#00CC96',
    '#19D3F3',
    '#B6E880',
    '#FF97FF',
    '#FECB52',
    '#9D7BD8',
    '#00B5D8',
    '#EF553B',
    '#FF6692',
]


def _benchtest_folder_url(serial, benchtest_id):
    return (
        f'{BENCHTEST_DRIVE_BASE}/benchtest_id_{benchtest_id}/DB_{serial}/'
    )


def _benchtest_plot_url(serial, benchtest_id, measurement):
    return (
        f'{BENCHTEST_DRIVE_BASE}/benchtest_id_{benchtest_id}/DB_{serial}/'
        f'DBSNo_{serial}_PPrGTH_{measurement}.html'
    )


def _build_serial_benchtest_slots(benchtest_rows):
    mapping = defaultdict(list)
    for benchtest in benchtest_rows:
        for slot_num in range(1, 5):
            serial = benchtest.get(f'db_slot{slot_num}')
            if not serial:
                continue
            mapping[serial].append({
                'benchtest_id': benchtest['id'],
                'md': slot_num,
                'slot_name': f'MD{slot_num}',
            })
    return mapping


def _latest_benchtest_slot(serial_benchtest_slots):
    slots = serial_benchtest_slots or []
    if not slots:
        return None
    return max(slots, key=lambda item: item['benchtest_id'])


def _occurrence_label(serial, benchtest_id=None, slot_name=None, mode_name=None):
    serial_text = str(serial)
    if benchtest_id and slot_name:
        return f'{serial_text} -> benchtest{benchtest_id}@{slot_name}'
    if mode_name:
        return f'{serial_text} -> {mode_name}'
    return serial_text


def _collect_board_failure_occurrences(
    row,
    serial_benchtest_slots,
    failed_tests_reader=get_failed_tests_for_serial,
):
    serial = row['serial_no']
    slots = serial_benchtest_slots.get(serial, [])
    latest_slot = _latest_benchtest_slot(slots)
    occurrences = []

    if row.get('e_test') == 0:
        occurrences.append({
            'mode': 'E-Test',
            'serial': serial,
            'benchtest_id': latest_slot['benchtest_id'] if latest_slot else None,
            'slot_name': latest_slot['slot_name'] if latest_slot else None,
            'measurement': None,
            'label': _occurrence_label(serial, mode_name='E-Test'),
            'plot_url': (
                _benchtest_folder_url(serial, latest_slot['benchtest_id'])
                if latest_slot else None
            ),
        })

    if row.get('p_test') == 0:
        occurrences.append({
            'mode': 'P-Test',
            'serial': serial,
            'benchtest_id': latest_slot['benchtest_id'] if latest_slot else None,
            'slot_name': latest_slot['slot_name'] if latest_slot else None,
            'measurement': None,
            'label': _occurrence_label(serial, mode_name='P-Test'),
            'plot_url': (
                _benchtest_folder_url(serial, latest_slot['benchtest_id'])
                if latest_slot else None
            ),
        })

    for slot_info in slots:
        benchtest_id = slot_info['benchtest_id']
        failed_tests, _ = failed_tests_reader(serial, benchtest_id)
        if not failed_tests:
            continue
        for test_name in failed_tests:
            occurrences.append({
                'mode': test_name,
                'serial': serial,
                'benchtest_id': benchtest_id,
                'slot_name': slot_info['slot_name'],
                'measurement': test_name,
                'label': _occurrence_label(
                    serial,
                    benchtest_id=benchtest_id,
                    slot_name=slot_info['slot_name'],
                ),
                'plot_url': _benchtest_plot_url(serial, benchtest_id, test_name),
            })

    if not occurrences:
        occurrences.append({
            'mode': 'Other Failure',
            'serial': serial,
            'benchtest_id': latest_slot['benchtest_id'] if latest_slot else None,
            'slot_name': latest_slot['slot_name'] if latest_slot else None,
            'measurement': None,
            'label': _occurrence_label(serial, mode_name='Other Failure'),
            'plot_url': (
                _benchtest_folder_url(serial, latest_slot['benchtest_id'])
                if latest_slot else None
            ),
        })

    return occurrences


def _merge_serial_mode_occurrences(occurrences):
    serial = occurrences[0]['serial']
    mode = occurrences[0]['mode']

    benchtests = []
    seen_benchtests = set()
    for occurrence in sorted(
        occurrences,
        key=lambda item: (item.get('benchtest_id') or 0, item.get('slot_name') or ''),
    ):
        benchtest_id = occurrence.get('benchtest_id')
        slot_name = occurrence.get('slot_name')
        if benchtest_id is None:
            continue
        benchtest_key = (benchtest_id, slot_name)
        if benchtest_key in seen_benchtests:
            continue
        seen_benchtests.add(benchtest_key)
        benchtests.append({
            'benchtest_id': benchtest_id,
            'slot_name': slot_name,
            'label': f'benchtest{benchtest_id}@{slot_name}',
            'plot_url': occurrence.get('plot_url'),
            'measurement': occurrence.get('measurement'),
        })

    if benchtests:
        benchtest_labels = ', '.join(item['label'] for item in benchtests)
        label = f'{serial} -> {benchtest_labels}'
    else:
        label = occurrences[0].get('label') or _occurrence_label(serial, mode_name=mode)

    merged = {
        'mode': mode,
        'serial': serial,
        'benchtests': benchtests,
        'measurement': occurrences[0].get('measurement'),
        'label': label,
        'plot_url': benchtests[0]['plot_url'] if len(benchtests) == 1 else None,
    }
    if len(benchtests) == 1:
        merged['benchtest_id'] = benchtests[0]['benchtest_id']
        merged['slot_name'] = benchtests[0]['slot_name']
    return merged


def _merge_occurrences_for_board(occurrences):
    by_mode = defaultdict(list)
    for occurrence in occurrences:
        by_mode[occurrence['mode']].append(occurrence)
    return [
        _merge_serial_mode_occurrences(mode_occurrences)
        for mode_occurrences in by_mode.values()
    ]


def _assign_mode_colors(mode_names):
    colors = dict(FAILURE_MODE_COLORS)
    palette_index = 0
    for mode in sorted(mode_names):
        if mode in colors:
            continue
        colors[mode] = BENCHTEST_COLOR_PALETTE[palette_index % len(BENCHTEST_COLOR_PALETTE)]
        palette_index += 1
    return colors


def build_production_statistics(db_rows, benchtest_rows):
    serial_to_benchtests, _, _ = _build_benchtest_maps(benchtest_rows)
    serial_benchtest_slots = _build_serial_benchtest_slots(benchtest_rows)

    mode_occurrences = defaultdict(list)
    batch_mode_totals = defaultdict(lambda: defaultdict(int))

    for row in db_rows:
        decoded = decode_serial(row['serial_no'])
        if decoded['tag'] == 90:
            continue

        if _classify_board(row, serial_to_benchtests) != 'failed':
            continue

        batch = decoded['batch']
        board_occurrences = _merge_occurrences_for_board(
            _collect_board_failure_occurrences(row, serial_benchtest_slots)
        )
        for occurrence in board_occurrences:
            mode_occurrences[occurrence['mode']].append(occurrence)
            batch_mode_totals[batch][occurrence['mode']] += 1

    all_modes = sorted(
        mode for mode, occurrences in mode_occurrences.items()
        if len(occurrences) > 0
    )
    colors = _assign_mode_colors(all_modes)

    pie_modes = []
    total_occurrences = 0
    for mode in all_modes:
        occurrences = mode_occurrences[mode]
        total_occurrences += len(occurrences)
        pie_modes.append({
            'name': mode,
            'value': len(occurrences),
            'color': colors[mode],
            'occurrences': occurrences,
        })

    for mode_entry in pie_modes:
        mode_entry['percentage'] = (
            round(mode_entry['value'] / total_occurrences * 100, 1)
            if total_occurrences else 0.0
        )

    batches = sorted(
        batch
        for batch, mode_counts in batch_mode_totals.items()
        if sum(mode_counts.values()) > 0
    )

    failed_serials = {
        occurrence['serial']
        for occurrences in mode_occurrences.values()
        for occurrence in occurrences
    }

    return {
        'success': True,
        'timestamp': datetime.utcnow().strftime('%Y-%m-%d - %H:%M:%S'),
        'total_failed_boards': len(failed_serials),
        'failure_modes_pie': {
            'modes': pie_modes,
            'labels': [mode['name'] for mode in pie_modes],
            'values': [mode['value'] for mode in pie_modes],
            'percentages': [mode['percentage'] for mode in pie_modes],
            'colors': [mode['color'] for mode in pie_modes],
        },
        'failures_by_batch': {
            'batches': batches,
            'modes': [
                {
                    'name': mode,
                    'values': [batch_mode_totals[batch].get(mode, 0) for batch in batches],
                    'color': colors[mode],
                    'total': len(mode_occurrences[mode]),
                }
                for mode in all_modes
            ],
        },
        'colors': colors,
    }
