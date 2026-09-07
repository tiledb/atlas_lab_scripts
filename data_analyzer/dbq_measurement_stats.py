"""Measurement statistics for DBQ_MkX plots and Statistics.yaml sidecars."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


def format_stat_number(value, *, sig=4):
    """Compact numeric formatting for legends and YAML readability."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 'n/a'
    if not np.isfinite(number):
        return 'n/a'
    if number == 0:
        return '0'
    abs_number = abs(number)
    if abs_number >= 1000:
        return f'{number:.2f}'
    if abs_number >= 100:
        return f'{number:.3f}'
    if abs_number >= 1:
        return f'{number:.4g}'
    if abs_number >= 1e-3:
        return f'{number:.4g}'
    return f'{number:.3e}'


def compute_y_stats(y_values):
    """Return summary stats for a y-series, or None if empty/non-finite."""
    try:
        arr = np.asarray(y_values, dtype=float).ravel()
    except (TypeError, ValueError):
        return None
    arr = arr[np.isfinite(arr)]
    n = int(arr.size)
    if n == 0:
        return None

    mean = float(np.mean(arr))
    std_dev = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    y_min = float(np.min(arr))
    y_max = float(np.max(arr))
    median = float(np.median(arr))
    deviations = np.abs(arr - mean)
    max_deviation = float(np.max(deviations)) if n else 0.0
    rms = float(np.sqrt(np.mean(arr ** 2)))
    variance = float(std_dev ** 2)

    return {
        'n': n,
        'mean': mean,
        'average': mean,
        'std_dev': std_dev,
        'variance': variance,
        'min': y_min,
        'max': y_max,
        'median': median,
        'range': y_max - y_min,
        'max_deviation': max_deviation,
        'rms': rms,
    }


def measurement_legend_label(channel_name, stats):
    """Legend text for a measurement channel: name (mean ± std_dev)."""
    if not stats:
        return str(channel_name)
    mean_txt = format_stat_number(stats['mean'])
    std_txt = format_stat_number(stats['std_dev'])
    return f'{channel_name} ({mean_txt} ± {std_txt})'


def reference_legend_label(ref_name, value):
    """Legend text for Truth/Lower/Upper: name (value)."""
    return f'{ref_name} ({format_stat_number(value)})'


def apply_plot_legend_stats(fig, channel_stats, *, truth_name=None, lower_name=None, upper_name=None,
                            truth_value=None, lower_value=None, upper_value=None):
    """Rename figure traces for legend display after styling."""
    if fig is None:
        return fig

    ref_values = {}
    if truth_name is not None and truth_value is not None:
        ref_values[str(truth_name)] = truth_value
    if lower_name is not None and lower_value is not None:
        ref_values[str(lower_name)] = lower_value
    if upper_name is not None and upper_value is not None:
        ref_values[str(upper_name)] = upper_value

    for trace in fig.data:
        name = getattr(trace, 'name', None)
        if name is None:
            continue
        name = str(name)
        if name in ref_values:
            trace.name = reference_legend_label(name, ref_values[name])
            continue
        stats = (channel_stats or {}).get(name)
        if stats:
            trace.name = measurement_legend_label(name, stats)
    return fig


def build_variable_stats_payload(ivar, caption, thresholds, channel_data, *, table=None, dimensions=None):
    """
    channel_data: dict channel_name -> iterable of y values
    """
    channels = CommentedMap()
    for channel_name, y_values in (channel_data or {}).items():
        stats = compute_y_stats(y_values)
        if not stats:
            continue
        entry = CommentedMap()
        for key in (
            'n', 'mean', 'average', 'std_dev', 'variance',
            'min', 'max', 'median', 'range', 'max_deviation', 'rms',
        ):
            entry[key] = stats[key]
        channels[str(channel_name)] = entry

    payload = CommentedMap()
    payload['variable'] = str(ivar)
    if caption is not None:
        payload['caption'] = str(caption)
    if dimensions is not None and str(dimensions).strip() != '':
        payload['dimensions'] = str(dimensions).strip()
    if table is not None:
        payload['table'] = str(table)
    if thresholds is not None:
        payload['thresholds'] = list(thresholds)
    payload['channels'] = channels
    return payload


def write_board_statistics_yaml(
    path,
    *,
    serial,
    benchtest_id,
    variables_payload,
    start_time=None,
    stop_time=None,
    generated_at=None,
):
    """Write DBSNo_*_Statistics.yaml for one board."""
    stamp = generated_at or datetime.now()
    if not isinstance(stamp, datetime):
        stamp = datetime.now()

    doc = CommentedMap()
    doc['serial_no'] = serial if isinstance(serial, int) else str(serial)
    doc['benchtest_id'] = int(benchtest_id) if benchtest_id is not None else None
    doc['generated_at'] = stamp.strftime('%Y-%m-%d %H:%M:%S')
    if start_time is not None:
        doc['test_start'] = str(start_time)
    if stop_time is not None:
        doc['test_stop'] = str(stop_time)
    doc['variables'] = CommentedMap()
    for key, payload in (variables_payload or {}).items():
        doc['variables'][str(key)] = payload

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_handler = YAML()
    yaml_handler.default_flow_style = False
    yaml_handler.indent(mapping=2, sequence=4, offset=2)
    yaml_handler.width = 4096
    with out_path.open('w', encoding='utf-8') as handle:
        yaml_handler.dump(doc, handle)
    return out_path
