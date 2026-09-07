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
):
    """
    Entry point used by DBQ_Mk6 for one daughterboard / MD slot.

    Parameters from DBQ_Mk6:
      client, benchtest_id, board_serial, md_index (0-based),
      start_time / stop_time (ISO-Z InfluxQL strings),
      out_dir (board plot folder), dbq_plot_style
    """
    print(
        f'  [piro_extra] Generating extra plots for serial={board_serial} '
        f'MD{int(md_index)+1} BT={benchtest_id}'
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
        written.extend(
            write_linearity_samples_plots(client, spec=spec, **common)
        )
    print(f'  [piro_extra] Done ({len(written)} files)')
    return written
