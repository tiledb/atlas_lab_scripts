"""Burn-in period analysis using InfluxDB oven telemetry."""

import json
from datetime import datetime
from math import exp
from pathlib import Path

from production_config import load_production_config
from production_summary import decode_serial, _parse_datetime

BOLTZMANN_EV_K = 8.617e-5
MEASUREMENT_NAME = 'Burnin_Oven'
MAX_PLOT_POINTS = 2500
SECRETS_YAML_PATH = Path(__file__).parent.parent.parent / 'secrets' / 'secrets.yaml'
BURN_IN_CACHE_DIR = Path('/var/www/html/drive/production_plots/burn_in')
DEFAULT_BURN_IN_CACHE_DIR = BURN_IN_CACHE_DIR
CACHE_VERSION = 2
BURN_IN_AXIS_TICK_COUNT = 10


def burn_in_equation_text(temperature_offset_c):
    return (
        'AF = exp[(Ea / kB) × (1/T_use − 1/T_test)], '
        f'T_test = (Toven + {temperature_offset_c:g}) °C converted to K, '
        f'kB = {BOLTZMANN_EV_K:g} eV/K'
    )


def _load_secrets():
    try:
        from ruamel.yaml import YAML

        yaml_handler = YAML()
        with open(SECRETS_YAML_PATH, 'r') as secrets_file:
            return yaml_handler.load(secrets_file) or {}
    except Exception as exc:
        print(f'Error loading secrets for burn-in analysis: {exc}')
        return {}


def get_influx_client():
    try:
        from influxdb import InfluxDBClient
    except ImportError as exc:
        raise RuntimeError('influxdb package is not installed') from exc

    secrets = _load_secrets()
    config = secrets.get('tiledb-influxdb', {})
    if not config:
        raise RuntimeError('InfluxDB configuration is missing')

    return InfluxDBClient(
        host=config['host'],
        port=config['port'],
        username=config['username'],
        password=config['password'],
        database=config.get('database', 'tiledb'),
    )


def get_influx_source_info():
    secrets = _load_secrets()
    config = secrets.get('tiledb-influxdb', {})
    database = config.get('database', 'tiledb') if config else 'tiledb'
    fields = ['Toven', 'LVPower']
    if not config:
        return {
            'host': None,
            'port': None,
            'database': database,
            'measurement': MEASUREMENT_NAME,
            'fields': fields,
            'description': (
                f'database "{database}", measurement "{MEASUREMENT_NAME}" '
                f'(fields: {", ".join(fields)}) — InfluxDB config missing'
            ),
        }

    host = config.get('host', '')
    port = config.get('port')
    address = f'{host}:{port}' if port else host
    return {
        'host': host,
        'port': port,
        'database': database,
        'measurement': MEASUREMENT_NAME,
        'fields': fields,
        'description': (
            f'{address}, database "{database}", measurement "{MEASUREMENT_NAME}" '
            f'(fields: {", ".join(fields)})'
        ),
    }


def _format_influx_time(value):
    dt = _parse_datetime(value)
    if not dt:
        return None
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def _parse_influx_time(value):
    if isinstance(value, datetime):
        return value
    text = str(value).replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return _parse_datetime(value)


def _query_burnin_points(client, start_dt, stop_dt):
    start_text = _format_influx_time(start_dt)
    stop_text = _format_influx_time(stop_dt)
    if not start_text or not stop_text:
        return []

    query = (
        f'SELECT "Toven", "LVPower" '
        f'FROM "{MEASUREMENT_NAME}" '
        f"WHERE time >= '{start_text}' AND time <= '{stop_text}'"
    )
    return list(client.query(query).get_points())


def _forward_fill(values):
    filled = []
    last_value = None
    for value in values:
        if value is not None:
            last_value = value
        filled.append(last_value)
    return filled


def _is_power_on(value):
    if value is None:
        return False
    try:
        return float(value) >= 0.5
    except (TypeError, ValueError):
        return False


def acceleration_factor(temperature_c, use_temperature_c, activation_energy_ev):
    if temperature_c is None:
        return 0.0
    try:
        temperature_c = float(temperature_c)
        use_temperature_c = float(use_temperature_c)
        activation_energy_ev = float(activation_energy_ev)
    except (TypeError, ValueError):
        return 0.0

    t_test_k = temperature_c + 273.15
    t_use_k = use_temperature_c + 273.15
    if t_test_k <= 0 or t_use_k <= 0:
        return 0.0
    return exp((activation_energy_ev / BOLTZMANN_EV_K) * ((1.0 / t_use_k) - (1.0 / t_test_k)))


def _compute_aging_series(rows, lvpower_values, toven_values, use_temperature_c, activation_energy_ev):
    cumulative_aging = 0.0
    accelerated_aging_hours = []
    for index, row in enumerate(rows):
        if index > 0 and _is_power_on(lvpower_values[index - 1]) and toven_values[index] is not None:
            previous_row = rows[index - 1]
            dt_hours = (row['timestamp'] - previous_row['timestamp']).total_seconds() / 3600.0
            if dt_hours > 0:
                af = acceleration_factor(
                    toven_values[index],
                    use_temperature_c,
                    activation_energy_ev,
                )
                cumulative_aging += af * dt_hours
        accelerated_aging_hours.append(round(cumulative_aging, 4))
    return accelerated_aging_hours


def _build_time_series(points, burn_in_start, config):
    rows = []
    for point in sorted(points, key=lambda item: item.get('time', '')):
        timestamp = _parse_influx_time(point.get('time'))
        if not timestamp:
            continue
        rows.append({
            'timestamp': timestamp,
            'toven': point.get('Toven'),
            'lvpower': point.get('LVPower'),
        })

    if not rows:
        return {
            'elapsed_hours': [],
            'toven_c': [],
            'lvpower': [],
            'total_elapsed_hours': 0.0,
            'point_count': 0,
        }

    temperature_offset = float(config.get('burnin_temperature_offset_c', 0.0))
    toven_values = _forward_fill([row['toven'] for row in rows])
    lvpower_values = _forward_fill([row['lvpower'] for row in rows])

    elapsed_hours = []
    toven_c = []
    lvpower = []
    for index, row in enumerate(rows):
        elapsed = (row['timestamp'] - burn_in_start).total_seconds() / 3600.0
        elapsed_hours.append(round(elapsed, 4))
        if toven_values[index] is not None:
            toven_c.append(round(float(toven_values[index]) + temperature_offset, 3))
        else:
            toven_c.append(None)
        lvpower.append(1 if _is_power_on(lvpower_values[index]) else 0)

    return {
        'elapsed_hours': elapsed_hours,
        'toven_c': toven_c,
        'lvpower': lvpower,
        'total_elapsed_hours': elapsed_hours[-1] if elapsed_hours else 0.0,
        'point_count': len(rows),
    }


def _downsample_series(series, max_points=MAX_PLOT_POINTS):
    length = len(series.get('elapsed_hours', []))
    if length <= max_points:
        return series

    step = max(length // max_points, 1)
    indices = list(range(0, length, step))
    if indices[-1] != length - 1:
        indices.append(length - 1)

    downsampled = {
        'elapsed_hours': [series['elapsed_hours'][index] for index in indices],
        'toven_c': [series['toven_c'][index] for index in indices],
        'lvpower': [series['lvpower'][index] for index in indices],
        'total_elapsed_hours': series.get('total_elapsed_hours', 0.0),
        'point_count': series.get('point_count', 0),
    }
    return downsampled


def _format_cache_parameter(value):
    return f'{float(value):g}'


def _slot_cache_slug(slot_id):
    return str(slot_id or 'burnin').lower().replace('_', '')


def _period_cache_basename(
    burn_in_start,
    burn_in_stop,
    use_temperature_c,
    activation_energy_ev,
    slot_id=None,
):
    start_text = burn_in_start.strftime('%Y%m%dT%H%M%S')
    stop_text = burn_in_stop.strftime('%Y%m%dT%H%M%S')
    tuse_text = _format_cache_parameter(use_temperature_c)
    ea_text = _format_cache_parameter(activation_energy_ev)
    return (
        f'{_slot_cache_slug(slot_id)}_{start_text}_{stop_text}'
        f'_tuse{tuse_text}_ea{ea_text}'
    )


def _period_cache_path(
    burn_in_start,
    burn_in_stop,
    use_temperature_c,
    activation_energy_ev,
    slot_id=None,
    config=None,
):
    basename = _period_cache_basename(
        burn_in_start,
        burn_in_stop,
        use_temperature_c,
        activation_energy_ev,
        slot_id=slot_id,
    )
    return get_burn_in_cache_dir(config) / f'{basename}.json'


def _period_plot_html_path(
    burn_in_start,
    burn_in_stop,
    use_temperature_c,
    activation_energy_ev,
    slot_id=None,
    config=None,
):
    basename = _period_cache_basename(
        burn_in_start,
        burn_in_stop,
        use_temperature_c,
        activation_energy_ev,
        slot_id=slot_id,
    )
    return get_burn_in_cache_dir(config) / f'{basename}.html'


def get_burn_in_cache_dir(config=None):
    if config is None:
        config = load_production_config()
    cache_dir = str(config.get('burnin_cache_dir', '')).strip()
    if not cache_dir:
        cache_dir = str(DEFAULT_BURN_IN_CACHE_DIR)
    return Path(cache_dir)


def clear_burn_in_cache(config=None):
    cache_dir = get_burn_in_cache_dir(config)
    if not cache_dir.exists():
        return {
            'cache_dir': str(cache_dir),
            'removed': 0,
        }

    removed = 0
    for path in cache_dir.iterdir():
        if not path.is_file():
            continue
        try:
            path.unlink()
            removed += 1
        except OSError as exc:
            print(f'Error removing burn-in cache file {path}: {exc}')
    return {
        'cache_dir': str(cache_dir),
        'removed': removed,
    }


def _resolve_default_burnin_parameters(config):
    profiles = config.get('burnin_use_profiles') or []
    energies = config.get('burnin_activation_energies') or []
    if not profiles or not energies:
        return None, None

    profile_name = config.get('burnin_default_use_profile')
    profile = next(
        (item for item in profiles if item.get('name') == profile_name),
        profiles[0],
    )
    default_energy = config.get('burnin_default_activation_energy_ev')
    energy = next(
        (item for item in energies if item.get('value') == default_energy),
        energies[0],
    )
    return profile, energy


def _compute_aging_hours(series, use_temperature_c, activation_energy_ev):
    cumulative = 0.0
    aging_hours = []
    elapsed_hours = series.get('elapsed_hours') or []
    toven_c = series.get('toven_c') or []
    lvpower = series.get('lvpower') or []

    for index, elapsed in enumerate(elapsed_hours):
        if (
            index > 0
            and lvpower[index - 1] == 1
            and toven_c[index] is not None
        ):
            dt_hours = elapsed - elapsed_hours[index - 1]
            if dt_hours > 0:
                t_test_k = float(toven_c[index]) + 273.15
                t_use_k = float(use_temperature_c) + 273.15
                af = exp(
                    (float(activation_energy_ev) / BOLTZMANN_EV_K)
                    * ((1.0 / t_use_k) - (1.0 / t_test_k))
                )
                cumulative += af * dt_hours
        aging_hours.append(round(cumulative, 4))
    return aging_hours


def _compute_power_on_hours(series, power_field='lvpower'):
    elapsed_hours = series.get('elapsed_hours') or []
    power_values = series.get(power_field) or []
    total = 0.0
    for index in range(1, len(elapsed_hours)):
        if power_values[index - 1] == 1:
            total += elapsed_hours[index] - elapsed_hours[index - 1]
    return total


def _format_avg_af_legend_suffix(aging_hours, power_on_hours):
    if not aging_hours or not power_on_hours or power_on_hours <= 0:
        return ''
    max_aging = aging_hours[-1]
    if not max_aging:
        return ''
    return f', avg AF={max_aging / power_on_hours:.2f}'


def _format_burn_in_numeric_tick(value, span):
    if span >= 100:
        return str(int(round(value)))
    if span >= 10:
        rounded = round(value, 1)
        return str(int(rounded)) if rounded == int(rounded) else f'{rounded:.1f}'
    rounded = round(value, 2)
    return str(int(rounded)) if rounded == int(rounded) else f'{rounded:.2f}'


def _format_burn_in_hours_days_tick(hours):
    rounded_hours = round(float(hours), 1)
    hours_text = (
        str(int(rounded_hours))
        if rounded_hours == int(rounded_hours)
        else f'{rounded_hours:.1f}'
    )
    days = rounded_hours / 24.0
    rounded_days = round(days, 1)
    days_text = (
        str(int(rounded_days))
        if rounded_days == int(rounded_days)
        else f'{rounded_days:.1f}'
    )
    return f'{hours_text} h ({days_text} d)'


def _expand_burn_in_range(min_value, max_value, floor_min=None):
    if max_value <= min_value:
        max_value = min_value + 1
    span = max_value - min_value
    pad = span * 0.02 or 0.5
    range_min = max(floor_min, min_value - pad) if floor_min is not None else min_value - pad
    return range_min, max_value + pad


def _build_burn_in_linear_tick_values(min_value, max_value, count=BURN_IN_AXIS_TICK_COUNT):
    if count < 2:
        return [min_value]
    if max_value <= min_value:
        max_value = min_value + 1
    return [
        round(min_value + ((max_value - min_value) * index) / (count - 1), 3)
        for index in range(count)
    ]


def _build_burn_in_axis_tick_config(max_elapsed, max_aging, min_temperature, max_temperature):
    x_min, x_max = _expand_burn_in_range(0.0, max_elapsed, floor_min=0.0)
    y_min, y_max = _expand_burn_in_range(0.0, max_aging, floor_min=0.0)
    temp_min, temp_max = _expand_burn_in_range(min_temperature, max_temperature)

    x_tickvals = _build_burn_in_linear_tick_values(x_min, x_max)
    x_span = x_max - x_min
    x_ticktext = [_format_burn_in_numeric_tick(value, x_span) for value in x_tickvals]

    aging_tickvals = _build_burn_in_linear_tick_values(y_min, y_max)
    aging_ticktext = [_format_burn_in_hours_days_tick(value) for value in aging_tickvals]

    temp_tickvals = _build_burn_in_linear_tick_values(temp_min, temp_max)
    temp_span = temp_max - temp_min
    temp_ticktext = [_format_burn_in_numeric_tick(value, temp_span) for value in temp_tickvals]

    return {
        'x_range': [x_min, x_max],
        'x_tickvals': x_tickvals,
        'x_ticktext': x_ticktext,
        'aging_range': [y_min, y_max],
        'aging_tickvals': aging_tickvals,
        'aging_ticktext': aging_ticktext,
        'temp_range': [temp_min, temp_max],
        'temp_tickvals': temp_tickvals,
        'temp_ticktext': temp_ticktext,
    }


def _write_period_plot_html(
    burn_in_start,
    burn_in_stop,
    series,
    config,
    slot_id=None,
    use_temperature_c=None,
    activation_energy_ev=None,
):
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError as exc:
        print(f'Plotly not available for burn-in HTML export: {exc}')
        return None

    profile, energy = _resolve_default_burnin_parameters(config)
    if not profile or not energy:
        return None

    t_use_c = float(use_temperature_c if use_temperature_c is not None else profile['temperature_c'])
    ea_ev = float(activation_energy_ev if activation_energy_ev is not None else energy['value'])
    offset = float(config.get('burnin_temperature_offset_c', 0.0))
    aging_hours = _compute_aging_hours(series, t_use_c, ea_ev)
    aging_label = f"{profile['name']} {t_use_c}°C, Ea={ea_ev} eV"
    power_on_hours = _compute_power_on_hours(series, 'lvpower')
    avg_af_suffix = _format_avg_af_legend_suffix(aging_hours, power_on_hours)
    title_suffix = f' - {slot_id}' if slot_id else ''
    lv_states = ['ON' if value == 1 else 'OFF' for value in series.get('lvpower', [])]
    toven_values = [value for value in series.get('toven_c', []) if value is not None]
    max_elapsed = series['elapsed_hours'][-1] if series.get('elapsed_hours') else 0.0
    max_aging = aging_hours[-1] if aging_hours else 0.0
    min_temperature = min(toven_values) if toven_values else 0.0
    max_temperature = max(toven_values) if toven_values else 100.0
    axis_ticks = _build_burn_in_axis_tick_config(
        max_elapsed,
        max_aging,
        min_temperature,
        max_temperature,
    )

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.72, 0.28],
        specs=[[{'secondary_y': True}], [{}]],
    )
    fig.add_trace(go.Scatter(
        x=series['elapsed_hours'],
        y=aging_hours,
        mode='lines',
        name=f'Accelerated Aging ({aging_label}{avg_af_suffix})',
        line=dict(color='#AB63FA', width=2),
    ), row=1, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(
        x=series['elapsed_hours'],
        y=series['toven_c'],
        mode='lines',
        name=f'Oven Temperature (Toven + {offset:g}°C)',
        line=dict(color='#EF553B', width=2),
    ), row=1, col=1, secondary_y=True)
    fig.add_trace(go.Scatter(
        x=series['elapsed_hours'],
        y=series['lvpower'],
        mode='lines',
        name='LVPower',
        line=dict(color='#19D3F3', width=2, shape='hv'),
        customdata=lv_states,
        hovertemplate='Elapsed: %{x:.2f} h<br>LVPower: %{customdata}<extra></extra>',
    ), row=2, col=1)
    fig.update_layout(
        title=f'Burn-In Period{title_suffix}',
        height=600,
        margin=dict(t=60, r=80, b=100, l=120),
        hovermode='x unified',
        legend=dict(
            orientation='h',
            yanchor='top',
            y=-0.18,
            x=0.5,
            xanchor='center',
        ),
    )
    fig.update_yaxes(
        title_text='Accelerated Aging',
        range=axis_ticks['aging_range'],
        tickmode='array',
        tickvals=axis_ticks['aging_tickvals'],
        ticktext=axis_ticks['aging_ticktext'],
        automargin=True,
        row=1,
        col=1,
        secondary_y=False,
    )
    fig.update_yaxes(
        title_text='Oven Temperature (°C)',
        range=axis_ticks['temp_range'],
        tickmode='array',
        tickvals=axis_ticks['temp_tickvals'],
        ticktext=axis_ticks['temp_ticktext'],
        row=1,
        col=1,
        secondary_y=True,
    )
    fig.update_yaxes(
        title_text='LVPower',
        tickmode='array',
        tickvals=[0, 1],
        ticktext=['OFF', 'ON'],
        range=[-0.05, 1.05],
        row=2,
        col=1,
    )
    fig.update_xaxes(
        title_text='Elapsed Time (hours)',
        range=axis_ticks['x_range'],
        tickmode='array',
        tickvals=axis_ticks['x_tickvals'],
        ticktext=axis_ticks['x_ticktext'],
        row=2,
        col=1,
    )
    fig.update_xaxes(
        range=axis_ticks['x_range'],
        tickmode='array',
        tickvals=axis_ticks['x_tickvals'],
        ticktext=axis_ticks['x_ticktext'],
        showticklabels=False,
        row=1,
        col=1,
    )

    html_path = _period_plot_html_path(
        burn_in_start,
        burn_in_stop,
        t_use_c,
        ea_ev,
        slot_id=slot_id,
        config=config,
    )
    cache_dir = get_burn_in_cache_dir(config)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fig.write_html(html_path, include_plotlyjs='cdn', full_html=True)
    return html_path.name


def _load_period_cache(
    burn_in_start,
    burn_in_stop,
    temperature_offset_c,
    use_temperature_c,
    activation_energy_ev,
    slot_id=None,
    config=None,
):
    cache_path = _period_cache_path(
        burn_in_start,
        burn_in_stop,
        use_temperature_c,
        activation_energy_ev,
        slot_id=slot_id,
        config=config,
    )
    if not cache_path.exists():
        return None

    try:
        cached = json.loads(cache_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        print(f'Error reading burn-in cache {cache_path}: {exc}')
        return None

    if cached.get('version') != CACHE_VERSION:
        return None

    start_text = burn_in_start.strftime('%Y-%m-%d %H:%M:%S')
    stop_text = burn_in_stop.strftime('%Y-%m-%d %H:%M:%S')
    if cached.get('burn_in_start') != start_text or cached.get('burn_in_stop') != stop_text:
        return None

    if cached.get('temperature_offset_c') != temperature_offset_c:
        return None

    series = cached.get('series') or {}
    if not series.get('point_count'):
        return None

    return cached


def _save_period_cache(
    burn_in_start,
    burn_in_stop,
    temperature_offset_c,
    series,
    totals,
    config=None,
    slot_id=None,
    use_temperature_c=None,
    activation_energy_ev=None,
):
    profile, energy = _resolve_default_burnin_parameters(config or {})
    t_use_c = use_temperature_c
    ea_ev = activation_energy_ev
    if profile and energy:
        if t_use_c is None:
            t_use_c = profile['temperature_c']
        if ea_ev is None:
            ea_ev = energy['value']
    if t_use_c is None or ea_ev is None:
        return None

    cache_dir = get_burn_in_cache_dir(config)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _period_cache_path(
        burn_in_start,
        burn_in_stop,
        t_use_c,
        ea_ev,
        slot_id=slot_id,
        config=config,
    )
    plot_html = None
    if config is not None:
        plot_html = _write_period_plot_html(
            burn_in_start,
            burn_in_stop,
            series,
            config,
            slot_id=slot_id,
            use_temperature_c=t_use_c,
            activation_energy_ev=ea_ev,
        )

    payload = {
        'version': CACHE_VERSION,
        'burn_in_start': burn_in_start.strftime('%Y-%m-%d %H:%M:%S'),
        'burn_in_stop': burn_in_stop.strftime('%Y-%m-%d %H:%M:%S'),
        'temperature_offset_c': temperature_offset_c,
        'cached_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'series': series,
        'totals': totals,
    }
    if plot_html:
        payload['plot_html'] = plot_html
    cache_path.write_text(json.dumps(payload), encoding='utf-8')
    return plot_html


def _clear_period_cache(burn_in_start, burn_in_stop, slot_id=None, config=None):
    cache_dir = get_burn_in_cache_dir(config)
    start_text = burn_in_start.strftime('%Y%m%dT%H%M%S')
    stop_text = burn_in_stop.strftime('%Y%m%dT%H%M%S')
    slot_slug = _slot_cache_slug(slot_id)
    pattern = f'{slot_slug}_{start_text}_{stop_text}_*'
    for path in cache_dir.glob(pattern):
        try:
            path.unlink()
        except OSError as exc:
            print(f'Error clearing burn-in cache {path}: {exc}')

    legacy_stem = f'{start_text}__{stop_text}'
    for suffix in ('.json', '.html'):
        legacy_path = cache_dir / f'{legacy_stem}{suffix}'
        if not legacy_path.exists():
            continue
        try:
            legacy_path.unlink()
        except OSError as exc:
            print(f'Error clearing legacy burn-in cache {legacy_path}: {exc}')


def _fetch_period_series(
    burn_in_start,
    burn_in_stop,
    config,
    influx_client=None,
    force_recompute=False,
    slot_id=None,
):
    temperature_offset = float(config.get('burnin_temperature_offset_c', 0.0))
    profile, energy = _resolve_default_burnin_parameters(config)
    if not profile or not energy:
        return {'success': False, 'error': 'Burn-in T_use profile and activation energy are not configured'}
    t_use_c = profile['temperature_c']
    ea_ev = energy['value']

    if force_recompute:
        _clear_period_cache(burn_in_start, burn_in_stop, slot_id=slot_id, config=config)
    elif not force_recompute:
        cached = _load_period_cache(
            burn_in_start,
            burn_in_stop,
            temperature_offset,
            t_use_c,
            ea_ev,
            slot_id=slot_id,
            config=config,
        )
        if cached:
            return {
                'success': True,
                'series': cached['series'],
                'totals': cached['totals'],
                'cached': True,
                'cached_at': cached.get('cached_at'),
                'plot_html': cached.get('plot_html'),
            }

    client = influx_client
    owns_client = False
    if client is None:
        try:
            client = get_influx_client()
            owns_client = True
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    try:
        points = _query_burnin_points(client, burn_in_start, burn_in_stop)
    except Exception as exc:
        return {'success': False, 'error': f'InfluxDB query failed: {exc}'}
    finally:
        if owns_client and client is not None:
            try:
                client.close()
            except Exception:
                pass

    series = _build_time_series(points, burn_in_start, config)
    if not series['point_count']:
        return {
            'success': False,
            'error': (
                f'No {MEASUREMENT_NAME} telemetry found '
                f'from {burn_in_start:%Y-%m-%d %H:%M:%S} '
                f'to {burn_in_stop:%Y-%m-%d %H:%M:%S}'
            ),
        }

    downsampled = _downsample_series(series)
    totals = {
        'elapsed_hours': series['total_elapsed_hours'],
        'raw_point_count': series['point_count'],
    }
    plot_html = _save_period_cache(
        burn_in_start,
        burn_in_stop,
        temperature_offset,
        downsampled,
        totals,
        config=config,
        slot_id=slot_id,
    )
    return {
        'success': True,
        'series': downsampled,
        'totals': totals,
        'cached': False,
        'cached_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'plot_html': plot_html,
    }


def list_burn_in_boards(db_rows):
    boards = []
    for row in db_rows:
        decoded = decode_serial(row['serial_no'])
        if decoded['tag'] == 90:
            continue

        burn_in_start = _parse_datetime(row.get('burn_in_start'))
        burn_in_stop = _parse_datetime(row.get('burn_in_stop'))
        if not burn_in_start or not burn_in_stop or burn_in_stop <= burn_in_start:
            continue

        duration_hours = (burn_in_stop - burn_in_start).total_seconds() / 3600.0
        boards.append({
            'serial': row['serial_no'],
            'batch': decoded['batch'],
            'burn_in_start': burn_in_start.strftime('%Y-%m-%d %H:%M:%S'),
            'burn_in_stop': burn_in_stop.strftime('%Y-%m-%d %H:%M:%S'),
            'duration_hours': round(duration_hours, 2),
        })

    boards.sort(key=lambda board: board['burn_in_start'], reverse=True)
    return boards


def _burn_in_period_key(burn_in_start, burn_in_stop):
    return (
        burn_in_start.strftime('%Y-%m-%d %H:%M:%S'),
        burn_in_stop.strftime('%Y-%m-%d %H:%M:%S'),
    )


def list_burn_in_slots(db_rows):
    period_map = {}
    for row in db_rows:
        decoded = decode_serial(row['serial_no'])
        if decoded['tag'] == 90:
            continue

        burn_in_start = _parse_datetime(row.get('burn_in_start'))
        burn_in_stop = _parse_datetime(row.get('burn_in_stop'))
        if not burn_in_start or not burn_in_stop or burn_in_stop <= burn_in_start:
            continue

        period_key = _burn_in_period_key(burn_in_start, burn_in_stop)
        if period_key not in period_map:
            duration_hours = (burn_in_stop - burn_in_start).total_seconds() / 3600.0
            period_map[period_key] = {
                'burn_in_start': period_key[0],
                'burn_in_stop': period_key[1],
                'duration_hours': round(duration_hours, 2),
                'boards': [],
            }

        period_map[period_key]['boards'].append({
            'serial': row['serial_no'],
            'batch': decoded['batch'],
            'position': decoded['position'],
        })

    slots = []
    for index, period_key in enumerate(
        sorted(period_map.keys(), key=lambda key: key[0]),
        start=1,
    ):
        slot_data = period_map[period_key]
        boards = sorted(slot_data['boards'], key=lambda board: board['serial'])
        batches = sorted({board['batch'] for board in boards})
        slots.append({
            'slot_id': f'BurnInSlot{index}',
            'burn_in_start': slot_data['burn_in_start'],
            'burn_in_stop': slot_data['burn_in_stop'],
            'duration_hours': slot_data['duration_hours'],
            'board_count': len(boards),
            'batches': batches,
            'boards': boards,
        })

    slots.sort(key=lambda slot: slot['burn_in_start'], reverse=True)
    return slots


def _find_burn_in_slot(db_rows, slot_id):
    slot_text = str(slot_id).strip()
    for slot in list_burn_in_slots(db_rows):
        if slot['slot_id'] == slot_text:
            return slot
    return None


def _burn_in_config_payload(config):
    cache_dir = get_burn_in_cache_dir(config)
    return {
        'temperature_offset_c': config['burnin_temperature_offset_c'],
        'cache_dir': str(cache_dir),
        'use_profiles': config['burnin_use_profiles'],
        'activation_energies': config['burnin_activation_energies'],
        'default_use_profile': config['burnin_default_use_profile'],
        'default_activation_energy_ev': config['burnin_default_activation_energy_ev'],
        'equation': burn_in_equation_text(config['burnin_temperature_offset_c']),
        'influx_source': get_influx_source_info(),
    }


def build_burn_in_plot(db_rows, serial, influx_client=None):
    serial_text = str(serial)
    board_row = next(
        (row for row in db_rows if str(row['serial_no']) == serial_text),
        None,
    )
    if not board_row:
        return {'success': False, 'error': f'Board {serial_text} not found'}

    burn_in_start = _parse_datetime(board_row.get('burn_in_start'))
    burn_in_stop = _parse_datetime(board_row.get('burn_in_stop'))
    if not burn_in_start or not burn_in_stop:
        return {
            'success': False,
            'error': f'Board {serial_text} does not have burn-in start/stop timestamps',
        }
    if burn_in_stop <= burn_in_start:
        return {
            'success': False,
            'error': f'Board {serial_text} has an invalid burn-in period',
        }

    return _build_burn_in_plot_for_period(
        db_rows,
        burn_in_start,
        burn_in_stop,
        influx_client=influx_client,
    )


def build_burn_in_plot_for_slot(db_rows, slot_id, influx_client=None, force_recompute=False):
    slot = _find_burn_in_slot(db_rows, slot_id)
    if not slot:
        return {'success': False, 'error': f'Burn-in slot {slot_id} not found'}

    burn_in_start = _parse_datetime(slot['burn_in_start'])
    burn_in_stop = _parse_datetime(slot['burn_in_stop'])
    if not burn_in_start or not burn_in_stop:
        return {
            'success': False,
            'error': f'{slot["slot_id"]} does not have burn-in start/stop timestamps',
        }
    if burn_in_stop <= burn_in_start:
        return {
            'success': False,
            'error': f'{slot["slot_id"]} has an invalid burn-in period',
        }

    result = _build_burn_in_plot_for_period(
        db_rows,
        burn_in_start,
        burn_in_stop,
        influx_client=influx_client,
        force_recompute=force_recompute,
        slot_id=slot['slot_id'],
    )
    if not result.get('success'):
        result['slot_id'] = slot['slot_id']
        return result

    result.update({
        'slot_id': slot['slot_id'],
        'board_count': slot['board_count'],
        'batches': slot['batches'],
        'boards': slot['boards'],
    })
    return result


def _build_burn_in_plot_for_period(
    db_rows,
    burn_in_start,
    burn_in_stop,
    influx_client=None,
    force_recompute=False,
    slot_id=None,
):
    config = load_production_config()
    period_result = _fetch_period_series(
        burn_in_start,
        burn_in_stop,
        config,
        influx_client=influx_client,
        force_recompute=force_recompute,
        slot_id=slot_id,
    )
    if not period_result.get('success'):
        return period_result

    return {
        'success': True,
        'burn_in_start': burn_in_start.strftime('%Y-%m-%d %H:%M:%S'),
        'burn_in_stop': burn_in_stop.strftime('%Y-%m-%d %H:%M:%S'),
        'duration_hours': round((burn_in_stop - burn_in_start).total_seconds() / 3600.0, 2),
        'series': period_result['series'],
        'totals': period_result['totals'],
        'cached': period_result.get('cached', False),
        'cached_at': period_result.get('cached_at'),
        'plot_html': period_result.get('plot_html'),
        'config': _burn_in_config_payload(config),
    }


def build_burn_in_plot_all_slots(db_rows, influx_client=None, force_recompute=False):
    config = load_production_config()
    slots = list_burn_in_slots(db_rows)
    if not slots:
        return {'success': False, 'error': 'No burn-in slots found'}

    client = influx_client
    owns_client = False
    if client is None:
        try:
            client = get_influx_client()
            owns_client = True
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    slot_payloads = []
    errors = []
    all_cached = True
    try:
        for slot in slots:
            burn_in_start = _parse_datetime(slot['burn_in_start'])
            burn_in_stop = _parse_datetime(slot['burn_in_stop'])
            if not burn_in_start or not burn_in_stop or burn_in_stop <= burn_in_start:
                errors.append(f'{slot["slot_id"]}: invalid burn-in period')
                continue

            period_result = _fetch_period_series(
                burn_in_start,
                burn_in_stop,
                config,
                influx_client=client,
                force_recompute=force_recompute,
                slot_id=slot['slot_id'],
            )
            if not period_result.get('success'):
                errors.append(f'{slot["slot_id"]}: {period_result.get("error", "unknown error")}')
                continue

            if not period_result.get('cached'):
                all_cached = False

            slot_payloads.append({
                'slot_id': slot['slot_id'],
                'burn_in_start': slot['burn_in_start'],
                'burn_in_stop': slot['burn_in_stop'],
                'duration_hours': slot['duration_hours'],
                'board_count': slot['board_count'],
                'batches': slot['batches'],
                'boards': slot['boards'],
                'series': period_result['series'],
                'cached': period_result.get('cached', False),
                'cached_at': period_result.get('cached_at'),
                'plot_html': period_result.get('plot_html'),
            })
    finally:
        if owns_client and client is not None:
            try:
                client.close()
            except Exception:
                pass

    if not slot_payloads:
        return {
            'success': False,
            'error': 'No telemetry found for any burn-in slot',
            'errors': errors,
        }

    return {
        'success': True,
        'mode': 'all_slots',
        'slots': slot_payloads,
        'errors': errors,
        'cached': all_cached,
        'config': _burn_in_config_payload(config),
    }


def _period_cache_is_available(burn_in_start, burn_in_stop, config, slot_id=None):
    temperature_offset = float(config.get('burnin_temperature_offset_c', 0.0))
    profile, energy = _resolve_default_burnin_parameters(config)
    if not profile or not energy:
        return False
    return _load_period_cache(
        burn_in_start,
        burn_in_stop,
        temperature_offset,
        profile['temperature_c'],
        energy['value'],
        slot_id=slot_id,
        config=config,
    ) is not None


def build_burn_in_overview(db_rows):
    config = load_production_config()
    slots = list_burn_in_slots(db_rows)
    all_slots_cached = bool(slots)
    for slot in slots:
        burn_in_start = _parse_datetime(slot['burn_in_start'])
        burn_in_stop = _parse_datetime(slot['burn_in_stop'])
        if not burn_in_start or not burn_in_stop:
            all_slots_cached = False
            break
        if not _period_cache_is_available(
            burn_in_start,
            burn_in_stop,
            config,
            slot_id=slot['slot_id'],
        ):
            all_slots_cached = False
            break
    return {
        'success': True,
        'slots': slots,
        'boards': list_burn_in_boards(db_rows),
        'config': _burn_in_config_payload(config),
        'all_slots_cached': all_slots_cached,
    }
