"""Production configuration for schedule uploads and timeline offsets."""

from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML

WEBUI_DIR = Path(__file__).parent
CONFIG_PATH = WEBUI_DIR / 'production_config.yaml'
SCHEDULE_CSV_PATH = WEBUI_DIR / 'production_schedule.csv'
SCHEDULE_BACKUP_DIR = WEBUI_DIR / 'production_schedule_backups'

DEFAULT_BURNIN_USE_PROFILES = [
    {'name': 'ATLAS', 'temperature_c': 25.0},
    {'name': 'Lab Table', 'temperature_c': 60.0},
]

DEFAULT_BURNIN_ACTIVATION_ENERGIES = [
    {
        'value': 0.3,
        'description': 'Typical for moisture-induced corrosion or package delamination.',
    },
    {
        'value': 0.5,
        'description': (
            'Standard default values used by the military and aerospace industries '
            'for general semiconductor hardware when the exact failure mechanism is unknown.'
        ),
    },
    {
        'value': 0.6,
        'description': (
            'Standard default values used by the military and aerospace industries '
            'for general semiconductor hardware when the exact failure mechanism is unknown.'
        ),
    },
    {
        'value': 0.7,
        'description': 'Common for electromigration in silicon interconnects and dielectric breakdowns.',
    },
    {
        'value': 0.9,
        'description': 'Associated with severe charge-trapping contamination and ionic impurities.',
    },
    {
        'value': 1.0,
        'description': 'Associated with severe charge-trapping contamination and ionic impurities.',
    },
]

DEFAULT_LONG_BURNIN_USE_PROFILES = [dict(item) for item in DEFAULT_BURNIN_USE_PROFILES]
DEFAULT_LONG_BURNIN_ACTIVATION_ENERGIES = [
    {
        'value': 0.3,
        'label': '0.3 eV',
        'description': 'Moisture damage and ungluing.',
    },
    {
        'value': 0.5,
        'label': '0.5 eV',
        'description': 'Military default for unknown defects.',
    },
    {
        'value': 0.7,
        'label': '0.7 eV',
        'description': 'Silicon wire wear and dielectric break.',
    },
    {
        'value': 0.9,
        'label': '0.9 eV',
        'description': 'Trapped charges and chemical contamination.',
    },
    {
        'value': 1.0,
        'label': '1.0 eV',
        'description': 'Higher Trapped charges + chemical contamination.',
    },
]
DEFAULT_LONG_BURNIN_VOLTAGE_BETAS = [
    {
        'value': 2.0,
        'description': (
            'Multi-layer ceramic capacitors (MLCCs)\n'
            'Insulation resistance degradation, dielectric breakdown, and oxygen vacancy migration '
            '(β = 1.5->3.0).'
        ),
    },
    {
        'value': 4.0,
        'description': (
            'Aluminum electrolytic capacitors\n'
            'Electrolyte vaporization and internal pressure buildup leading to seal rupture '
            '(β = 3.0->5.0).'
        ),
    },
    {
        'value': 3.5,
        'description': (
            'Solid tantalum capacitors\n'
            'Self-healing failure breakdown and localized manganese dioxide (MnO₂) reduction '
            '(β = 3.0->4.0).'
        ),
    },
    {
        'value': 6.0,
        'description': (
            'Thin-film transistors & optoelectronics\n'
            'Hot carrier injection (HCI) and gate-oxide breakdown in older or wider semiconductor nodes '
            '(β = 5.0->7.0).'
        ),
    },
    {
        'value': 10.0,
        'description': (
            'Ultra-thin gate dielectrics (modern ICs)\n'
            'Time-dependent dielectric breakdown (TDDB) in advanced microscopic silicon structures, '
            'where voltage stress is highly non-linear (β = 10.0+).'
        ),
    },
]
DEFAULT_LONG_BURNIN_PECK_EXPONENTS = [
    {
        'value': 2.0,
        'description': (
            'Hermetically sealed & ruggedized modules\n'
            'Package delamination or moisture ingress along the lead-frame interfaces of robust '
            'industrial packages (n = 2.0->2.5).'
        ),
    },
    {
        'value': 2.66,
        'description': (
            'Aluminum metallization / bare die\n'
            "Peck's baseline for temperature-humidity accelerated testing of aluminum corrosion "
            'and galvanic corrosion of bare internal wiring (n = 2.66).'
        ),
    },
    {
        'value': 3.0,
        'description': (
            'Consumer plastics & liquid crystal displays\n'
            'General standard for electronics epoxy packaging; commonly 0.7 eV for LCDs (n = 3.0).'
        ),
    },
    {
        'value': 4.5,
        'description': (
            'Military & aerospace hardware (MIL-HDBK-217F)\n'
            'Strict baseline for temperature and humidity stress factors on electronic components; '
            'captures aggressive multi-layer circuit board insulation degradation (n = 4.5).'
        ),
    },
]
DEFAULT_LONG_BURNIN_RH_USE_OPTIONS = [5.0, 10.0, 15.0]

DEFAULT_BURNIN_CACHE_DIR = '/var/www/html/drive/production_plots/burn_in'

DEFAULT_CONFIG = {
    'pretest_offset_days': 0,
    'post_test_offset_days': 0,
    'burnin_offset_days': 0,
    'burnin_temperature_offset_c': 0.0,
    'burnin_cache_dir': DEFAULT_BURNIN_CACHE_DIR,
    'burnin_use_profiles': DEFAULT_BURNIN_USE_PROFILES,
    'burnin_activation_energies': DEFAULT_BURNIN_ACTIVATION_ENERGIES,
    'burnin_default_use_profile': DEFAULT_BURNIN_USE_PROFILES[0]['name'],
    'burnin_default_activation_energy_ev': 0.7,
    'long_burnin_board_serial': '1101037',
    'long_burnin_start': '',
    'long_burnin_stop': '',
    'long_burnin_fpga_a_label': 'KU FPGA A',
    'long_burnin_fpga_b_label': 'KU FPGA B',
    'long_burnin_temperature_offset_c': 0.0,
    'long_burnin_use_profiles': DEFAULT_LONG_BURNIN_USE_PROFILES,
    'long_burnin_activation_energies': DEFAULT_LONG_BURNIN_ACTIVATION_ENERGIES,
    'long_burnin_default_use_profile': DEFAULT_LONG_BURNIN_USE_PROFILES[0]['name'],
    'long_burnin_default_activation_energy_ev': 0.7,
    'long_burnin_v_use_v': 10.0,
    'long_burnin_v_test_v': 12.0,
    'long_burnin_voltage_betas': DEFAULT_LONG_BURNIN_VOLTAGE_BETAS,
    'long_burnin_default_voltage_beta': 2.0,
    'long_burnin_rh_use_options': DEFAULT_LONG_BURNIN_RH_USE_OPTIONS,
    'long_burnin_default_rh_use_pct': 10.0,
    'long_burnin_peck_exponents': DEFAULT_LONG_BURNIN_PECK_EXPONENTS,
    'long_burnin_default_peck_exponent': 3.0,
}


def _normalize_use_profiles(profiles):
    normalized = []
    for profile in profiles or []:
        if not isinstance(profile, dict):
            continue
        name = str(profile.get('name', '')).strip()
        if not name:
            continue
        try:
            temperature_c = float(profile.get('temperature_c'))
        except (TypeError, ValueError):
            continue
        normalized.append({
            'name': name,
            'temperature_c': temperature_c,
        })
    return normalized or [dict(item) for item in DEFAULT_BURNIN_USE_PROFILES]


def _normalize_activation_energies(energies):
    normalized = []
    for energy in energies or []:
        if not isinstance(energy, dict):
            continue
        try:
            value = float(energy.get('value'))
        except (TypeError, ValueError):
            continue
        normalized.append({
            'value': value,
            'label': str(energy.get('label', '')).strip(),
            'description': str(energy.get('description', '')).strip(),
        })
    return normalized or [dict(item) for item in DEFAULT_BURNIN_ACTIVATION_ENERGIES]


def _normalize_value_options(options, default_options):
    normalized = []
    for option in options or []:
        if not isinstance(option, dict):
            continue
        try:
            value = float(option.get('value'))
        except (TypeError, ValueError):
            continue
        normalized.append({
            'value': value,
            'description': str(option.get('description', '')).strip(),
        })
    return normalized or [dict(item) for item in default_options]


def _normalize_rh_use_options(values):
    normalized = []
    for value in values or []:
        try:
            normalized.append(float(value))
        except (TypeError, ValueError):
            continue
    return normalized or list(DEFAULT_LONG_BURNIN_RH_USE_OPTIONS)


def _normalize_config(data):
    config = dict(DEFAULT_CONFIG)
    for key in ('pretest_offset_days', 'post_test_offset_days', 'burnin_offset_days'):
        if key in data:
            try:
                config[key] = int(data[key])
            except (TypeError, ValueError):
                pass

    if 'burnin_temperature_offset_c' in data:
        try:
            config['burnin_temperature_offset_c'] = float(data['burnin_temperature_offset_c'])
        except (TypeError, ValueError):
            pass

    if 'burnin_cache_dir' in data:
        cache_dir = str(data['burnin_cache_dir']).strip()
        if cache_dir:
            config['burnin_cache_dir'] = cache_dir

    if 'burnin_use_profiles' in data:
        config['burnin_use_profiles'] = _normalize_use_profiles(data['burnin_use_profiles'])

    if 'burnin_activation_energies' in data:
        config['burnin_activation_energies'] = _normalize_activation_energies(
            data['burnin_activation_energies']
        )

    profiles = config['burnin_use_profiles']
    energies = config['burnin_activation_energies']
    profile_names = {profile['name'] for profile in profiles}
    energy_values = {energy['value'] for energy in energies}

    if data.get('burnin_default_use_profile') in profile_names:
        config['burnin_default_use_profile'] = data['burnin_default_use_profile']
    elif config['burnin_default_use_profile'] not in profile_names:
        config['burnin_default_use_profile'] = profiles[0]['name']

    default_energy = data.get('burnin_default_activation_energy_ev', config['burnin_default_activation_energy_ev'])
    try:
        default_energy = float(default_energy)
    except (TypeError, ValueError):
        default_energy = config['burnin_default_activation_energy_ev']
    if default_energy in energy_values:
        config['burnin_default_activation_energy_ev'] = default_energy
    elif config['burnin_default_activation_energy_ev'] not in energy_values:
        config['burnin_default_activation_energy_ev'] = energies[0]['value']

    if 'long_burnin_board_serial' in data:
        config['long_burnin_board_serial'] = str(data['long_burnin_board_serial']).strip()

    for key in ('long_burnin_start', 'long_burnin_stop', 'long_burnin_fpga_a_label', 'long_burnin_fpga_b_label'):
        if key in data:
            config[key] = str(data[key] or '').strip()

    if 'long_burnin_temperature_offset_c' in data:
        try:
            config['long_burnin_temperature_offset_c'] = float(data['long_burnin_temperature_offset_c'])
        except (TypeError, ValueError):
            pass

    if 'long_burnin_use_profiles' in data:
        config['long_burnin_use_profiles'] = _normalize_use_profiles(data['long_burnin_use_profiles'])

    if 'long_burnin_activation_energies' in data:
        config['long_burnin_activation_energies'] = _normalize_activation_energies(
            data['long_burnin_activation_energies']
        )

    long_profiles = config['long_burnin_use_profiles']
    long_energies = config['long_burnin_activation_energies']
    long_profile_names = {profile['name'] for profile in long_profiles}
    long_energy_values = {energy['value'] for energy in long_energies}

    if data.get('long_burnin_default_use_profile') in long_profile_names:
        config['long_burnin_default_use_profile'] = data['long_burnin_default_use_profile']
    elif config['long_burnin_default_use_profile'] not in long_profile_names:
        config['long_burnin_default_use_profile'] = long_profiles[0]['name']

    long_default_energy = data.get(
        'long_burnin_default_activation_energy_ev',
        config['long_burnin_default_activation_energy_ev'],
    )
    try:
        long_default_energy = float(long_default_energy)
    except (TypeError, ValueError):
        long_default_energy = config['long_burnin_default_activation_energy_ev']
    if long_default_energy in long_energy_values:
        config['long_burnin_default_activation_energy_ev'] = long_default_energy
    elif config['long_burnin_default_activation_energy_ev'] not in long_energy_values:
        config['long_burnin_default_activation_energy_ev'] = long_energies[0]['value']

    for key in ('long_burnin_v_use_v', 'long_burnin_v_test_v'):
        if key in data:
            try:
                config[key] = float(data[key])
            except (TypeError, ValueError):
                pass

    if 'long_burnin_voltage_betas' in data:
        config['long_burnin_voltage_betas'] = _normalize_value_options(
            data['long_burnin_voltage_betas'],
            DEFAULT_LONG_BURNIN_VOLTAGE_BETAS,
        )

    if 'long_burnin_peck_exponents' in data:
        config['long_burnin_peck_exponents'] = _normalize_value_options(
            data['long_burnin_peck_exponents'],
            DEFAULT_LONG_BURNIN_PECK_EXPONENTS,
        )

    if 'long_burnin_rh_use_options' in data:
        config['long_burnin_rh_use_options'] = _normalize_rh_use_options(data['long_burnin_rh_use_options'])

    voltage_betas = config['long_burnin_voltage_betas']
    beta_values = {item['value'] for item in voltage_betas}
    default_beta = data.get('long_burnin_default_voltage_beta', config['long_burnin_default_voltage_beta'])
    try:
        default_beta = float(default_beta)
    except (TypeError, ValueError):
        default_beta = config['long_burnin_default_voltage_beta']
    if default_beta in beta_values:
        config['long_burnin_default_voltage_beta'] = default_beta
    elif config['long_burnin_default_voltage_beta'] not in beta_values:
        config['long_burnin_default_voltage_beta'] = voltage_betas[0]['value']

    peck_exponents = config['long_burnin_peck_exponents']
    peck_values = {item['value'] for item in peck_exponents}
    default_peck = data.get('long_burnin_default_peck_exponent', config['long_burnin_default_peck_exponent'])
    try:
        default_peck = float(default_peck)
    except (TypeError, ValueError):
        default_peck = config['long_burnin_default_peck_exponent']
    if default_peck in peck_values:
        config['long_burnin_default_peck_exponent'] = default_peck
    elif config['long_burnin_default_peck_exponent'] not in peck_values:
        config['long_burnin_default_peck_exponent'] = peck_exponents[0]['value']

    rh_use_options = config['long_burnin_rh_use_options']
    default_rh_use = data.get('long_burnin_default_rh_use_pct', config['long_burnin_default_rh_use_pct'])
    try:
        default_rh_use = float(default_rh_use)
    except (TypeError, ValueError):
        default_rh_use = config['long_burnin_default_rh_use_pct']
    if default_rh_use in rh_use_options:
        config['long_burnin_default_rh_use_pct'] = default_rh_use
    elif config['long_burnin_default_rh_use_pct'] not in rh_use_options:
        config['long_burnin_default_rh_use_pct'] = rh_use_options[0]

    return config


def load_production_config():
    if not CONFIG_PATH.exists():
        return _normalize_config({})

    try:
        yaml_handler = YAML()
        with open(CONFIG_PATH, 'r') as config_file:
            data = yaml_handler.load(config_file) or {}
    except Exception as exc:
        print(f'Error loading production config: {exc}')
        return _normalize_config({})

    return _normalize_config(data)


def save_production_config(config):
    merged = _normalize_config(load_production_config())
    merged.update(_normalize_config(config))

    yaml_handler = YAML()
    yaml_handler.default_flow_style = False
    with open(CONFIG_PATH, 'w') as config_file:
        yaml_handler.dump(merged, config_file)
    return merged


def save_burn_in_config(config):
    current = load_production_config()
    current['burnin_temperature_offset_c'] = config.get(
        'burnin_temperature_offset_c',
        current['burnin_temperature_offset_c'],
    )
    current['burnin_use_profiles'] = config.get(
        'burnin_use_profiles',
        current['burnin_use_profiles'],
    )
    current['burnin_activation_energies'] = config.get(
        'burnin_activation_energies',
        current['burnin_activation_energies'],
    )
    if config.get('burnin_default_use_profile'):
        current['burnin_default_use_profile'] = config['burnin_default_use_profile']
    if config.get('burnin_default_activation_energy_ev') is not None:
        current['burnin_default_activation_energy_ev'] = config['burnin_default_activation_energy_ev']
    if config.get('burnin_cache_dir'):
        current['burnin_cache_dir'] = str(config['burnin_cache_dir']).strip()
    return save_production_config(current)


def save_long_burn_in_config(config):
    current = load_production_config()
    for key in (
        'long_burnin_board_serial',
        'long_burnin_start',
        'long_burnin_stop',
        'long_burnin_fpga_a_label',
        'long_burnin_fpga_b_label',
        'long_burnin_temperature_offset_c',
        'long_burnin_use_profiles',
        'long_burnin_activation_energies',
        'long_burnin_default_use_profile',
        'long_burnin_default_activation_energy_ev',
        'long_burnin_v_use_v',
        'long_burnin_v_test_v',
        'long_burnin_voltage_betas',
        'long_burnin_default_voltage_beta',
        'long_burnin_rh_use_options',
        'long_burnin_default_rh_use_pct',
        'long_burnin_peck_exponents',
        'long_burnin_default_peck_exponent',
    ):
        if key in config and config[key] is not None:
            current[key] = config[key]
    return save_production_config(current)


def backup_and_save_schedule(uploaded_file):
    SCHEDULE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    if SCHEDULE_CSV_PATH.exists():
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_path = SCHEDULE_BACKUP_DIR / f'{timestamp}_production_schedule.csv'
        backup_path.write_bytes(SCHEDULE_CSV_PATH.read_bytes())

    uploaded_file.save(SCHEDULE_CSV_PATH)
    return SCHEDULE_CSV_PATH.name


def save_schedule_text(csv_text, path=None):
    """Save schedule CSV text, backing up the current file first."""
    target_path = Path(path) if path else SCHEDULE_CSV_PATH
    SCHEDULE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_path = SCHEDULE_BACKUP_DIR / f'{timestamp}_production_schedule.csv'
        backup_path.write_bytes(target_path.read_bytes())

    target_path.write_text(csv_text, encoding='utf-8')
    return target_path.name
