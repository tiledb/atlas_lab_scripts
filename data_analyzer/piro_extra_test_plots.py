"""Extra advanced plots for DBQ_MkX (own Influx queries, no thresholds).

Called from DBQ_Mk6 after the standard per-board plot generation. The parent
passes labels/timeframe/board identity; this module queries Influx itself.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import plotly.graph_objects as go

GAINS = ('HG', 'LG')
CHANNEL_INDEXES = tuple(range(12))  # CH0 .. CH11
NO_GAIN = None  # sentinel for measurements without HG/LG

# Shared plot family configs: one HTML per (MD, CH[, gain]).
# index_tag: Influx tag used to order points along a trace ('step' or 'sample').
# x_mode: 'field' uses x_field; 'index_plus_one' uses index_tag value + 1 as x.
LINEARITY_SAMPLE_SPECS = (
    {
        'measurement': 'ADC_Linearity_Samples',
        'index_tag': 'step',
        'indices': tuple(range(9)),  # 0 .. 8
        'x_mode': 'field',
        'x_field': 'adc_input',
        'y_field': 'value',
        'x_title': 'adc_input (DAQ counts)',
        'y_title': 'value (ADC counts)',
        'caption_prefix': 'ADC Linearity Samples',
        'file_token': 'ADC_Linearity_Samples',
        'has_gain': True,
        'extra_filters': (),
    },
    {
        'measurement': 'CIS_Linearity_Samples',
        'index_tag': 'step',
        'indices': tuple(range(40)),  # 0 .. 39
        'x_mode': 'field',
        'x_field': 'dac_charge',
        'y_field': 'value',
        'x_title': 'dac_charge (DAQ counts)',
        'y_title': 'value (ADC counts)',
        'caption_prefix': 'CIS Linearity Samples',
        'file_token': 'CIS_Linearity_Samples',
        'has_gain': True,
        'extra_filters': (),
    },
    {
        'measurement': 'Integrator_Linearity_Samples',
        'index_tag': 'step',
        'indices': tuple(range(20)),  # 0 .. 19
        'x_mode': 'field',
        'x_field': 'dac_charge',
        'y_field': 'value',
        'x_title': 'dac_charge (DAQ counts)',
        'y_title': 'value (ADC counts)',
        'caption_prefix': 'Integrator Linearity Samples',
        'file_token': 'Integrator_Linearity_Samples',
        'has_gain': False,
        'extra_filters': (),
    },
    {
        'measurement': 'CIS_Samples',
        'index_tag': 'sample',
        'indices': tuple(range(16)),  # 0 .. 15
        'x_mode': 'index_plus_one',
        'x_field': None,
        'y_field': 'value',
        'x_title': 'sample',
        'y_title': 'value (ADC counts)',
        'caption_prefix': 'CIS Samples',
        'file_token': 'CIS_Samples',
        'has_gain': True,
        'extra_filters': (('event', '0'),),
    },
)

# Canonical names selectable via generate_extra_plots_for_board(plots=[...]).
EXTRA_PLOT_LINK_EYE = 'Link_Eye_Diagram_Samples'
EXTRA_PLOT_NAMES = tuple(
    spec['measurement'] for spec in LINEARITY_SAMPLE_SPECS
) + (EXTRA_PLOT_LINK_EYE,)


def channel_tag(md_number, ch_index):
    """Build Influx tag value, e.g. PprGTH_MD1_CH0."""
    return f'PprGTH_MD{int(md_number)}_CH{int(ch_index)}'


def _format_time_display(iso_z):
    """ISO-Z / Influx time string -> readable 'YYYY-MM-DD HH:MM:SS'."""
    if iso_z is None:
        return 'n/a'
    text = str(iso_z).strip()
    if not text:
        return 'n/a'
    if text.endswith('Z'):
        text = text[:-1]
    if '.' in text:
        text = text.split('.', 1)[0]
    return text.replace('T', ' ')


def linearity_samples_query(measurement, md_number, start_time, stop_time, extra_filters=()):
    """InfluxQL for all samples of one measurement/MD in the time window."""
    channel_clause = ' OR '.join(
        f'"channel"=\'{channel_tag(md_number, ch)}\'' for ch in CHANNEL_INDEXES
    )
    clauses = [
        f'time >= \'{start_time}\'',
        f'time <= \'{stop_time}\'',
        f'({channel_clause})',
    ]
    for tag_key, tag_value in extra_filters or ():
        clauses.append(f'"{tag_key}"=\'{tag_value}\'')
    # SELECT * so tag values (channel, gain, step/sample, …) are returned.
    return (
        f'SELECT * FROM "{measurement}" WHERE ' + ' AND '.join(clauses)
    )


def _group_points_by_channel_gain_time(
    points,
    *,
    y_field,
    indices,
    has_gain=True,
    index_tag='step',
    x_mode='field',
    x_field=None,
    extra_filters=(),
):
    """
    points -> {(channel, gain_or_None): {time: [(index, x, y), ...]}}
    When has_gain is False, gain_or_None is always None.
    """
    index_set = set(indices)
    required_tags = {str(k): str(v) for k, v in (extra_filters or ())}
    grouped = defaultdict(lambda: defaultdict(list))
    for point in points or []:
        channel = point.get('channel')
        if not channel:
            continue
        skip = False
        for tag_key, tag_value in required_tags.items():
            if str(point.get(tag_key)) != tag_value:
                skip = True
                break
        if skip:
            continue
        if has_gain:
            gain = point.get('gain')
            if gain not in GAINS:
                continue
        else:
            gain = NO_GAIN
        try:
            index = int(point.get(index_tag))
        except (TypeError, ValueError):
            continue
        if index not in index_set:
            continue
        y_val = point.get(y_field)
        if y_val is None:
            continue
        if x_mode == 'index_plus_one':
            x_val = float(index + 1)
        else:
            x_val = point.get(x_field)
            if x_val is None:
                continue
            x_val = float(x_val)
        grouped[(str(channel), gain)][point['time']].append(
            (index, x_val, float(y_val))
        )
    return grouped


def _build_linearity_samples_figure(
    time_groups,
    *,
    caption,
    x_title,
    y_title,
    dbq_plot_style=None,
    serial=None,
    benchtest_id=None,
    start_time=None,
    stop_time=None,
):
    """One scatter+line per Influx timestamp group; no legend; closest-point hover."""
    fig = go.Figure()
    hover_by_trace = []
    for stamp in sorted(time_groups.keys()):
        rows = sorted(time_groups[stamp], key=lambda row: row[0])
        xs = [row[1] for row in rows]
        ys = [row[2] for row in rows]
        if not xs:
            continue
        stamp_disp = _format_time_display(stamp)
        hovertemplate = (
            f't={stamp_disp}<br>x=%{{x}}<br>y=%{{y}}<extra></extra>'
        )
        hover_by_trace.append(hovertemplate)
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode='lines+markers',
                name=stamp_disp,
                showlegend=False,
                hovertemplate=hovertemplate,
            )
        )

    n_traces = len(fig.data)

    try:
        from dbq_plot_config import style_dbq_figure

        style_dbq_figure(
            fig,
            dbq_plot_style,
            serial=serial,
            ivar=caption,
            dimensions='',
            threshold_mode=None,
            start_time=start_time,
            stop_time=stop_time,
            benchtest_id=benchtest_id,
        )
    except Exception:
        pass

    font = ((dbq_plot_style or {}).get('font') or {})
    hover_size = int(font.get('hover_size') or font.get('size') or 12)
    summary_size = max(10, min(hover_size, int(font.get('tick_size') or 12)))

    summary_text = (
        f'<b>Summary</b><br>'
        f'Benchtest: {benchtest_id}<br>'
        f'From: {_format_time_display(start_time)}'
        f'&nbsp;&nbsp;To: {_format_time_display(stop_time)}<br>'
        f'Traces: {n_traces}'
    )

    # Room for x-axis title + fully visible summary box (large fonts need more).
    margin_b = max(260, 140 + summary_size * 8)
    current_margin = fig.layout.margin
    if current_margin is not None and getattr(current_margin, 'b', None) is not None:
        margin_b = max(int(current_margin.b or 0), margin_b)

    fig.update_layout(
        showlegend=False,
        hovermode='closest',
        margin_b=margin_b,
        annotations=list(fig.layout.annotations or []) + [
            dict(
                text=summary_text,
                xref='paper',
                yref='paper',
                x=0.0,
                y=-0.28,
                xanchor='left',
                yanchor='top',
                showarrow=False,
                align='left',
                bgcolor='rgba(255,255,255,0.95)',
                bordercolor='#333333',
                borderwidth=1,
                borderpad=8,
                font=dict(
                    family=font.get('family') or 'Arial, sans-serif',
                    size=summary_size,
                    color=font.get('color') or '#333333',
                ),
            )
        ],
    )
    fig.update_xaxes(title_text=x_title)
    fig.update_yaxes(title_text=y_title)
    # Re-apply after style_dbq_figure (which overwrites hover templates).
    for trace, hovertemplate in zip(fig.data, hover_by_trace):
        trace.hovertemplate = hovertemplate
    return fig


def write_linearity_samples_plots(
    client,
    *,
    spec,
    benchtest_id,
    board_serial,
    md_index,
    start_time,
    stop_time,
    out_dir,
    dbq_plot_style=None,
):
    """
    Query one *_Samples measurement for MD{md_index+1} and write one HTML plot
    per (CHY[, gain]) under out_dir.
    """
    measurement = spec['measurement']
    has_gain = bool(spec.get('has_gain', True))
    md_number = int(md_index) + 1
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    query = linearity_samples_query(
        measurement,
        md_number,
        start_time,
        stop_time,
        extra_filters=spec.get('extra_filters') or (),
    )
    print(f'  [piro_extra] {measurement} query MD{md_number}: {query}')
    try:
        result = client.query(query)
        points = list(result.get_points())
    except Exception as exc:
        print(f'  [piro_extra] {measurement} query failed: {exc}')
        return []

    if not points:
        print(f'  [piro_extra] No {measurement} data for MD{md_number}')
        return []

    grouped = _group_points_by_channel_gain_time(
        points,
        y_field=spec['y_field'],
        indices=spec.get('indices') or spec.get('steps') or (),
        has_gain=has_gain,
        index_tag=spec.get('index_tag') or 'step',
        x_mode=spec.get('x_mode') or 'field',
        x_field=spec.get('x_field'),
        extra_filters=spec.get('extra_filters') or (),
    )
    written = []

    try:
        from dbq_plot_config import write_html_options
        html_opts = write_html_options(dbq_plot_style)
    except Exception:
        html_opts = {}

    gain_values = GAINS if has_gain else (NO_GAIN,)
    for ch_index in CHANNEL_INDEXES:
        channel = channel_tag(md_number, ch_index)
        for gain in gain_values:
            time_groups = grouped.get((channel, gain))
            if not time_groups:
                continue

            if has_gain:
                caption = (
                    f'{spec["caption_prefix"]} MD{md_number} CH{ch_index} {gain}'
                )
                filename = (
                    f'DBSNo_{board_serial}_PPrGTH_{spec["file_token"]}_'
                    f'MD{md_number}_CH{ch_index}_{gain}.html'
                )
            else:
                caption = (
                    f'{spec["caption_prefix"]} MD{md_number} CH{ch_index}'
                )
                filename = (
                    f'DBSNo_{board_serial}_PPrGTH_{spec["file_token"]}_'
                    f'MD{md_number}_CH{ch_index}.html'
                )

            fig = _build_linearity_samples_figure(
                time_groups,
                caption=caption,
                x_title=spec['x_title'],
                y_title=spec['y_title'],
                dbq_plot_style=dbq_plot_style,
                serial=board_serial,
                benchtest_id=benchtest_id,
                start_time=start_time,
                stop_time=stop_time,
            )
            plot_file = out_path / filename
            fig.write_html(str(plot_file), **html_opts)
            written.append(plot_file)
            print(
                f'  [piro_extra] Wrote {plot_file.name} '
                f'({len(time_groups)} timestamp groups)'
            )

    return written


def _spec_by_measurement(name):
    for spec in LINEARITY_SAMPLE_SPECS:
        if spec['measurement'] == name:
            return spec
    raise KeyError(f'Unknown linearity sample measurement: {name}')


def write_adc_linearity_samples_plots(client, **kwargs):
    """Backward-compatible wrapper for ADC_Linearity_Samples."""
    return write_linearity_samples_plots(
        client,
        spec=_spec_by_measurement('ADC_Linearity_Samples'),
        **kwargs,
    )


def write_cis_linearity_samples_plots(client, **kwargs):
    """Wrapper for CIS_Linearity_Samples."""
    return write_linearity_samples_plots(
        client,
        spec=_spec_by_measurement('CIS_Linearity_Samples'),
        **kwargs,
    )


def write_integrator_linearity_samples_plots(client, **kwargs):
    """Wrapper for Integrator_Linearity_Samples (no gain)."""
    return write_linearity_samples_plots(
        client,
        spec=_spec_by_measurement('Integrator_Linearity_Samples'),
        **kwargs,
    )


def write_cis_samples_plots(client, **kwargs):
    """Wrapper for CIS_Samples (sample 0..15, event=0, HG/LG)."""
    return write_linearity_samples_plots(
        client,
        spec=_spec_by_measurement('CIS_Samples'),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Link eye diagrams (IBERT 2D h x v overlays)
# ---------------------------------------------------------------------------

MEASUREMENT_LINK_EYE = 'Link_Eye_Diagram_Samples'
EYE_UPLINKS = ('uplink A0', 'uplink A1', 'uplink B0', 'uplink B1')
EYE_H_MAX = 131  # inclusive
EYE_V_MAX = 64   # inclusive
DEFAULT_MAX_EYES = 10  # max diagrams used for overlap + summary stats

EYE_METRIC_KEYS = (
    'open_area',
    'max_h_open',
    'max_v_open',
    'eye_height',
    'rms_jitter',
    'peak_to_peak_jitter',
    'q_factor',
    'snr',
    'crossing_point',
    'ber',
)
EYE_STATS_COLUMN_1 = (
    'open_area',
    'max_h_open',
    'max_v_open',
    'eye_height',
)
EYE_STATS_COLUMN_2 = (
    'rms_jitter',
    'peak_to_peak_jitter',
    'q_factor',
    'snr',
    'crossing_point',
    'ber',
)


def _md_tag_key(md_number):
    return f'PprGTH MD{int(md_number)}'


def _uplink_file_token(uplink):
    """'uplink A0' -> 'A0'."""
    text = str(uplink).strip()
    if text.lower().startswith('uplink '):
        return text.split(None, 1)[1]
    return text.replace(' ', '_')


def link_eye_diagram_query(md_number, uplink, start_time, stop_time):
    md_tag = _md_tag_key(md_number)
    return (
        f'SELECT * FROM "{MEASUREMENT_LINK_EYE}" '
        f'WHERE time >= \'{start_time}\' AND time <= \'{stop_time}\' '
        f'AND "{md_tag}"=\'{uplink}\''
    )


def _group_eye_diagrams(points, *, md_number):
    """
    Group 2D eye samples into {time: {(h, v): value}}.

    Expects tags h, v and field value, plus MD tag identifying the uplink series.
    """
    diagrams = defaultdict(dict)
    for point in points or []:
        try:
            h = int(point.get('h'))
            v = int(point.get('v'))
        except (TypeError, ValueError):
            continue
        if h < 0 or h > EYE_H_MAX or v < 0 or v > EYE_V_MAX:
            continue
        value = point.get('value')
        if value is None:
            continue
        diagrams[point['time']][(h, v)] = float(value)
    return diagrams


def _select_eye_diagrams(diagrams, max_eyes=DEFAULT_MAX_EYES):
    """Keep up to max_eyes most recent diagrams (by timestamp)."""
    if not diagrams:
        return {}
    try:
        limit = int(max_eyes)
    except (TypeError, ValueError):
        limit = DEFAULT_MAX_EYES
    if limit <= 0:
        return {}
    stamps = sorted(diagrams.keys())
    if len(stamps) <= limit:
        return dict(diagrams)
    chosen = stamps[-limit:]
    return {stamp: diagrams[stamp] for stamp in chosen}


def _diagram_to_array(grid):
    """Sparse {(h,v): value} -> dense float array shape (v+1, h+1)."""
    import numpy as np

    data = np.zeros((EYE_V_MAX + 1, EYE_H_MAX + 1), dtype=float)
    for (h, v), value in (grid or {}).items():
        if 0 <= h <= EYE_H_MAX and 0 <= v <= EYE_V_MAX:
            data[v, h] = value
    return data


def _compute_eye_metrics(data, threshold=1e-6):
    """Eye metrics for one 2D diagram (aligned with tile_scripts/read_eye.py)."""
    import numpy as np
    from itertools import groupby

    try:
        from math import erfc
    except ImportError:  # pragma: no cover
        erfc = None

    if data is None or data.size == 0 or np.all(data == 0):
        return {
            'open_area': 0.0,
            'max_h_open': 0.0,
            'max_v_open': 0.0,
            'eye_height': 0.0,
            'rms_jitter': 0.0,
            'peak_to_peak_jitter': 0.0,
            'q_factor': 0.0,
            'snr': 0.0,
            'crossing_point': 0.5,
            'ber': 1.0,
        }

    v_dim, h_dim = data.shape
    max_val = float(np.max(data))
    min_val = float(np.min(data))
    thr = threshold if threshold > 0 else max_val * 0.01
    mask = data >= thr
    open_area = float(np.sum(mask) / (v_dim * h_dim))

    max_h_open = max(
        (sum(1 for _ in g) for row in mask for k, g in groupby(row) if k),
        default=0,
    )
    max_v_open = max(
        (sum(1 for _ in g) for col in mask.T for k, g in groupby(col) if k),
        default=0,
    )
    eye_height = max_val - min_val

    mid_val = (max_val + min_val) / 2.0
    crossing_positions = []
    for row in data:
        for i in range(1, len(row)):
            if (row[i - 1] < mid_val <= row[i]) or (row[i - 1] >= mid_val > row[i]):
                crossing_positions.append(i)
    if crossing_positions:
        rms_jitter = float(np.std(crossing_positions))
        peak_to_peak_jitter = float(np.max(crossing_positions) - np.min(crossing_positions))
        crossing_point = float(np.mean(crossing_positions) / h_dim)
    else:
        rms_jitter = 0.0
        peak_to_peak_jitter = 0.0
        crossing_point = 0.5

    ones = data > mid_val
    zeros = data <= mid_val
    mu1, sigma1 = (float(data[ones].mean()), float(data[ones].std())) if np.any(ones) else (0.0, 1.0)
    mu0, sigma0 = (float(data[zeros].mean()), float(data[zeros].std())) if np.any(zeros) else (0.0, 1.0)
    q_factor = (mu1 - mu0) / (sigma1 + sigma0) if (sigma1 + sigma0) > 0 else 0.0
    snr = eye_height / (float(np.std(data)) or 1.0)
    if erfc is not None and q_factor > 0:
        ber_estimate = 0.5 * erfc(q_factor / (2 ** 0.5))
    else:
        ber_estimate = 1.0

    return {
        'open_area': open_area,
        'max_h_open': float(max_h_open),
        'max_v_open': float(max_v_open),
        'eye_height': eye_height,
        'rms_jitter': rms_jitter,
        'peak_to_peak_jitter': peak_to_peak_jitter,
        'q_factor': q_factor,
        'snr': snr,
        'crossing_point': crossing_point,
        'ber': float(ber_estimate),
    }


def _aggregate_eye_metrics(diagrams):
    """Per-metric mean, std_dev, min, max across diagrams."""
    import numpy as np

    per_eye = [_compute_eye_metrics(_diagram_to_array(grid)) for grid in diagrams.values()]
    if not per_eye:
        return {}

    aggregated = {}
    for key in EYE_METRIC_KEYS:
        values = np.asarray([metrics[key] for metrics in per_eye], dtype=float)
        mean = float(np.mean(values))
        std_dev = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
        aggregated[key] = {
            'mean': mean,
            'std_dev': std_dev,
            'min': float(np.min(values)),
            'max': float(np.max(values)),
        }
    return aggregated


def _format_metric_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 'n/a'
    abs_number = abs(number)
    if abs_number == 0:
        return '0'
    if abs_number >= 100:
        return f'{number:.2f}'
    if abs_number >= 1:
        return f'{number:.4g}'
    if abs_number >= 1e-3:
        return f'{number:.4g}'
    return f'{number:.3e}'


def _format_one_eye_metric_line(aggregated, key):
    """One HTML line: metric: mean ± std (min … max)."""
    stats = (aggregated or {}).get(key)
    if not stats:
        return None
    mean = _format_metric_number(stats['mean'])
    std_dev = _format_metric_number(stats['std_dev'])
    y_min = _format_metric_number(stats['min'])
    y_max = _format_metric_number(stats['max'])
    return (
        f'{key}: {mean} ± {std_dev} '
        f'(min {y_min}, max {y_max})'
    )


def _format_eye_stats_column_html(aggregated, keys, *, header=None):
    """
    Plotly annotations only support a small HTML subset (no <table>).
    Build a <br>-separated column of metric lines.
    """
    lines = []
    if header:
        lines.append(header)
    for key in keys:
        line = _format_one_eye_metric_line(aggregated, key)
        if line:
            lines.append(line)
    return '<br>'.join(lines) if lines else '&nbsp;'


def _eye_overlap_grid(diagrams):
    """
    Average value at each (h, v) across diagrams (overlap composite).
    Returns (h_axis, v_axis, z_matrix) suitable for go.Heatmap.
    """
    if not diagrams:
        return [], [], []

    sums = defaultdict(float)
    counts = defaultdict(int)
    for grid in diagrams.values():
        for (h, v), value in grid.items():
            sums[(h, v)] += value
            counts[(h, v)] += 1

    h_axis = list(range(0, EYE_H_MAX + 1))
    v_axis = list(range(0, EYE_V_MAX + 1))
    z = []
    for v in v_axis:
        row = []
        for h in h_axis:
            n = counts.get((h, v), 0)
            row.append((sums[(h, v)] / n) if n else None)
        z.append(row)
    return h_axis, v_axis, z


def _box_annotation(
    text,
    *,
    dbq_plot_style=None,
    x=0.0,
    y=-0.18,
    compact=False,
    xanchor='left',
    size_offset=0,
):
    font = ((dbq_plot_style or {}).get('font') or {})
    hover_size = int(font.get('hover_size') or font.get('size') or 12)
    tick_size = int(font.get('tick_size') or 12)
    if compact:
        summary_size = max(9, min(11, tick_size, hover_size))
    else:
        summary_size = max(10, min(hover_size, tick_size))
    summary_size = max(8, summary_size + int(size_offset or 0))
    return dict(
        text=text,
        xref='paper',
        yref='paper',
        x=x,
        y=y,
        xanchor=xanchor,
        yanchor='top',
        showarrow=False,
        align='left',
        bgcolor='rgba(255,255,255,0.95)',
        bordercolor='#333333',
        borderwidth=1,
        borderpad=8,
        font=dict(
            family=font.get('family') or 'Arial, sans-serif',
            size=summary_size,
            color=font.get('color') or '#333333',
        ),
    )


def _summary_annotation(text, *, dbq_plot_style=None, y=-0.28, extra_lines=0, compact=False):
    """Legacy single-box helper used by non-eye plots if needed."""
    annotation = _box_annotation(
        text,
        dbq_plot_style=dbq_plot_style,
        x=0.0,
        y=y,
        compact=compact,
    )
    summary_size = annotation['font']['size']
    margin_b = max(160, 90 + summary_size * (4 + max(0, int(extra_lines))))
    margin_b = min(margin_b, 320)
    return annotation, margin_b


def _build_eye_overlap_figure(
    diagrams,
    *,
    caption,
    dbq_plot_style=None,
    serial=None,
    benchtest_id=None,
    start_time=None,
    stop_time=None,
    max_eyes=DEFAULT_MAX_EYES,
):
    """Overlapped eye diagrams as a mean heatmap; summary + eye-stats boxes."""
    selected = _select_eye_diagrams(diagrams, max_eyes=max_eyes)
    n_diagrams = len(selected)
    n_available = len(diagrams)
    h_axis, v_axis, z = _eye_overlap_grid(selected)
    aggregated = _aggregate_eye_metrics(selected)

    fig = go.Figure()
    if h_axis and v_axis:
        fig.add_trace(
            go.Heatmap(
                x=h_axis,
                y=v_axis,
                z=z,
                colorbar=dict(title='value'),
                hovertemplate=(
                    'horizontal=%{x}<br>vertical=%{y}<br>value=%{z}<extra></extra>'
                ),
                name='eye overlap',
            )
        )

    try:
        from dbq_plot_config import style_dbq_figure

        style_dbq_figure(
            fig,
            dbq_plot_style,
            serial=serial,
            ivar=caption,
            dimensions='',
            threshold_mode=None,
            start_time=start_time,
            stop_time=stop_time,
            benchtest_id=benchtest_id,
        )
    except Exception:
        pass

    diagrams_line = f'Diagrams: {n_diagrams}'
    if n_available > n_diagrams:
        diagrams_line += f' (of {n_available}; max_eyes={max_eyes})'

    summary_text = '<br>'.join([
        '<b>Summary</b>',
        f'Benchtest: {benchtest_id}',
        f'From: {_format_time_display(start_time)}'
        f'&nbsp;&nbsp;To: {_format_time_display(stop_time)}',
        diagrams_line,
    ])
    # Plotly annotations cannot render <table>; use two adjacent boxes as columns.
    eye_stats_header = '<b>Eye Stats</b> (mean ± std_dev)'
    eye_stats_col1 = _format_eye_stats_column_html(
        aggregated,
        EYE_STATS_COLUMN_1,
        header=eye_stats_header,
    )
    eye_stats_col2 = _format_eye_stats_column_html(
        aggregated,
        EYE_STATS_COLUMN_2,
        header=eye_stats_header,
    )

    # Below tick labels + x-axis title (same clearance as linearity summary boxes).
    box_y = -0.30
    box_kw = dict(dbq_plot_style=dbq_plot_style, y=box_y, compact=True, size_offset=2)
    summary_box = _box_annotation(
        summary_text,
        x=0.0,
        xanchor='left',
        **box_kw,
    )
    eye_stats_box_1 = _box_annotation(
        eye_stats_col1,
        x=0.30,
        xanchor='left',
        **box_kw,
    )
    eye_stats_box_2 = _box_annotation(
        eye_stats_col2,
        x=0.62,
        xanchor='left',
        **box_kw,
    )

    # Room for axis title + ~7-line eye-stats columns (must stay on-canvas).
    summary_size = summary_box['font']['size']
    margin_b = max(300, 140 + summary_size * 12)
    current_margin = fig.layout.margin
    if current_margin is not None and getattr(current_margin, 'b', None) is not None:
        margin_b = max(int(current_margin.b or 0), margin_b)

    try:
        fig_height = int(
            (fig.layout.height or 0)
            or ((dbq_plot_style or {}).get('figure') or {}).get('height')
            or 560
        )
    except (TypeError, ValueError):
        fig_height = 560
    min_plot_area = 420
    top_margin = int(getattr(fig.layout.margin, 't', None) or 70)
    needed_height = margin_b + min_plot_area + top_margin
    if fig_height < needed_height:
        fig_height = needed_height

    fig.update_layout(
        showlegend=False,
        hovermode='closest',
        height=fig_height,
        margin_b=margin_b,
        annotations=list(fig.layout.annotations or []) + [
            summary_box,
            eye_stats_box_1,
            eye_stats_box_2,
        ],
    )
    fig.update_xaxes(title_text='horizontal (a.u.)')
    fig.update_yaxes(title_text='vertical (a.u.)')
    if fig.data:
        fig.data[0].hovertemplate = (
            'horizontal=%{x}<br>vertical=%{y}<br>value=%{z}<extra></extra>'
        )
    return fig


def write_link_eye_diagram_plots(
    client,
    *,
    benchtest_id,
    board_serial,
    md_index,
    start_time,
    stop_time,
    out_dir,
    dbq_plot_style=None,
    max_eyes=DEFAULT_MAX_EYES,
):
    """
    Query Link_Eye_Diagram_Samples for one MD and write one overlapped eye
    HTML per uplink (A0/A1/B0/B1).
    """
    md_number = int(md_index) + 1
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    written = []

    try:
        from dbq_plot_config import write_html_options
        html_opts = write_html_options(dbq_plot_style)
    except Exception:
        html_opts = {}

    for uplink in EYE_UPLINKS:
        query = link_eye_diagram_query(md_number, uplink, start_time, stop_time)
        print(f'  [piro_extra] {MEASUREMENT_LINK_EYE} query MD{md_number} {uplink}')
        try:
            points = list(client.query(query).get_points())
        except Exception as exc:
            print(f'  [piro_extra] {MEASUREMENT_LINK_EYE} query failed ({uplink}): {exc}')
            continue

        if not points:
            print(f'  [piro_extra] No eye data for MD{md_number} {uplink}')
            continue

        diagrams = _group_eye_diagrams(points, md_number=md_number)
        if not diagrams:
            print(
                f'  [piro_extra] Eye points present but no usable h/v pairs '
                f'for MD{md_number} {uplink}'
            )
            continue

        uplink_tok = _uplink_file_token(uplink)
        caption = f'Link Eye Diagram Samples MD{md_number} {uplink}'
        fig = _build_eye_overlap_figure(
            diagrams,
            caption=caption,
            dbq_plot_style=dbq_plot_style,
            serial=board_serial,
            benchtest_id=benchtest_id,
            start_time=start_time,
            stop_time=stop_time,
            max_eyes=max_eyes,
        )
        filename = (
            f'DBSNo_{board_serial}_PPrGTH_Link_Eye_Diagram_Samples_'
            f'MD{md_number}_{uplink_tok}.html'
        )
        plot_file = out_path / filename
        fig.write_html(str(plot_file), **html_opts)
        written.append(plot_file)
        selected_n = min(len(diagrams), int(max_eyes) if max_eyes else 0)
        print(
            f'  [piro_extra] Wrote {plot_file.name} '
            f'({selected_n}/{len(diagrams)} diagrams overlapped)'
        )

    return written


def resolve_extra_plot_names(plots=None):
    """
    Normalize a plots selection to a list of canonical names.

    None / empty / 'all' / ['all'] -> all EXTRA_PLOT_NAMES.
    Accepts a string or an iterable of strings (measurement names).
    Unknown names raise ValueError.
    """
    if plots is None:
        return list(EXTRA_PLOT_NAMES)
    if isinstance(plots, str):
        plots = [plots]
    names = [str(name).strip() for name in plots if str(name).strip()]
    if not names or any(name.lower() == 'all' for name in names):
        return list(EXTRA_PLOT_NAMES)

    known = {name.lower(): name for name in EXTRA_PLOT_NAMES}
    resolved = []
    unknown = []
    for name in names:
        key = name.lower()
        if key in known:
            canon = known[key]
            if canon not in resolved:
                resolved.append(canon)
        else:
            unknown.append(name)
    if unknown:
        raise ValueError(
            'Unknown extra plot name(s): '
            + ', '.join(unknown)
            + '. Valid: '
            + ', '.join(EXTRA_PLOT_NAMES)
        )
    return resolved


def generate_extra_plots_for_board(
    client,
    *,
    benchtest_id,
    board_serial,
    md_index,
    start_time,
    stop_time,
    out_dir,
    dbq_plot_style=None,
    plots=None,
    max_eyes=DEFAULT_MAX_EYES,
):
    """
    Entry point used by DBQ_Mk6 for one daughterboard / MD slot.

    Parameters from DBQ_Mk6:
      client, benchtest_id, board_serial, md_index (0-based),
      start_time / stop_time (ISO-Z InfluxQL strings),
      out_dir (board plot folder), dbq_plot_style,
      plots: optional list of measurement names to generate; all if omitted.
            e.g. ['ADC_Linearity_Samples', 'Link_Eye_Diagram_Samples']
      max_eyes: max Link_Eye_Diagram_Samples diagrams used for overlap/stats
                (default DEFAULT_MAX_EYES=10).
    """
    selected = resolve_extra_plot_names(plots)
    print(
        f'  [piro_extra] Generating extra plots for serial={board_serial} '
        f'MD{int(md_index)+1} BT={benchtest_id}: {", ".join(selected)}'
    )
    written = []
    common = dict(
        benchtest_id=benchtest_id,
        board_serial=board_serial,
        md_index=md_index,
        start_time=start_time,
        stop_time=stop_time,
        out_dir=out_dir,
        dbq_plot_style=dbq_plot_style,
    )
    for spec in LINEARITY_SAMPLE_SPECS:
        if spec['measurement'] not in selected:
            continue
        written.extend(
            write_linearity_samples_plots(client, spec=spec, **common)
        )
    if EXTRA_PLOT_LINK_EYE in selected:
        written.extend(
            write_link_eye_diagram_plots(
                client,
                max_eyes=max_eyes,
                **common,
            )
        )
    print(f'  [piro_extra] Done ({len(written)} files)')
    return written
