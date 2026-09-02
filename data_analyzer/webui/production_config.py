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

DEFAULT_CONFIG = {
    'pretest_offset_days': 0,
    'post_test_offset_days': 0,
    'burnin_offset_days': 0,
    'burnin_temperature_offset_c': 0.0,
    'burnin_use_profiles': DEFAULT_BURNIN_USE_PROFILES,
    'burnin_activation_energies': DEFAULT_BURNIN_ACTIVATION_ENERGIES,
    'burnin_default_use_profile': DEFAULT_BURNIN_USE_PROFILES[0]['name'],
    'burnin_default_activation_energy_ev': 0.7,
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
            'description': str(energy.get('description', '')).strip(),
        })
    return normalized or [dict(item) for item in DEFAULT_BURNIN_ACTIVATION_ENERGIES]


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
