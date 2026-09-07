"""DBQ_MkX plot visual configuration (shared by DBQ_Mk6 and the web UI)."""

from copy import deepcopy
from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML

DATA_ANALYZER_DIR = Path(__file__).resolve().parent
CONFIG_PATH = DATA_ANALYZER_DIR / 'dbq_plot_config.yaml'

DEFAULT_DBQ_PLOT_CONFIG = {
    'figure': {
        'template': 'plotly_white',
        'width': None,
        'height': 560,
        'paper_bgcolor': 'white',
        'plot_bgcolor': 'white',
        'margin_l': 60,
        'margin_r': 40,
        'margin_t': 70,
        'margin_b': 50,
        'hovermode': 'x unified',
    },
    'font': {
        'family': 'Arial, sans-serif',
        'color': '#333333',
        'size': 12,
        'title_size': 16,
        'axis_title_size': 13,
        'tick_size': 11,
        'legend_size': 11,
        'hover_size': 12,
    },
    'labels': {
        'x_title': 'Time',
        'y_title_is_varname': True,
        'y_title': 'Value',
        'legend_title': 'Uplink Channel',
        'title_template': (
            'DBSNo: {serial} - PPrGTH: {ivar} '
            '(BT {benchtest_id} -> {test_length}) (Gen -> {generated_at})'
        ),
        'title_time_format': '%Y-%m-%d %H:%M:%S',
    },
    'data_traces': {
        'mode': 'lines',
        'line_width': 1.5,
        'marker_size': 5,
        'opacity': 1.0,
    },
    'reference_traces': {
        'truth_name': 'TruthValue',
        'truth_color': 'rgba(255, 0, 0, 1)',
        'truth_width': 2.0,
        'truth_dash': 'solid',
        'lower_name': 'LowerLimit',
        'lower_color': 'rgba(255, 0, 0, 1)',
        'lower_width': 2.0,
        'lower_dash': 'dash',
        'upper_name': 'UpperLimit',
        'upper_color': 'rgba(255, 0, 0, 1)',
        'upper_width': 2.0,
        'upper_dash': 'dash',
    },
    'legend': {
        'show': True,
        'position': 'outside_right',
        'orientation': 'v',
        'x': 1.02,
        'y': 1.0,
        'xanchor': 'left',
        'yanchor': 'top',
        'bgcolor': 'rgba(255,255,255,0.85)',
        'borderwidth': 0,
    },
    'axes': {
        'showgrid_x': True,
        'showgrid_y': True,
        'zeroline': False,
        'gridcolor': '#e4e8ee',
        'show_borders': False,
        'border_color': '#333333',
        'border_width': 1.0,
    },
    'output': {
        'include_plotlyjs': True,
    },
}

# Named legend placements applied unless position == 'custom'.
LEGEND_POSITION_PRESETS = {
    'outside_right': {
        'orientation': 'v',
        'x': 1.02,
        'y': 1.0,
        'xanchor': 'left',
        'yanchor': 'top',
    },
    'top_left': {
        'orientation': 'v',
        'x': 0.01,
        'y': 0.99,
        'xanchor': 'left',
        'yanchor': 'top',
    },
    'top_right': {
        'orientation': 'v',
        'x': 0.99,
        'y': 0.99,
        'xanchor': 'right',
        'yanchor': 'top',
    },
    'bottom_left': {
        'orientation': 'v',
        'x': 0.01,
        'y': 0.01,
        'xanchor': 'left',
        'yanchor': 'bottom',
    },
    'bottom_right': {
        'orientation': 'v',
        'x': 0.99,
        'y': 0.01,
        'xanchor': 'right',
        'yanchor': 'bottom',
    },
    'top': {
        'orientation': 'h',
        'x': 0.5,
        'y': 1.02,
        'xanchor': 'center',
        'yanchor': 'bottom',
    },
    'bottom': {
        'orientation': 'h',
        'x': 0.5,
        'y': -0.28,
        'xanchor': 'center',
        'yanchor': 'top',
        'min_margin_b': 120,
    },
}


def _as_dict(value, default):
    if not isinstance(value, dict):
        return deepcopy(default)
    merged = deepcopy(default)
    for key, default_value in default.items():
        if key not in value:
            continue
        raw = value[key]
        if isinstance(default_value, dict):
            merged[key] = _as_dict(raw, default_value)
        else:
            merged[key] = raw
    return merged


def _as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ('1', 'true', 'yes', 'on'):
            return True
        if text in ('0', 'false', 'no', 'off', ''):
            return False
    if value is None:
        return default
    return bool(value)


def _as_float(value, default):
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_optional_int(value):
    try:
        if value is None or value == '':
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_dbq_plot_config(raw=None):
    """Return a full config dict with defaults filled in."""
    config = _as_dict(raw or {}, DEFAULT_DBQ_PLOT_CONFIG)

    fig = config['figure']
    fig['template'] = str(fig.get('template') or 'plotly_white')
    fig['width'] = _as_optional_int(fig.get('width'))
    fig['height'] = _as_optional_int(fig.get('height')) or 560
    fig['paper_bgcolor'] = str(fig.get('paper_bgcolor') or 'white')
    fig['plot_bgcolor'] = str(fig.get('plot_bgcolor') or 'white')
    fig['margin_l'] = int(_as_float(fig.get('margin_l'), 60))
    fig['margin_r'] = int(_as_float(fig.get('margin_r'), 40))
    fig['margin_t'] = int(_as_float(fig.get('margin_t'), 70))
    fig['margin_b'] = int(_as_float(fig.get('margin_b'), 50))
    fig['hovermode'] = str(fig.get('hovermode') or 'x unified')

    font = config['font']
    font['family'] = str(font.get('family') or 'Arial, sans-serif')
    font['color'] = str(font.get('color') or '#333333')
    for key, default in (
        ('size', 12),
        ('title_size', 16),
        ('axis_title_size', 13),
        ('tick_size', 11),
        ('legend_size', 11),
        ('hover_size', 12),
    ):
        font[key] = int(_as_float(font.get(key), default))

    labels = config['labels']
    labels['x_title'] = str(labels.get('x_title') or 'Time')
    labels['y_title_is_varname'] = _as_bool(labels.get('y_title_is_varname'), True)
    labels['y_title'] = str(labels.get('y_title') or 'Value')
    labels['legend_title'] = str(labels.get('legend_title') or 'Uplink Channel')
    labels['title_template'] = str(
        labels.get('title_template')
        or 'DBSNo: {serial} - PPrGTH: {ivar} (Gen -> {generated_at})'
    )
    labels['title_time_format'] = str(labels.get('title_time_format') or '%Y-%m-%d %H:%M:%S')

    traces = config['data_traces']
    mode = str(traces.get('mode') or 'lines').strip().lower()
    if mode not in ('lines', 'lines+markers', 'markers'):
        mode = 'lines'
    traces['mode'] = mode
    traces['line_width'] = _as_float(traces.get('line_width'), 1.5)
    traces['marker_size'] = _as_float(traces.get('marker_size'), 5)
    traces['opacity'] = max(0.0, min(1.0, _as_float(traces.get('opacity'), 1.0)))

    refs = config['reference_traces']
    for prefix, default_name, default_dash in (
        ('truth', 'TruthValue', 'solid'),
        ('lower', 'LowerLimit', 'dash'),
        ('upper', 'UpperLimit', 'dash'),
    ):
        refs[f'{prefix}_name'] = str(refs.get(f'{prefix}_name') or default_name)
        refs[f'{prefix}_color'] = str(refs.get(f'{prefix}_color') or 'rgba(255, 0, 0, 1)')
        refs[f'{prefix}_width'] = _as_float(refs.get(f'{prefix}_width'), 2.0)
        dash = str(refs.get(f'{prefix}_dash') or default_dash).strip().lower()
        if dash not in ('solid', 'dot', 'dash', 'longdash', 'dashdot', 'longdashdot'):
            dash = default_dash
        refs[f'{prefix}_dash'] = dash

    legend = config['legend']
    legend['show'] = _as_bool(legend.get('show'), True)
    position = str(legend.get('position') or 'outside_right').strip().lower().replace(' ', '_')
    if position not in LEGEND_POSITION_PRESETS and position != 'custom':
        position = 'outside_right'
    legend['position'] = position
    if position in LEGEND_POSITION_PRESETS:
        preset = LEGEND_POSITION_PRESETS[position]
        legend['orientation'] = preset['orientation']
        legend['x'] = preset['x']
        legend['y'] = preset['y']
        legend['xanchor'] = preset['xanchor']
        legend['yanchor'] = preset['yanchor']
        min_margin_b = preset.get('min_margin_b')
        if min_margin_b is not None:
            fig = config['figure']
            fig['margin_b'] = max(int(fig.get('margin_b') or 0), int(min_margin_b))
    else:
        orientation = str(legend.get('orientation') or 'v').strip().lower()
        legend['orientation'] = 'h' if orientation == 'h' else 'v'
        legend['x'] = _as_float(legend.get('x'), 1.02)
        legend['y'] = _as_float(legend.get('y'), 1.0)
        xanchor = str(legend.get('xanchor') or 'left').strip().lower()
        yanchor = str(legend.get('yanchor') or 'top').strip().lower()
        if xanchor not in ('left', 'center', 'right'):
            xanchor = 'left'
        if yanchor not in ('top', 'middle', 'bottom'):
            yanchor = 'top'
        legend['xanchor'] = xanchor
        legend['yanchor'] = yanchor
    legend['bgcolor'] = str(legend.get('bgcolor') or 'rgba(255,255,255,0.85)')
    legend['borderwidth'] = int(_as_float(legend.get('borderwidth'), 0))

    axes = config['axes']
    axes['showgrid_x'] = _as_bool(axes.get('showgrid_x'), True)
    axes['showgrid_y'] = _as_bool(axes.get('showgrid_y'), True)
    axes['zeroline'] = _as_bool(axes.get('zeroline'), False)
    axes['gridcolor'] = str(axes.get('gridcolor') or '#e4e8ee')
    axes['show_borders'] = _as_bool(axes.get('show_borders'), False)
    axes['border_color'] = str(axes.get('border_color') or '#333333')
    axes['border_width'] = _as_float(axes.get('border_width'), 1.0)

    output = config['output']
    include_js = output.get('include_plotlyjs', True)
    if isinstance(include_js, str):
        text = include_js.strip().lower()
        # same_folder is our alias for Plotly's "directory" mode (one plotly.min.js per folder).
        if text in ('cdn', 'directory', 'same_folder', 'true', 'false'):
            if text == 'false':
                include_js = False
            elif text == 'true':
                include_js = True
            elif text in ('directory', 'same_folder'):
                include_js = 'same_folder'
            else:
                include_js = text
        else:
            include_js = True
    elif not isinstance(include_js, bool):
        include_js = True
    output['include_plotlyjs'] = include_js

    return config


def load_dbq_plot_config(path=None):
    """Load and normalize DBQ plot style config from YAML."""
    config_path = Path(path) if path else CONFIG_PATH
    raw = {}
    if config_path.is_file():
        try:
            yaml_handler = YAML(typ='safe')
            loaded = yaml_handler.load(config_path) or {}
            if isinstance(loaded, dict):
                raw = loaded
        except Exception as exc:
            print(f'Warning: failed to load {config_path}: {exc}')
    return normalize_dbq_plot_config(raw)


def save_dbq_plot_config(config, path=None):
    """Normalize and persist DBQ plot style config."""
    config_path = Path(path) if path else CONFIG_PATH
    normalized = normalize_dbq_plot_config(config)
    yaml_handler = YAML()
    yaml_handler.default_flow_style = False
    yaml_handler.indent(mapping=2, sequence=4, offset=2)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w', encoding='utf-8') as handle:
        yaml_handler.dump(normalized, handle)
    return normalized


def format_test_length(start_time=None, stop_time=None, test_length=None):
    """Human-readable test duration for plot titles."""
    if test_length is not None and str(test_length).strip() != '':
        return str(test_length).strip()
    seconds = test_length_seconds(start_time=start_time, stop_time=stop_time)
    if seconds is None:
        return 'n/a'
    return format_duration_seconds(seconds)


def test_length_seconds(start_time=None, stop_time=None):
    """Return duration in whole seconds, or None if timestamps are missing/invalid."""
    if start_time is None or stop_time is None:
        return None
    try:
        start = start_time if isinstance(start_time, datetime) else datetime.fromisoformat(
            str(start_time).replace(' ', 'T')
        )
        stop = stop_time if isinstance(stop_time, datetime) else datetime.fromisoformat(
            str(stop_time).replace(' ', 'T')
        )
        return max(0, int((stop - start).total_seconds()))
    except Exception:
        return None


def format_duration_seconds(total_seconds):
    """Format a non-negative second count as e.g. 2h 15m / 15m 30s / 45s."""
    try:
        total_seconds = max(0, int(total_seconds))
    except (TypeError, ValueError):
        return 'n/a'
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f'{hours}h {minutes:02d}m'
    if minutes:
        return f'{minutes}m {seconds:02d}s'
    return f'{seconds}s'


def format_dbq_plot_title(
    style,
    serial,
    ivar,
    generated_at=None,
    *,
    test_length=None,
    start_time=None,
    stop_time=None,
    benchtest_id=None,
):
    labels = (style or {}).get('labels') or {}
    stamp = generated_at or datetime.now()
    if not isinstance(stamp, datetime):
        stamp = datetime.now()
    time_format = labels.get('title_time_format') or '%Y-%m-%d %H:%M:%S'
    duration = format_test_length(
        start_time=start_time,
        stop_time=stop_time,
        test_length=test_length,
    )
    bt_id = '' if benchtest_id is None else str(benchtest_id)
    template = labels.get('title_template') or (
        'DBSNo: {serial} - PPrGTH: {ivar} '
        '(BT {benchtest_id} -> {test_length}) (Gen -> {generated_at})'
    )
    values = {
        'serial': serial,
        'ivar': ivar,
        'generated_at': stamp.strftime(time_format),
        'test_length': duration,
        'duration': duration,
        'benchtest_id': bt_id,
        'bt': bt_id,
    }
    try:
        return template.format(**values)
    except Exception:
        return (
            f'DBSNo: {serial} - {ivar} (BT {bt_id} -> {duration}) '
            f'(Gen -> {stamp.strftime(time_format)})'
        )


def px_line_labels(style, ivar, dimensions=None):
    """Labels dict for plotly.express.line.

    Y-axis is ``measurement (dimensions)`` when units are set; otherwise the
    caption/variable name (``ivar``).
    """
    from vars_config import format_y_axis_label

    labels = (style or {}).get('labels') or {}
    measurement = ivar if labels.get('y_title_is_varname', True) else (labels.get('y_title') or 'Value')
    y_title = format_y_axis_label(measurement, dimensions)
    return {
        'x': labels.get('x_title') or 'Time',
        'y': y_title,
        'channel': labels.get('legend_title') or 'Uplink Channel',
    }


def style_dbq_figure(
    fig,
    style=None,
    *,
    serial=None,
    ivar=None,
    dimensions=None,
    threshold_mode=None,
    test_length=None,
    start_time=None,
    stop_time=None,
    benchtest_id=None,
):
    """Apply configured visual style to a DBQ Plotly figure in-place."""
    if fig is None:
        return fig
    style = normalize_dbq_plot_config(style)
    fig_cfg = style['figure']
    font = style['font']
    labels = style['labels']
    traces = style['data_traces']
    refs = style['reference_traces']
    legend = style['legend']
    axes = style['axes']

    if dimensions is not None and str(dimensions).strip() != '':
        from vars_config import format_y_axis_label
        measurement = ivar if labels.get('y_title_is_varname', True) else labels.get('y_title')
        y_title = format_y_axis_label(measurement, dimensions)
    else:
        y_title = ivar if labels.get('y_title_is_varname', True) else labels.get('y_title')
    title_text = format_dbq_plot_title(
        style,
        serial=serial,
        ivar=ivar,
        test_length=test_length,
        start_time=start_time,
        stop_time=stop_time,
        benchtest_id=benchtest_id,
    )

    xaxis = dict(
        title=dict(
            text=labels.get('x_title') or 'Time',
            font=dict(size=font['axis_title_size'], family=font['family'], color=font['color']),
        ),
        tickfont=dict(size=font['tick_size'], family=font['family'], color=font['color']),
        showgrid=bool(axes['showgrid_x']),
        gridcolor=axes['gridcolor'],
        zeroline=bool(axes['zeroline']),
    )
    yaxis = dict(
        title=dict(
            text=y_title or ivar or 'Value',
            font=dict(size=font['axis_title_size'], family=font['family'], color=font['color']),
        ),
        tickfont=dict(size=font['tick_size'], family=font['family'], color=font['color']),
        showgrid=bool(axes['showgrid_y']),
        gridcolor=axes['gridcolor'],
        zeroline=bool(axes['zeroline']),
    )
    if axes.get('show_borders'):
        border = {
            'showline': True,
            'linewidth': axes.get('border_width', 1.0),
            'linecolor': axes.get('border_color') or '#333333',
            'mirror': True,
            'ticks': 'outside',
        }
        xaxis.update(border)
        yaxis.update(border)

    layout_update = dict(
        template=fig_cfg['template'],
        paper_bgcolor=fig_cfg['paper_bgcolor'],
        plot_bgcolor=fig_cfg['plot_bgcolor'],
        margin=dict(
            l=fig_cfg['margin_l'],
            r=fig_cfg['margin_r'],
            t=fig_cfg['margin_t'],
            b=fig_cfg['margin_b'],
        ),
        hovermode=fig_cfg['hovermode'],
        hoverlabel=dict(
            font=dict(
                family=font['family'],
                size=font['hover_size'],
                color=font['color'],
            ),
        ),
        font=dict(
            family=font['family'],
            size=font['size'],
            color=font['color'],
        ),
        title=dict(
            text=title_text,
            font=dict(
                family=font['family'],
                size=font['title_size'],
                color=font['color'],
            ),
        ),
        legend=dict(
            orientation=legend['orientation'],
            x=legend['x'],
            y=legend['y'],
            xanchor=legend.get('xanchor') or 'left',
            yanchor=legend.get('yanchor') or 'top',
            bgcolor=legend['bgcolor'],
            borderwidth=legend['borderwidth'],
            font=dict(
                family=font['family'],
                size=font['legend_size'],
                color=font['color'],
            ),
            title=dict(
                text=labels.get('legend_title') or 'Uplink Channel',
                font=dict(
                    family=font['family'],
                    size=font['legend_size'],
                    color=font['color'],
                ),
            ),
        ),
        showlegend=bool(legend['show']),
        xaxis=xaxis,
        yaxis=yaxis,
    )
    if fig_cfg.get('width'):
        layout_update['width'] = fig_cfg['width']
    if fig_cfg.get('height'):
        layout_update['height'] = fig_cfg['height']
    fig.update_layout(**layout_update)

    # Compact one-line hover: "trace: x=… y=…" (no "Uplink Channel:" / long axis titles).
    hovertemplate = '%{fullData.name}: x=%{x} y=%{y}<extra></extra>'

    # Style data channel traces (skip reference names for line/marker styling).
    ref_names = {
        refs['truth_name'],
        refs['lower_name'],
        refs['upper_name'],
    }
    for trace in fig.data:
        name = getattr(trace, 'name', None)
        try:
            trace.hovertemplate = hovertemplate
        except Exception:
            pass
        if name in ref_names:
            continue
        try:
            trace.opacity = traces['opacity']
            if traces['mode']:
                trace.mode = traces['mode']
            if getattr(trace, 'line', None) is not None:
                trace.line.width = traces['line_width']
            if 'markers' in traces['mode'] and getattr(trace, 'marker', None) is not None:
                trace.marker.size = traces['marker_size']
        except Exception:
            pass

    if threshold_mode == 1 or threshold_mode == 'truth':
        fig.update_traces(
            selector={'name': refs['truth_name']},
            line={
                'color': refs['truth_color'],
                'width': refs['truth_width'],
                'dash': refs['truth_dash'],
            },
        )
    if threshold_mode == 2 or threshold_mode == 'limits':
        fig.update_traces(
            selector={'name': refs['lower_name']},
            line={
                'color': refs['lower_color'],
                'width': refs['lower_width'],
                'dash': refs['lower_dash'],
            },
        )
        fig.update_traces(
            selector={'name': refs['upper_name']},
            line={
                'color': refs['upper_color'],
                'width': refs['upper_width'],
                'dash': refs['upper_dash'],
            },
        )
    return fig


def resolve_include_plotlyjs(value):
    """Map config value to a Plotly write_html include_plotlyjs argument."""
    if value == 'same_folder' or value == 'directory':
        return 'directory'
    return value


def write_html_options(style=None):
    style = normalize_dbq_plot_config(style)
    return {
        'include_plotlyjs': resolve_include_plotlyjs(style['output']['include_plotlyjs']),
    }
