"""Long burn-in analysis using TileBurninTest InfluxDB telemetry."""

import json
from datetime import datetime
from math import exp
from pathlib import Path

from burn_in import (
    BOLTZMANN_EV_K,
    MAX_PLOT_POINTS,
    _format_influx_time,
    _forward_fill,
    _is_power_on,
    _parse_influx_time,
    acceleration_factor,
    get_influx_client,
)
from production_config import load_production_config
from production_summary import _parse_datetime

MEASUREMENT_NAME = 'TileBurninTest'
LONG_BURN_IN_CACHE_DIR = Path('/var/www/html/drive/production_plots/long_burn_in')
CACHE_VERSION = 2


def long_burn_in_arrhenius_equation_text(temperature_offset_c):
    return 'AF = exp[(Ea / kB) × (1/T_use -> 1/T_test)]'


def long_burn_in_eyring_equation_text(temperature_offset_c, v_test_v, v_use_v):
    return (
        'AF = exp[(Ea / kB) × (1/T_use -> 1/T_test)] × (V_test / V_use)^β, '
        f'V_test = {v_test_v:g} V, V_use = {v_use_v:g} V'
    )


def long_burn_in_peck_equation_text(temperature_offset_c):
    return 'AF = (RH_test / RH_use)^n × exp[(Ea / kB) × (1/T_use -> 1/T_test)]'


def long_burn_in_equation_text(temperature_offset_c):
    return long_burn_in_arrhenius_equation_text(temperature_offset_c)


def eyring_acceleration_factor(
    temperature_c,
    use_temperature_c,
    activation_energy_ev,
    v_test_v,
    v_use_v,
    beta,
):
    arrhenius = acceleration_factor(temperature_c, use_temperature_c, activation_energy_ev)
    try:
        v_test_v = float(v_test_v)
        v_use_v = float(v_use_v)
        beta = float(beta)
    except (TypeError, ValueError):
        return 0.0
    if v_use_v <= 0 or v_test_v <= 0:
        return 0.0
    return arrhenius * ((v_test_v / v_use_v) ** beta)


def peck_acceleration_factor(
    temperature_c,
    use_temperature_c,
    activation_energy_ev,
    rh_test_pct,
    rh_use_pct,
    peck_exponent,
):
    arrhenius = acceleration_factor(temperature_c, use_temperature_c, activation_energy_ev)
    try:
        rh_test_pct = float(rh_test_pct)
        rh_use_pct = float(rh_use_pct)
        peck_exponent = float(peck_exponent)
    except (TypeError, ValueError):
        return 0.0
    if rh_use_pct <= 0 or rh_test_pct <= 0:
        return 0.0
    return ((rh_test_pct / rh_use_pct) ** peck_exponent) * arrhenius


def _board_tag_key(board_serial):
    return f'TileBurninOven {str(board_serial).strip()}'


def get_influx_source_info():
    from burn_in import get_influx_source_info as burn_in_source

    base = burn_in_source()
    return {
        **base,
        'measurement': MEASUREMENT_NAME,
        'fields': [
            'env_temp',
            'env_hum',
            'power_state',
            'power_good',
            'db_temperature',
        ],
        'description': (
            f'{base.get("host")}:{base.get("port")}, database "{base.get("database")}", '
            f'measurement "{MEASUREMENT_NAME}" '
            f'(fields: env_temp, env_hum, power_state, power_good, db_temperature)'
        ),
    }


def _resolve_period(config):
    board_serial = str(config.get('long_burnin_board_serial', '')).strip()
    if not board_serial:
        return None, None, None, 'Long burn-in board serial is not configured'

    start_dt = _parse_datetime(config.get('long_burnin_start'))
    if not start_dt:
        return None, None, None, 'Long burn-in start time is not configured'

    stop_text = str(config.get('long_burnin_stop', '')).strip()
    stop_dt = _parse_datetime(stop_text) if stop_text else datetime.now().replace(microsecond=0)
    if stop_dt <= start_dt:
        return None, None, None, 'Long burn-in stop time must be after the start time'

    return board_serial, start_dt, stop_dt, None


def _query_env_power_points(client, start_dt, stop_dt):
    start_text = _format_influx_time(start_dt)
    stop_text = _format_influx_time(stop_dt)
    if not start_text or not stop_text:
        return []

    query = (
        f'SELECT "env_temp", "env_hum", "power_state", "power_good" '
        f'FROM "{MEASUREMENT_NAME}" '
        f"WHERE time >= '{start_text}' AND time <= '{stop_text}'"
    )
    return list(client.query(query).get_points())


def _query_fpga_temperature_points(client, start_dt, stop_dt, board_serial, fpga_label):
    start_text = _format_influx_time(start_dt)
    stop_text = _format_influx_time(stop_dt)
    tag_key = _board_tag_key(board_serial)
    if not start_text or not stop_text or not fpga_label:
        return []

    query = (
        f'SELECT "db_temperature" '
        f'FROM "{MEASUREMENT_NAME}" '
        f"WHERE time >= '{start_text}' AND time <= '{stop_text}' "
        f"AND \"{tag_key}\" = '{fpga_label}'"
    )
    return list(client.query(query).get_points())


def _is_power_pair_on(power_state, power_good):
    return _is_power_on(power_state) and _is_power_on(power_good)


def _downsample_long_burn_series(series, max_points=MAX_PLOT_POINTS):
    length = len(series.get('elapsed_hours', []))
    if length <= max_points:
        return series

    step = max(length // max_points, 1)
    indices = list(range(0, length, step))
    if indices[-1] != length - 1:
        indices.append(length - 1)

    keys = [
        'elapsed_hours',
        'env_temp_c',
        'env_hum',
        'fpga_a_temp_c',
        'fpga_b_temp_c',
        'power_state',
        'power_good',
        'power_on',
    ]
    downsampled = {
        key: [series[key][index] for index in indices]
        for key in keys
        if key in series
    }
    downsampled['total_elapsed_hours'] = series.get('total_elapsed_hours', 0.0)
    downsampled['point_count'] = series.get('point_count', 0)
    return downsampled


def _merge_point_store(store, timestamp, updates):
    if timestamp not in store:
        store[timestamp] = {}
    store[timestamp].update(updates)


def _build_time_series(env_points, fpga_a_points, fpga_b_points, period_start, config):
    store = {}

    for point in env_points:
        timestamp = _parse_influx_time(point.get('time'))
        if not timestamp:
            continue
        _merge_point_store(store, timestamp, {
            'env_temp': point.get('env_temp'),
            'env_hum': point.get('env_hum'),
            'power_state': point.get('power_state'),
            'power_good': point.get('power_good'),
        })

    for point in fpga_a_points:
        timestamp = _parse_influx_time(point.get('time'))
        if not timestamp:
            continue
        _merge_point_store(store, timestamp, {'fpga_a_temp': point.get('db_temperature')})

    for point in fpga_b_points:
        timestamp = _parse_influx_time(point.get('time'))
        if not timestamp:
            continue
        _merge_point_store(store, timestamp, {'fpga_b_temp': point.get('db_temperature')})

    if not store:
        return {
            'elapsed_hours': [],
            'env_temp_c': [],
            'env_hum': [],
            'fpga_a_temp_c': [],
            'fpga_b_temp_c': [],
            'power_state': [],
            'power_good': [],
            'power_on': [],
            'total_elapsed_hours': 0.0,
            'point_count': 0,
        }

    rows = []
    for timestamp in sorted(store.keys()):
        payload = store[timestamp]
        rows.append({
            'timestamp': timestamp,
            'env_temp': payload.get('env_temp'),
            'env_hum': payload.get('env_hum'),
            'power_state': payload.get('power_state'),
            'power_good': payload.get('power_good'),
            'fpga_a_temp': payload.get('fpga_a_temp'),
            'fpga_b_temp': payload.get('fpga_b_temp'),
        })

    temperature_offset = float(config.get('long_burnin_temperature_offset_c', 0.0))
    env_temp_values = _forward_fill([row['env_temp'] for row in rows])
    env_hum_values = _forward_fill([row['env_hum'] for row in rows])
    fpga_a_values = _forward_fill([row['fpga_a_temp'] for row in rows])
    fpga_b_values = _forward_fill([row['fpga_b_temp'] for row in rows])
    power_state_values = _forward_fill([row['power_state'] for row in rows])
    power_good_values = _forward_fill([row['power_good'] for row in rows])

    elapsed_hours = []
    env_temp_c = []
    env_hum = []
    fpga_a_temp_c = []
    fpga_b_temp_c = []
    power_state = []
    power_good = []
    power_on = []

    for index, row in enumerate(rows):
        elapsed = (row['timestamp'] - period_start).total_seconds() / 3600.0
        elapsed_hours.append(round(elapsed, 4))

        env_value = env_temp_values[index]
        if env_value is not None:
            env_temp_c.append(round(float(env_value) + temperature_offset, 3))
        else:
            env_temp_c.append(None)

        for value_list, source_values in (
            (fpga_a_temp_c, fpga_a_values),
            (fpga_b_temp_c, fpga_b_values),
        ):
            value = source_values[index]
            if value is not None:
                value_list.append(round(float(value), 3))
            else:
                value_list.append(None)

        hum_value = env_hum_values[index]
        env_hum.append(round(float(hum_value), 3) if hum_value is not None else None)

        state_on = 1 if _is_power_on(power_state_values[index]) else 0
        good_on = 1 if _is_power_on(power_good_values[index]) else 0
        power_state.append(state_on)
        power_good.append(good_on)
        power_on.append(1 if _is_power_pair_on(power_state_values[index], power_good_values[index]) else 0)

    return {
        'elapsed_hours': elapsed_hours,
        'env_temp_c': env_temp_c,
        'env_hum': env_hum,
        'fpga_a_temp_c': fpga_a_temp_c,
        'fpga_b_temp_c': fpga_b_temp_c,
        'power_state': power_state,
        'power_good': power_good,
        'power_on': power_on,
        'total_elapsed_hours': elapsed_hours[-1] if elapsed_hours else 0.0,
        'point_count': len(rows),
    }


def _compute_aging_hours(series, temperature_key, use_temperature_c, activation_energy_ev):
    return _compute_model_aging_hours(
        series,
        temperature_key,
        'arrhenius',
        use_temperature_c=use_temperature_c,
        activation_energy_ev=activation_energy_ev,
    )


def _compute_model_aging_hours(
    series,
    temperature_key,
    model,
    use_temperature_c,
    activation_energy_ev,
    v_test_v=12.0,
    v_use_v=10.0,
    beta=2.0,
    rh_use_pct=10.0,
    peck_exponent=3.0,
):
    cumulative = 0.0
    aging_hours = []
    elapsed_hours = series.get('elapsed_hours') or []
    temperatures = series.get(temperature_key) or []
    humidity = series.get('env_hum') or []
    power_on = series.get('power_on') or []

    for index, elapsed in enumerate(elapsed_hours):
        if (
            index > 0
            and power_on[index - 1] == 1
            and temperatures[index] is not None
        ):
            dt_hours = elapsed - elapsed_hours[index - 1]
            if dt_hours > 0:
                if model == 'eyring':
                    af = eyring_acceleration_factor(
                        temperatures[index],
                        use_temperature_c,
                        activation_energy_ev,
                        v_test_v,
                        v_use_v,
                        beta,
                    )
                elif model == 'peck':
                    af = peck_acceleration_factor(
                        temperatures[index],
                        use_temperature_c,
                        activation_energy_ev,
                        humidity[index] if index < len(humidity) else None,
                        rh_use_pct,
                        peck_exponent,
                    )
                else:
                    af = acceleration_factor(
                        temperatures[index],
                        use_temperature_c,
                        activation_energy_ev,
                    )
                cumulative += af * dt_hours
        aging_hours.append(round(cumulative, 4))
    return aging_hours


def _format_cache_parameter(value):
    return f'{float(value):g}'


def _cache_basename(board_serial, start_dt, stop_dt, use_temperature_c, activation_energy_ev):
    start_text = start_dt.strftime('%Y%m%dT%H%M%S')
    stop_text = stop_dt.strftime('%Y%m%dT%H%M%S')
    tuse_text = _format_cache_parameter(use_temperature_c)
    ea_text = _format_cache_parameter(activation_energy_ev)
    return (
        f'longburnin{board_serial}_{start_text}_{stop_text}'
        f'_tuse{tuse_text}_ea{ea_text}'
    )


def _cache_path(board_serial, start_dt, stop_dt, use_temperature_c, activation_energy_ev):
    basename = _cache_basename(board_serial, start_dt, stop_dt, use_temperature_c, activation_energy_ev)
    return LONG_BURN_IN_CACHE_DIR / f'{basename}.json'


def _plot_html_path(board_serial, start_dt, stop_dt, use_temperature_c, activation_energy_ev):
    basename = _cache_basename(board_serial, start_dt, stop_dt, use_temperature_c, activation_energy_ev)
    return LONG_BURN_IN_CACHE_DIR / f'{basename}.html'


def _load_cache(board_serial, start_dt, stop_dt, temperature_offset_c, use_temperature_c, activation_energy_ev):
    cache_path = _cache_path(board_serial, start_dt, stop_dt, use_temperature_c, activation_energy_ev)
    if not cache_path.exists():
        return None

    try:
        cached = json.loads(cache_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        print(f'Error reading long burn-in cache {cache_path}: {exc}')
        return None

    if cached.get('version') != CACHE_VERSION:
        return None
    if cached.get('board_serial') != str(board_serial):
        return None
    if cached.get('temperature_offset_c') != temperature_offset_c:
        return None

    start_text = start_dt.strftime('%Y-%m-%d %H:%M:%S')
    stop_text = stop_dt.strftime('%Y-%m-%d %H:%M:%S')
    if cached.get('period_start') != start_text or cached.get('period_stop') != stop_text:
        return None

    series = cached.get('series') or {}
    if not series.get('point_count'):
        return None
    return cached


def _write_long_burn_in_plot_html(
    board_serial,
    start_dt,
    stop_dt,
    series,
    config,
    use_temperature_c,
    activation_energy_ev,
    cached_at=None,
):
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        from plotly.io import to_html
    except ImportError as exc:
        print(f'Plotly not available for long burn-in HTML export: {exc}')
        return None

    offset = float(config.get('long_burnin_temperature_offset_c', 0.0))
    fpga_a_label = config.get('long_burnin_fpga_a_label', 'KU FPGA A')
    fpga_b_label = config.get('long_burnin_fpga_b_label', 'KU FPGA B')
    v_test_v = float(config.get('long_burnin_v_test_v', 12.0))
    v_use_v = float(config.get('long_burnin_v_use_v', 10.0))
    beta = float(config.get('long_burnin_default_voltage_beta', 2.0))
    rh_use_pct = float(config.get('long_burnin_default_rh_use_pct', 10.0))
    peck_exponent = float(config.get('long_burnin_default_peck_exponent', 3.0))
    profile_name = config.get('long_burnin_default_use_profile') or 'T_use'
    cached_stamp = cached_at or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    model_specs = [
        {
            'title': 'Arrhenius Model (Temperature)',
            'model': 'arrhenius',
            'params': {},
            'include_humidity': False,
        },
        {
            'title': (
                f'Eyring Model (Temperature + Voltage), '
                f'β={beta:g}, V={v_test_v:g}/{v_use_v:g} V'
            ),
            'model': 'eyring',
            'params': {
                'v_test_v': v_test_v,
                'v_use_v': v_use_v,
                'beta': beta,
            },
            'include_humidity': False,
        },
        {
            'title': (
                f"Peck's Law (Temperature + Humidity), "
                f'RH_use={rh_use_pct:g}%, n={peck_exponent:g}'
            ),
            'model': 'peck',
            'params': {
                'rh_use_pct': rh_use_pct,
                'peck_exponent': peck_exponent,
            },
            'include_humidity': True,
        },
    ]

    figures_html = []
    for spec in model_specs:
        aging_env = _compute_model_aging_hours(
            series, 'env_temp_c', spec['model'], use_temperature_c, activation_energy_ev, **spec['params'],
        )
        aging_a = _compute_model_aging_hours(
            series, 'fpga_a_temp_c', spec['model'], use_temperature_c, activation_energy_ev, **spec['params'],
        )
        aging_b = _compute_model_aging_hours(
            series, 'fpga_b_temp_c', spec['model'], use_temperature_c, activation_energy_ev, **spec['params'],
        )
        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.62, 0.19, 0.19],
            specs=[[{'secondary_y': True}], [{}], [{}]],
        )
        fig.add_trace(go.Scatter(
            x=series['elapsed_hours'], y=aging_env, mode='lines',
            name=f'Env Aging ({profile_name} {use_temperature_c:g}°C, Ea={activation_energy_ev:g} eV)',
            line=dict(color='#636EFA', width=2),
        ), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(
            x=series['elapsed_hours'], y=aging_a, mode='lines',
            name=f'{fpga_a_label} Aging',
            line=dict(color='#EF553B', width=2),
        ), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(
            x=series['elapsed_hours'], y=aging_b, mode='lines',
            name=f'{fpga_b_label} Aging',
            line=dict(color='#00CC96', width=2),
        ), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(
            x=series['elapsed_hours'], y=series['env_temp_c'], mode='lines',
            name=f'Env Temperature (+{offset:g}°C)',
            line=dict(color='#636EFA', width=1.8, dash='dot'),
        ), row=1, col=1, secondary_y=True)
        fig.add_trace(go.Scatter(
            x=series['elapsed_hours'], y=series['fpga_a_temp_c'], mode='lines',
            name=f'{fpga_a_label} Temp',
            line=dict(color='#EF553B', width=1.8, dash='dot'),
        ), row=1, col=1, secondary_y=True)
        fig.add_trace(go.Scatter(
            x=series['elapsed_hours'], y=series['fpga_b_temp_c'], mode='lines',
            name=f'{fpga_b_label} Temp',
            line=dict(color='#00CC96', width=1.8, dash='dot'),
        ), row=1, col=1, secondary_y=True)
        if spec['include_humidity']:
            fig.add_trace(go.Scatter(
                x=series['elapsed_hours'], y=series.get('env_hum'), mode='lines',
                name='Env Humidity',
                line=dict(color='#AB63FA', width=1.6, dash='dashdot'),
            ), row=1, col=1, secondary_y=True)
        fig.add_trace(go.Scatter(
            x=series['elapsed_hours'], y=series['power_state'], mode='lines',
            name='power_state', line=dict(color='#19D3F3', width=2, shape='hv'),
        ), row=2, col=1)
        fig.add_trace(go.Scatter(
            x=series['elapsed_hours'], y=series['power_good'], mode='lines',
            name='power_good', line=dict(color='#FFA15A', width=2, shape='hv'),
        ), row=3, col=1)
        fig.update_layout(
            title=spec['title'],
            height=700,
            margin=dict(t=60, r=80, b=90, l=100),
            hovermode='x unified',
            legend=dict(orientation='h', yanchor='top', y=-0.12, x=0.5, xanchor='center'),
        )
        fig.update_yaxes(title_text='Accelerated Aging', row=1, col=1, secondary_y=False)
        fig.update_yaxes(
            title_text='Temperature (°C) / Humidity (%)' if spec['include_humidity'] else 'Temperature (°C)',
            row=1, col=1, secondary_y=True,
        )
        fig.update_yaxes(title_text='power_state', tickvals=[0, 1], ticktext=['OFF', 'ON'], range=[-0.05, 1.05], row=2, col=1)
        fig.update_yaxes(title_text='power_good', tickvals=[0, 1], ticktext=['OFF', 'ON'], range=[-0.05, 1.05], row=3, col=1)
        fig.update_xaxes(title_text='Elapsed Time (hours)', row=3, col=1)
        figures_html.append(to_html(fig, include_plotlyjs=('cdn' if not figures_html else False), full_html=False))

    from plot_cache import cache_banner_html
    html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<title>Long Burn-In {board_serial}</title></head><body>'
        f'{cache_banner_html(cached_stamp)}'
        f'<h2 style="font-family:sans-serif;margin:16px;">'
        f'Long Burn-In Board {board_serial} · '
        f'{start_dt:%Y-%m-%d %H:%M:%S} → {stop_dt:%Y-%m-%d %H:%M:%S}'
        f'</h2>'
        + ''.join(figures_html)
        + '</body></html>'
    )
    LONG_BURN_IN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    html_path = _plot_html_path(board_serial, start_dt, stop_dt, use_temperature_c, activation_energy_ev)
    html_path.write_text(html, encoding='utf-8')
    return html_path.name


def _clear_board_cache(board_serial):
    LONG_BURN_IN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pattern = f'longburnin{board_serial}_*'
    for path in LONG_BURN_IN_CACHE_DIR.glob(pattern):
        try:
            path.unlink()
        except OSError as exc:
            print(f'Error clearing long burn-in cache {path}: {exc}')


def _clear_cache(board_serial, start_dt, stop_dt):
    # Keep signature for callers; clear all cache files for this board.
    _clear_board_cache(board_serial)


def _save_cache(
    board_serial,
    start_dt,
    stop_dt,
    temperature_offset_c,
    use_temperature_c,
    activation_energy_ev,
    series,
    totals,
    config=None,
):
    LONG_BURN_IN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _clear_board_cache(board_serial)
    cache_path = _cache_path(board_serial, start_dt, stop_dt, use_temperature_c, activation_energy_ev)
    cached_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    plot_html = None
    if config is not None:
        try:
            plot_html = _write_long_burn_in_plot_html(
                board_serial,
                start_dt,
                stop_dt,
                series,
                config,
                use_temperature_c,
                activation_energy_ev,
                cached_at=cached_at,
            )
        except Exception as exc:
            print(f'Error writing long burn-in HTML plot: {exc}')
            plot_html = None
    payload = {
        'version': CACHE_VERSION,
        'board_serial': str(board_serial),
        'period_start': start_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'period_stop': stop_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'temperature_offset_c': temperature_offset_c,
        'cached_at': cached_at,
        'series': series,
        'totals': totals,
    }
    if plot_html:
        payload['plot_html'] = plot_html
    cache_path.write_text(json.dumps(payload), encoding='utf-8')
    return cache_path.name, plot_html


def _ensure_plot_html(
    board_serial,
    start_dt,
    stop_dt,
    series,
    config,
    use_temperature_c,
    activation_energy_ev,
    cached_at=None,
):
    html_path = _plot_html_path(board_serial, start_dt, stop_dt, use_temperature_c, activation_energy_ev)
    if html_path.exists():
        from plot_cache import inject_cache_banner
        inject_cache_banner(html_path, cached_at)
        return html_path.name
    try:
        return _write_long_burn_in_plot_html(
            board_serial,
            start_dt,
            stop_dt,
            series,
            config,
            use_temperature_c,
            activation_energy_ev,
            cached_at=cached_at,
        )
    except Exception as exc:
        print(f'Error ensuring long burn-in HTML plot: {exc}')
        return None


def _cache_fallback_result(cached, config=None, use_temperature_c=None, activation_energy_ev=None):
    plot_html = cached.get('plot_html')
    if config is not None and cached.get('series') and use_temperature_c is not None and activation_energy_ev is not None:
        start_dt = datetime.strptime(cached['period_start'], '%Y-%m-%d %H:%M:%S')
        stop_dt = datetime.strptime(cached['period_stop'], '%Y-%m-%d %H:%M:%S')
        plot_html = _ensure_plot_html(
            cached.get('board_serial'),
            start_dt,
            stop_dt,
            cached['series'],
            config,
            use_temperature_c,
            activation_energy_ev,
            cached_at=cached.get('cached_at'),
        )
    return {
        'success': True,
        'series': cached['series'],
        'totals': cached['totals'],
        'cached': True,
        'cached_at': cached.get('cached_at'),
        'plot_html': plot_html,
        'cache_fallback': True,
    }


def _resolve_default_parameters(config):
    profiles = config.get('long_burnin_use_profiles') or []
    energies = config.get('long_burnin_activation_energies') or []
    if not profiles or not energies:
        return None, None

    profile_name = config.get('long_burnin_default_use_profile')
    profile = next(
        (item for item in profiles if item.get('name') == profile_name),
        profiles[0],
    )
    default_energy = config.get('long_burnin_default_activation_energy_ev')
    energy = next(
        (item for item in energies if item.get('value') == default_energy),
        energies[0],
    )
    return profile, energy


def _config_payload(config):
    profile, energy = _resolve_default_parameters(config)
    board_serial, start_dt, stop_dt, period_error = _resolve_period(config)
    temperature_offset = float(config.get('long_burnin_temperature_offset_c', 0.0))
    v_test_v = float(config.get('long_burnin_v_test_v', 12.0))
    v_use_v = float(config.get('long_burnin_v_use_v', 10.0))
    return {
        'board_serial': config.get('long_burnin_board_serial', ''),
        'period_start': start_dt.strftime('%Y-%m-%d %H:%M:%S') if start_dt else config.get('long_burnin_start', ''),
        'period_stop': stop_dt.strftime('%Y-%m-%d %H:%M:%S') if stop_dt else (
            config.get('long_burnin_stop') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ),
        'period_stop_is_now': not str(config.get('long_burnin_stop', '')).strip(),
        'fpga_a_label': config.get('long_burnin_fpga_a_label', 'KU FPGA A'),
        'fpga_b_label': config.get('long_burnin_fpga_b_label', 'KU FPGA B'),
        'temperature_offset_c': temperature_offset,
        'use_profiles': config.get('long_burnin_use_profiles', []),
        'activation_energies': config.get('long_burnin_activation_energies', []),
        'default_use_profile': config.get('long_burnin_default_use_profile'),
        'default_activation_energy_ev': config.get('long_burnin_default_activation_energy_ev'),
        'v_use_v': v_use_v,
        'v_test_v': v_test_v,
        'voltage_betas': config.get('long_burnin_voltage_betas', []),
        'default_voltage_beta': config.get('long_burnin_default_voltage_beta'),
        'rh_use_options': config.get('long_burnin_rh_use_options', []),
        'default_rh_use_pct': config.get('long_burnin_default_rh_use_pct'),
        'peck_exponents': config.get('long_burnin_peck_exponents', []),
        'default_peck_exponent': config.get('long_burnin_default_peck_exponent'),
        'equation': long_burn_in_arrhenius_equation_text(temperature_offset),
        'equation_arrhenius': long_burn_in_arrhenius_equation_text(temperature_offset),
        'equation_eyring': long_burn_in_eyring_equation_text(temperature_offset, v_test_v, v_use_v),
        'equation_peck': long_burn_in_peck_equation_text(temperature_offset),
        'influx_source': get_influx_source_info(),
        'board_tag_key': _board_tag_key(config.get('long_burnin_board_serial', '')),
        'period_error': period_error,
    }


def _fetch_series(config, influx_client=None, force_recompute=False):
    board_serial, start_dt, stop_dt, period_error = _resolve_period(config)
    if period_error:
        return {'success': False, 'error': period_error}

    temperature_offset = float(config.get('long_burnin_temperature_offset_c', 0.0))
    profile, energy = _resolve_default_parameters(config)
    if not profile or not energy:
        return {'success': False, 'error': 'Long burn-in T_use profile and activation energy are not configured'}

    t_use_c = profile['temperature_c']
    ea_ev = energy['value']
    fpga_a_label = config.get('long_burnin_fpga_a_label', 'KU FPGA A')
    fpga_b_label = config.get('long_burnin_fpga_b_label', 'KU FPGA B')

    if force_recompute:
        _clear_cache(board_serial, start_dt, stop_dt)

    def _try_cache_fallback(reason):
        cached = _load_cache(board_serial, start_dt, stop_dt, temperature_offset, t_use_c, ea_ev)
        if cached:
            result = _cache_fallback_result(
                cached,
                config=config,
                use_temperature_c=t_use_c,
                activation_energy_ev=ea_ev,
            )
            result['cache_fallback_reason'] = reason
            return result
        return None

    client = influx_client
    owns_client = False
    if client is None:
        try:
            client = get_influx_client()
            owns_client = True
        except Exception as exc:
            fallback = _try_cache_fallback(str(exc))
            if fallback:
                return fallback
            return {'success': False, 'error': str(exc)}

    try:
        env_points = _query_env_power_points(client, start_dt, stop_dt)
        fpga_a_points = _query_fpga_temperature_points(
            client, start_dt, stop_dt, board_serial, fpga_a_label,
        )
        fpga_b_points = _query_fpga_temperature_points(
            client, start_dt, stop_dt, board_serial, fpga_b_label,
        )
    except Exception as exc:
        fallback = _try_cache_fallback(f'InfluxDB query failed: {exc}')
        if fallback:
            return fallback
        return {'success': False, 'error': f'InfluxDB query failed: {exc}'}
    finally:
        if owns_client and client is not None:
            try:
                client.close()
            except Exception:
                pass

    series = _build_time_series(env_points, fpga_a_points, fpga_b_points, start_dt, config)
    if not series['point_count']:
        fallback = _try_cache_fallback('No live telemetry found')
        if fallback:
            return fallback
        return {
            'success': False,
            'error': (
                f'No {MEASUREMENT_NAME} telemetry found for board {board_serial} '
                f'from {start_dt:%Y-%m-%d %H:%M:%S} to {stop_dt:%Y-%m-%d %H:%M:%S}'
            ),
        }

    downsampled = _downsample_long_burn_series(series)
    totals = {
        'elapsed_hours': series['total_elapsed_hours'],
        'raw_point_count': series['point_count'],
    }
    _, plot_html = _save_cache(
        board_serial,
        start_dt,
        stop_dt,
        temperature_offset,
        t_use_c,
        ea_ev,
        downsampled,
        totals,
        config=config,
    )
    return {
        'success': True,
        'series': downsampled,
        'totals': totals,
        'cached': False,
        'cached_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'plot_html': plot_html,
    }


def build_long_burn_in_overview():
    config = load_production_config()
    board_serial, start_dt, stop_dt, period_error = _resolve_period(config)
    cached = False
    if not period_error:
        profile, energy = _resolve_default_parameters(config)
        if profile and energy:
            cached = _load_cache(
                board_serial,
                start_dt,
                stop_dt,
                float(config.get('long_burnin_temperature_offset_c', 0.0)),
                profile['temperature_c'],
                energy['value'],
            ) is not None

    payload = _config_payload(config)
    payload.update({
        'success': True,
        'cached': cached,
    })
    return payload


def build_long_burn_in_plot(influx_client=None, force_recompute=False):
    config = load_production_config()
    board_serial, start_dt, stop_dt, period_error = _resolve_period(config)
    if period_error:
        return {'success': False, 'error': period_error, 'config': _config_payload(config)}

    period_result = _fetch_series(config, influx_client=influx_client, force_recompute=force_recompute)
    if not period_result.get('success'):
        period_result['config'] = _config_payload(config)
        return period_result

    return {
        'success': True,
        'board_serial': board_serial,
        'period_start': start_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'period_stop': stop_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'duration_hours': round((stop_dt - start_dt).total_seconds() / 3600.0, 2),
        'series': period_result['series'],
        'totals': period_result['totals'],
        'cached': period_result.get('cached', False),
        'cached_at': period_result.get('cached_at'),
        'plot_html': period_result.get('plot_html'),
        'cache_fallback': period_result.get('cache_fallback', False),
        'config': _config_payload(config),
    }
