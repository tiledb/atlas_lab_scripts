"""Burn-in period analysis using InfluxDB oven telemetry."""

import json
from datetime import datetime, timedelta
from math import exp
from pathlib import Path

from production_config import load_production_config, utc_from_interpreted_db_datetime
from production_summary import decode_serial, _parse_datetime

BOLTZMANN_EV_K = 8.617e-5
MEASUREMENT_NAME = 'Burnin_Oven'
ACCRUED_MINS_FIELD = 'BurninAccruedMins'
ACCRUED_MINS_FIELD_ALIASES = ('BurninAccruedMins', 'BurningAccruedMins')
MAX_PLOT_POINTS = 2500
SECRETS_YAML_PATH = Path(__file__).parent.parent.parent / 'secrets' / 'secrets.yaml'
BURN_IN_CACHE_DIR = Path('/var/www/html/drive/production_plots/burn_in')
DEFAULT_BURN_IN_CACHE_DIR = BURN_IN_CACHE_DIR
CACHE_VERSION = 7
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
    fields = ['Toven', 'LVPower', ACCRUED_MINS_FIELD]
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


def _format_db_window_for_influx(value):
    dt = _parse_datetime(value)
    if not dt:
        return None
    utc_dt = utc_from_interpreted_db_datetime(dt)
    return utc_dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def _parse_influx_time(value):
    if isinstance(value, datetime):
        return value
    text = str(value).replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return _parse_datetime(value)


def _query_burnin_points(client, start_dt, stop_dt):
    start_text = _format_db_window_for_influx(start_dt)
    stop_text = _format_db_window_for_influx(stop_dt)
    if not start_text or not stop_text:
        return []

    query = (
        f'SELECT "Toven", "LVPower", "{ACCRUED_MINS_FIELD}" '
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


def _parse_numeric(value):
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _point_accrued_mins(point):
    for key in ACCRUED_MINS_FIELD_ALIASES:
        value = _parse_numeric(point.get(key))
        if value is not None:
            return value
    return None


def _mean_temperature(*values):
    temps = [float(value) for value in values if value is not None]
    if not temps:
        return None
    return sum(temps) / len(temps)


def _insert_gap_fill_rows(rows, gap_threshold_hours):
    if len(rows) < 2 or gap_threshold_hours < 0:
        return rows
    filled = [rows[0]]
    for current in rows[1:]:
        previous = filled[-1]
        dt_hours = (current['timestamp'] - previous['timestamp']).total_seconds() / 3600.0
        if dt_hours > gap_threshold_hours:
            average_temp = _mean_temperature(previous.get('toven'), current.get('toven'))
            start_stamp = previous['timestamp'] + timedelta(milliseconds=1)
            end_stamp = current['timestamp'] - timedelta(milliseconds=1)
            if start_stamp < end_stamp:
                filled.append({
                    'timestamp': start_stamp,
                    'toven': average_temp if average_temp is not None else previous.get('toven'),
                    'lvpower': 1,
                    'accrued': previous.get('accrued'),
                    'gap_fill': 1,
                })
                filled.append({
                    'timestamp': end_stamp,
                    'toven': average_temp if average_temp is not None else current.get('toven'),
                    'lvpower': 1,
                    'accrued': current.get('accrued'),
                    'gap_fill': 1,
                })
            current = dict(current)
            current['gap_fill'] = 1
        filled.append(current)
    return filled


def _stretch_elapsed_for_gap_fill(elapsed_hours, accrued_mins, gap_fill):
    """Give filled intervals at least the accrued-minutes width so aging can ramp."""
    if len(elapsed_hours) < 2:
        return elapsed_hours
    adjusted = [round(float(elapsed_hours[0]), 4)]
    extra = 0.0
    for index in range(1, len(elapsed_hours)):
        wall_dt = float(elapsed_hours[index]) - float(elapsed_hours[index - 1])
        dt = wall_dt
        if index < len(gap_fill) and gap_fill[index] == 1:
            prev_accrued = accrued_mins[index - 1] if index - 1 < len(accrued_mins) else None
            curr_accrued = accrued_mins[index] if index < len(accrued_mins) else None
            if prev_accrued is not None and curr_accrued is not None:
                accrued_dt = max(0.0, (float(curr_accrued) - float(prev_accrued)) / 60.0)
                dt = max(wall_dt, accrued_dt)
        extra += dt - wall_dt
        adjusted.append(round(float(elapsed_hours[index]) + extra, 4))
    return adjusted


def _iter_gap_fill_segments(gap_fill, length):
    if length <= 0:
        return
    if length == 1:
        yield (0, 0, False)
        return
    segment_start = 0
    segment_fill = len(gap_fill) > 1 and gap_fill[1] == 1
    for index in range(2, length):
        is_fill = index < len(gap_fill) and gap_fill[index] == 1
        if is_fill != segment_fill:
            yield (segment_start, index - 1, segment_fill)
            segment_start = index - 1
            segment_fill = is_fill
    yield (segment_start, length - 1, segment_fill)


def _add_gap_split_traces(
    fig,
    x_values,
    y_values,
    gap_fill,
    *,
    name,
    color,
    row,
    col,
    secondary_y=False,
    width=2.2,
    solid_dash='solid',
    fill_dash='dash',
    shape='linear',
    legendgroup=None,
    showlegend=True,
    customdata=None,
    hovertemplate=None,
    hoverinfo=None,
):
    import plotly.graph_objects as go

    length = len(x_values or [])
    y_values = y_values or []
    gap_fill = gap_fill or []
    traces = []
    for start, end, is_fill in _iter_gap_fill_segments(gap_fill, length):
        trace_kwargs = {
            'x': x_values[start:end + 1],
            'y': y_values[start:end + 1],
            'mode': 'lines',
            'name': name,
            'line': dict(
                color=color,
                width=width,
                dash=fill_dash if is_fill else solid_dash,
                shape=shape,
            ),
            'legendgroup': legendgroup or name,
            'showlegend': False,
        }
        if hovertemplate:
            trace_kwargs['hovertemplate'] = hovertemplate
        if hoverinfo:
            trace_kwargs['hoverinfo'] = hoverinfo
        if customdata is not None:
            trace_kwargs['customdata'] = customdata[start:end + 1]
        traces.append((go.Scatter(**trace_kwargs), is_fill))

    legend_shown = False
    for trace, is_fill in traces:
        if showlegend and not legend_shown and not is_fill:
            trace.showlegend = True
            legend_shown = True
    if showlegend and not legend_shown and traces:
        traces[0][0].showlegend = True

    for trace, _is_fill in traces:
        fig.add_trace(trace, row=row, col=col, secondary_y=secondary_y)


def _empty_time_series():
    return {
        'elapsed_hours': [],
        'toven_c': [],
        'lvpower': [],
        'accrued_mins': [],
        'gap_fill': [],
        'gap_threshold_hours': 0.5,
        'total_elapsed_hours': 0.0,
        'point_count': 0,
    }


def _interval_is_accrued_fill(series, index):
    if index <= 0:
        return False
    gap_fill = series.get('gap_fill') or []
    return index < len(gap_fill) and gap_fill[index] == 1


def _interval_duration_hours(series, index):
    elapsed = series.get('elapsed_hours') or []
    if index <= 0 or index >= len(elapsed):
        return 0.0
    elapsed_dt = elapsed[index] - elapsed[index - 1]
    if not _interval_is_accrued_fill(series, index):
        return max(0.0, elapsed_dt)
    accrued = series.get('accrued_mins') or []
    if index >= len(accrued):
        return max(0.0, elapsed_dt)
    prev = accrued[index - 1]
    curr = accrued[index]
    if prev is None or curr is None:
        return max(0.0, elapsed_dt)
    return max(0.0, (curr - prev) / 60.0)


def _interval_temperature(series, index):
    toven = series.get('toven_c') or []
    curr = toven[index] if index < len(toven) else None
    if not _interval_is_accrued_fill(series, index):
        return curr
    prev = toven[index - 1] if index - 1 < len(toven) else None
    return _mean_temperature(prev, curr)


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


def _build_time_series(points, burn_in_start, burn_in_stop, config):
    rows = []
    for point in sorted(points, key=lambda item: item.get('time', '')):
        timestamp = _parse_influx_time(point.get('time'))
        if not timestamp:
            continue
        rows.append({
            'timestamp': timestamp,
            'toven': point.get('Toven'),
            'lvpower': point.get('LVPower'),
            'accrued': _point_accrued_mins(point),
            'gap_fill': 0,
        })

    if not rows:
        series = _empty_time_series()
        series['gap_threshold_hours'] = (
            float(config.get('burnin_gap_threshold_min', 30.0) or 30.0) / 60.0
        )
        return series

    temperature_offset = float(config.get('burnin_temperature_offset_c', 0.0))
    accrued_start = float(config.get('burnin_accrued_min_start', 0.0) or 0.0)
    accrued_end = float(config.get('burnin_accrued_min_end', 7200.0) or 7200.0)
    gap_threshold_min = float(config.get('burnin_gap_threshold_min', 30.0) or 30.0)
    gap_threshold_hours = max(0.0, gap_threshold_min / 60.0)
    toven_values = _forward_fill([row['toven'] for row in rows])
    lvpower_values = _forward_fill([row['lvpower'] for row in rows])
    accrued_values = _forward_fill([row['accrued'] for row in rows])
    start_utc = utc_from_interpreted_db_datetime(burn_in_start)
    stop_utc = utc_from_interpreted_db_datetime(burn_in_stop) if burn_in_stop else None
    has_accrued = any(value is not None for value in accrued_values)

    for index, row in enumerate(rows):
        row['toven'] = toven_values[index]
        row['lvpower'] = lvpower_values[index]
        row['accrued'] = accrued_values[index]

    first = rows[0]
    first_elapsed_hours = (first['timestamp'] - start_utc).total_seconds() / 3600.0
    first_accrued = first['accrued']
    if has_accrued and first['timestamp'] >= start_utc and (
        first_elapsed_hours > gap_threshold_hours
        or (first_accrued is not None and first_accrued > accrued_start + 1e-9)
    ):
        rows.insert(0, {
            'timestamp': start_utc,
            'toven': first['toven'],
            'lvpower': 1,
            'accrued': accrued_start,
            'gap_fill': 0,
        })
        rows[1]['gap_fill'] = 1

    last = rows[-1]
    last_accrued = last['accrued']
    if has_accrued and last_accrued is not None and last_accrued < accrued_end - 1e-9:
        end_timestamp = last['timestamp']
        if stop_utc is not None and stop_utc >= last['timestamp']:
            end_timestamp = stop_utc
        rows.append({
            'timestamp': end_timestamp,
            'toven': last['toven'],
            'lvpower': 1,
            'accrued': accrued_end,
            'gap_fill': 1,
        })

    rows = _insert_gap_fill_rows(rows, gap_threshold_hours)

    elapsed_hours = []
    toven_c = []
    lvpower = []
    accrued_mins = []
    gap_fill = []
    for row in rows:
        elapsed = (row['timestamp'] - start_utc).total_seconds() / 3600.0
        elapsed_hours.append(round(elapsed, 4))
        if row['toven'] is not None:
            toven_c.append(round(float(row['toven']) + temperature_offset, 3))
        else:
            toven_c.append(None)
        lvpower.append(1 if _is_power_on(row['lvpower']) else 0)
        accrued_mins.append(
            None if row['accrued'] is None else round(float(row['accrued']), 4)
        )
        gap_fill.append(1 if row.get('gap_fill') else 0)

    elapsed_hours = _stretch_elapsed_for_gap_fill(elapsed_hours, accrued_mins, gap_fill)

    return {
        'elapsed_hours': elapsed_hours,
        'toven_c': toven_c,
        'lvpower': lvpower,
        'accrued_mins': accrued_mins,
        'gap_fill': gap_fill,
        'gap_threshold_hours': gap_threshold_hours,
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
    source_gap = series.get('gap_fill') or [0] * length
    for index, flag in enumerate(source_gap):
        if flag == 1:
            indices.append(index)
    indices = sorted(set(indices))

    downsampled = {
        'elapsed_hours': [series['elapsed_hours'][index] for index in indices],
        'toven_c': [series['toven_c'][index] for index in indices],
        'lvpower': [series['lvpower'][index] for index in indices],
        'accrued_mins': [
            (series.get('accrued_mins') or [None] * length)[index]
            for index in indices
        ],
        'gap_fill': [],
        'gap_threshold_hours': series.get('gap_threshold_hours', 0.5),
        'total_elapsed_hours': series.get('total_elapsed_hours', 0.0),
        'point_count': series.get('point_count', 0),
    }
    for position, index in enumerate(indices):
        filled = source_gap[index] == 1
        if position > 0:
            previous = indices[position - 1]
            filled = filled or any(
                source_gap[mid] == 1 for mid in range(previous + 1, index + 1)
            )
        downsampled['gap_fill'].append(1 if filled else 0)
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
    lvpower = series.get('lvpower') or []

    for index, _elapsed in enumerate(elapsed_hours):
        if index > 0:
            if _interval_is_accrued_fill(series, index):
                temperature = _interval_temperature(series, index)
                dt_hours = _interval_duration_hours(series, index)
                if temperature is not None and dt_hours > 0:
                    cumulative += acceleration_factor(
                        temperature,
                        use_temperature_c,
                        activation_energy_ev,
                    ) * dt_hours
            elif (
                index < len(lvpower)
                and lvpower[index - 1] == 1
                and _interval_temperature(series, index) is not None
            ):
                dt_hours = _interval_duration_hours(series, index)
                if dt_hours > 0:
                    cumulative += acceleration_factor(
                        _interval_temperature(series, index),
                        use_temperature_c,
                        activation_energy_ev,
                    ) * dt_hours
        aging_hours.append(round(cumulative, 4))
    return aging_hours


def _compute_power_on_hours(series, power_field='lvpower'):
    elapsed_hours = series.get('elapsed_hours') or []
    power_values = series.get(power_field) or []
    total = 0.0
    for index in range(1, len(elapsed_hours)):
        if _interval_is_accrued_fill(series, index):
            total += _interval_duration_hours(series, index)
        elif index - 1 < len(power_values) and power_values[index - 1] == 1:
            total += max(0.0, elapsed_hours[index] - elapsed_hours[index - 1])
    return total


def _average_power_on_temperature(series):
    temps = series.get('toven_c') or []
    power = series.get('lvpower') or []
    values = [
        float(temp)
        for temp, powered in zip(temps, power)
        if temp is not None and powered == 1
    ]
    if not values:
        return None
    return sum(values) / len(values)


def _slot_compare_metrics(slot, t_use_c, ea_ev):
    series = slot.get('series') or {}
    elapsed = series.get('elapsed_hours') or []
    aging_hours = _compute_aging_hours(series, t_use_c, ea_ev) if elapsed else []
    power_on_hours = _compute_power_on_hours(series, 'lvpower') if elapsed else 0.0
    running_hours = elapsed[-1] if elapsed else float(slot.get('duration_hours') or 0.0)
    avg_af = None
    if aging_hours and power_on_hours > 0:
        avg_af = aging_hours[-1] / power_on_hours
    return {
        'slot_id': slot.get('slot_id') or 'slot',
        'start': slot.get('burn_in_start') or '—',
        'stop': slot.get('burn_in_stop') or '—',
        'running_hours': running_hours,
        'burn_in_hours': power_on_hours,
        'avg_af': avg_af,
        'avg_temp': _average_power_on_temperature(series),
        'aging_hours': aging_hours[-1] if aging_hours else 0.0,
    }


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


def _format_burn_in_aged_legend(hours):
    base = _format_burn_in_hours_days_tick(hours or 0.0)
    years = round(float(hours or 0.0), 1) / (24.0 * 365.25)
    rounded_years = round(years, 2)
    years_text = (
        str(int(rounded_years))
        if rounded_years == int(rounded_years)
        else f'{rounded_years:.2f}'
    )
    return f'{base} ({years_text} years)'


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
    aged_legend = _format_burn_in_aged_legend(aging_hours[-1] if aging_hours else 0.0)
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
    gap_fill = series.get('gap_fill') or []
    _add_gap_split_traces(
        fig,
        series['elapsed_hours'],
        aging_hours,
        gap_fill,
        name=f'Accelerated · {aged_legend}{avg_af_suffix} ({aging_label})',
        color='#AB63FA',
        row=1,
        col=1,
        secondary_y=False,
        width=2,
    )
    _add_gap_split_traces(
        fig,
        series['elapsed_hours'],
        series['toven_c'],
        gap_fill,
        name=f'Oven Temperature (Toven + {offset:g}°C)',
        color='#EF553B',
        row=1,
        col=1,
        secondary_y=True,
        width=2,
    )
    _add_gap_split_traces(
        fig,
        series['elapsed_hours'],
        series['lvpower'],
        gap_fill,
        name='LVPower',
        color='#19D3F3',
        row=2,
        col=1,
        width=2,
        shape='hv',
        customdata=lv_states,
        hovertemplate='Elapsed: %{x:.2f} h<br>LVPower: %{customdata}<extra></extra>',
    )
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
    from plot_cache import inject_cache_banner
    inject_cache_banner(html_path, datetime.now())
    return html_path.name


ALL_SLOTS_HTML_NAME = 'burn_in_all_slots_latest.html'
SLOT_PLOT_COLORS = (
    '#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3',
    '#FF6692', '#B6E880', '#FF97FF', '#FECB52', '#7A5195', '#BC5090',
)


def _mean_std(values):
    nums = []
    for value in values or []:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number != number:
            continue
        nums.append(number)
    if not nums:
        return None, None
    mean = sum(nums) / len(nums)
    if len(nums) == 1:
        return mean, 0.0
    variance = sum((value - mean) ** 2 for value in nums) / (len(nums) - 1)
    return mean, variance ** 0.5


def _title_with_mean_std(title, values, decimals, unit=''):
    mean, std = _mean_std(values)
    if mean is None:
        return title
    unit_text = f' {unit}' if unit else ''
    return f'{title}<br>{mean:.{decimals}f} ± {std:.{decimals}f}{unit_text}'


def _build_all_slots_compare_figure(slot_payloads, t_use_c, ea_ev):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    metrics = [_slot_compare_metrics(slot, t_use_c, ea_ev) for slot in slot_payloads or []]
    if not metrics:
        return None

    labels = [item['slot_id'] for item in metrics]
    colors = [SLOT_PLOT_COLORS[index % len(SLOT_PLOT_COLORS)] for index in range(len(metrics))]
    periods = [f"{item['start']} -> {item['stop']}" for item in metrics]

    def _values(key):
        values = []
        for item in metrics:
            value = item.get(key)
            values.append(None if value is None else float(value))
        return values

    avg_af = _values('avg_af')
    aging_days = [
        None if item.get('aging_hours') is None else float(item['aging_hours']) / 24.0
        for item in metrics
    ]
    running_hours = _values('running_hours')
    burn_in_hours = _values('burn_in_hours')
    avg_temp = _values('avg_temp')

    fig = make_subplots(
        rows=3,
        cols=2,
        specs=[
            [{}, {}],
            [{}, {}],
            [{}, None],
        ],
        subplot_titles=(
            _title_with_mean_std('Average AF', avg_af, 2),
            _title_with_mean_std('Accelerated Aging', aging_days, 1, 'd'),
            _title_with_mean_std('Running Time', running_hours, 1, 'h'),
            _title_with_mean_std('Burn-In Time', burn_in_hours, 1, 'h'),
            _title_with_mean_std('Average Burn-In Temp', avg_temp, 1, '°C'),
        ),
        vertical_spacing=0.12,
        horizontal_spacing=0.1,
    )
    specs = [
        (1, 1, avg_af, 'AF', 2),
        (1, 2, aging_days, 'Days', 1),
        (2, 1, running_hours, 'Hours', 1),
        (2, 2, burn_in_hours, 'Hours', 1),
        (3, 1, avg_temp, '°C', 1),
    ]
    for row, col, values, y_title, decimals in specs:
        plotted = [0.0 if value is None else value for value in values]
        y_max = max(plotted) if plotted else 0.0
        fig.add_trace(go.Bar(
            x=labels,
            y=plotted,
            marker=dict(color=colors),
            text=[
                '' if value is None else f'{value:.{decimals}f}'
                for value in values
            ],
            textposition='outside',
            textfont=dict(size=11),
            cliponaxis=False,
            customdata=periods,
            hovertemplate='%{x}<br>%{y:.2f}<br>%{customdata}<extra></extra>',
            showlegend=False,
        ), row=row, col=col)
        fig.update_yaxes(
            title_text=y_title,
            rangemode='tozero',
            range=[0, y_max * 1.22 if y_max > 0 else 1],
            row=row,
            col=col,
        )
        fig.update_xaxes(tickangle=-35 if len(labels) > 6 else 0, row=row, col=col)

    fig.update_layout(
        title='Burn-In Slot Comparison',
        height=1080,
        margin=dict(t=80, r=30, b=80, l=60),
    )
    return fig


def _write_all_slots_plot_html(slot_payloads, config, cached_at=None):
    try:
        from plotly.subplots import make_subplots
    except ImportError as exc:
        print(f'Plotly not available for burn-in all-slots HTML export: {exc}')
        return None

    profile, energy = _resolve_default_burnin_parameters(config)
    if not profile or not energy:
        return None

    t_use_c = float(profile['temperature_c'])
    ea_ev = float(energy['value'])
    offset = float(config.get('burnin_temperature_offset_c', 0.0))
    aging_label = f"{profile['name']} {t_use_c}°C, Ea={ea_ev} eV"

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.72, 0.28],
        specs=[[{'secondary_y': True}], [{}]],
    )

    max_elapsed = 0.0
    max_aging = 0.0
    min_temperature = None
    max_temperature = None

    for index, slot in enumerate(slot_payloads or []):
        series = slot.get('series') or {}
        if not series.get('elapsed_hours'):
            continue
        color = SLOT_PLOT_COLORS[index % len(SLOT_PLOT_COLORS)]
        slot_id = slot.get('slot_id') or f'slot_{index}'
        aging_hours = _compute_aging_hours(series, t_use_c, ea_ev)
        power_on_hours = _compute_power_on_hours(series, 'lvpower')
        avg_af_suffix = _format_avg_af_legend_suffix(aging_hours, power_on_hours)
        aged_legend = _format_burn_in_aged_legend(aging_hours[-1] if aging_hours else 0.0)
        lv_states = ['ON' if value == 1 else 'OFF' for value in series.get('lvpower', [])]

        gap_fill = series.get('gap_fill') or []
        _add_gap_split_traces(
            fig,
            series['elapsed_hours'],
            aging_hours,
            gap_fill,
            name=f'{slot_id} · {aged_legend}{avg_af_suffix}',
            color=color,
            row=1,
            col=1,
            secondary_y=False,
            legendgroup=slot_id,
            hovertemplate=(
                f'Slot: {slot_id}<br>'
                'Elapsed: %{x:.2f} h<br>'
                'Aging: %{y:.2f} h'
                '<extra></extra>'
            ),
        )
        _add_gap_split_traces(
            fig,
            series['elapsed_hours'],
            series.get('toven_c'),
            gap_fill,
            name=f'{slot_id} Temp',
            color=color,
            row=1,
            col=1,
            secondary_y=True,
            solid_dash='dot',
            legendgroup=slot_id,
            showlegend=False,
            hovertemplate=(
                f'Slot: {slot_id}<br>'
                'Elapsed: %{x:.2f} h<br>'
                'Toven: %{y:.2f} °C'
                '<extra></extra>'
            ),
        )
        _add_gap_split_traces(
            fig,
            series['elapsed_hours'],
            series.get('lvpower'),
            gap_fill,
            name=f'{slot_id} LVPower',
            color=color,
            row=2,
            col=1,
            width=2,
            shape='hv',
            legendgroup=slot_id,
            showlegend=False,
            customdata=lv_states,
            hovertemplate=(
                f'Slot: {slot_id}<br>'
                'Elapsed: %{x:.2f} h<br>'
                'LVPower: %{customdata}<extra></extra>'
            ),
        )

        if series['elapsed_hours']:
            max_elapsed = max(max_elapsed, series['elapsed_hours'][-1] or 0.0)
        if aging_hours:
            max_aging = max(max_aging, aging_hours[-1] or 0.0)
        for value in series.get('toven_c') or []:
            if value is None:
                continue
            min_temperature = value if min_temperature is None else min(min_temperature, value)
            max_temperature = value if max_temperature is None else max(max_temperature, value)

    if min_temperature is None:
        min_temperature = 0.0
    if max_temperature is None:
        max_temperature = 100.0

    axis_ticks = _build_burn_in_axis_tick_config(
        max_elapsed,
        max_aging,
        min_temperature,
        max_temperature,
    )
    n_legend = sum(
        1 for slot in slot_payloads or []
        if (slot.get('series') or {}).get('elapsed_hours')
    )
    extra_legend_px = max(0, n_legend - 1) * 22
    gap_min = float(config.get('burnin_gap_threshold_min', 30.0) or 30.0)
    accrued_start = float(config.get('burnin_accrued_min_start', 0.0) or 0.0)
    accrued_end = float(config.get('burnin_accrued_min_end', 7200.0) or 7200.0)
    fig.update_layout(
        title=(
            f'Burn-In All Slots ({aging_label}, Toven + {offset:g}°C, '
            f'gap fill {gap_min:g} min, BurninAccruedMins {accrued_start:g}→{accrued_end:g})'
        ),
        height=700 + extra_legend_px,
        margin=dict(t=60, r=80, b=100 + max(n_legend, 1) * 22, l=120),
        hovermode='x unified',
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=0,
            yref='container',
            x=0.5,
            xanchor='center',
            font=dict(size=11),
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

    cache_dir = get_burn_in_cache_dir(config)
    cache_dir.mkdir(parents=True, exist_ok=True)
    html_path = cache_dir / ALL_SLOTS_HTML_NAME
    from plotly.io import to_html
    from plot_cache import cache_banner_html
    compare_fig = _build_all_slots_compare_figure(slot_payloads, t_use_c, ea_ev)
    html_parts = [
        '<!DOCTYPE html><html><head><meta charset="utf-8">',
        '<title>Burn-In All Slots</title></head><body>',
        cache_banner_html(cached_at),
        to_html(fig, include_plotlyjs='cdn', full_html=False),
    ]
    if compare_fig is not None:
        html_parts.append(to_html(compare_fig, include_plotlyjs=False, full_html=False))
    html_parts.append('</body></html>')
    html_path.write_text('\n'.join(html_parts), encoding='utf-8')
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
    _clear_slot_cache(slot_id=slot_id, config=config)
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
        try:
            plot_html = _write_period_plot_html(
                burn_in_start,
                burn_in_stop,
                series,
                config,
                slot_id=slot_id,
                use_temperature_c=t_use_c,
                activation_energy_ev=ea_ev,
            )
        except Exception as exc:
            print(f'Error writing burn-in HTML plot: {exc}')
            plot_html = None

    cached_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    payload = {
        'version': CACHE_VERSION,
        'burn_in_start': burn_in_start.strftime('%Y-%m-%d %H:%M:%S'),
        'burn_in_stop': burn_in_stop.strftime('%Y-%m-%d %H:%M:%S'),
        'temperature_offset_c': temperature_offset_c,
        'cached_at': cached_at,
        'series': series,
        'totals': totals,
    }
    if plot_html:
        payload['plot_html'] = plot_html
    cache_path.write_text(json.dumps(payload), encoding='utf-8')
    return plot_html


def _clear_slot_cache(slot_id=None, config=None):
    cache_dir = get_burn_in_cache_dir(config)
    if not cache_dir.exists():
        return
    slot_slug = _slot_cache_slug(slot_id)
    for path in cache_dir.glob(f'{slot_slug}_*'):
        try:
            path.unlink()
        except OSError as exc:
            print(f'Error clearing burn-in cache {path}: {exc}')


def _clear_period_cache(burn_in_start, burn_in_stop, slot_id=None, config=None):
    # Clear all cached files for this slot before regenerating.
    _clear_slot_cache(slot_id=slot_id, config=config)


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
            plot_html = cached.get('plot_html')
            html_path = _period_plot_html_path(
                burn_in_start,
                burn_in_stop,
                t_use_c,
                ea_ev,
                slot_id=slot_id,
                config=config,
            )
            try:
                if not html_path.exists():
                    plot_html = _write_period_plot_html(
                        burn_in_start,
                        burn_in_stop,
                        cached['series'],
                        config,
                        slot_id=slot_id,
                        use_temperature_c=t_use_c,
                        activation_energy_ev=ea_ev,
                    )
                else:
                    from plot_cache import inject_cache_banner
                    inject_cache_banner(html_path, cached.get('cached_at'))
                    plot_html = html_path.name
            except Exception as exc:
                print(f'Error ensuring burn-in HTML plot: {exc}')
            return {
                'success': True,
                'series': cached['series'],
                'totals': cached['totals'],
                'cached': True,
                'cached_at': cached.get('cached_at'),
                'plot_html': plot_html,
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

    series = _build_time_series(points, burn_in_start, burn_in_stop, config)
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


def _format_burn_in_timestamp(value):
    parsed = _parse_datetime(value)
    if not parsed:
        return None
    return parsed.strftime('%Y-%m-%d %H:%M:%S')


def build_burn_in_slot_management(db_rows):
    """Slots plus every selectable board, including boards with no burn-in yet."""
    slots = list_burn_in_slots(db_rows)
    slot_by_period = {
        (slot['burn_in_start'], slot['burn_in_stop']): slot['slot_id']
        for slot in slots
    }
    boards = []
    for row in db_rows:
        decoded = decode_serial(row['serial_no'])
        if decoded['tag'] == 90:
            continue
        start = _format_burn_in_timestamp(row.get('burn_in_start'))
        stop = _format_burn_in_timestamp(row.get('burn_in_stop'))
        in_slot = bool(start and stop and stop > start)
        boards.append({
            'serial': row['serial_no'],
            'batch': decoded['batch'],
            'position': decoded['position'],
            'burn_in': 1 if row.get('burn_in') == 1 else 0,
            'burn_in_start': start,
            'burn_in_stop': stop,
            'burn_in_op': row.get('burn_in_op') or None,
            'slot_id': slot_by_period.get((start, stop)) if in_slot else None,
        })
    boards.sort(key=lambda board: (board['batch'], board['position'], board['serial']))
    return {
        'success': True,
        'slots': slots,
        'boards': boards,
    }


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
        'accrued_min_start': config.get('burnin_accrued_min_start', 0.0),
        'accrued_min_end': config.get('burnin_accrued_min_end', 7200.0),
        'gap_threshold_min': config.get('burnin_gap_threshold_min', 30.0),
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

    plot_html = None
    try:
        plot_html = _write_all_slots_plot_html(slot_payloads, config)
    except Exception as exc:
        print(f'Error writing burn-in all-slots HTML plot: {exc}')
        plot_html = None

    return {
        'success': True,
        'mode': 'all_slots',
        'slots': slot_payloads,
        'errors': errors,
        'cached': all_cached,
        'plot_html': plot_html,
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
