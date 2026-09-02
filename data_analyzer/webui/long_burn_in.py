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
    cumulative = 0.0
    aging_hours = []
    elapsed_hours = series.get('elapsed_hours') or []
    temperatures = series.get(temperature_key) or []
    power_on = series.get('power_on') or []

    for index, elapsed in enumerate(elapsed_hours):
        if (
            index > 0
            and power_on[index - 1] == 1
            and temperatures[index] is not None
        ):
            dt_hours = elapsed - elapsed_hours[index - 1]
            if dt_hours > 0:
                cumulative += acceleration_factor(
                    temperatures[index],
                    use_temperature_c,
                    activation_energy_ev,
                ) * dt_hours
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


def _save_cache(
    board_serial,
    start_dt,
    stop_dt,
    temperature_offset_c,
    use_temperature_c,
    activation_energy_ev,
    series,
    totals,
):
    LONG_BURN_IN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _cache_path(board_serial, start_dt, stop_dt, use_temperature_c, activation_energy_ev)
    payload = {
        'version': CACHE_VERSION,
        'board_serial': str(board_serial),
        'period_start': start_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'period_stop': stop_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'temperature_offset_c': temperature_offset_c,
        'cached_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'series': series,
        'totals': totals,
    }
    cache_path.write_text(json.dumps(payload), encoding='utf-8')
    return cache_path.name


def _clear_cache(board_serial, start_dt, stop_dt):
    start_text = start_dt.strftime('%Y%m%dT%H%M%S')
    stop_text = stop_dt.strftime('%Y%m%dT%H%M%S')
    pattern = f'longburnin{board_serial}_{start_text}_{stop_text}_*'
    for path in LONG_BURN_IN_CACHE_DIR.glob(pattern):
        try:
            path.unlink()
        except OSError as exc:
            print(f'Error clearing long burn-in cache {path}: {exc}')


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
    else:
        cached = _load_cache(board_serial, start_dt, stop_dt, temperature_offset, t_use_c, ea_ev)
        if cached:
            return {
                'success': True,
                'series': cached['series'],
                'totals': cached['totals'],
                'cached': True,
                'cached_at': cached.get('cached_at'),
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
        env_points = _query_env_power_points(client, start_dt, stop_dt)
        fpga_a_points = _query_fpga_temperature_points(
            client, start_dt, stop_dt, board_serial, fpga_a_label,
        )
        fpga_b_points = _query_fpga_temperature_points(
            client, start_dt, stop_dt, board_serial, fpga_b_label,
        )
    except Exception as exc:
        return {'success': False, 'error': f'InfluxDB query failed: {exc}'}
    finally:
        if owns_client and client is not None:
            try:
                client.close()
            except Exception:
                pass

    series = _build_time_series(env_points, fpga_a_points, fpga_b_points, start_dt, config)
    if not series['point_count']:
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
    _save_cache(
        board_serial,
        start_dt,
        stop_dt,
        temperature_offset,
        t_use_c,
        ea_ev,
        downsampled,
        totals,
    )
    return {
        'success': True,
        'series': downsampled,
        'totals': totals,
        'cached': False,
        'cached_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
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
        'config': _config_payload(config),
    }
