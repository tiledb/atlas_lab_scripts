"""Helpers for vars.yaml threshold entries (list or dict with metadata)."""

from __future__ import annotations


def get_var_thresholds(entry):
    """Return the numeric/string threshold list for a variable entry."""
    if isinstance(entry, list):
        return list(entry)
    if isinstance(entry, dict):
        for key in ('thresholds', 'values', 'limits'):
            if key in entry and isinstance(entry[key], list):
                return list(entry[key])
        # Single scalar stored under thresholds
        if 'thresholds' in entry and not isinstance(entry['thresholds'], list):
            return [entry['thresholds']]
    if entry is None:
        return []
    return [entry]


def get_var_essential(entry):
    """Return essential flag as 0 or 1."""
    if isinstance(entry, dict):
        raw = entry.get('essential', 0)
        try:
            return 1 if int(raw) else 0
        except (TypeError, ValueError):
            if isinstance(raw, str) and raw.strip().lower() in ('1', 'true', 'yes', 'on'):
                return 1
            return 0
    return 0


def get_var_caption(entry, default_name=''):
    """Return plot caption; falls back to variable name."""
    if isinstance(entry, dict):
        caption = entry.get('caption')
        if caption is not None and str(caption).strip() != '':
            return str(caption).strip()
    return str(default_name or '')


def get_var_dimensions(entry, default=''):
    """Return y-axis dimensions/units string; empty if unset."""
    if isinstance(entry, dict):
        dimensions = entry.get('dimensions')
        if dimensions is not None and str(dimensions).strip() != '':
            return str(dimensions).strip()
    return str(default or '')


def format_y_axis_label(measurement, dimensions=None):
    """Y-axis text: ``measurement (dimensions)`` when units are set, else measurement."""
    name = str(measurement or '').strip()
    units = str(dimensions or '').strip()
    if name and units:
        return f'{name} ({units})'
    return name or units


def normalize_var_entry(entry, name=''):
    """Normalize a variable entry to {thresholds, essential, caption, dimensions}."""
    thresholds = get_var_thresholds(entry)
    essential = get_var_essential(entry)
    caption = get_var_caption(entry, default_name=name)
    if not caption:
        caption = str(name or '')
    dimensions = get_var_dimensions(entry, default='')
    return {
        'thresholds': thresholds,
        'essential': essential,
        'caption': caption,
        'dimensions': dimensions,
    }


def normalize_vars_config(config):
    """Return a deep-normalized copy of the full vars config."""
    if not isinstance(config, dict):
        return {}
    out = {}
    for table, table_vars in config.items():
        if not isinstance(table_vars, dict):
            continue
        out[table] = {}
        for var_name, entry in table_vars.items():
            out[table][var_name] = normalize_var_entry(entry, name=var_name)
    return out


def format_thresholds_for_form(thresholds):
    """Format threshold list as editable text like [1, 2]."""
    if not isinstance(thresholds, list):
        thresholds = get_var_thresholds(thresholds)
    parts = []
    for value in thresholds:
        parts.append(str(value))
    return '[' + ', '.join(parts) + ']'


def parse_thresholds_text(value_str):
    """Parse a thresholds text field into a list of ints/floats/strings."""
    if value_str is None:
        return []
    text = str(value_str).strip()
    if not text:
        return []
    if text.startswith('[') and text.endswith(']'):
        inner = text[1:-1].strip()
        if not inner:
            return []
        values = [v.strip() for v in inner.split(',')]
    else:
        values = [text]
    parsed = []
    for v in values:
        if v == '':
            continue
        try:
            if '.' in v or 'e' in v.lower():
                parsed.append(float(v))
            else:
                parsed.append(int(v))
        except ValueError:
            parsed.append(v)
    return parsed
