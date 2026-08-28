"""Production configuration for schedule uploads and timeline offsets."""

from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML

WEBUI_DIR = Path(__file__).parent
CONFIG_PATH = WEBUI_DIR / 'production_config.yaml'
SCHEDULE_CSV_PATH = WEBUI_DIR / 'production_schedule.csv'
SCHEDULE_BACKUP_DIR = WEBUI_DIR / 'production_schedule_backups'

DEFAULT_CONFIG = {
    'pretest_offset_days': 0,
    'post_test_offset_days': 0,
    'burnin_offset_days': 0,
}


def load_production_config():
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)

    try:
        yaml_handler = YAML()
        with open(CONFIG_PATH, 'r') as config_file:
            data = yaml_handler.load(config_file) or {}
    except Exception as exc:
        print(f'Error loading production config: {exc}')
        return dict(DEFAULT_CONFIG)

    config = dict(DEFAULT_CONFIG)
    for key in DEFAULT_CONFIG:
        if key in data:
            try:
                config[key] = int(data[key])
            except (TypeError, ValueError):
                config[key] = DEFAULT_CONFIG[key]
    return config


def save_production_config(config):
    merged = dict(DEFAULT_CONFIG)
    for key in DEFAULT_CONFIG:
        if key in config:
            try:
                merged[key] = int(config[key])
            except (TypeError, ValueError):
                merged[key] = DEFAULT_CONFIG[key]

    yaml_handler = YAML()
    yaml_handler.default_flow_style = False
    with open(CONFIG_PATH, 'w') as config_file:
        yaml_handler.dump(merged, config_file)
    return merged


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
