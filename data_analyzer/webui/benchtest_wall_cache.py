"""JSON cache for the Benchtests wall (/api/benchtest_list).

Same idea as production-history snapshots: serve the latest cached wall quickly,
rebuild on demand with ?recompute=1, and fall back to cache if live build fails.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

BENCHTEST_WALL_CACHE_DIR = Path('/var/www/html/drive/production_plots/benchtest_wall')
CACHE_VERSION = 1
LATEST_JSON_NAME = 'benchtest_wall_latest.json'


def get_benchtest_wall_cache_dir():
    return BENCHTEST_WALL_CACHE_DIR


def _json_default(value):
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return str(value)


def save_benchtest_wall_cache(payload, cached_at=None):
    """Write stamped + latest JSON for the benchtest wall payload."""
    BENCHTEST_WALL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    moment = cached_at or datetime.now()
    if isinstance(moment, str):
        cached_at_text = moment
        stamp_for_name = datetime.now()
    else:
        cached_at_text = moment.strftime('%Y-%m-%d %H:%M:%S')
        stamp_for_name = moment

    for path in BENCHTEST_WALL_CACHE_DIR.glob('benchtest_wall_*'):
        try:
            path.unlink()
        except OSError as exc:
            print(f'Error clearing benchtest wall cache {path}: {exc}')

    body = dict(payload or {})
    body['version'] = CACHE_VERSION
    body['cached_at'] = cached_at_text
    body['success'] = True
    # Drop ephemeral flags before writing.
    body.pop('newly_cached', None)
    body.pop('cache_fallback', None)
    body.pop('cache_fallback_reason', None)

    json_text = json.dumps(body, default=_json_default)
    stamped = stamp_for_name.strftime('%Y%m%dT%H%M%S')
    stamped_json = BENCHTEST_WALL_CACHE_DIR / f'benchtest_wall_{stamped}.json'
    latest_json = BENCHTEST_WALL_CACHE_DIR / LATEST_JSON_NAME

    stamped_json.write_text(json_text, encoding='utf-8')
    latest_json.write_text(json_text, encoding='utf-8')

    return {
        'cache_dir': str(BENCHTEST_WALL_CACHE_DIR),
        'cached_at': cached_at_text,
        'json': stamped_json.name,
        'latest_json': latest_json.name,
    }


def load_benchtest_wall_cache():
    """Return latest cached benchtest-wall payload, or None."""
    latest_json = BENCHTEST_WALL_CACHE_DIR / LATEST_JSON_NAME
    if not latest_json.exists():
        return None
    try:
        payload = json.loads(latest_json.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        print(f'Error reading benchtest wall cache {latest_json}: {exc}')
        return None
    if payload.get('version') != CACHE_VERSION:
        return None
    if not payload.get('success'):
        return None
    if not isinstance(payload.get('benchtests'), list):
        return None
    return payload
