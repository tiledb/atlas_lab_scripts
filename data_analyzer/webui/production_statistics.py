"""Failure mode statistics for the web UI dashboard."""

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML

from benchtest_results import get_failed_tests_for_serial
from production_config import (
    load_production_config,
    resolve_statistics_failure_group_id,
)
from production_summary import (
    _build_benchtest_maps,
    _classify_board,
    _counts_as_failed_after_burnin,
    _format_board_serial,
    _parse_datetime,
    _serial_benchtest_results,
    decode_serial,
)

BENCHTEST_DRIVE_BASE = 'https://piro-atlas-lab.fysik.su.se/drive/benchtests'
VARS_YAML_PATH = Path(__file__).parent.parent / 'vars.yaml'
EXTRA_FAILURE_MODES = ('E-Test', 'P-Test', 'Other Failure')
HIDDEN_FAILURE_MODES = {'Other Failure'}
HIDDEN_FAILURE_GROUPS = {'ungrouped'}

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
            mapping[_format_board_serial(serial)].append({
                'benchtest_id': benchtest['id'],
                'md': slot_num,
                'slot_name': f'MD{slot_num}',
                'test_stop': benchtest.get('test_stop'),
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
    serial_key = _format_board_serial(serial)
    slots = serial_benchtest_slots.get(serial_key, [])
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
        failed_tests, _ = failed_tests_reader(serial_key, benchtest_id)
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


def _unique_board_occurrences(occurrences):
    """Keep one entry per board, combining repeated tests and benchtests."""
    by_serial = defaultdict(list)
    order = []
    for occurrence in occurrences or []:
        key = str(occurrence.get('serial'))
        if key not in by_serial:
            order.append(key)
        by_serial[key].append(occurrence)

    merged_list = []
    for key in order:
        items = by_serial[key]
        merged = _merge_serial_mode_occurrences(items)
        source_modes = []
        for item in items:
            name = item.get('source_mode') or item.get('mode')
            if name and name not in source_modes:
                source_modes.append(name)
        merged['source_modes'] = source_modes
        if source_modes:
            mode_text = ', '.join(source_modes)
            if merged.get('benchtests'):
                benchtest_labels = ', '.join(item['label'] for item in merged['benchtests'])
                merged['label'] = f'{merged["serial"]} -> {benchtest_labels} · {mode_text}'
            else:
                merged['label'] = (
                    f'{merged["serial"]} -> {mode_text}'
                    if len(source_modes) > 1
                    else merged.get('label') or f'{merged["serial"]} -> {mode_text}'
                )
        merged_list.append(merged)
    return merged_list


def _assign_mode_colors(mode_names):
    colors = dict(FAILURE_MODE_COLORS)
    palette_index = 0
    for mode in sorted(mode_names):
        if mode in colors:
            continue
        colors[mode] = BENCHTEST_COLOR_PALETTE[palette_index % len(BENCHTEST_COLOR_PALETTE)]
        palette_index += 1
    return colors


def list_possible_failure_modes(config=None):
    config = config or load_production_config()
    modes = []
    seen = set()

    try:
        yaml_handler = YAML()
        data = yaml_handler.load(VARS_YAML_PATH.read_text(encoding='utf-8')) or {}
    except Exception as exc:
        print(f'Error reading failure-mode names from vars.yaml: {exc}')
        data = {}

    for section, items in data.items() if isinstance(data, dict) else []:
        if not isinstance(items, dict):
            continue
        for name, spec in items.items():
            if not isinstance(spec, dict):
                continue
            key = str(name)
            if key in seen:
                continue
            seen.add(key)
            modes.append({
                'name': key,
                'section': str(section),
                'caption': str(spec.get('caption') or ''),
            })

    for name in EXTRA_FAILURE_MODES:
        if name in seen:
            continue
        seen.add(name)
        modes.append({
            'name': name,
            'section': 'Board Status',
            'caption': name,
        })

    mapping = config.get('statistics_failure_mode_groups') or {}
    for name in mapping:
        key = str(name)
        if key in seen:
            continue
        seen.add(key)
        modes.append({
            'name': key,
            'section': 'Custom',
            'caption': '',
        })

    modes.sort(key=lambda item: (item['section'].lower(), item['name'].lower()))
    return modes


def statistics_failure_config_payload(config=None):
    config = config or load_production_config()
    groups = config.get('statistics_failure_groups') or []
    mapping = config.get('statistics_failure_mode_groups') or {}
    modes = []
    for item in list_possible_failure_modes(config):
        group_id = resolve_statistics_failure_group_id(item['name'], mapping)
        modes.append({
            **item,
            'group_id': group_id,
            'default_group_id': resolve_statistics_failure_group_id(item['name'], {}),
        })
    return {
        'groups': groups,
        'modes': modes,
        'mapping': {item['name']: item['group_id'] for item in modes},
    }


def _pie_payload(mode_names, mode_occurrences, colors):
    pie_modes = []
    total_boards = 0
    for mode in mode_names:
        occurrences = _unique_board_occurrences(mode_occurrences.get(mode) or [])
        total_boards += len(occurrences)
        pie_modes.append({
            'name': mode,
            'value': len(occurrences),
            'color': colors[mode],
            'occurrences': occurrences,
        })
    for mode_entry in pie_modes:
        mode_entry['percentage'] = (
            round(mode_entry['value'] / total_boards * 100, 1)
            if total_boards else 0.0
        )
    return {
        'modes': pie_modes,
        'labels': [mode['name'] for mode in pie_modes],
        'values': [mode['value'] for mode in pie_modes],
        'percentages': [mode['percentage'] for mode in pie_modes],
        'colors': [mode['color'] for mode in pie_modes],
    }


def build_production_statistics(db_rows, benchtest_rows):
    serial_to_benchtests, serial_to_benchtest_stops, _ = _build_benchtest_maps(benchtest_rows)
    serial_to_tests = _serial_benchtest_results(benchtest_rows)
    serial_benchtest_slots = _build_serial_benchtest_slots(benchtest_rows)
    config = load_production_config()
    groups = config.get('statistics_failure_groups') or []
    mapping = config.get('statistics_failure_mode_groups') or {}
    groups_by_id = {group['id']: group for group in groups}

    mode_occurrences = defaultdict(list)
    batch_mode_totals = defaultdict(lambda: defaultdict(int))
    batch_mode_seen = set()
    grouped_occurrences = defaultdict(list)
    grouped_batch_totals = defaultdict(lambda: defaultdict(int))
    grouped_batch_seen = set()
    failed_serials = set()

    for row in db_rows:
        decoded = decode_serial(row['serial_no'])
        if decoded['tag'] == 90:
            continue

        classification = _classify_board(row, serial_to_benchtests)
        if not _counts_as_failed_after_burnin(
            row,
            classification,
            serial_to_tests,
            serial_to_benchtest_stops,
        ):
            continue

        batch = decoded['batch']
        serial = row['serial_no']
        serial_key = _format_board_serial(serial)
        failed_serials.add(serial_key)
        board_occurrences = _merge_occurrences_for_board(
            _collect_board_failure_occurrences(row, serial_benchtest_slots)
        )
        for occurrence in board_occurrences:
            mode_name = occurrence['mode']
            if mode_name not in HIDDEN_FAILURE_MODES:
                mode_occurrences[mode_name].append(occurrence)
                mode_key = (batch, mode_name, serial_key)
                if mode_key not in batch_mode_seen:
                    batch_mode_seen.add(mode_key)
                    batch_mode_totals[batch][mode_name] += 1

            group_id = resolve_statistics_failure_group_id(mode_name, mapping)
            if group_id in HIDDEN_FAILURE_GROUPS:
                continue
            group = groups_by_id.get(group_id)
            if not group:
                continue
            grouped_occurrences[group['id']].append({
                **occurrence,
                'source_mode': mode_name,
                'label': f"{occurrence.get('label') or serial} · {mode_name}",
            })
            batch_group_key = (group['id'], batch, serial_key)
            if batch_group_key not in grouped_batch_seen:
                grouped_batch_seen.add(batch_group_key)
                grouped_batch_totals[batch][group['id']] += 1

    for group_id, occurrences in list(grouped_occurrences.items()):
        grouped_occurrences[group_id] = _unique_board_occurrences(occurrences)

    for mode_name, occurrences in list(mode_occurrences.items()):
        mode_occurrences[mode_name] = _unique_board_occurrences(occurrences)

    all_modes = sorted(
        mode for mode, occurrences in mode_occurrences.items()
        if len(occurrences) > 0 and mode not in HIDDEN_FAILURE_MODES
    )
    colors = _assign_mode_colors(all_modes)

    batches = sorted(
        batch
        for batch, mode_counts in batch_mode_totals.items()
        if sum(mode_counts.values()) > 0
    )

    grouped_pie_modes = []
    grouped_total = 0
    display_groups = [
        group for group in groups
        if group['id'] not in HIDDEN_FAILURE_GROUPS
    ]
    for group in display_groups:
        occurrences = grouped_occurrences.get(group['id'], [])
        value = len(occurrences)
        grouped_total += value
        grouped_pie_modes.append({
            'name': group['name'],
            'group_id': group['id'],
            'value': value,
            'color': group['color'],
            'occurrences': occurrences,
        })
    for mode_entry in grouped_pie_modes:
        mode_entry['percentage'] = (
            round(mode_entry['value'] / grouped_total * 100, 1)
            if grouped_total else 0.0
        )

    grouped_batches = sorted(
        batch
        for batch, group_counts in grouped_batch_totals.items()
        if sum(group_counts.values()) > 0
    )

    return {
        'success': True,
        'timestamp': datetime.utcnow().strftime('%Y-%m-%d - %H:%M:%S'),
        'total_failed_boards': len(failed_serials),
        'failure_modes_pie': _pie_payload(all_modes, mode_occurrences, colors),
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
        'failure_groups_pie': {
            'modes': grouped_pie_modes,
            'labels': [mode['name'] for mode in grouped_pie_modes],
            'values': [mode['value'] for mode in grouped_pie_modes],
            'percentages': [mode['percentage'] for mode in grouped_pie_modes],
            'colors': [mode['color'] for mode in grouped_pie_modes],
        },
        'failure_groups_by_batch': {
            'batches': grouped_batches,
            'modes': [
                {
                    'name': group['name'],
                    'group_id': group['id'],
                    'values': [
                        grouped_batch_totals[batch].get(group['id'], 0)
                        for batch in grouped_batches
                    ],
                    'color': group['color'],
                    'total': len(grouped_occurrences.get(group['id'], [])),
                }
                for group in display_groups
            ],
        },
        'colors': colors,
    }
